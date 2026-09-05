import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:http/http.dart' as http;
import 'package:latlong2/latlong.dart';

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

class _NavigationPageState extends State<NavigationPage> {
  final startLat = TextEditingController(text: '22.192');
  final startLon = TextEditingController(text: '113.539');
  final endLat = TextEditingController(text: '22.188');
  final endLon = TextEditingController(text: '113.535');
  final chat = TextEditingController();
  final points = <LatLng>[];
  String status = '輸入起點與終點後規劃路線';
  bool loading = false;
  bool preferBus = false;

  Future<void> plan() async {
    setState(() { loading = true; status = '規劃中...'; });
    try {
      final response = await http.post(
        Uri.parse('http://10.0.2.2:8000/route/plan'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'start_lat': double.parse(startLat.text), 'start_lon': double.parse(startLon.text),
          'end_lat': double.parse(endLat.text), 'end_lon': double.parse(endLon.text),
          'prefer_bus': preferBus,
        }),
      );
      final data = jsonDecode(response.body);
      if (response.statusCode != 200) throw Exception(data['detail'] ?? '請求失敗');
      final coordinates = data['geojson']['features'][0]['geometry']['coordinates'] as List;
      setState(() {
        points
          ..clear()
          ..addAll(coordinates.map((point) => LatLng((point[1] as num).toDouble(), (point[0] as num).toDouble())));
        status = '距離 ${(data['geojson']['properties']['total_distance'] as num).toStringAsFixed(0)} 公尺';
      });
    } catch (error) {
      setState(() => status = '錯誤：$error');
    } finally {
      setState(() => loading = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('澳門智慧導航')),
        body: Column(children: [
          Padding(padding: const EdgeInsets.all(12), child: Column(children: [
            Row(children: [Expanded(child: _field('起點緯度', startLat)), Expanded(child: _field('起點經度', startLon))]),
            Row(children: [Expanded(child: _field('終點緯度', endLat)), Expanded(child: _field('終點經度', endLon))]),
            SwitchListTile(title: const Text('優先使用公車'), value: preferBus, onChanged: (value) => setState(() => preferBus = value)),
            SizedBox(width: double.infinity, child: FilledButton(onPressed: loading ? null : plan, child: Text(loading ? '規劃中...' : '規劃路線'))),
            Text(status),
          ])),
          Expanded(child: FlutterMap(options: MapOptions(initialCenter: const LatLng(22.192, 113.539), initialZoom: 13), children: [
            TileLayer(urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png', userAgentPackageName: 'com.example.macau_navigation'),
            if (points.length > 1) PolylineLayer(polylines: [Polyline(points: points, color: Colors.blue, strokeWidth: 5)]),
          ])),
          Padding(padding: const EdgeInsets.all(8), child: Row(children: [
            Expanded(child: TextField(controller: chat, decoration: const InputDecoration(hintText: '例如：我想坐公車，最多步行2公里'))),
            IconButton(icon: const Icon(Icons.send), onPressed: () { if (chat.text.isNotEmpty) setState(() => status = '偏好已收到：${chat.text}'); }),
          ])),
        ]),
      );

  Widget _field(String label, TextEditingController controller) => Padding(
        padding: const EdgeInsets.all(4),
        child: TextField(controller: controller, keyboardType: const TextInputType.numberWithOptions(decimal: true), decoration: InputDecoration(labelText: label, border: const OutlineInputBorder())),
      );
}
