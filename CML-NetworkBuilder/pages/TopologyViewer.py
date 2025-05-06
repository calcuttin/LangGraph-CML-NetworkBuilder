import streamlit as st
from pyvis.network import Network
import json
import os
from datetime import datetime
import streamlit.components.v1 as components

def draw_network_topology(mcp_model: dict):
    net = Network(height="700px", width="100%", bgcolor="#ffffff", font_color="black", notebook=False)

    devices = mcp_model.get("network_design", {}).get("devices", [])
    links = mcp_model.get("network_design", {}).get("links", [])

    for device in devices:
        net.add_node(device["name"], label=device["name"], color="lightblue" if device["type"] == "router" else "lightgreen")

    for link in links:
        if len(link["endpoints"]) == 2:
            net.add_edge(link["endpoints"][0], link["endpoints"][1], label=link.get("link_type", "ethernet"))

    os.makedirs("saved_models", exist_ok=True)
    filename = f"saved_models/topology_viewer_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.html"
    net.save_graph(filename)

    st.markdown("### 📺 Topology Preview")
    components.html(f"""
    <iframe src="/saved_models/{os.path.basename(filename)}" width="100%" height="750px" frameborder="0"></iframe>
    """, height=800, scrolling=True)

st.title("🖼 Topology Viewer")

saved_files = [f for f in os.listdir("saved_models") if f.endswith(".json")]
selected_file = st.selectbox("Select a topology to view", ["Select..."] + saved_files)

if selected_file != "Select...":
    with open(f"saved_models/{selected_file}", "r") as f:
        mcp_model = json.load(f)
    draw_network_topology(mcp_model)