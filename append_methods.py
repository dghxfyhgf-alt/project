append_content = '''
      } else {
        setState(() {
          _chatMessages.add(_ChatMessage(
            text: "解析失敗: ${response.statusCode}",
            isUser: false,
          ));
        });
      }
    } catch (e) {
      setState(() {
        _chatMessages.add(_ChatMessage(
          text: "解析錯誤: $e",
          isUser: false,
        ));
      });
    } finally {
      setState(() {
        _isParsingIntent = false;
      });
    }
  }

  void _applyParsedIntent(Map<String, dynamic> data) {
    setState(() {
      if (data["avoid_stairs"] != null) _avoidStairs = data["avoid_stairs"] as bool;
      if (data["max_slope"] != null) _maxSlope = (data["max_slope"] as num).toDouble();
      if (data["max_walk_km"] != null) _maxWalkKm = (data["max_walk_km"] as num).toDouble();
      if (data["prefer_bus"] != null) _preferBus = data["prefer_bus"] as bool;
      if (data["wheelchair"] != null) _wheelchair = data["wheelchair"] as bool;
    });
  }

  String _formatIntentResponse(Map<String, dynamic> data) {
    final parts = <String>[];
    if ((data["tags"] as List?)?.isNotEmpty == true) parts.add("標籤: ${(data["tags"] as List).join(",")}");
    if (data["avoid_stairs"] == true) parts.add("避開階梯");
    if (data["max_slope"] != null) parts.add("最大坡度: ${data["max_slope"]}%");
    if (data["max_walk_km"] != null) parts.add("最大步行: ${data["max_walk_km"]}km");
    if (data["prefer_bus"] == true) parts.add("優先公車");
    if (data["wheelchair"] == true) parts.add("無障礙模式");
    if (data["poi_category"] != null) parts.add("POI類別: ${data["poi_category"]}");
    return parts.isEmpty ? "解析完成(無具體偏好)" : parts.join("\\n");
  }

  Future<void> _searchPlaces(String query, bool isStart) async {
    if (query.length < 2) {
      setState(() {
        if (isStart) {
          _startSuggestions = [];
        } else {
          _endSuggestions = [];
        }
      });
      return;
    }

    try {
      final response = await http.get(
        Uri.parse("$_apiBase/geocode/search?q=${Uri.encodeComponent(query)}&limit=8"),
        headers: {"Accept": "application/json"},
      ).timeout(const Duration(seconds: 5));

      if (response.statusCode == 200) {
        final List<dynamic> data = jsonDecode(response.body);
        final results = data.map((e) => _GeocodeResult.fromJson(e)).toList();
        setState(() {
          if (isStart) {
            _startSuggestions = results;
          } else {
            _endSuggestions = results;
          }
        });
      }
    } catch (e) {
      // Ignore search errors
    }
  }

  void _removeOverlays() {
    // No overlays to remove with new approach
  }

  void _selectPlace(_GeocodeResult place, bool isStart) {
    _removeOverlays();
    final lat = place.lat;
    final lon = place.lon;

    setState(() {
      if (isStart) {
        _startNameController.text = place.displayName;
        _startLatController.text = lat.toString();
        _startLonController.text = lon.toString();
        _startSuggestions = [];
      } else {
        _endNameController.text = place.displayName;
        _endLatController.text = lat.toString();
        _endLonController.text = lon.toString();
        _endSuggestions = [];
      }
    });

    _updateSelectionMarker(isStart, LatLng(lat, lon));
  }

  void _updateSelectionMarker(bool isStart, LatLng point) {
    setState(() {
      if (isStart) {
        _markers.removeWhere((m) => m.type == 'start_select');
        _markers.add(_MapMarker(
          point: point,
          type: 'start_select',
          label: '起點',
        ));
      } else {
        _markers.removeWhere((m) => m.type == 'end_select');
        _markers.add(_MapMarker(
          point: point,
          type: 'end_select',
          label: '終點',
        ));
      }
    });
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _mapController.move(point, _initialZoom);
    });
    if (_startLatController.text.isNotEmpty && _endLatController.text.isNotEmpty) {
      _planRoute();
    }
  }

  void _onMapTap(LatLng point) {
    if (_isSelectingStart) {
      _selectPlaceFromMap(point, true);
    } else if (_isSelectingEnd) {
      _selectPlaceFromMap(point, false);
    }
  }

  Future<void> _selectPlaceFromMap(LatLng point, bool isStart) async {
    try {
      final response = await http.get(
        Uri.parse('$_apiBase/geocode/reverse?lat=${point.latitude}&lon=${point.longitude}'),
        headers: {'Accept': 'application/json'},
      ).timeout(const Duration(seconds: 5));

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        final name = data['display_name'] as String? ?? '選取位置';

        setState(() {
          if (isStart) {
            _startNameController.text = name;
            _startLatController.text = point.latitude.toString();
            _startLonController.text = point.longitude.toString();
          } else {
            _endNameController.text = name;
            _endLatController.text = point.latitude.toString();
            _endLonController.text = point.longitude.toString();
          }
        });
        _updateSelectionMarker(isStart, point);
      }
    } catch (e) {
      setState(() {
        if (isStart) {
          _startLatController.text = point.latitude.toString();
          _startLonController.text = point.longitude.toString();
        } else {
          _endLatController.text = point.latitude.toString();
          _endLonController.text = point.longitude.toString();
        }
      });
      _updateSelectionMarker(isStart, point);
    }
  }

  Future<void> _planRoute() async {
    if (_startLatController.text.isEmpty || _startLonController.text.isEmpty ||
        _endLatController.text.isEmpty || _endLonController.text.isEmpty) {
      setState(() => _error = '請輸入起點和終點座標');
      return;
    }

    setState(() {
      _isLoading = true;
      _error = null;
    });

    try {
      final prefs = <String, dynamic>{
        'avoid_stairs': _avoidStairs,
        'max_slope': _maxSlope,
        'max_walk_km': _maxWalkKm,
        'prefer_bus': _preferBus,
        'wheelchair': _wheelchair,
      };

      final response = await http.post(
        Uri.parse('$_apiBase/route/plan'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'start_lat': double.parse(_startLatController.text),
          'start_lon': double.parse(_startLonController.text),
          'end_lat': double.parse(_endLatController.text),
          'end_lon': double.parse(_endLonController.text),
          'preferences': prefs,
        }),
      ).timeout(const Duration(seconds: 15));

      if (response.statusCode == 200) {
        final geojson = jsonDecode(response.body);
        _parseGeojson(geojson);
      } else {
        setState(() {
          _isLoading = false;
          _error = '路線規劃失敗: ${response.statusCode}';
        });
      }
    } catch (e) {
      setState(() {
        _isLoading = false;
        _error = '錯誤: $e';
      });
    }
  }

  void _parseGeojson(Map<String, dynamic> geojson) {
    _routePoints.clear();
    _segments.clear();
    _markers.removeWhere((m) => m.type == 'start' || m.type == 'end' || m.type == 'bus_stop');

    final features = geojson['features'] as List<dynamic>?;
    if (features == null) return;

    for (final feature in features) {
      final props = feature['properties'] as Map<String, dynamic>?;
      final geom = feature['geometry'] as Map<String, dynamic>?;
      if (props == null || geom == null) continue;

      final type = geom['type'] as String?;
      final coords = geom['coordinates'];

      if (type == 'LineString') {
        final mode = props['mode'] as String? ?? 'walk';
        final points = <LatLng>[];
        for (final coord in coords) {
          points.add(LatLng((coord[1] as num).toDouble(), (coord[0] as num).toDouble()));
        }

        if (mode == 'bus') {
          _segments.add(_RouteSegment(
            points: points,
            color: Colors.orange,
            width: 5.0,
            isBus: true,
            routeName: props['route'] as String? ?? '',
            distance: (props['distance'] as num?)?.toDouble() ?? 0,
            time: (props['time'] as num?)?.toDouble() ?? 0,
          ));
        } else {
          _segments.add(_RouteSegment(
            points: points,
            color: Colors.blue,
            width: 4.0,
            isBus: false,
            distance: (props['distance'] as num?)?.toDouble() ?? 0,
            time: (props['time'] as num?)?.toDouble() ?? 0,
          ));
        }

        _routePoints.addAll(points);
      } else if (type == 'Point') {
        final markerType = props['type'] as String? ?? '';
        if (markerType == 'start' || markerType == 'end' || markerType == 'bus_stop') {
          _markers.add(_MapMarker(
            point: LatLng((coords[1] as num).toDouble(), (coords[0] as num).toDouble()),
            type: markerType,
            label: props['label'] as String? ?? '',
            route: props['route'] as String? ?? '',
          ));
        }
      }
    }

    _routeProperties = geojson['properties'] as Map<String, dynamic>?;

    if (_routePoints.isNotEmpty) {
      _mapController.fitCamera(CameraFit.bounds(
        bounds: LatLngBounds.fromPoints(_routePoints),
        padding: const EdgeInsets.all(50),
      ));
    }

    setState(() {
      _isLoading = false;
    });
  }
}
'''

with open(r'C:\Users\ASUS\Documents\Default Project\frontend\lib\map_page.dart', 'a', encoding='utf-8') as f:
    f.write(append_content)

print('Appended missing methods successfully')