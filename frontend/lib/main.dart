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

class _NavigationPageState extends State<NavigationPage> {
  final mapController = MapController();
  final startSearch = TextEditingController();
  final endSearch = TextEditingController();
  final chat = TextEditingController();
  final routePoints = <LatLng>[];
  final suggestions = <bool, List<_Place>>{true: [], false: []};
  final timers = <bool, Timer?>{true: null, false: null};

  _Place? startPlace;
  _Place? endPlace;
  _SelectionMode selectionMode = _SelectionMode.none;
  String status = '搜尋地點，或按按鈕後直接點擊地圖';
  bool loading = false;
  bool preferBus = false;

  @override
  void dispose() {
    startSearch.dispose();
    endSearch.dispose();
    chat.dispose();
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

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('澳門智慧導航')),
        body: Column(
          children: [
            Padding(
              padding: const EdgeInsets.all(12),
              child: Column(
                children: [
                  _placeField('起點', startSearch, true),
                  _placeField('終點', endSearch, false),
                  SwitchListTile(
                    title: const Text('優先使用公車'),
                    value: preferBus,
                    onChanged: (value) => setState(() => preferBus = value),
                  ),
                  SizedBox(
                    width: double.infinity,
                    child: FilledButton(
                      onPressed: loading ? null : plan,
                      child: Text(loading ? '規劃中...' : '規劃路線'),
                    ),
                  ),
                  Text(status, maxLines: 2, overflow: TextOverflow.ellipsis),
                ],
              ),
            ),
            Expanded(
              child: FlutterMap(
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
                    if (startPlace != null)
                      _marker(startPlace!.point, Colors.green, Icons.trip_origin),
                    if (endPlace != null)
                      _marker(endPlace!.point, Colors.red, Icons.flag),
                  ]),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.all(8),
              child: Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: chat,
                      decoration: const InputDecoration(
                        hintText: '例如：我想坐公車，最多步行2公里',
                      ),
                    ),
                  ),
                  IconButton(
                    icon: const Icon(Icons.send),
                    onPressed: () {
                      if (chat.text.isNotEmpty) {
                        setState(() => status = '偏好已收到：${chat.text}');
                      }
                    },
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
