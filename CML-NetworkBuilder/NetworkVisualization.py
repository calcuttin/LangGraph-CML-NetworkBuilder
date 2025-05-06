import streamlit as st
import plotly.graph_objects as go
import networkx as nx
import ipaddress
import math
import random

def draw_network_topology_plotly(mcp_model, dark_mode=False, layout_type='spring', node_status=None):
    """
    Generate an interactive network topology diagram using Plotly, respecting dark/light mode,
    layout choice, and showing node status.
    
    Args:
        mcp_model: Dictionary containing network design info with devices and links
        dark_mode: Boolean indicating if dark mode is enabled
        layout_type: String specifying the layout algorithm ('spring', 'kamada_kawai', 'circular', 'shell')
        node_status: Optional dictionary mapping node names to their status ('up', 'down', etc.)
    """
    # --- Theme Colors ---
    bg_color = '#1e1e1e' if dark_mode else '#ffffff'  # Dark gray or white
    text_color = '#ffffff' if dark_mode else '#000000'  # White or black
    grid_color = '#444444' if dark_mode else '#dddddd'  # Lighter gray grid for dark mode
    line_color = '#bbbbbb' if dark_mode else '#888888' # Lighter lines for dark mode
    hover_bg = '#333333' if dark_mode else '#ffffff'
    hover_font = '#ffffff' if dark_mode else '#000000'
    status_colors = {
        'up': '#28a745', # Green
        'down': '#dc3545', # Red
        'unknown': '#ffc107' # Yellow
    }

    # Early safety check
    if not mcp_model or not isinstance(mcp_model, dict):
        st.error("❌ Error: Invalid or missing network model provided to visualization.")
        return None
        
    # Extract devices and links safely
    network_design = mcp_model.get("network_design", {})
    if not isinstance(network_design, dict):
        st.error("❌ Error: network_design section is missing or invalid.")
        return None
        
    devices = network_design.get("devices", [])
    links = network_design.get("links", [])
    
    if not isinstance(devices, list):
        st.error(f"❌ Error: Devices data is not a list (found type: {type(devices)}).")
        return None
    if not isinstance(links, list):
        st.error(f"❌ Error: Links data is not a list (found type: {type(links)}).")
        return None
        
    if not devices:
        st.warning("ℹ️ No devices found in the network model to visualize.")
        return None
    
    # Create a networkx graph
    G = nx.Graph()
    
    # Add nodes with detailed attributes
    for device in devices:
        # Ensure device is a dictionary
        if not isinstance(device, dict):
            st.warning(f"Skipping invalid device entry: {device}")
            continue
            
        name = device.get("name", "Unnamed")
        dev_type = device.get("type", "router").lower()
        # Get status (default to unknown if not provided)
        status = (node_status or {}).get(name, 'unknown') 
        
        # Build comprehensive hover info
        hover_info = f"<b>{name}</b> ({dev_type.title()})<br><b>Status: {status.upper()}</b><br>"
        
        # Add interface information with proper HTML formatting
        interfaces = device.get("interfaces", [])
        if isinstance(interfaces, list): # Check if interfaces is a list
            hover_info += "<br>---<br><b>Interfaces:</b><br>"
            for iface in interfaces:
                if not isinstance(iface, dict):
                    continue  # Skip non-dict interfaces
                    
                iface_name = iface.get("name", "")
                ip = iface.get("ip", "")
                mask = iface.get("mask", "")
                link_to = iface.get("link_to", "")
                
                # Try to format subnet more clearly if possible
                subnet_display = ""
                if ip and mask:
                    try:
                        prefix_length = sum([bin(int(x)).count('1') for x in mask.split('.')])
                        subnet_display = f"/{prefix_length}"
                    except:
                        subnet_display = ""
                
                # Format link info with arrow
                link_info = f" → {link_to}" if link_to else ""
                hover_info += f"• <b>{iface_name}:</b> {ip}{subnet_display}{link_info}<br>"
        
        # Add any protocol information
        config = device.get("config", "")
        if isinstance(config, str):
            protocols = []
            if "ospf" in config.lower():
                protocols.append("OSPF")
            if "eigrp" in config.lower():
                protocols.append("EIGRP")
            if "bgp" in config.lower():
                protocols.append("BGP")
            
            if protocols:
                hover_info += f"<br>---<br><b>Protocols:</b> {', '.join(protocols)}<br>"
        
        # Add node to graph with attributes
        G.add_node(name, 
                  type=dev_type,
                  status=status, # Store status
                  hover_text=hover_info)
    
    # Add edges to the graph
    for link in links:
        if not isinstance(link, dict):
            st.warning(f"Skipping invalid link entry: {link}")
            continue
            
        endpoints = link.get("endpoints", [])
        if isinstance(endpoints, list) and len(endpoints) == 2:
            # Ensure endpoints exist as nodes in the graph
            if endpoints[0] not in G.nodes() or endpoints[1] not in G.nodes():
                st.warning(f"Skipping link with missing node: {endpoints}")
                continue
                
            # Create hover info for the link
            link_type = link.get("link_type", "ethernet")
            subnet = link.get("subnet", "")
            ips = link.get("ips", [])
            
            # Build edge hover information
            edge_info = f"<b>Link:</b> {endpoints[0]} ↔ {endpoints[1]}<br>"
            edge_info += f"<b>Type:</b> {link_type}<br>"
            if subnet:
                edge_info += f"<b>Subnet:</b> {subnet}<br>"
            
            if ips and isinstance(ips, list) and len(ips) >= 2:
                edge_info += f"<b>IPs:</b> {ips[0]} | {ips[1]}"
            
            # Add the edge with attributes
            G.add_edge(endpoints[0], endpoints[1], 
                      type=link_type,
                      subnet=subnet,
                      hover_text=edge_info)
    
    # Check if graph has nodes before proceeding
    if not G.nodes():
        st.warning("ℹ️ No valid network elements to display.")
        return None
    
    # --- Apply selected layout algorithm ---
    try:
        if len(G.nodes()) == 0: # Handle empty graph case
             pos = {}
        elif layout_type == 'kamada_kawai':
             pos = nx.kamada_kawai_layout(G)
        elif layout_type == 'circular':
             pos = nx.circular_layout(G)
        elif layout_type == 'shell':
             pos = nx.shell_layout(G)
        elif layout_type == 'spectral':
             pos = nx.spectral_layout(G)
        # Default to spring layout
        else: 
            k_val = 1.0 / math.sqrt(len(G.nodes())) if len(G.nodes()) > 0 else 1.0
            pos = nx.spring_layout(G, k=k_val, seed=42)
    except Exception as e:
        st.error(f"❌ Error creating graph layout ({layout_type}): {str(e)}")
        # Fallback to simple spring layout if possible
        try:
            pos = nx.spring_layout(G, seed=42)
        except:
            st.error("❌ Failed to generate even fallback layout.")
            return None
    
    # Define colors and shapes based on device types
    node_colors = {
        "router": "#66B2FF",       # Light blue
        "switch": "#66FF66",       # Light green
        "firewall": "#FF9999",     # Light red/salmon
        "server": "#CCCCCC",       # Light gray
        "ext-server": "#CCCCCC"    # Light gray
    }
    
    # --- Use more diverse Plotly symbols --- 
    node_shapes = {
        "router": "circle",
        "switch": "square",
        "firewall": "diamond",
        "server": "triangle-up",
        "ext-server": "cross",
        "pc": "circle-x", 
        "host": "circle-dot",
        "default": "circle" # Fallback symbol
    }
    
    # Create node traces by device type for better legend
    node_traces = {}
    try:
        node_attributes = nx.get_node_attributes(G, 'type')
        device_types = set(node_attributes.values()) if node_attributes else set()
    except Exception as e:
        st.warning(f"Could not get node types: {e}")
        device_types = set()
        
    if not device_types:
        st.info("No device types found, using default 'router' visualization.")
        device_types = {"router"} # Default fallback
        
    for device_type in device_types:
        color = node_colors.get(device_type, "#808080")  # Gray as default
        shape = node_shapes.get(device_type, node_shapes["default"])
        
        node_traces[device_type] = go.Scatter(
            x=[],
            y=[],
            text=[],
            mode='markers+text',
            name=device_type.title() if isinstance(device_type, str) else 'Unknown',
            hoverinfo='text',
            hoverlabel=dict(
                bgcolor=hover_bg,
                font_size=12,
                font_family="Arial",
                font_color=hover_font
            ),
            marker=dict(
                size=35,
                color=color,
                symbol=shape,
                line=dict(color=text_color, width=1) # Border color initially based on theme
            ),
            textfont=dict(color=text_color, size=10), # Adjust text color
            textposition="bottom center"
        )
    
    # Add nodes to the corresponding traces and apply status styling
    node_x_coords = {}
    node_y_coords = {}
    node_border_colors = {}
    
    for node, attrs in G.nodes(data=True):
        if node not in pos: continue # Skip nodes without position
        x, y = pos[node]
        node_type = attrs.get('type', 'router')
        status = attrs.get('status', 'unknown')
        border_color = status_colors.get(status, status_colors['unknown'])
        
        # Get or create the trace for this node type
        if node_type not in node_traces:
             # Find the first available trace as a fallback template
            fallback_trace_key = next(iter(node_traces), 'router') 
            if fallback_trace_key not in node_traces:
                 # If still no trace, create a default router trace
                 node_traces['router'] = go.Scatter(x=[],y=[],text=[],mode='markers+text', name='Router', hoverinfo='text', marker=dict(size=35, color='#66B2FF', line=dict(width=2)), textfont=dict(color=text_color, size=10), textposition='bottom center')
                 node_traces['router'].marker.line.color = status_colors['unknown'] # Set default border
            node_traces[node_type] = node_traces.get(fallback_trace_key).copy()
            node_traces[node_type].name = node_type.title() if isinstance(node_type, str) else 'Unknown'
            # Ensure copied trace attributes are lists
            for attr in ['x', 'y', 'text', 'hovertext']:
                 setattr(node_traces[node_type], attr, [])

        trace = node_traces[node_type]
        
        # Store coordinates and border color for this node
        node_x_coords.setdefault(node_type, []).append(x)
        node_y_coords.setdefault(node_type, []).append(y)
        node_border_colors.setdefault(node_type, []).append(border_color)
        
        # Add node label and hover text
        if not hasattr(trace, 'text') or trace.text is None: trace.text = []
        if not hasattr(trace, 'hovertext') or trace.hovertext is None: trace.hovertext = []
            
        trace.text = list(trace.text) + [node]
        trace.hovertext = list(trace.hovertext) + [attrs.get('hover_text', node)]

    # Assign collected coordinates and border colors to traces
    for node_type, trace in node_traces.items():
        trace.x = node_x_coords.get(node_type, [])
        trace.y = node_y_coords.get(node_type, [])
        trace.marker.line.color = node_border_colors.get(node_type, []) # Apply status colors to border
        trace.marker.line.width = 2 # Make border visible
    
    # Create edge traces based on link types
    edge_types = {}
    for u, v, data in G.edges(data=True):
        if u not in pos or v not in pos: continue # Skip edges without node positions
        edge_type = data.get('type', 'ethernet')
        if edge_type not in edge_types:
            edge_types[edge_type] = {
                'x': [], 
                'y': [], 
                'hovertext': [],
                'color': line_color,  # Use theme line color
                'width': 2,
                'dash': 'solid'
            }
            
            # Set special styling for different link types
            if edge_type == 'serial':
                edge_types[edge_type]['dash'] = 'dash'
            elif edge_type == 'wireless':
                edge_types[edge_type]['dash'] = 'dot'
            elif edge_type == 'vxlan' or (isinstance(edge_type, str) and edge_type.startswith('tunnel')):
                edge_types[edge_type]['color'] = '#FF6600'  # Orange for overlay/tunnel
                edge_types[edge_type]['dash'] = 'dashdot'
            elif edge_type == 'internet':
                edge_types[edge_type]['color'] = '#9933FF'  # Purple for internet
        
        # Add the edge path
        x0, y0 = pos[u]
        x1, y1 = pos[v]
        
        # Add the edge with None to create separation between edges
        edge_types[edge_type]['x'].extend([x0, x1, None])
        edge_types[edge_type]['y'].extend([y0, y1, None])
        
        # Add hover text if available
        edge_types[edge_type]['hovertext'].append(data.get('hover_text', f"{u} - {v}"))
    
    # Create the traces for edges
    edge_traces = []
    for edge_type, edge_data in edge_types.items():
        # Ensure we have hovertext data for each edge segment
        segment_count = len(edge_data['x']) // 3  # Each edge has 3 points (start, end, None)
        if segment_count == 0:
            continue  # Skip if no edges
            
        hovertext_list = edge_data.get('hovertext', [])
        if not isinstance(hovertext_list, list):
            hovertext_list = [] # Fallback to empty list

        # Repeat hovertext for each edge segment, ensuring we don't go out of bounds
        if segment_count > len(hovertext_list):
             if hovertext_list: # Only repeat if list is not empty
                 hovertext_list = hovertext_list * (segment_count // len(hovertext_list) + 1)
             else:
                 hovertext_list = ["Link"] * segment_count # Default text if original list was empty
        final_hovertext = hovertext_list[:segment_count]
        
        edge_trace = go.Scatter(
            x=edge_data['x'],
            y=edge_data['y'],
            mode='lines',
            name=edge_type.title() if isinstance(edge_type, str) else 'Link',
            hoverinfo='text',
            hoverlabel=dict(
                bgcolor=hover_bg,
                font_size=10,
                font_family="Arial",
                font_color=hover_font
            ),
            text=final_hovertext,
            line=dict(
                width=edge_data['width'],
                color=edge_data['color'],
                dash=edge_data['dash']
            )
        )
        edge_traces.append(edge_trace)
    
    # Create figure with all traces
    fig_data = edge_traces + list(node_traces.values())
    if not fig_data:
         st.warning("No data to plot for the network topology.")
         return None
         
    fig = go.Figure(
        data=fig_data,
        layout=go.Layout(
            title=dict(text='Network Topology Diagram', font=dict(size=20, color=text_color)), # Corrected property + color
            showlegend=True,
            legend=dict(
                title="Network Elements",
                font=dict(color=text_color),
                x=0,
                y=1,
                xanchor='left',
                yanchor='bottom',
                orientation='h'
            ),
            hovermode='closest',
            margin=dict(b=20, l=5, r=5, t=40),
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            plot_bgcolor=bg_color, # Set plot bg color
            paper_bgcolor=bg_color, # Set paper bg color
            height=700,
            annotations=[
                dict(
                    text="Hover over elements for details",
                    showarrow=False,
                    xref="paper", yref="paper",
                    x=0.01, y=0.01,
                    font=dict(color=text_color)
                )
            ]
        )
    )
    
    # Add better interactivity
    fig.update_layout(
        hoverlabel=dict(
            bgcolor=hover_bg,
            font_size=12,
            font_family="Arial",
            font_color=hover_font
        ),
        dragmode='pan',  # Allow panning
    )
    
    # Only add update menus if we have nodes to display
    if G.nodes():
        # Enable zooming and panning tools
        fig.update_layout(
            updatemenus=[
                dict(
                    type="buttons",
                    direction="left",
                    buttons=[
                        dict(
                            args=[{"dragmode": "pan"}],
                            label="Pan",
                            method="relayout"
                        ),
                        dict(
                            args=[{"dragmode": "zoom"}],
                            label="Zoom",
                            method="relayout"
                        ),
                        dict(
                            args=[{"visible": [True] * len(fig.data)}],
                            label="Reset",
                            method="update"
                        )
                    ],
                    pad={"r": 10, "t": 10},
                    showactive=True,
                    x=0.05,
                    y=1.15,
                    xanchor="left",
                    yanchor="top",
                    bgcolor='#aaaaaa' if dark_mode else '#cccccc',
                    bordercolor=text_color,
                    font=dict(color=text_color)
                )
            ]
        )
    
    # Display the interactive plot in Streamlit
    try:
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(f"❌ Error displaying chart: {str(e)}")
        st.warning("Unable to render network visualization due to an error.")
    
    # Return the figure for potential future use
    return fig


# Legacy wrapper function for backward compatibility
def draw_network_topology(mcp_model):
    """Legacy wrapper for the original draw_network_topology function"""
    # Pass dark_mode state if available
    dark_mode = st.session_state.get('dark_mode_active', False)
    return draw_network_topology_plotly(mcp_model, dark_mode=dark_mode) 