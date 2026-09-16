import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:http/http.dart' as http;
import 'package:latlong2/latlong.dart';

const apiBaseUrl = String.fromEnvironment(
  'API_BASE_URL',
  defaultValue: 'http://127.0.0.1:8000',
);

void main() => runApp(const MacauNavigationApp());

class MacauNavigationApp extends StatelessWidget {
  const MacauNavigationApp({super.key});

  @override
  Widget build(BuildContext context) => MaterialApp(
        title: 'Macau Navigation',
        theme: ThemeData(colorSchemeSeed: Colors.teal, useMaterial3: true),
        home: const NavigationPage(),
      );
}

class NavigationPage extends StatefulWidget {
  const NavigationPage({super.key});

  @override
  State<NavigationPage> createState() => _NavigationPageState();
}

enum _SelectionMode { none, start, end }

class _Place {
  const _Place({
    required this.name,
    required this.latitude,
    required this.longitude,
  });

  final String name;
  final double latitude;
  final double longitude;

  LatLng get point => LatLng(latitude, longitude);

  factory _Place.fromSearchJson(Map<String, dynamic> json) => _Place(
        name: json['display_name'] as String? ?? '未命名地點',
        latitude: double.parse(json['lat'].toString()),
        longitude: double.parse(json['lon'].toString()),
      );
}

class _CulturalPlace {
  const _CulturalPlace(this.data);

  final Map<String, dynamic> data;

  LatLng get point => LatLng(
        (data['latitude'] as num).toDouble(),
        (data['longitude'] as num).toDouble(),
      );

  String get name =>
      data['name'] as String? ?? data['name_en'] as String? ?? '未命名文化地点';
}

class _NavigationPageState extends State<NavigationPage> {
  final mapController = MapController();
  final startSearch = TextEditingController();
  final endSearch = TextEditingController();
  final routePoints = <LatLng>[];
  Map<String, dynamic>? tourPlan;
  bool tourConfirmed = false;
  final suggestions = <bool, List<_Place>>{true: [], false: []};
  final timers = <bool, Timer?>{true: null, false: null};

  _Place? startPlace;
  _Place? endPlace;
  _SelectionMode selectionMode = _SelectionMode.none;
  String status = '搜尋地點，或按按鈕後直接點擊地圖';
  bool loading = false;
  bool preferBus = false;
  bool showTerrain = false;
  String tourCategory = '历史文化';
  int availableHours = 6;
  int maxStops = 4;
  String routeProfile = '普通步行';
  double maxSlope = 15;
  Map<String, dynamic>? demHealth;
  bool demHealthLoading = false;
  bool showCulturalPlaces = true;
  bool showNearbyCulturalPlaces = true;
  bool culturalPlacesLoading = false;
  List<_CulturalPlace> culturalPlaces = [];
  bool showMapPanel = false;

  @override
  void initState() {
    super.initState();
    _loadDemHealth();
    _loadCulturalPlaces();
  }

  Future<void> _loadCulturalPlaces() async {
    setState(() => culturalPlacesLoading = true);
    try {
      final response = await http
          .get(Uri.parse('$apiBaseUrl/cultural-places'))
          .timeout(const Duration(seconds: 10));
      if (response.statusCode != 200) {
        throw Exception('文化地点读取失败：${response.statusCode}');
      }
      final payload = jsonDecode(response.body) as Map<String, dynamic>;
      final items = (payload['places'] as List<dynamic>? ?? [])
          .whereType<Map<String, dynamic>>()
          .map(_CulturalPlace.new)
          .toList();
      if (mounted) {
        setState(() {
          culturalPlaces = items;
          status = '已加载 ${items.length} 个文化地点';
        });
      }
    } catch (error) {
      if (mounted) setState(() => status = '文化地点图层读取失败：$error');
    } finally {
      if (mounted) setState(() => culturalPlacesLoading = false);
    }
  }

