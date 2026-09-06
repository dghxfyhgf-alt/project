import osmnx as ox
import networkx as nx
import os

def download_macau_network():
    place_name = "Macau"
    network_type = "walk"
    
    print(f"正在下載 {place_name} 的道路網路數據 (network_type='{network_type}')...")
    
    graph = ox.graph_from_place(place_name, network_type=network_type)
    
    print(f"下載完成。節點數: {graph.number_of_nodes()}, 邊數: {graph.number_of_edges()}")
    
    output_dir = "data"
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "macau_network.graphml")
    
    print(f"正在儲存至 {output_path}...")
    ox.save_graphml(graph, filepath=output_path)
    
    print("儲存完成！")
    return graph

if __name__ == "__main__":
    download_macau_network()