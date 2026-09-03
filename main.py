from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List
import osmnx as ox
import networkx as nx
from geojson import Feature, FeatureCollection, LineString
import json

app = FastAPI(title="Macau Route Planner", version="1.0.0")

GRAPH_PATH = "data/macau_network.graphml"
graph: nx.MultiDiGraph = None

class RouteRequest(BaseModel):
    start_lat: float = Field(..., description="起點緯度", ge=-90, le=90)
    start_lon: float = Field(..., description="起點經度", ge=-180, le=180)
    end_lat: float = Field(..., description="終點緯度", ge=-90, le=90)
    end_lon: float = Field(..., description="終點經度", ge=-180, le=180)
    weight: Optional[str] = Field("length", description="路徑權重屬性名稱 (如: length, travel_time)")

class RouteResponse(BaseModel):
    type: str = "FeatureCollection"
    features: List[dict]

@app.on_event("startup")
async def load_graph():
    global graph
    try:
        graph = ox.load_graphml(GRAPH_PATH)
        print(f"圖載入成功: {graph.number_of_nodes()} 節點, {graph.number_of_edges()} 邊")
    except FileNotFoundError:
        raise RuntimeError(f"找不到圖檔案: {GRAPH_PATH}")
    except Exception as e:
        raise RuntimeError(f"載入圖檔案失敗: {str(e)}")

@app.post("/route/plan", response_model=RouteResponse)
async def plan_route(request: RouteRequest):
    if graph is None:
        raise HTTPException(status_code=500, detail="圖資料尚未載入完成")
    
    try:
        orig_node = ox.distance.nearest_nodes(graph, request.start_lon, request.start_lat)
        dest_node = ox.distance.nearest_nodes(graph, request.end_lon, request.end_lat)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"最近節點查找失敗: {str(e)}")
    
    try:
        route_nodes = ox.shortest_path(graph, orig_node, dest_node, weight=request.weight)
    except nx.NetworkXNoPath:
        raise HTTPException(status_code=404, detail="找不到可行路徑")
    except KeyError:
        raise HTTPException(status_code=400, detail=f"權重屬性 '{request.weight}' 不存在於圖中")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"路徑計算失敗: {str(e)}")
    
    if not route_nodes:
        raise HTTPException(status_code=404, detail="找不到可行路徑")
    
    coordinates = []
    for node_id in route_nodes:
        node_data = graph.nodes[node_id]
        coordinates.append([node_data["x"], node_data["y"]])
    
    line_string = LineString(coordinates)
    feature = Feature(geometry=line_string, properties={
        "weight": request.weight,
        "node_count": len(route_nodes)
    })
    
    return RouteResponse(type="FeatureCollection", features=[feature])

@app.get("/health")
async def health_check():
    return {"status": "healthy", "graph_loaded": graph is not None}