  void _showCulturalDetails(_CulturalPlace place) {
    final data = place.data;
    String value(String key) =>
        (data[key] as String?)?.trim().isNotEmpty == true
            ? data[key] as String
            : '未提供';
    final category = [
      data['tourism'],
      data['amenity'],
      data['historic'],
      data['heritage'],
    ].whereType<String>().where((item) => item.isNotEmpty).join(' / ');
    showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(place.name),
        content: SingleChildScrollView(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _culturalDetail('英文名称', value('name_en')),
              _culturalDetail('葡萄牙文名称', value('name_pt')),
              _culturalDetail('地点类别', category.isEmpty ? '未分类' : category),
              _culturalDetail('营业时间', value('opening_hours')),
              _culturalDetail('官方网站', value('website')),
              _culturalDetail('运营机构', value('operator')),
              _culturalDetail(
                '区域',
                data['area_status'] == 'macau' ? '澳门境内' : '周边地点',
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context), child: const Text('关闭')),
        ],
      ),
    );
  }

  Widget _culturalDetail(String label, String value) => Padding(
        padding: const EdgeInsets.only(bottom: 8),
        child: Text('$label：$value'),
      );

  Widget _culturalLayerStatus() => Row(
        children: [
          Icon(
            culturalPlaces.isNotEmpty
                ? Icons.check_circle
                : Icons.warning_amber,
            size: 18,
            color: culturalPlaces.isNotEmpty ? Colors.green : Colors.orange,
          ),
          const SizedBox(width: 6),
          Expanded(
            child: Text(
              culturalPlacesLoading
                  ? '正在读取文化地点...'
                  : culturalPlaces.isNotEmpty
                      ? '文化地点：${culturalPlaces.length} 个'
                      : '文化地点未加载',
            ),
          ),
          if (!culturalPlacesLoading && culturalPlaces.isEmpty)
            TextButton(
              onPressed: _loadCulturalPlaces,
              child: const Text('重试'),
            ),
        ],
      );

  Marker _culturalMarker(_CulturalPlace place) => Marker(
        point: place.point,
        width: 42,
        height: 42,
        child: GestureDetector(
          onTap: () => _showCulturalDetails(place),
          child: Icon(
            place.data['area_status'] == 'nearby'
                ? Icons.location_city
                : Icons.account_balance,
            color: place.data['area_status'] == 'nearby'
                ? Colors.deepOrange
                : Colors.purple,
            size: 30,
          ),
        ),
      );

  Future<void> _loadDemHealth() async {
    setState(() => demHealthLoading = true);
    try {
      final response = await http
          .get(Uri.parse('$apiBaseUrl/health'))
          .timeout(const Duration(seconds: 8));
      if (response.statusCode != 200) {
        throw Exception('DEM 状态查询失败：${response.statusCode}');
      }
      if (!mounted) return;
      setState(
          () => demHealth = jsonDecode(response.body) as Map<String, dynamic>);
    } catch (_) {
      if (mounted) setState(() => demHealth = null);
    } finally {
      if (mounted) setState(() => demHealthLoading = false);
    }
  }

  void _showDemInfo() {
    final metadata = demHealth?['dem_metadata'] as Map<String, dynamic>?;
    showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('GeoTIFF 高程如何帮助路线规划'),
        content: SingleChildScrollView(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'GeoTIFF 是一张带有地理坐标的高程网格。每个像元保存一个高度值，后端沿道路采样这些高度，计算坡度、爬升和下降。',
              ),
              const SizedBox(height: 12),
              _demStep(Icons.grid_on, '1. 高程像元', 'dem.tif 为地图上的高程网格。'),
              _demStep(Icons.trending_up, '2. 坡度分析', '比较道路前后高程，识别平路、上坡和下坡。'),
              _demStep(Icons.accessible, '3. 路线筛选', '轮椅、婴儿车和行李模式会避开过陡道路。'),
              _demStep(
                  Icons.route, '4. 最终验证', 'AI 只推荐景点，真实道路仍由 OSM 路网和地形数据验证。'),
              const Divider(),
              if (demHealthLoading)
                const Text('正在读取 DEM 状态...')
              else if (demHealth == null)
                const Text('暂时无法连接 backend，无法读取 DEM 状态。')
              else
                _demStatus(metadata),
            ],
          ),
        ),
        actions: [
          TextButton(onPressed: _loadDemHealth, child: const Text('重新读取')),
          TextButton(
              onPressed: () => Navigator.pop(context), child: const Text('关闭')),
        ],
      ),
    );
  }

  void _toggleTerrain() {
    if (demHealth?['dem_loaded'] != true) {
      setState(() => status = 'DEM 尚未加载，无法显示地形图层');
      _loadDemHealth();
      return;
    }
    setState(() => showTerrain = !showTerrain);
  }

  Widget _demStep(IconData icon, String title, String description) => Padding(
        padding: const EdgeInsets.only(bottom: 10),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(icon, size: 20, color: Colors.teal),
            const SizedBox(width: 8),
            Expanded(child: Text('$title：$description')),
          ],
        ),
      );

  Widget _demStatus(Map<String, dynamic>? metadata) {
    final loaded = demHealth?['dem_loaded'] == true;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          loaded ? 'DEM 状态：已加载' : 'DEM 状态：未加载',
          style: TextStyle(
            fontWeight: FontWeight.bold,
            color: loaded ? Colors.green.shade700 : Colors.orange.shade800,
          ),
        ),
        if (metadata != null) ...[
          Text('坐标系：${metadata['crs'] ?? '未知'}'),
          Text('网格：${metadata['width']} × ${metadata['height']}'),
          Text('分辨率：${metadata['resolution']}'),
        ],
      ],
    );
  }

  @override
  void dispose() {
    startSearch.dispose();
    endSearch.dispose();
    for (final timer in timers.values) {
      timer?.cancel();
    }
    super.dispose();
  }

  void _queueSearch(String query, bool isStart) {
    timers[isStart]?.cancel();
    if (query.trim().length < 2) {
      setState(() => suggestions[isStart] = []);
      return;
    }
    timers[isStart] = Timer(const Duration(milliseconds: 450), () {
      _searchPlaces(query.trim(), isStart);
    });
  }

  Future<void> _searchPlaces(String query, bool isStart) async {
    try {
      final response = await http.get(
        Uri.parse(
          '$apiBaseUrl/geocode/search?q=${Uri.encodeComponent(query)}&limit=5',
        ),
        headers: {'Accept': 'application/json'},
      ).timeout(const Duration(seconds: 8));
      if (response.statusCode != 200) {
        throw Exception('搜尋服務回傳 ${response.statusCode}');
      }
      final data = jsonDecode(response.body) as List<dynamic>;
      if (!mounted) return;
      setState(() {
        suggestions[isStart] = data
            .whereType<Map<String, dynamic>>()
            .map(_Place.fromSearchJson)
            .toList();
      });
    } catch (error) {
      if (!mounted) return;
      setState(() => status = '地點搜尋失敗：$error');
    }
  }

  void _selectSearchResult(_Place place, bool isStart) {
    setState(() {
      if (isStart) {
        startPlace = place;
        startSearch.text = place.name;
      } else {
        endPlace = place;
        endSearch.text = place.name;
      }
      suggestions[isStart] = [];
      selectionMode = _SelectionMode.none;
      status = '${isStart ? '起點' : '終點'}已選取：${place.name}';
    });
    _maybePlan();
  }

  void _startMapSelection(bool isStart) {
    setState(() {
      selectionMode = isStart ? _SelectionMode.start : _SelectionMode.end;
      status = '請在地圖上點擊${isStart ? '起點' : '終點'}位置';
    });
  }

  Future<void> _onMapTap(TapPosition _, LatLng point) async {
    final mode = selectionMode;
    if (mode == _SelectionMode.none) return;
    final isStart = mode == _SelectionMode.start;
    setState(() => status = '正在取得地點名稱...');
    try {
      final response = await http.get(
        Uri.parse(
          '$apiBaseUrl/geocode/reverse?lat=${point.latitude}&lon=${point.longitude}',
        ),
        headers: {'Accept': 'application/json'},
      ).timeout(const Duration(seconds: 8));
      final data = response.statusCode == 200
          ? jsonDecode(response.body) as Map<String, dynamic>
          : <String, dynamic>{};
      final place = _Place(
        name: data['display_name'] as String? ?? '地圖選取位置',
        latitude: point.latitude,
        longitude: point.longitude,
      );
      if (!mounted) return;
      setState(() {
        if (isStart) {
          startPlace = place;
          startSearch.text = place.name;
        } else {
          endPlace = place;
          endSearch.text = place.name;
        }
        selectionMode = _SelectionMode.none;
        status = '${isStart ? '起點' : '終點'}已選取：${place.name}';
      });
      _maybePlan();
    } catch (error) {
      if (!mounted) return;
      final place = _Place(
        name: '地圖選取位置',
        latitude: point.latitude,
        longitude: point.longitude,
      );
      setState(() {
        if (isStart) {
          startPlace = place;
          startSearch.text = place.name;
        } else {
          endPlace = place;
          endSearch.text = place.name;
        }
        selectionMode = _SelectionMode.none;
        status = '已選取座標，但無法取得名稱：$error';
      });
      _maybePlan();
    }
  }

  void _maybePlan() {
    if (startPlace != null && endPlace != null) {
      plan();
    }
  }

  Future<void> plan() async {
    final start = startPlace;
    final end = endPlace;
    if (start == null || end == null) {
      setState(() => status = '請先選取起點和終點');
      return;
    }

    setState(() {
      loading = true;
      status = '正在規劃路線...';
    });
    try {
      final response = await http.post(
        Uri.parse('$apiBaseUrl/route/plan'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'start_lat': start.latitude,
          'start_lon': start.longitude,
          'end_lat': end.latitude,
          'end_lon': end.longitude,
          'prefer_bus': preferBus,
        }),
      );
      final data = jsonDecode(response.body) as Map<String, dynamic>;
      if (response.statusCode != 200) {
        throw Exception(data['detail'] ?? '路線規劃失敗');
      }
      final coordinates =
          data['geojson']['features'][0]['geometry']['coordinates'] as List;
      if (coordinates.length < 2) {
        throw Exception('找不到有效路線，路線只包含一個地圖節點');
      }
      final parsedPoints = coordinates
          .map(
            (point) => LatLng(
              (point[1] as num).toDouble(),
              (point[0] as num).toDouble(),
            ),
          )
          .toList();
      final distance =
          (data['geojson']['properties']['total_distance'] as num).toDouble();
      if (distance <= 0 || parsedPoints.length < 2) {
        throw Exception('找不到有效路線，起點和終點可能落在同一個路網節點');
      }
      if (!mounted) return;
      setState(() {
        routePoints
          ..clear()
          ..addAll(parsedPoints);
        status = '路線完成，距離 ${distance.toStringAsFixed(0)} 公尺';
      });
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (routePoints.length > 1) {
          mapController.fitCamera(
            CameraFit.bounds(
              bounds: LatLngBounds.fromPoints(routePoints),
              padding: const EdgeInsets.all(48),
            ),
          );
        }
      });
    } catch (error) {
      if (mounted) setState(() => status = '路線規劃失敗：$error');
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  Future<void> _planTour() async {
    final message = '我想进行$tourCategory旅游，预计有$availableHours小时，最多参观$maxStops个景点。'
        '${routeProfile == '普通步行' ? '' : '请使用$routeProfile模式，最大坡度${maxSlope.toStringAsFixed(0)}%。'}'
        '${preferBus ? '优先考虑公交。' : ''}';
    setState(() {
      loading = true;
      status = '正在分析旅游目的并规划行程...';
      tourConfirmed = false;
    });
    try {
      final response = await http.post(
        Uri.parse('$apiBaseUrl/ai/plan_tour'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'message': message,
          'start_lat': startPlace?.latitude,
          'start_lon': startPlace?.longitude,
          'start_name': startPlace?.name,
          'end_lat': endPlace?.latitude,
          'end_lon': endPlace?.longitude,
          'prefer_bus': preferBus,
          'max_stops': maxStops,
          'available_minutes': availableHours * 60,
          'profile': _profileValue,
        }),
      );
      final data = jsonDecode(response.body) as Map<String, dynamic>;
      if (response.statusCode != 200) {
        throw Exception(data['detail'] ?? '行程规划失败');
      }
      if (!mounted) return;
      setState(() {
        tourPlan = data;
        status = data['needs_clarification'] == true
            ? data['clarification_question'] as String? ?? '请补充起点'
            : '行程已生成，请确认后再绘制路线';
      });
    } catch (error) {
      if (mounted) setState(() => status = 'AI 行程规划失败：$error');
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  Future<void> _confirmTour() async {
    final plannedStops = tourPlan?['stops'];
    if (plannedStops is! List || plannedStops.isEmpty) {
      setState(() => status = '行程至少需要两个地点');
      return;
    }
    final stops = <Map<String, dynamic>>[];
    if (startPlace != null) {
      stops.add({
        'id': 'user_start',
        'name': startPlace!.name,
        'latitude': startPlace!.latitude,
        'longitude': startPlace!.longitude,
        'category': 'history',
        'stay_minutes': 5,
        'reason': '用户选择的起点',
        'source': 'user',
      });
    }
    stops.addAll(plannedStops.cast<Map<String, dynamic>>());
    if (endPlace != null) {
      stops.add({
        'id': 'user_end',
        'name': endPlace!.name,
        'latitude': endPlace!.latitude,
        'longitude': endPlace!.longitude,
        'category': 'history',
        'stay_minutes': 5,
        'reason': '用户选择的终点',
        'source': 'user',
      });
    }
    if (stops.length < 2) {
      setState(() => status = '请先选择起点，或确认至少两个行程地点');
      return;
    }
    setState(() {
      loading = true;
      status = '正在验证各段道路路线...';
    });
    try {
      final response = await http.post(
        Uri.parse('$apiBaseUrl/tour/route'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'stops': stops, 'prefer_bus': preferBus}),
      );
      final data = jsonDecode(response.body) as Map<String, dynamic>;
      if (response.statusCode != 200) {
        throw Exception(data['detail'] ?? '多站路线验证失败');
      }
      final points = (data['coordinates'] as List)
          .map((point) => LatLng(
                (point[1] as num).toDouble(),
                (point[0] as num).toDouble(),
              ))
          .toList();
      if (points.length < 2) throw Exception('验证后没有有效路线');
      if (!mounted) return;
      setState(() {
        routePoints
          ..clear()
          ..addAll(points);
        tourConfirmed = true;
        status =
            '行程路线已确认，距离 ${(data['total_distance_m'] as num).toStringAsFixed(0)} 公尺';
      });
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (routePoints.length > 1) {
          mapController.fitCamera(CameraFit.bounds(
            bounds: LatLngBounds.fromPoints(routePoints),
            padding: const EdgeInsets.all(48),
          ));
        }
      });
    } catch (error) {
      if (mounted) setState(() => status = '行程路线验证失败：$error');
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  String get _profileValue => switch (routeProfile) {
        '避免楼梯' => 'avoid_stairs',
        '轮椅友好' => 'wheelchair',
        '婴儿车友好' => 'stroller',
        '携带行李' => 'luggage',
        _ => 'normal',
      };

  Widget _tourPlannerCard() => Card(
        elevation: 0,
        color: Theme.of(context).colorScheme.surfaceContainerHighest,
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(children: [
                Icon(Icons.auto_awesome,
                    color: Theme.of(context).colorScheme.primary),
                const SizedBox(width: 8),
                const Text('AI 行程规划',
                    style:
                        TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
              ]),
              const SizedBox(height: 4),
              const Text('选择偏好，AI 推荐景点，再由道路和地形数据验证。'),
              const SizedBox(height: 14),
              DropdownButtonFormField<String>(
                initialValue: tourCategory,
                decoration: const InputDecoration(
                  labelText: '旅游主题',
                  prefixIcon: Icon(Icons.explore),
                  border: OutlineInputBorder(),
                ),
                items: const [
                  '历史文化',
                  '美食探索',
                  '自然风景',
                  '家庭亲子',
                  '购物休闲',
                  '宗教与建筑',
                ]
                    .map((item) =>
                        DropdownMenuItem(value: item, child: Text(item)))
                    .toList(),
                onChanged: (value) =>
                    setState(() => tourCategory = value ?? tourCategory),
              ),
              const SizedBox(height: 12),
              Row(children: [
                Expanded(
                  child: DropdownButtonFormField<int>(
                    initialValue: availableHours,
                    decoration: const InputDecoration(
                      labelText: '可用时间',
                      prefixIcon: Icon(Icons.schedule),
                      border: OutlineInputBorder(),
                    ),
                    items: [1, 2, 4, 6, 8]
                        .map((hours) => DropdownMenuItem(
                            value: hours, child: Text('$hours 小时')))
                        .toList(),
                    onChanged: (value) => setState(
                        () => availableHours = value ?? availableHours),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: DropdownButtonFormField<int>(
                    initialValue: maxStops,
                    decoration: const InputDecoration(
                      labelText: '景点数量',
                      prefixIcon: Icon(Icons.place),
                      border: OutlineInputBorder(),
                    ),
                    items: [2, 3, 4, 5, 6]
                        .map((count) => DropdownMenuItem(
                            value: count, child: Text('最多 $count 个')))
                        .toList(),
                    onChanged: (value) =>
                        setState(() => maxStops = value ?? maxStops),
                  ),
                ),
              ]),
              const SizedBox(height: 12),
              DropdownButtonFormField<String>(
                initialValue: routeProfile,
                decoration: const InputDecoration(
                  labelText: '路线偏好',
                  prefixIcon: Icon(Icons.accessibility_new),
                  border: OutlineInputBorder(),
                ),
                items: const [
                  '普通步行',
                  '避免楼梯',
                  '轮椅友好',
                  '婴儿车友好',
                  '携带行李',
                ]
                    .map((item) =>
                        DropdownMenuItem(value: item, child: Text(item)))
                    .toList(),
                onChanged: (value) =>
                    setState(() => routeProfile = value ?? routeProfile),
              ),
              if (routeProfile != '普通步行')
                Row(children: [
                  const Text('最大坡度'),
                  Expanded(
                    child: Slider(
                      value: maxSlope,
                      min: 5,
                      max: 25,
                      divisions: 4,
                      label: '${maxSlope.toStringAsFixed(0)}%',
                      onChanged: (value) => setState(() => maxSlope = value),
                    ),
                  ),
                  Text('${maxSlope.toStringAsFixed(0)}%'),
                ]),
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('优先使用公交'),
                value: preferBus,
                onChanged: (value) => setState(() => preferBus = value),
              ),
              SizedBox(
                width: double.infinity,
                child: FilledButton.icon(
                  onPressed: loading ? null : _planTour,
                  icon: const Icon(Icons.auto_awesome),
                  label: Text(loading ? '正在生成行程...' : '生成 AI 行程'),
                ),
              ),
            ],
          ),
        ),
      );

  Widget _tourPanel() {
    final planData = tourPlan;
    final stops = planData?['stops'];
    if (planData == null ||
        stops is! List ||
        stops.isEmpty ||
        planData['needs_clarification'] == true) {
      return const SizedBox.shrink();
    }
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(8),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('建议行程：${planData['purpose'] ?? ''}',
                maxLines: 2, overflow: TextOverflow.ellipsis),
            ...stops.asMap().entries.map((entry) {
              final stop = entry.value as Map<String, dynamic>;
              return ListTile(
                dense: true,
                leading: CircleAvatar(child: Text('${entry.key + 1}')),
                title: Text(stop['name'] as String),
                subtitle:
                    Text('${stop['stay_minutes']} 分钟 · ${stop['reason']}'),
              );
            }),
            if (!tourConfirmed)
              FilledButton.icon(
                onPressed: loading ? null : _confirmTour,
                icon: const Icon(Icons.check),
                label: const Text('确认行程并显示路线'),
              ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('澳門智慧導航')),
        body: Column(
          children: [
            if (showMapPanel)
              SizedBox(
                height: 360,
                child: SingleChildScrollView(
                  padding: const EdgeInsets.all(12),
                  child: Column(
                    children: [
                      Row(
                        children: [
                          const Expanded(
                            child: Text(
                              '路线与行程控制',
                              style: TextStyle(fontWeight: FontWeight.bold),
                            ),
                          ),
                          IconButton(
                            tooltip: '收起，让地图完整显示',
                            onPressed: () =>
                                setState(() => showMapPanel = false),
                            icon: const Icon(Icons.keyboard_arrow_up),
                          ),
                        ],
                      ),
                      _placeField('起點', startSearch, true),
                      _placeField('終點', endSearch, false),
                      SizedBox(
                        width: double.infinity,
                        child: FilledButton(
                          onPressed: loading ? null : plan,
                          child: Text(loading ? '規劃中...' : '規劃路线'),
                        ),
                      ),
                      _tourPlannerCard(),
                      Text(status,
                          maxLines: 2, overflow: TextOverflow.ellipsis),
                      _culturalLayerStatus(),
                      Align(
                        alignment: Alignment.centerLeft,
                        child: TextButton.icon(
                          onPressed: _showDemInfo,
                          icon: const Icon(Icons.info_outline),
                          label: const Text('了解 GeoTIFF 高程如何影响路线'),
                        ),
                      ),
                      _tourPanel(),
                    ],
                  ),
                ),
              ),
            Expanded(
              child: Stack(
                children: [
                  FlutterMap(
                    mapController: mapController,
                    options: MapOptions(
                      initialCenter: const LatLng(22.192, 113.539),
                      initialZoom: 13,
                      onTap: _onMapTap,
                    ),
                    children: [
                      TileLayer(
                        urlTemplate:
                            'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                        userAgentPackageName: 'com.macau.navigation',
                      ),
                      if (showTerrain)
                        OverlayImageLayer(
                          overlayImages: [
                            OverlayImage(
                              bounds: LatLngBounds(
                                LatLng(
                                  (demHealth?['dem_metadata']['bounds'][1]
                                          as num)
                                      .toDouble(),
                                  (demHealth?['dem_metadata']['bounds'][0]
                                          as num)
                                      .toDouble(),
                                ),
                                // ignore: prefer_const_constructors
                                LatLng(
                                  (demHealth?['dem_metadata']['bounds'][3]
                                          as num)
                                      .toDouble(),
                                  (demHealth?['dem_metadata']['bounds'][2]
                                          as num)
                                      .toDouble(),
                                ),
                              ),
                              opacity: 0.45,
                              // ignore: prefer_const_constructors
                              imageProvider: NetworkImage(
                                '$apiBaseUrl/terrain/overlay.png',
                              ),
                            ),
                          ],
                        ),
                      if (routePoints.length > 1)
                        PolylineLayer(
                          polylines: [
                            Polyline(
                              points: routePoints,
                              color: Colors.blue,
                              strokeWidth: 5,
                            ),
                          ],
                        ),
                      MarkerLayer(markers: [
                        if (showCulturalPlaces)
                          ...culturalPlaces
                              .where((place) =>
                                  showNearbyCulturalPlaces ||
                                  place.data['area_status'] == 'macau')
                              .map(_culturalMarker),
                        if (startPlace != null)
                          _marker(startPlace!.point, Colors.green,
                              Icons.trip_origin),
                        if (endPlace != null)
                          _marker(endPlace!.point, Colors.red, Icons.flag),
                      ]),
                    ],
                  ),
                  Positioned(
                    top: 16,
                    left: 16,
                    child: FloatingActionButton.small(
                      heroTag: 'map-controls-toggle',
                      tooltip: '打开路线和行程控制',
                      onPressed: () => setState(() => showMapPanel = true),
                      child: Icon(showMapPanel ? Icons.map : Icons.tune),
                    ),
                  ),
                  Positioned(
                    top: 16,
                    right: 16,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.end,
                      children: [
                        Card(
                          elevation: 4,
                          child: FilledButton.icon(
                            onPressed: _toggleTerrain,
                            icon: const Icon(Icons.terrain),
                            label: Text(showTerrain ? '隐藏地形图层' : '显示 QGIS 地形'),
                          ),
                        ),
                        Card(
                          elevation: 4,
                          child: FilledButton.icon(
                            onPressed: culturalPlacesLoading
                                ? null
                                : () => setState(
                                      () => showCulturalPlaces =
                                          !showCulturalPlaces,
                                    ),
                            icon: const Icon(Icons.account_balance),
                            label:
                                Text(showCulturalPlaces ? '隐藏文化地点' : '显示文化地点'),
                          ),
                        ),
                        if (showCulturalPlaces)
                          Card(
                            elevation: 4,
                            child: FilterChip(
                              selected: showNearbyCulturalPlaces,
                              label: const Text('显示周边地点'),
                              onSelected: (value) => setState(
                                  () => showNearbyCulturalPlaces = value),
                            ),
                          ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      );

  Widget _placeField(
    String label,
    TextEditingController controller,
    bool isStart,
  ) {
    final items = suggestions[isStart] ?? [];
    return Column(
      children: [
        Row(
          children: [
            Expanded(
              child: TextField(
                controller: controller,
                onChanged: (value) => _queueSearch(value, isStart),
                decoration: InputDecoration(
                  labelText: label,
                  hintText: '輸入地點名稱',
                  border: const OutlineInputBorder(),
                  prefixIcon: Icon(
                    isStart ? Icons.trip_origin : Icons.flag,
                    color: isStart ? Colors.green : Colors.red,
                  ),
                ),
              ),
            ),
            const SizedBox(width: 8),
            OutlinedButton.icon(
              onPressed: () => _startMapSelection(isStart),
              icon: const Icon(Icons.map),
              label: const Text('地圖選取'),
            ),
          ],
        ),
        if (items.isNotEmpty)
          ...items.map(
            (place) => ListTile(
              dense: true,
              leading: const Icon(Icons.place),
              title: Text(place.name),
              onTap: () => _selectSearchResult(place, isStart),
            ),
          ),
      ],
    );
  }

  Marker _marker(LatLng point, Color color, IconData icon) => Marker(
        point: point,
        width: 44,
        height: 44,
        child: Icon(icon, color: color, size: 36),
      );
}
