import streamlit as st
import pandas as pd
from dotenv import load_dotenv
load_dotenv()  # Ensure .env is loaded immediately at startup
import json
from datetime import datetime
import os
from langgraph.graph import StateGraph, END
from typing import TypedDict
from langchain_openai import ChatOpenAI
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.tools import tool
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
import time
import base64
from io import BytesIO
import yaml
import traceback
from PIL import Image
from NetworkValidator import NetworkValidator
from NetworkParser import parse_network_request
from IPython.display import display
from NetworkVisualization import draw_network_topology, draw_network_topology_plotly
import re

# --- Template-based topology generators for reliable network creation ---
def create_template_topology(topology_type, num_devices, protocol=None, device_type="router"):
    """Generate a standard topology based on common topology patterns.
    
    Args:
        topology_type: String, one of: 'ring', 'star', 'mesh', 'bus', 'line'
        num_devices: Number of devices to include
        protocol: Optional routing protocol (OSPF, EIGRP, BGP, etc.)
        device_type: Type of device to create (router, switch, etc.)
        
    Returns:
        Dictionary with 'devices' and 'links' lists ready for the topology builder
    """
    devices = []
    links = []
    
    # Create the devices
    for i in range(1, num_devices + 1):
        devices.append({
            "name": f"{device_type.capitalize()}{i}",
            "type": device_type.lower()
        })
    
    # Create the links based on topology type
    if topology_type.lower() == "ring":
        # Each device connects to the next, and the last connects to the first
        for i in range(num_devices):
            next_idx = (i + 1) % num_devices
            link = {
                "endpoints": [devices[i]["name"], devices[next_idx]["name"]],
                "link_type": "ethernet"  # Default link type
            }
            links.append(link)
    
    elif topology_type.lower() == "star":
        # First device is the hub, all others connect to it
        hub = devices[0]["name"]
        for i in range(1, num_devices):
            link = {
                "endpoints": [hub, devices[i]["name"]],
                "link_type": "ethernet"  # Default link type
            }
            links.append(link)
    
    elif topology_type.lower() == "mesh":
        # Every device connects to every other device
        for i in range(num_devices):
            for j in range(i + 1, num_devices):
                link = {
                    "endpoints": [devices[i]["name"], devices[j]["name"]],
                    "link_type": "ethernet"  # Default link type
                }
                links.append(link)
    
    elif topology_type.lower() == "bus" or topology_type.lower() == "line":
        # Devices connect in a line
        for i in range(num_devices - 1):
            link = {
                "endpoints": [devices[i]["name"], devices[i+1]["name"]],
                "link_type": "ethernet"  # Default link type
            }
            links.append(link)
    
    topology = {
        "devices": devices,
        "links": links
    }
    
    # Add protocol if specified
    if protocol:
        topology["protocol"] = protocol.upper()
    
    return topology

def detect_topology_pattern(text):
    """Detect if the user is requesting a common topology pattern.
    
    Args:
        text: User's input text
        
    Returns:
        Tuple of (topology_type, num_devices, protocol, device_type) or None if no pattern detected
    """
    
    # Look for topology type keywords
    topology_type = None
    if re.search(r'\b(ring|loop|circular|circle)\b', text, re.IGNORECASE):
        topology_type = "ring"
    elif re.search(r'\b(star|hub.+spoke|hub|spoke|central|radial)\b', text, re.IGNORECASE):
        topology_type = "star"
    elif re.search(r'\b(full.?mesh|mesh|fully.connected|complete)\b', text, re.IGNORECASE):
        topology_type = "mesh"
    elif re.search(r'\b(bus|line|linear|daisy.?chain|in.?a.?row|chain)\b', text, re.IGNORECASE):
        topology_type = "bus"
    
    # Look for numbers of devices
    num_match = re.search(r'(\d+)\s+(router|switch|firewall|device|computer|server|host)', text, re.IGNORECASE)
    if not num_match:
        # Try alternate patterns if the first one didn't match
        num_match = re.search(r'(\d+)[\s-]+(node|device|equipment)', text, re.IGNORECASE)
    if not num_match:
        # Just look for any number followed by a word
        num_match = re.search(r'(\d+)', text, re.IGNORECASE)
    
    num_devices = int(num_match.group(1)) if num_match else None
    
    # Look for device type
    device_type = "router"  # Default
    if re.search(r'\bswitch', text, re.IGNORECASE):
        device_type = "switch"
    elif re.search(r'\bfirewall', text, re.IGNORECASE):
        device_type = "firewall"
    
    # Look for protocol
    protocol = None
    if re.search(r'\bOSPF\b', text, re.IGNORECASE):
        protocol = "OSPF"
    elif re.search(r'\bEIGRP\b', text, re.IGNORECASE):
        protocol = "EIGRP"
    elif re.search(r'\bBGP\b', text, re.IGNORECASE):
        protocol = "BGP"
    elif re.search(r'\bRIP\b', text, re.IGNORECASE):
        protocol = "RIP"
    elif re.search(r'\bstatic\b', text, re.IGNORECASE):
        protocol = "STATIC"
    
    # If no specific topology mentioned but we have devices, default to ring topology
    # Ring is a good default as it's commonly used in network designs
    if not topology_type and num_devices:
        if num_devices == 2:
            topology_type = "bus"  # For 2 devices, a simple line makes sense
        elif num_devices <= 6:
            topology_type = "ring"  # Ring works well for small to medium networks
        else:
            topology_type = "star"  # Star is better for larger number of devices
    
    # Return None if we couldn't detect both topology type and number of devices
    if not topology_type or not num_devices:
        return None
    
    return (topology_type, num_devices, protocol, device_type)

# --- Place the function here ---
def assign_ip_addresses(devices, links, base_network="10.0.0.0/8", subnet_prefix=30):
    import ipaddress
    device_map = {dev["name"]: dev for dev in devices}
    network = ipaddress.ip_network(base_network, strict=False)
    subnet_gen = network.subnets(new_prefix=subnet_prefix)
    link_count = 0
    
    # Check if this is a VXLAN topology
    vxlan_enabled = any("VTEP" in dev["name"] for dev in devices) or any(link.get("link_type") == "vxlan" for link in links)
    
    # If VXLAN enabled, assign loopback IPs for VTEPs
    if vxlan_enabled:
        loopback_network = ipaddress.ip_network("192.168.100.0/24")
        loopback_ips = list(loopback_network.hosts())
        vtep_devices = [d for d in devices if "VTEP" in d["name"] or (d["type"] == "switch" and any("VTEP" in link_dev for link_dev in [l["endpoints"][0] for l in links] + [l["endpoints"][1] for l in links] if d["name"] in link_dev))]
        
        for i, dev in enumerate(vtep_devices):
            if "interfaces" not in dev:
                dev["interfaces"] = []
            dev["interfaces"].append({
                "name": "Loopback0",
                "ip": str(loopback_ips[i]),
                "mask": "255.255.255.255",
                "description": "VTEP IP for VXLAN",
                "is_loopback": True
            })
    
    # Process physical links first
    physical_links = [link for link in links if link.get("is_overlay") != True]
    for link in physical_links:
        try:
            subnet = next(subnet_gen)
        except StopIteration:
            print("Ran out of subnets for links! Not all links will be assigned IPs.")
            break
        endpoints = link["endpoints"]
        ips = list(subnet.hosts())
        if len(endpoints) != 2 or len(ips) < 2:
            continue
        for i, dev_name in enumerate(endpoints):
            dev = device_map.get(dev_name)
            if dev is not None:
                if "interfaces" not in dev:
                    dev["interfaces"] = []
                iface_name = f"GigabitEthernet0/{link_count}"
                dev["interfaces"].append({
                    "name": iface_name,
                    "ip": str(ips[i]),
                    "mask": str(subnet.netmask),
                    "link_to": endpoints[1-i]
                })
        link["subnet"] = str(subnet)
        link["ips"] = [str(ip) for ip in ips]
        link_count += 1
    
    # Now handle overlay/VXLAN links
    vxlan_links = [link for link in links if link.get("is_overlay") == True]
    for link in vxlan_links:
        link["vxlan_tunnel"] = True
        # These don't get physical interfaces, but we record the VNI
        # We'll use this later to generate the appropriate VXLAN config
        
    # If VXLAN enabled, add L2VNI and L3VNI info to the topology
    if vxlan_enabled:
        # Assign L2 VNIs for broadcast domains
        l2vni_base = 10000
        # Assign L3 VNI for L3 routing
        l3vni_base = 50000
        
        for i, dev in enumerate(vtep_devices):
            dev_vnis = []
            for link in vxlan_links:
                if dev["name"] in link["endpoints"]:
                    dev_vnis.append(link.get("vni", l2vni_base + i))
            
            if dev_vnis:
                if "vxlan_config" not in dev:
                    dev["vxlan_config"] = {}
                dev["vxlan_config"]["l2vnis"] = dev_vnis
                dev["vxlan_config"]["l3vni"] = l3vni_base
    
    return vxlan_enabled

# --- Protocol Configuration Generator ---
def generate_device_configs(devices, links, requested_protocol=None):
    """
    Generate device configurations based on the requested routing protocol.
    
    Args:
        devices: List of device dictionaries
        links: List of link dictionaries
        requested_protocol: Routing protocol to configure (OSPF, EIGRP, BGP, STATIC)
        
    Returns:
        Updated list of device dictionaries with configuration
    """
    if not requested_protocol:
        return devices  # No protocol requested, return devices unchanged
    
    # Create a map of device names to their objects for easier lookup
    device_map = {dev["name"]: dev for dev in devices}
    
    # Get connected networks for each device
    device_networks = {}
    for link in links:
        if "subnet" in link:
            subnet = link["subnet"]
            endpoints = link.get("endpoints", [])
            
            # Add this subnet to each connected device's list
            for endpoint in endpoints:
                if endpoint in device_map:
                    if endpoint not in device_networks:
                        device_networks[endpoint] = []
                    device_networks[endpoint].append(subnet)
    
    # Generate configs based on protocol
    if requested_protocol == "OSPF":
        # Use process ID 1 and area 0 for simplicity
        process_id = 1
        area = 0
        
        for dev_name, networks in device_networks.items():
            if dev_name in device_map and device_map[dev_name]["type"] == "router":
                device = device_map[dev_name]
                
                # Start with the device's existing config or create a basic one
                if "config" not in device or not device["config"]:
                    device["config"] = f"hostname {dev_name}\n"
                
                # Add OSPF configuration
                ospf_config = [f"router ospf {process_id}"]
                
                # Add network statements for each connected subnet
                for network in networks:
                    if network:
                        try:
                            # Parse the subnet to get the network address and mask
                            import ipaddress
                            subnet_obj = ipaddress.IPv4Network(network, strict=False)
                            network_addr = str(subnet_obj.network_address)
                            wildcard = str(ipaddress.IPv4Address(int(subnet_obj.hostmask)))
                            ospf_config.append(f" network {network_addr} {wildcard} area {area}")
                        except Exception as e:
                            # Fall back to simple format if parsing fails
                            ospf_config.append(f" network {network} area {area}")
                
                # Append the OSPF config to the device config
                device["config"] += "\n" + "\n".join(ospf_config)
    
    elif requested_protocol == "EIGRP":
        # Use AS 100 for simplicity
        as_number = 100
        
        for dev_name, networks in device_networks.items():
            if dev_name in device_map and device_map[dev_name]["type"] == "router":
                device = device_map[dev_name]
                
                # Start with the device's existing config or create a basic one
                if "config" not in device or not device["config"]:
                    device["config"] = f"hostname {dev_name}\n"
                
                # Add EIGRP configuration
                eigrp_config = [f"router eigrp {as_number}"]
                
                # Add network statements for each connected subnet
                for network in networks:
                    if network:
                        try:
                            # Parse the subnet to get the network address
                            import ipaddress
                            subnet_obj = ipaddress.IPv4Network(network, strict=False)
                            network_addr = str(subnet_obj.network_address)
                            eigrp_config.append(f" network {network_addr}")
                        except Exception as e:
                            # Fall back to simple format if parsing fails
                            eigrp_config.append(f" network {network}")
                
                eigrp_config.append(" no auto-summary")
                
                # Append the EIGRP config to the device config
                device["config"] += "\n" + "\n".join(eigrp_config)
    
    elif requested_protocol == "BGP":
        # Use ASN 65000 for simplicity
        asn = 65000
        
        for dev_name, networks in device_networks.items():
            if dev_name in device_map and device_map[dev_name]["type"] == "router":
                device = device_map[dev_name]
                
                # Start with the device's existing config or create a basic one
                if "config" not in device or not device["config"]:
                    device["config"] = f"hostname {dev_name}\n"
                
                # Get router ID from first interface if possible
                router_id = None
                if "interfaces" in device:
                    for iface in device["interfaces"]:
                        if "ip" in iface and iface["ip"]:
                            router_id = iface["ip"]
                            break
                
                # Add BGP configuration
                bgp_config = [f"router bgp {asn}"]
                if router_id:
                    bgp_config.append(f" bgp router-id {router_id}")
                
                # Add network statements for each connected subnet
                for network in networks:
                    if network:
                        try:
                            # Parse the subnet to get the network address and mask
                            import ipaddress
                            subnet_obj = ipaddress.IPv4Network(network, strict=False)
                            network_addr = str(subnet_obj.network_address)
                            mask = str(subnet_obj.netmask)
                            bgp_config.append(f" network {network_addr} mask {mask}")
                        except Exception as e:
                            # Fall back to simpler format if parsing fails
                            bgp_config.append(f" network {network}")
                
                # Append the BGP config to the device config
                device["config"] += "\n" + "\n".join(bgp_config)
                
    elif requested_protocol == "STATIC":
        # This is more complex and would require knowledge of the desired topology
        # For now, just add a default route to each device pointing to the first connected device
        for dev_name, networks in device_networks.items():
            if dev_name in device_map and device_map[dev_name]["type"] == "router":
                device = device_map[dev_name]
                
                # Start with the device's existing config or create a basic one
                if "config" not in device or not device["config"]:
                    device["config"] = f"hostname {dev_name}\n"
                
                # Find connected devices through links
                connected_devices = []
                for link in links:
                    endpoints = link.get("endpoints", [])
                    if dev_name in endpoints:
                        # Get the other endpoint
                        other_device = endpoints[0] if endpoints[1] == dev_name else endpoints[1]
                        connected_devices.append(other_device)
                
                # Add static routes for demonstration
                static_config = []
                if connected_devices:
                    # Get the next hop IP if possible
                    next_hop = None
                    if "interfaces" in device_map[connected_devices[0]]:
                        for iface in device_map[connected_devices[0]]["interfaces"]:
                            if "ip" in iface and iface["ip"]:
                                next_hop = iface["ip"]
                                break
                    
                    if next_hop:
                        static_config.append(f"ip route 0.0.0.0 0.0.0.0 {next_hop}")
                
                # Append the static config to the device config
                if static_config:
                    device["config"] += "\n" + "\n".join(static_config)
    
    return devices

# --- Logo helper for base64 encoding ---
import base64
from io import BytesIO

def logo_to_base64(img):
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode()

load_dotenv()

# --- Helper functions for topology generation ---
def create_vxlan_multisite_topology(num_sites, internet_connected=True):
    """
    Creates a VXLAN multi-site topology with a main datacenter and remote sites.
    - num_sites: Total number of sites (including main DC)
    - internet_connected: If True, sites are connected via "internet" links, otherwise direct links
    """
    devices = []
    links = []
    
    # Create main datacenter (site 0)
    dc_router = {"name": "DC_Border_Router", "type": "router"}
    dc_spine1 = {"name": "DC_Spine1", "type": "switch"}
    dc_spine2 = {"name": "DC_Spine2", "type": "switch"}
    dc_leaf1 = {"name": "DC_Leaf1_VTEP", "type": "switch"}
    dc_leaf2 = {"name": "DC_Leaf2_VTEP", "type": "switch"}
    dc_server1 = {"name": "DC_Server1", "type": "server"}
    dc_server2 = {"name": "DC_Server2", "type": "server"}
    
    devices.extend([dc_router, dc_spine1, dc_spine2, dc_leaf1, dc_leaf2, dc_server1, dc_server2])
    
    # Connect DC devices
    links.append({"endpoints": [dc_router["name"], dc_spine1["name"]], "link_type": "ethernet"})
    links.append({"endpoints": [dc_router["name"], dc_spine2["name"]], "link_type": "ethernet"})
    links.append({"endpoints": [dc_spine1["name"], dc_leaf1["name"]], "link_type": "ethernet"})
    links.append({"endpoints": [dc_spine1["name"], dc_leaf2["name"]], "link_type": "ethernet"})
    links.append({"endpoints": [dc_spine2["name"], dc_leaf1["name"]], "link_type": "ethernet"})
    links.append({"endpoints": [dc_spine2["name"], dc_leaf2["name"]], "link_type": "ethernet"})
    links.append({"endpoints": [dc_leaf1["name"], dc_server1["name"]], "link_type": "ethernet"})
    links.append({"endpoints": [dc_leaf2["name"], dc_server2["name"]], "link_type": "ethernet"})
    
    # Create branch sites
    for i in range(1, num_sites):
        site_name = f"Site{i}"
        site_router = {"name": f"{site_name}_Router", "type": "router"}
        site_switch = {"name": f"{site_name}_Switch_VTEP", "type": "switch"}
        site_server = {"name": f"{site_name}_Server", "type": "server"}
        
        devices.extend([site_router, site_switch, site_server])
        
        # Connect site components
        links.append({"endpoints": [site_router["name"], site_switch["name"]], "link_type": "ethernet"})
        links.append({"endpoints": [site_switch["name"], site_server["name"]], "link_type": "ethernet"})
        
        # Connect to DC Router (WAN/Internet links)
        link_type = "internet" if internet_connected else "ethernet"
        links.append({"endpoints": [dc_router["name"], site_router["name"]], "link_type": link_type})
        
        # Add logical VXLAN overlay links (these won't be actual interfaces but represent the overlay)
        # In a real network, these would be VXLAN tunnels over the internet/WAN
        links.append({
            "endpoints": [dc_leaf1["name"], site_switch["name"]], 
            "link_type": "vxlan", 
            "vni": 10000 + i,
            "is_overlay": True
        })
    
    # Add EVPN/BGP protocol for VXLAN control plane
    return {
        "devices": devices, 
        "links": links,
        "vxlan_enabled": True,
        "evpn_enabled": True,
        "protocol": "BGP"
    }

# --- Helper: Safe CMLManager lazy loader with error handling ---
def get_cml_manager():
    try:
        from CMLConnector import CMLManager
        if st.session_state.get("design_mode", False):
            raise Exception("Design mode enabled – CML connection skipped.")
        return CMLManager()
    except Exception as e:
        if "Design mode enabled" not in str(e):
            st.warning(f"⚠️ Could not connect to CML server: {e}")
        return None

# CML node interface limits and preferred node definitions
CML_NODE_INTERFACE_LIMITS = {
    "iosv": 4,
    "csr1000v": 10,
    "iosvl2": 8,
    "nxosv9000": 32,
    "asav": 10,
    "ubuntu": 4,
    "ext-server": 4,
    "alpine": 4,
    "win10-desktop": 4,
}

# Preferred node definition selection logic
PREFERRED_ROUTER = [
    (4, "iosv"),
    (10, "csr1000v"),
]
PREFERRED_SWITCH = [
    (8, "iosvl2"),
    (32, "nxosv9000"),
]
PREFERRED_SERVER = [
    (4, "ubuntu"),
]

# Helper to select node definition based on type and interface count
def select_node_definition(dev_type, iface_count):
    if dev_type == "router":
        for max_if, node_def in PREFERRED_ROUTER:
            if iface_count <= max_if:
                return node_def, CML_NODE_INTERFACE_LIMITS[node_def]
        return "csr1000v", CML_NODE_INTERFACE_LIMITS["csr1000v"]
    elif dev_type == "switch":
        for max_if, node_def in PREFERRED_SWITCH:
            if iface_count <= max_if:
                return node_def, CML_NODE_INTERFACE_LIMITS[node_def]
        return "nxosv9000", CML_NODE_INTERFACE_LIMITS["nxosv9000"]
    elif dev_type in ["server", "ext-server", "alpine", "win10-desktop"]:
        return "ubuntu", CML_NODE_INTERFACE_LIMITS["ubuntu"]
    elif dev_type == "firewall":
        return "asav", CML_NODE_INTERFACE_LIMITS["asav"]
    else:
        return dev_type, 4  # Default fallback

def edit_devices_ui(devices, node_definitions, valid_types, context_prefix="chat"): 
    import re
    editable_devices = []
    # Build link map for interface counting
    link_map = {}
    for dev in devices:
        link_map[dev["name"]] = 0
    # Count links per device
    for dev in devices:
        dev_name = dev["name"]
        for other_dev in devices:
            if "links" in dev and other_dev["name"] in dev["links"]:
                link_map[dev_name] += 1
    # Or, more robustly, count from global links if available
    global_links = st.session_state.get('last_mcp_model', {}).get('network_design', {}).get('links', [])
    for link in global_links:
        for endpoint in link.get("endpoints", []):
            if endpoint in link_map:
                link_map[endpoint] += 1
    # Build a reverse link map for interface descriptions, including remote interface names
    endpoint_links = {}
    endpoint_iface_map = {}
    for link in global_links:
        endpoints = link.get("endpoints", [])
        if len(endpoints) == 2:
            dev_a, dev_b = endpoints
            # Map device to its connected device and link index
            if dev_a not in endpoint_links:
                endpoint_links[dev_a] = []
            if dev_b not in endpoint_links:
                endpoint_links[dev_b] = []
            endpoint_links[dev_a].append(dev_b)
            endpoint_links[dev_b].append(dev_a)
            # Store link index for interface mapping
            if dev_a not in endpoint_iface_map:
                endpoint_iface_map[dev_a] = {}
            if dev_b not in endpoint_iface_map:
                endpoint_iface_map[dev_b] = {}
            # Assume interface index matches order of links for now
            idx_a = endpoint_links[dev_a].index(dev_b)
            idx_b = endpoint_links[dev_b].index(dev_a)
            endpoint_iface_map[dev_a][dev_b] = idx_a
            endpoint_iface_map[dev_b][dev_a] = idx_b

    # Determine which protocols were requested in the parsed model
    requested_protocol = None
    if 'last_mcp_model' in st.session_state and st.session_state['last_mcp_model']:
        requested_protocol = st.session_state['last_mcp_model']['network_design'].get('protocol', None)
        if isinstance(requested_protocol, str):
            requested_protocol = requested_protocol.upper()

    for idx, device in enumerate(devices):
        dev_type = device.get("type", "router")
        iface_count = link_map.get(device["name"], 1)
        node_def, max_ifaces = select_node_definition(dev_type, iface_count)
        # UI warning if interface count exceeds any supported node definition
        if dev_type == "router" and iface_count > max_ifaces:
            st.warning(f"Device {device['name']} requires {iface_count} interfaces, but the max supported for routers is {max_ifaces} (CSR1000v). Reduce links or split the device.")
        if dev_type == "switch" and iface_count > max_ifaces:
            st.warning(f"Device {device['name']} requires {iface_count} interfaces, but the max supported for switches is {max_ifaces} (NXOSv9000). Reduce links or split the device.")
        if dev_type in ["server", "ext-server", "alpine", "win10-desktop"] and iface_count > max_ifaces:
            st.warning(f"Device {device['name']} requires {iface_count} interfaces, but the max supported for servers is {max_ifaces}. Reduce links or split the device.")
        # Set node definition and limit interface count
        device["node_definition"] = node_def
        with st.expander(f"🔧 Device {idx+1}: {device.get('name', 'Unnamed')}", expanded=True):
            name = st.text_input(f"Hostname for Device {idx+1}", value=device.get("name", f"Device{idx+1}"), key=f"{context_prefix}_name_{idx}")
            dev_type = st.selectbox(
                f"Device Type",
                valid_types,
                index=valid_types.index(device.get("type", "router")),
                help="Hover to see supported interface options per image.",
                key=f"{context_prefix}_type_{idx}"
            )
            st.caption(f"💡 Max interfaces for {node_def}: {max_ifaces}")
            interface_count = min(iface_count, max_ifaces)
            interface_configs = []
            existing_ifaces = device.get("interfaces", [])
            # Get connected devices for this node
            connected_devices = endpoint_links.get(device["name"], [])
            for i in range(interface_count):
                iface_prefix = "eth" if dev_type in ["server", "ext-server", "alpine", "win10-desktop"] else "GigabitEthernet0"
                iface = f"{iface_prefix}/{i}" if "GigabitEthernet" in iface_prefix else f"{iface_prefix}{i}"
                ip = st.text_input(f"IP for {iface}", value=existing_ifaces[i]["ip"] if i < len(existing_ifaces) else f"192.168.{idx}.{i+1}", key=f"{context_prefix}_iface_{idx}_{i}")
                # Enhanced auto-desc: include remote device and remote interface name if possible
                auto_desc = ""
                if i < len(connected_devices):
                    remote_dev = connected_devices[i]
                    remote_iface_idx = endpoint_iface_map.get(remote_dev, {}).get(device["name"], None)
                    if remote_iface_idx is not None:
                        remote_iface_prefix = "eth" if dev_type in ["server", "ext-server", "alpine", "win10-desktop"] else "GigabitEthernet0"
                        remote_iface = f"{remote_iface_prefix}/{remote_iface_idx}" if "GigabitEthernet" in remote_iface_prefix else f"{remote_iface_prefix}{remote_iface_idx}"
                        auto_desc = f"Connection to {remote_dev} ({remote_iface})"
                    else:
                        auto_desc = f"Connection to {remote_dev}"
                iface_desc = st.text_input(f"Description for {iface}", value=existing_ifaces[i]["desc"] if i < len(existing_ifaces) and "desc" in existing_ifaces[i] else auto_desc, key=f"{context_prefix}_desc_{idx}_{i}")
                interface_configs.append((iface, ip, None, iface_desc))
            raw_config = device.get("config", "")
            has_ospf_config = "router ospf" in raw_config
            has_eigrp_config = "router eigrp" in raw_config
            has_bgp_config = "router bgp" in raw_config
            ospf_config = {}
            eigrp_config = {}
            bgp_config = {}
            # --- Protocol auto-enable logic ---
            auto_enable_ospf = (requested_protocol == "OSPF" and device.get("type") == "router")
            auto_enable_eigrp = (requested_protocol == "EIGRP" and device.get("type") == "router")
            auto_enable_bgp = (requested_protocol == "BGP" and device.get("type") == "router")
            auto_enable_static = (requested_protocol == "STATIC" and device.get("type") == "router")
            enable_ospf = st.checkbox(f"Enable OSPF on {name}?", value=has_ospf_config or auto_enable_ospf, key=f"{context_prefix}_ospf_{idx}")
            enable_eigrp = st.checkbox(f"Enable EIGRP on {name}?", value=has_eigrp_config or auto_enable_eigrp, key=f"{context_prefix}_eigrp_{idx}")
            enable_bgp = st.checkbox(f"Enable BGP on {name}?", value=has_bgp_config or auto_enable_bgp, key=f"{context_prefix}_bgp_{idx}")
            enable_static = st.checkbox(f"Add Static Routes to {name}?", value=auto_enable_static, key=f"{context_prefix}_static_{idx}")
            static_config = []
            if enable_ospf:
                ospf_process_id = st.text_input(
                    f"OSPF Process ID for {name}",
                    value=ospf_config.get("process_id", "1"),
                    key=f"{context_prefix}_ospf_pid_{idx}"
                )
                ospf_networks = st.text_area(
                    f"OSPF Networks (one per line, CIDR format)",
                    value="\n".join(ospf_config.get("networks", ["10.0.0.0/24"])),
                    key=f"{context_prefix}_ospf_nets_{idx}"
                )
                ospf_area = st.text_input(
                    f"OSPF Area",
                    value=ospf_config.get("area", "0"),
                    key=f"{context_prefix}_ospf_area_{idx}"
                )
                ospf_config = {
                    "process_id": ospf_process_id,
                    "networks": ospf_networks.splitlines(),
                    "area": ospf_area
                }
            if enable_eigrp:
                eigrp_as = st.text_input(
                    f"EIGRP Autonomous System Number for {name}",
                    value=eigrp_config.get("as_number", "100"),
                    key=f"{context_prefix}_eigrp_as_{idx}"
                )
                eigrp_networks = st.text_area(
                    f"EIGRP Networks (one per line, CIDR format)",
                    value="\n".join(eigrp_config.get("networks", ["10.0.0.0/24"])),
                    key=f"{context_prefix}_eigrp_nets_{idx}"
                )
                eigrp_config = {
                    "as_number": eigrp_as,
                    "networks": eigrp_networks.splitlines()
                }
            if enable_bgp:
                bgp_asn = st.text_input(
                    f"BGP Autonomous System Number",
                    value=bgp_config.get("asn", "65001"),
                    key=f"{context_prefix}_bgp_asn_{idx}"
                )
                bgp_neighbors = st.text_area(
                    f"BGP Neighbors (one IP per line)",
                    value="\n".join(bgp_config.get("neighbors", ["192.0.2.2"])),
                    key=f"{context_prefix}_bgp_neighbors_{idx}"
                )
                bgp_networks = st.text_area(
                    f"BGP Networks to Advertise (one CIDR per line)",
                    value="\n".join(bgp_config.get("networks", ["192.168.0.0/24"])),
                    key=f"{context_prefix}_bgp_nets_{idx}"
                )
                bgp_config = {
                    "asn": bgp_asn,
                    "neighbors": bgp_neighbors.splitlines(),
                    "networks": bgp_networks.splitlines()
                }
            if enable_static:
                static_entries = st.text_area(f"Static Routes (format: destination subnet mask next-hop IP)", value="10.0.0.0 255.255.255.0 192.168.1.1", key=f"{context_prefix}_static_entries_{idx}")
                for line in static_entries.strip().splitlines():
                    parts = line.strip().split()
                    if len(parts) == 3:
                        static_config.append(parts)
            updated_device = device.copy()
            updated_device["name"] = name
            updated_device["type"] = dev_type
            updated_device["node_definition"] = node_def
            default_configs = {
                "router": "hostname {hostname}\n",
                "switch": "hostname {hostname}\nspanning-tree mode rapid-pvst\n",
                "firewall": "hostname {hostname}\n",
                "server": "#cloud-config\nhostname: {hostname}\n",
                "ext-server": "#cloud-config\nhostname: {hostname}\n"
            }
            base_config = default_configs.get(dev_type, "hostname {hostname}\n")
            config_lines = [base_config.format(hostname=name).strip()]
            for iface, ip, vlan, desc in interface_configs:
                config_lines.append(f"interface {iface}")
                if desc:
                    config_lines.append(f" description {desc}")
                if vlan:
                    config_lines.append(f" encapsulation dot1Q {vlan}")
                config_lines.append(f" ip address {ip} 255.255.255.0")
                config_lines.append(" no shutdown")
            if ospf_config:
                config_lines.append(f"router ospf {ospf_config['process_id']}")
                for network in ospf_config["networks"]:
                    if "/" in network:
                        ip, mask_length = network.split("/")
                        mask = {
                            "8": "255.0.0.0",
                            "16": "255.255.0.0",
                            "24": "255.255.255.0",
                            "30": "255.255.255.252"
                        }.get(mask_length, "255.255.255.0")
                        config_lines.append(f" network {ip} {mask} area {ospf_config['area']}")
            if eigrp_config:
                config_lines.append(f"router eigrp {eigrp_config['as_number']}")
                for network in eigrp_config["networks"]:
                    if "/" in network:
                        ip, _ = network.split("/")
                        config_lines.append(f" network {ip}")
                config_lines.append(" no auto-summary")
            if bgp_config:
                config_lines.append(f"router bgp {bgp_config['asn']}")
                for neighbor in bgp_config["neighbors"]:
                    config_lines.append(f" neighbor {neighbor} remote-as {bgp_config['asn']}")
                for network in bgp_config["networks"]:
                    if "/" in network:
                        ip, mask_length = network.split("/")
                        mask = {
                            "8": "255.0.0.0",
                            "16": "255.255.0.0",
                            "24": "255.255.255.0",
                            "30": "255.255.255.252"
                        }.get(mask_length, "255.255.255.0")
                        config_lines.append(f" network {ip} mask {mask}")
            for static_entry in static_config:
                dest, mask, next_hop = static_entry
                config_lines.append(f"ip route {dest} {mask} {next_hop}")
                
            # Add VXLAN configuration if necessary
            if "VTEP" in name or "vxlan_config" in updated_device:
                vxlan_config = updated_device.get("vxlan_config", {})
                l2vnis = vxlan_config.get("l2vnis", [])
                l3vni = vxlan_config.get("l3vni", 50000)
                
                # Configure VXLAN features
                config_lines.append("nv overlay evpn")
                config_lines.append("feature vn-segment-vlan-based")
                config_lines.append("feature nv overlay")
                config_lines.append("feature bgp")
                config_lines.append("feature interface-vlan")
                
                # Configure VLANs for VNIs
                for i, vni in enumerate(l2vnis):
                    vlan_id = 100 + i
                    config_lines.append(f"vlan {vlan_id}")
                    config_lines.append(f" name VXLAN-{vni}")
                    config_lines.append(f" vn-segment {vni}")
                
                # Configure BGP for EVPN
                loopback_ips = [iface for iface in updated_device.get("interfaces", []) if iface.get("is_loopback")]
                if loopback_ips:
                    vtep_ip = loopback_ips[0]["ip"]
                    config_lines.append(f"router bgp 65000")
                    config_lines.append(" router-id " + vtep_ip)
                    config_lines.append(" neighbor 192.168.100.1 remote-as 65000")
                    config_lines.append(" address-family l2vpn evpn")
                    config_lines.append("  send-community both")
                
                # Configure NVE interface
                config_lines.append("interface nve1")
                config_lines.append(" no shutdown")
                config_lines.append(" source-interface loopback0")
                for vni in l2vnis:
                    config_lines.append(f" member vni {vni}")
                    config_lines.append("  ingress-replication protocol bgp")
                
            updated_device["config"] = "\n".join(config_lines)
            editable_devices.append(updated_device)
    return editable_devices

# Initialize chat history if not already in session state
if 'chat_history' not in st.session_state:
    st.session_state['chat_history'] = []
if 'last_mcp_model' not in st.session_state:
    st.session_state['last_mcp_model'] = None

if 'lab_name' not in st.session_state:
    st.session_state['lab_name'] = "AutoGeneratedLab"  # Set default lab name

def show_flowchart_diagram():
    with st.expander("📈 MCP ➔ CML Deployment Flowchart", expanded=False):
        flowchart_html = """
<style>
.flowchart-container {
    display: flex;
    flex-direction: column;
    align-items: center;
    font-family: Arial, sans-serif;
    margin: 20px 0;
    line-height: 1.4;
}
.flowchart-row {
    display: flex;
    justify-content: center;
    width: 100%;
    margin-bottom: 15px;
}
.flowchart-step {
    border: 2px solid #4a90e2;
    border-radius: 8px;
    padding: 12px 16px;
    margin: 0 15px;
    width: 220px;
    text-align: center;
    font-size: 14px;
    position: relative;
}
.flowchart-connector {
    position: relative;
    font-size: 20px;
    padding: 5px;
    color: #555;
}
.flowchart-branch {
    display: flex;
    flex-direction: column;
    align-items: center;
    margin: 0 10px;
}
.flowchart-branch-label {
    font-size: 12px;
    margin-bottom: 5px;
    font-weight: bold;
    color: #555;
}
.phase-input { background-color: #e3f2fd; }
.phase-template { background-color: #f3e5f5; }
.phase-chat { background-color: #fff8e1; }
.phase-common { background-color: #e8f5e9; }
.phase-config { background-color: #f5f5f5; }
.phase-deploy { background-color: #fff3e0; }
.phase-run { background-color: #ede7f6; }
.double-arrow::after {
    content: "⇓";
    position: absolute;
    left: 50%;
    bottom: -25px;
    transform: translateX(-50%);
    font-size: 20px;
}
.arrow-right::after {
    content: "→";
    position: absolute;
    right: -20px;
    top: 50%;
    transform: translateY(-50%);
    font-size: 20px;
}
.arrow-left::after {
    content: "←";
    position: absolute;
    left: -20px;
    top: 50%;
    transform: translateY(-50%);
    font-size: 20px;
}
.arrow-down::after {
    content: "↓";
    position: absolute;
    left: 50%;
    bottom: -25px;
    transform: translateX(-50%);
    font-size: 20px;
}
.success-box {
    border-color: #4CAF50;
    border-width: 3px;
}
.warning-box {
    border-color: #FFC107;
    border-width: 2px;
}
.error-box {
    border-color: #F44336;
    border-width: 2px;
}
</style>
<div class="flowchart-container">
    <!-- Initial Input Row -->
    <div class="flowchart-row">
        <div class="flowchart-step phase-input">
            User Input
        </div>
    </div>
    
    <!-- Branch Decision Row -->
    <div class="flowchart-row">
        <div class="flowchart-connector">⇓</div>
    </div>
    
    <!-- Two Path Options -->
    <div class="flowchart-row">
        <div class="flowchart-branch">
            <div class="flowchart-branch-label">Template Path</div>
            <div class="flowchart-step phase-template">
                Select Predefined Template
            </div>
        </div>
        <div class="flowchart-branch">
            <div class="flowchart-branch-label">Chat Path</div>
            <div class="flowchart-step phase-chat">
                Natural Language Description
            </div>
        </div>
    </div>
    
    <!-- Template vs Chat Processing -->
    <div class="flowchart-row">
        <div class="flowchart-branch">
            <div class="flowchart-connector">⇓</div>
            <div class="flowchart-step phase-template">
                Load Template Structure
            </div>
        </div>
        <div class="flowchart-branch">
            <div class="flowchart-connector">⇓</div>
            <div class="flowchart-step phase-chat">
                LLM Topology Parser
            </div>
        </div>
    </div>
    
    <!-- Detection & Fallback Row -->
    <div class="flowchart-row">
        <div class="flowchart-branch">
            <div class="flowchart-connector">⇓</div>
            <div class="flowchart-step phase-common success-box">
                Ready-to-Use MCP Model
            </div>
        </div>
        <div class="flowchart-branch">
            <div class="flowchart-connector">⇓</div>
            <div class="flowchart-step phase-chat warning-box">
                Parser Success?
            </div>
        </div>
    </div>
    
    <!-- Fallback Decision & IP Assignment -->
    <div class="flowchart-row">
        <div class="flowchart-branch">
            <div class="flowchart-connector">⇓</div>
            <div class="flowchart-step phase-common">
                IP Address Assignment
            </div>
        </div>
        <div class="flowchart-branch">
            <div class="flowchart-row">
                <div class="flowchart-branch">
                    <div class="flowchart-connector" style="transform: translateX(-50px);">←</div>
                    <div class="flowchart-step phase-chat error-box" style="margin-bottom: 15px;">
                        No - Use Pattern Detection
                    </div>
                    <div class="flowchart-connector">⇓</div>
                    <div class="flowchart-step phase-template">
                        Generate Template Topology
                    </div>
                </div>
                <div class="flowchart-branch">
                    <div class="flowchart-connector" style="transform: translateX(50px);">→</div>
                    <div class="flowchart-step phase-chat success-box">
                        Yes - Use Parser Output
                    </div>
                </div>
            </div>
        </div>
    </div>
    
    <!-- Protocol Configuration -->
    <div class="flowchart-row">
        <div class="flowchart-connector">⇓</div>
    </div>
    <div class="flowchart-row">
        <div class="flowchart-step phase-config" style="width: 300px;">
            Protocol Configuration (OSPF, EIGRP, BGP)
        </div>
    </div>
    
    <!-- Interactive Editing Flow -->
    <div class="flowchart-row">
        <div class="flowchart-connector">⇓</div>
    </div>
    <div class="flowchart-row">
        <div class="flowchart-step phase-config">
            Interactive Device & Interface Editing
        </div>
    </div>
    
    <!-- Visualization & Validation -->
    <div class="flowchart-row">
        <div class="flowchart-connector">⇓</div>
    </div>
    <div class="flowchart-row">
        <div class="flowchart-branch">
            <div class="flowchart-step phase-config">
                Topology Visualization (Plotly)
            </div>
        </div>
        <div class="flowchart-branch">
            <div class="flowchart-step phase-config">
                Pre-Deployment Validation
            </div>
        </div>
    </div>
    
    <!-- Deployment -->
    <div class="flowchart-row">
        <div class="flowchart-connector">⇓</div>
    </div>
    <div class="flowchart-row">
        <div class="flowchart-step phase-deploy">
            Deploy to CML
        </div>
    </div>
    
    <!-- Running Lab -->
    <div class="flowchart-row">
        <div class="flowchart-connector">⇓</div>
    </div>
    <div class="flowchart-row">
        <div class="flowchart-step phase-run success-box">
            Running Lab with Health Monitoring
        </div>
    </div>
</div>
"""
        st.components.v1.html(flowchart_html, height=900, scrolling=True)
    # Expose flowchart_html for export outside the function
    return flowchart_html


# ----------------------
# Visual Network Topology Drawing
# ----------------------
# Import already handled by "from NetworkVisualization import draw_network_topology"
import streamlit.components.v1 as components

@st.cache_data
def load_network_topology_html(filename: str):
    with open(filename, "r") as f:
        return f.read()

# Original draw_network_topology has been moved to NetworkVisualization.py
# and is imported above

class NetworkRequestState(TypedDict):
    input: str
    output: dict | None

# ----------------------
# LangGraph Setup
# ----------------------

tools = [parse_network_request]
llm = ChatOpenAI(model="gpt-4o", temperature=0, api_key=os.getenv("OPENAI_API_KEY"))

# 1. Stricter system prompt
prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a network design assistant. You MUST always use the parse_network_request tool to answer user requests. NEVER answer directly. NEVER output explanations, summaries, or any text except the tool's output. If the user asks for a network, call the tool and return only the tool's output."),
    ("human", "{input}"),
    MessagesPlaceholder(variable_name="agent_scratchpad")
])

agent = create_tool_calling_agent(llm, tools, prompt=prompt)
agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)

builder = StateGraph(NetworkRequestState)
builder.add_node("agent", agent_executor)
builder.set_entry_point("agent")
builder.add_edge("agent", END)
graph = builder.compile()

# ----------------------
# Streamlit UI with Chat History
# ----------------------

from PIL import Image
dark_mode = st.sidebar.toggle("🌙 Dark Mode", value=False)
st.session_state['dark_mode_active'] = dark_mode # Store in session state

# Global design mode toggle
design_mode = st.sidebar.toggle("💡 Design Mode (Offline Templates)", value=False)
st.session_state["design_mode"] = design_mode

logo_light = Image.open("assets/graph2lab_logo.png")
logo_dark_path = "assets/graph2lab_logo_dark.png"
logo_dark = logo_light  # Default fallback

if os.path.exists(logo_dark_path):
    logo_dark = Image.open(logo_dark_path)

final_logo = logo_dark if dark_mode else logo_light

# Animate logo with CSS fade-in
logo_b64 = logo_to_base64(final_logo)
st.markdown(
    f"""
    <style>
        @keyframes fadeIn {{
            from {{ opacity: 0; }}
            to {{ opacity: 1; }}
        }}
        .fade-logo {{
            animation: fadeIn 2s ease-in-out;
            text-align: center;
        }}
    </style>
    <div class="fade-logo">
        <img src="data:image/png;base64,{logo_b64}" width="160"/>
    </div>
    """,
    unsafe_allow_html=True
)
st.title("🧠🧪 Graph2Lab: AI-Powered Network Lab Builder")

# --- Insert Project Version/Phase info above Capabilities Overview ---

version_style = f"""
    <div style="padding: 10px; border-radius: 8px; background-color: {'#2c2f33' if dark_mode else '#e0e0e0'}; color: {'#ffffff' if dark_mode else '#000000'}; font-size: 14px; text-align: center; margin-bottom: 10px;">
        <strong>🛠 Project Version:</strong> 3.0<br>
        <strong>🚦 Phase:</strong> Network Validation & Health Checks
    </div>
    <div style="font-size: 12px; margin-top: 4px; margin-bottom: 10px;">
        <strong>📋 Changelog:</strong>
        <ul style="text-align: left; margin: 4px 20px;">
            <li>Added built-in network validation tools (duplicate IPs, device names, VLAN, routing, protocol config)</li>
            <li>Added lab health check tab (lab state, node status, pre/post-deployment validation)</li>
            <li>UI: New "Validation & Health" tab for real-time feedback</li>
            <li>Foundation for automated connectivity tests (ping, traceroute, BGP neighbor checks)</li>
            <li>Roadmap for advanced validation, automated testing, and simulation features</li>
        </ul>
    </div>
"""
st.markdown(version_style, unsafe_allow_html=True)

# --- Insert Release Notes block immediately below version/changelog ---
release_notes = f"""
<div style="padding: 10px; border-radius: 8px; background-color: {'#2c2f33' if dark_mode else '#e0e0e0'}; color: {'#ffffff' if dark_mode else '#000000'}; font-size: 13px; margin-top: 10px;">
    <strong>📦 Release Notes:</strong>
    <ul style="text-align: left; margin: 4px 20px;">
        <li>Initial implementation of network validation and health check tools</li>
        <li>Pre-deployment validation for common config issues (IP, VLAN, routing, protocols)</li>
        <li>Post-deployment health checks for lab and node status</li>
        <li>All validation and health results shown in a dedicated UI tab</li>
        <li><strong>Phase 3.0 Roadmap:</strong>
            <ul>
                <li>Automated connectivity and protocol tests (ping, traceroute, BGP neighbor checks)</li>
                <li>Advanced topology and protocol validation</li>
                <li>Traffic generation and simulation tools</li>
                <li>Lab scheduling, snapshots, and resource monitoring</li>
                <li>Enhanced documentation and learning tools</li>
                <li>Collaboration and sharing features</li>
            </ul>
        </li>
    </ul>
</div>
"""
st.markdown(release_notes, unsafe_allow_html=True)

# --- Capabilities Overview Section ---
st.markdown("""
### 🔍 Capabilities Overview

Graph2Lab helps you **build, validate, customize, and deploy** network labs using AI-generated topologies.

- 🧠 **Natural Language Input**: Describe your desired network and let the AI generate the topology.
- 🛠 **Interactive Editing**: Customize interface configs, IP addresses, and protocol settings.
- 🧪 **Validation & Health Checks**: Instantly check for duplicate IPs, config errors, and lab health before and after deployment.
- 🛰 **Protocol Support**: Configure Static, OSPF, EIGRP, and BGP protocols with interface-level control.
- 💡 **Design Mode**: Offline mode lets you work with templates without needing CML access.
- 📈 **Visual Tools**: Network topology viewer, flowchart diagrams, and summary tables.
- 🚀 **One-Click Deployment**: Deploy your custom lab to Cisco Modeling Labs or queue it for later.
""")

# Show the flowchart and get the HTML for export
flowchart_html = show_flowchart_diagram()


# ----------------------
# Prebuilt Topology Templates
# ----------------------
with st.sidebar.expander("📚 Templates", expanded=True):
    # Load built-in templates
    templates = {
        "Hub and Spoke (3 Routers) (STATIC)": {
            "network_design": {
                "devices": [
                    {
                        "name": "HubRouter",
                        "type": "router",
                        "node_definition": "iosv",
                        "config": "hostname HubRouter\ninterface GigabitEthernet0/0\n ip address 10.1.1.1 255.255.255.252\n no shutdown\ninterface GigabitEthernet0/1\n ip address 10.1.2.1 255.255.255.252\n no shutdown"
                    },
                    {
                        "name": "Spoke1",
                        "type": "router",
                        "node_definition": "iosv",
                        "config": "hostname Spoke1\ninterface GigabitEthernet0/0\n ip address 10.1.1.2 255.255.255.252\n no shutdown"
                    },
                    {
                        "name": "Spoke2",
                        "type": "router",
                        "node_definition": "iosv",
                        "config": "hostname Spoke2\ninterface GigabitEthernet0/0\n ip address 10.1.2.2 255.255.255.252\n no shutdown"
                    }
                ],
                "links": [
                    {"endpoints": ["HubRouter", "Spoke1"], "link_type": "serial"},
                    {"endpoints": ["HubRouter", "Spoke2"], "link_type": "serial"}
                ]
            }
        },
        # ... (keep other built-in templates) ...
    }

    # Load custom templates from the custom_templates directory
    custom_templates_dir = "custom_templates"
    if os.path.exists(custom_templates_dir):
        for template_file in os.listdir(custom_templates_dir):
            if template_file.endswith(".json"):
                try:
                    with open(os.path.join(custom_templates_dir, template_file), "r") as f:
                        template_name = os.path.splitext(template_file)[0]
                        templates[template_name] = json.load(f)
                except Exception as e:
                    st.sidebar.error(f"Error loading template {template_file}: {e}")

    template_choice = st.selectbox("Select a Template", ["Select..."] + list(templates.keys()))

if template_choice != "Select...":
    selected_template = templates[template_choice]

    # --- Quick Summary Panel Below Template Selector ---
    summary = selected_template.get("network_design", {})
    devices = summary.get("devices", [])
    links = summary.get("links", [])
    device_types = [dev.get("type", "unknown") for dev in devices]
    protocols = set()
    for dev in devices:
        config = dev.get("config", "")
        if "ospf" in config: protocols.add("OSPF")
        if "eigrp" in config: protocols.add("EIGRP")
        if "bgp" in config: protocols.add("BGP")

    st.sidebar.markdown("### 🧾 Template Summary")
    st.sidebar.markdown(f"**Devices:** {len(devices)}")
    for dev_type in set(device_types):
        st.sidebar.markdown(f"- {dev_type.title()}: {device_types.count(dev_type)}")
    st.sidebar.markdown(f"**Links:** {len(links)}")
    st.sidebar.markdown(f"**Protocols:** {', '.join(protocols) if protocols else 'None detected'}")

    tab1, tab2, tab3, tab4 = st.tabs(["🖼 Topology Viewer", "🛠 Customize Devices", "📋 Deployment Summary", "🔍 Validation & Health"])

    with tab1:
        st.session_state['last_mcp_model'] = selected_template
        st.success(f"✅ Template `{template_choice}` loaded into session. You can now deploy it!")
        
        # Remove the visualization selector radio button
        # viz_option = st.radio(...)
        
        with st.spinner("Rendering network diagram..."):
            # Always call Plotly version, passing dark_mode
            draw_network_topology_plotly(selected_template, dark_mode=st.session_state.get('dark_mode_active', False))
            
        # --- Show device interface/IP table ---
        st.markdown("### Device Interface Details")
        for dev in devices:
            st.markdown(f"**{dev['name']} ({dev['type']})**")
            if "interfaces" in dev and dev["interfaces"]:
                st.table([
                    {
                        "Interface": iface["name"],
                        "IP Address": iface["ip"],
                        "Mask": iface["mask"],
                        "Connected To": iface.get("link_to", "-")
                    }
                    for iface in dev["interfaces"]
                ])
            else:
                st.info("No interfaces assigned.")
        # --- Export YAML button (always available if topology is loaded) ---
        if devices:
            st.markdown("#### Export All Device Configs (YAML)")
            yaml_export = {}
            for dev in devices:
                yaml_export[dev["name"]] = {
                    "type": dev["type"],
                    "interfaces": dev.get("interfaces", [])
                }
            yaml_str = yaml.dump(yaml_export, sort_keys=False)
            st.download_button(
                label="📥 Download YAML Configs",
                data=yaml_str,
                file_name="device_configs.yaml",
                mime="text/yaml"
            )

    with tab2:
        st.subheader("🛠️ Customize Device Configurations Before Deployment")
        mcp_model = st.session_state.get('last_mcp_model', None)
        if mcp_model is not None:
            devices = mcp_model["network_design"].get("devices", [])
            if devices:
                available_defs = {
                    "router": "iosv",
                    "switch": "iosvl2",
                    "firewall": "asav",
                    "server": "ubuntu",
                    "ext-server": "ext-server",
                    "csr": "csr1000v",
                    "nxos": "nxosv9000",
                    "win10": "win10-desktop",
                    "alpine": "alpine"
                }
                valid_types = list(available_defs.keys())
                node_definitions = available_defs
                edited_devices = edit_devices_ui(devices, node_definitions, valid_types, context_prefix="chat")
                if st.button("💾 Apply Edits to Devices (Chat)"):
                    mcp_model["network_design"]["devices"] = edited_devices
                    st.success("✅ Updated device configurations applied.")
                    # Use Plotly for visualization, passing dark_mode
                    draw_network_topology_plotly(mcp_model, dark_mode=st.session_state.get('dark_mode_active', False))
                if st.button("🔄 Reset Device Edits (Chat)"):
                    st.rerun()
            else:
                st.info("No devices to customize. Generate a topology first.")
        else:
            st.info("No topology loaded. Generate a topology first.")

    with tab3:
        st.markdown("### 📋 Full Deployment Summary")

        import re
        if edited_devices:
            summary_data = []
            def format_protocol_badges(protocol_list):
                badge_map = {
                    "OSPF": "🟢 OSPF",
                    "EIGRP": "🔵 EIGRP",
                    "BGP": "🟣 BGP",
                    "Static": "⚫ Static"
                }
                return ", ".join([badge_map.get(proto, proto) for proto in protocol_list])

            for dev in edited_devices:
                name = dev.get("name", "Unnamed")
                dev_type = dev.get("type", "unknown").title()
                definition = dev.get("node_definition", "iosv")
                config = dev.get("config", "")
                protocols = []
                vlans = set()
                interfaces = []
                ospf_pid = ospf_area = ""
                ospf_networks = []

                # --- Protocol variables for EIGRP, BGP, Static ---
                eigrp_as = ""
                eigrp_networks = []
                bgp_asn = ""
                bgp_neighbors = []
                bgp_networks = []
                static_route_lines = []

                current_iface = None
                for line in config.splitlines():
                    stripped = line.strip()
                    if stripped.startswith("interface"):
                        iface = stripped.split("interface")[-1].strip()
                        interfaces.append(iface)
                        current_iface = iface
                    elif "ip address" in stripped:
                        ip = stripped.split("ip address")[-1].strip().split()[0]
                        if interfaces:
                            interfaces[-1] = f"{interfaces[-1]} ({ip})"
                    elif "encapsulation dot1Q" in stripped:
                        vlan_id = stripped.split()[-1]
                        vlans.add(vlan_id)
                    elif stripped.startswith("router ospf"):
                        ospf_pid = stripped.split()[-1]
                    elif "area" in stripped and "network" in stripped:
                        ospf_area = stripped.split("area")[-1].strip()
                        ospf_networks.append(stripped.strip())

                # Protocol detection
                if "router ospf" in config: protocols.append("OSPF")
                if "router eigrp" in config: protocols.append("EIGRP")
                if "router bgp" in config: protocols.append("BGP")
                if "ip route" in config: protocols.append("Static")

                # --- Parse EIGRP ---
                if "router eigrp" in config:
                    eigrp_as_match = re.search(r"router eigrp (\d+)", config)
                    eigrp_as = eigrp_as_match.group(1) if eigrp_as_match else ""
                    eigrp_networks = re.findall(r"network (\d+\.\d+\.\d+\.\d+)", config)

                # --- Parse BGP ---
                if "router bgp" in config:
                    bgp_asn_match = re.search(r"router bgp (\d+)", config)
                    bgp_asn = bgp_asn_match.group(1) if bgp_asn_match else ""
                    bgp_neighbors = re.findall(r"neighbor (\S+) remote-as \d+", config)
                    bgp_network_matches = re.findall(r"network (\d+\.\d+\.\d+\.\d+) mask (\d+\.\d+\.\d+\.\d+)", config)
                    for ip, mask in bgp_network_matches:
                        bgp_networks.append(f"{ip} {mask}")

                # --- Parse Static Routes ---
                static_routes = re.findall(r"ip route (\d+\.\d+\.\d+\.\d+) (\d+\.\d+\.\d+\.\d+) (\d+\.\d+\.\d+\.\d+)", config)
                static_route_lines = [f"{dest} {mask} {nh}" for dest, mask, nh in static_routes]

                row = {
                    "Device": name,
                    "Type": dev_type,
                    "Image": definition,
                    "VLANs": ", ".join(sorted(vlans)) if vlans else "-",
                    "Protocols": format_protocol_badges(protocols) if protocols else "None",
                    "OSPF PID": ospf_pid,
                    "OSPF Area": ospf_area,
                    "OSPF Networks": "\n".join(ospf_networks) if ospf_networks else "-",
                    # New protocol fields
                    "EIGRP AS": eigrp_as,
                    "EIGRP Networks": "\n".join(eigrp_networks) if eigrp_networks else "-",
                    "BGP ASN": bgp_asn,
                    "BGP Neighbors": "\n".join(bgp_neighbors) if bgp_neighbors else "-",
                    "BGP Networks": "\n".join(bgp_networks) if bgp_networks else "-",
                    "Static Routes": "\n".join(static_route_lines) if static_route_lines else "-",
                }

                # Add individual interface columns
                for i in range(4):
                    row[f"Interface {i+1}"] = interfaces[i] if i < len(interfaces) else "-"

                summary_data.append(row)

            # Determine which protocol columns are relevant
            include_ospf = any("OSPF" in row.get("Protocols", "") for row in summary_data)
            include_eigrp = any("EIGRP" in row.get("Protocols", "") for row in summary_data)
            include_bgp = any("BGP" in row.get("Protocols", "") for row in summary_data)
            include_static = any("Static" in row.get("Protocols", "") for row in summary_data)

            # Drop unused protocol-specific fields
            for row in summary_data:
                if not include_ospf:
                    row.pop("OSPF PID", None)
                    row.pop("OSPF Area", None)
                    row.pop("OSPF Networks", None)
                if not include_eigrp:
                    row.pop("EIGRP AS", None)
                    row.pop("EIGRP Networks", None)
                if not include_bgp:
                    row.pop("BGP ASN", None)
                    row.pop("BGP Neighbors", None)
                    row.pop("BGP Networks", None)
                if not include_static:
                    row.pop("Static Routes", None)

            df_summary = pd.DataFrame(summary_data)
            st.dataframe(df_summary, use_container_width=True)

            # --- Export & Print Options ---
            st.markdown("#### 📤 Export & Print Options")

            col_export1, col_export2 = st.columns(2)

            with col_export1:
                csv = df_summary.to_csv(index=False).encode("utf-8")
                st.download_button(
                    label="📥 Export Summary to CSV",
                    data=csv,
                    file_name="deployment_summary.csv",
                    mime="text/csv"
                )

            with col_export2:
                st.button("🖨️ Print View", on_click=lambda: st.markdown(
                    """
                    <script>
                        window.print();
                    </script>
                    """,
                    unsafe_allow_html=True
                ))

    with tab4:
        st.markdown("### 🔍 Network Validation & Health Checks")
        
        if 'last_mcp_model' in st.session_state and st.session_state['last_mcp_model']:
            # Create validator instance
            validator = NetworkValidator(
                st.session_state['last_mcp_model']["network_design"]["devices"],
                st.session_state['last_mcp_model']["network_design"]["links"]
            )
            
            # Run validation
            validation_results = validator.validate_topology()
            
            # Display validation results
            st.markdown("#### 📋 Pre-Deployment Validation")
            if validation_results:
                for result in validation_results:
                    if result["type"] == "error":
                        st.error(f"❌ {result['category']}: {result['message']}")
                    elif result["type"] == "warning":
                        st.warning(f"⚠️ {result['category']}: {result['message']}")
                    else:
                        st.info(f"ℹ️ {result['category']}: {result['message']}")
            else:
                st.success("✅ No validation issues found!")
            
            # Health check section
            st.markdown("#### 🏥 Lab Health Status")
            if 'last_created_lab_id' in st.session_state:
                cml_manager = get_cml_manager()
                if cml_manager:
                    health_results = validator.run_health_checks(cml_manager)
                    if health_results:
                        for result in health_results:
                            if result["type"] == "error":
                                st.error(f"❌ {result['category']}: {result['message']}")
                            elif result["type"] == "warning":
                                st.warning(f"⚠️ {result['category']}: {result['message']}")
                            else:
                                st.info(f"ℹ️ {result['category']}: {result['message']}")
                    else:
                        st.success("✅ All health checks passed!")
                else:
                    st.warning("⚠️ CML connection not available for health checks")
            else:
                st.info("ℹ️ No lab deployed yet. Deploy a lab to run health checks.")
        else:
            st.info("ℹ️ No topology loaded. Generate or load a topology first.")

# ----------------------
# Save Current Topology as Template (Sidebar)
# ----------------------
with st.sidebar.expander("📝 Save Current Topology as Template", expanded=False):
    if 'last_mcp_model' in st.session_state and st.session_state['last_mcp_model']:
        template_name = st.text_input("Enter a name for the new template:")
        if st.button("💾 Save as Template"):
            if template_name.strip() == "":
                st.error("❌ Please enter a valid name.")
            else:
                os.makedirs("custom_templates", exist_ok=True)
                save_path = f"custom_templates/{template_name}.json"
                try:
                    with open(save_path, "w") as f:
                        json.dump(st.session_state['last_mcp_model'], f, indent=4)
                    st.success(f"✅ Template `{template_name}` saved successfully!")
                except Exception as e:
                    st.error(f"❌ Failed to save template: {e}")
    else:
        st.info("ℹ️ Generate or load a topology first to save as template.")

# ----------------------
# Save Topology as JSON Snapshot (Sidebar)
# ----------------------
with st.sidebar.expander("💾 Save Topology as JSON Snapshot", expanded=False):
    if 'last_mcp_model' in st.session_state and st.session_state['last_mcp_model']:
        snapshot_name = st.text_input("Custom filename (no spaces):", key="snapshot_name")
        if st.button("📥 Save Snapshot"):
            if snapshot_name.strip() == "":
                st.error("❌ Please enter a valid name.")
            else:
                os.makedirs("saved_models", exist_ok=True)
                snapshot_path = f"saved_models/{snapshot_name}.json"
                try:
                    with open(snapshot_path, "w") as f:
                        json.dump(st.session_state['last_mcp_model'], f, indent=4)
                    st.success(f"✅ Saved snapshot as `{snapshot_path}`")
                except Exception as e:
                    st.error(f"❌ Failed to save snapshot: {e}")
    else:
        st.info("ℹ️ No MCP model available to save.")


# ----------------------
# Lab Name: Move to Sidebar
# ----------------------
with st.sidebar.expander("📛 Lab Name", expanded=False):
    st.session_state['lab_name'] = st.text_input("Enter Lab ID:", value=st.session_state['lab_name'])

# Display previous chat history (MOVED HERE)
for message in st.session_state['chat_history']:
    with st.chat_message(message["role"]):
        st.markdown(message["text"])

# Get user input
user_input = st.chat_input("Describe your desired network topology...")

if user_input:
    # Do NOT render user or assistant messages immediately here
    # Only append to chat_history
    st.session_state['chat_history'].append({"role": "user", "text": user_input})
    if len(st.session_state['chat_history']) > 10:
        st.session_state['chat_history'] = st.session_state['chat_history'][-10:]

    with st.spinner("Thinking..."):
        try:
            # Avoid global declaration issues by always using st.session_state
            result = graph.invoke({"input": user_input})
            st.write("DEBUG: Raw agent result:", result)  # Debug print
            output = result.get("output", None)
            
            # 2. Only accept output if it is a dict (or valid JSON)
            def is_valid_topology_dict(d):
                return (
                    isinstance(d, dict) and
                    isinstance(d.get("devices", None), list) and
                    isinstance(d.get("links", None), list)
                )

            def normalize_links(topology):
                # Convert 'source'/'target' to 'endpoints' if needed
                for link in topology.get("links", []):
                    if "source" in link and "target" in link:
                        link["endpoints"] = [link.pop("source"), link.pop("target")]
                return topology

            # Try to parse output if it's a string
            if output and isinstance(output, str):
                try:
                    output = json.loads(output)
                except Exception as e:
                    st.error(f"❌ Output could not be parsed as JSON: {e}")

            # If output is a list, pick the one with the most devices and links
            if isinstance(output, list):
                best = None
                best_score = -1
                for candidate in output:
                    if is_valid_topology_dict(candidate):
                        # Calculate a score based on non-empty devices and links
                        device_score = len([d for d in candidate["devices"] if isinstance(d.get("name"), str) and len(d.get("name", "")) > 1])
                        link_score = len(candidate["links"])
                        score = device_score + link_score
                        if score > best_score:
                            best = candidate
                            best_score = score
                output = best if best is not None else output[0] if isinstance(output, list) and len(output) > 0 else output

            # If output is a dict, but has empty devices or links, try to warn the user
            if output and is_valid_topology_dict(output):
                output = normalize_links(output)
                
                # Initialize flag properly
                invalid_topology = False
                
                # Check for valid device names (not just single characters or generic terms)
                valid_devices = [d for d in output["devices"] if isinstance(d.get("name"), str) and len(d.get("name", "")) > 1 and d["name"] not in ["S", "Routers"]]
                
                if not valid_devices or not output["links"]:
                    # First try to detect if this is a common topology pattern
                    pattern_result = detect_topology_pattern(user_input)
                    
                    if pattern_result:
                        topology_type, num_devices, protocol, device_type = pattern_result
                        st.info(f"🔄 Using template-based topology for {num_devices} {device_type}s in a {topology_type} topology" + 
                               (f" with {protocol} protocol" if protocol else ""))
                        
                        try:
                            # Generate template topology
                            output = create_template_topology(
                                topology_type=topology_type,
                                num_devices=num_devices,
                                protocol=protocol,
                                device_type=device_type
                            )
                            
                            # Safety check to make sure output is valid
                            if not output or not isinstance(output, dict) or "devices" not in output or "links" not in output:
                                st.error(f"❌ Error generating topology template. Invalid output structure.")
                                st.session_state['chat_history'].append({
                                    "role": "assistant", 
                                    "text": "❌ There was an error generating the topology. Please try again with a different description."
                                })
                                invalid_topology = True
                            else:
                                # Update valid_devices for later use
                                valid_devices = output.get("devices", [])
                                # Reset invalid flag since we now have a valid topology
                                invalid_topology = False
                        except Exception as e:
                            st.error(f"❌ Error generating topology template: {str(e)}")
                            st.session_state['chat_history'].append({
                                "role": "assistant", 
                                "text": f"❌ Error generating topology: {str(e)}. Please try again."
                            })
                            invalid_topology = True
                    else:
                        st.error("❌ The agent did not generate a valid topology. Please try a more specific description (e.g., '6 routers named R1-R6 connected in a ring with ethernet links').")
                        st.write("DEBUG: Agent output had invalid devices or no links:", output)
                        
                        # Add the error to chat history
                        st.session_state['chat_history'].append({
                            "role": "assistant", 
                            "text": "❌ I couldn't generate a valid network topology from that description. Try a more specific pattern like '6 routers in a ring topology using OSPF' or '3 switches in a star topology'."
                        })
                        # Mark as invalid
                        invalid_topology = True
                
                # Only proceed if we have a valid topology
                if not invalid_topology:
                    # Ensure our final output has valid structure
                    if not isinstance(output, dict):
                        st.error("❌ Invalid topology structure detected.")
                        invalid_topology = True  # Set flag instead of return
                    
                    # Create the proper structure that the rest of the app expects
                    if not invalid_topology:  # Check flag before continuing
                        network_model = {
                            "network_design": output
                        }
                        
                        # Verify network_model structure
                        if not isinstance(network_model, dict) or "network_design" not in network_model:
                            st.error("❌ Invalid network model structure.")
                            invalid_topology = True  # Set flag instead of return
                        
                        # Store in session state
                        if not invalid_topology:  # Check flag before continuing
                            st.session_state['last_mcp_model'] = network_model
                            
                            st.success("✅ Network topology generated successfully!")
                            st.write("DEBUG: Using topology:", output)
                            
                            # Safety check before calling IP assignment
                            try:
                                # Assign IPs first (modifies devices/links in-place if needed for VXLAN)
                                vxlan_enabled = assign_ip_addresses(output.get("devices", []), output.get("links", []))

                                # --- Generate Protocol Config --- 
                                requested_protocol = output.get("protocol")
                                if requested_protocol:
                                    st.info(f"⚙️ Generating config for {requested_protocol}...")
                                    # Get devices/links potentially modified by assign_ip_addresses
                                    current_devices = output.get("devices", [])
                                    current_links = output.get("links", [])
                                    # Generate configs including the requested protocol
                                    devices_with_config = generate_device_configs(current_devices, current_links, requested_protocol=requested_protocol)
                                    # --- IMPORTANT: Update the model in session state --- 
                                    network_model["network_design"]["devices"] = devices_with_config
                                    st.session_state['last_mcp_model'] = network_model # Ensure session has updated devices
                                    st.info(f"✅ {requested_protocol} config generated.")
                                    
                                if vxlan_enabled:
                                    st.info("🔄 VXLAN overlay configured with appropriate VTEPs and VNIs")
                            except Exception as e:
                                st.error(f"❌ Error during IP/Config generation: {str(e)}")
                            
                            # Format and add the response to chat history
                            st.session_state['chat_history'].append({
                                "role": "assistant", 
                                "text": f"✅ Created a network with {len(valid_devices)} devices and {len(output['links'])} links."
                            })
                            
                            # Create tabs for viewing and editing the generated topology
                            tab1, tab2, tab3, tab4 = st.tabs(["🖼 Topology Viewer", "🛠 Customize Devices", "📋 Deployment Summary", "🔍 Validation & Health"])
                            
                            with tab1:
                                st.success(f"✅ Network topology generated successfully!")
                                
                                # Remove the visualization selector radio button
                                # viz_option = st.radio(...)
                                
                                with st.spinner("Rendering network diagram..."):
                                    # Always call Plotly version, passing dark_mode
                                    draw_network_topology_plotly(network_model, dark_mode=st.session_state.get('dark_mode_active', False))
                                    
                                # Show device interface/IP table 
                                st.markdown("### Device Interface Details")
                                for dev in output["devices"]:
                                    st.markdown(f"**{dev['name']} ({dev['type']})**")
                                    if "interfaces" in dev and dev["interfaces"]:
                                        st.table([
                                            {
                                                "Interface": iface["name"],
                                                "IP Address": iface["ip"],
                                                "Mask": iface["mask"],
                                                "Connected To": iface.get("link_to", "-")
                                            }
                                            for iface in dev["interfaces"]
                                        ])
                                    else:
                                        st.info("No interfaces assigned.")
                            
                            with tab2:
                                st.subheader("🛠️ Customize Device Configurations")
                                # Device customization section
                                if 'last_mcp_model' in st.session_state:
                                    current_model = st.session_state.get('last_mcp_model')
                                    # Use devices directly from the current_model for consistency
                                    devices_to_edit = current_model["network_design"].get("devices", [])
                                    if devices_to_edit:
                                        available_defs = {
                                            "router": "iosv",
                                            "switch": "iosvl2",
                                            "firewall": "asav",
                                            "server": "ubuntu",
                                            "ext-server": "ext-server",
                                            "csr": "csr1000v",
                                            "nxos": "nxosv9000",
                                            "win10": "win10-desktop",
                                            "alpine": "alpine"
                                        }
                                        valid_types = list(available_defs.keys())
                                        node_definitions = available_defs
                                        # Pass the devices from the model to the editor
                                        edited_devices = edit_devices_ui(devices_to_edit, node_definitions, valid_types, context_prefix="generated")
                                        if st.button("💾 Apply Edits to Devices", key="apply_edits_generated"):
                                            # Update the model in session state directly
                                            current_model["network_design"]["devices"] = edited_devices
                                            st.session_state['last_mcp_model'] = current_model # Update session state
                                            st.success("✅ Updated device configurations applied.")
                                            # Use Plotly for visualization, passing dark_mode
                                            draw_network_topology_plotly(current_model, dark_mode=st.session_state.get('dark_mode_active', False))
                                        if st.button("🔄 Reset Device Edits", key="reset_edits_generated"):
                                            st.rerun()
                            
                            with tab3:
                                st.markdown("### 📋 Deployment Summary")
                                import re
                                
                                # Always use the model from session state for the summary
                                if 'last_mcp_model' in st.session_state:
                                    current_model_for_summary = st.session_state.get('last_mcp_model')
                                    devices_for_summary = current_model_for_summary["network_design"].get("devices", [])
                                    
                                    if devices_for_summary:
                                        summary_data = []  # List to hold all device summary rows
                                        
                                        def format_protocol_badges(protocol_list):
                                            badge_map = {
                                                "OSPF": "🟢 OSPF",
                                                "EIGRP": "🔵 EIGRP",
                                                "BGP": "🟣 BGP",
                                                "Static": "⚫ Static"
                                            }
                                            return ", ".join([badge_map.get(proto, proto) for proto in protocol_list])
                                        
                                        # Process each device individually and add to summary_data
                                        for dev in devices_for_summary:
                                            name = dev.get("name", "Unnamed")
                                            dev_type = dev.get("type", "unknown").title()
                                            definition = dev.get("node_definition", "iosv")
                                            config = dev.get("config", "")
                                            protocols = []
                                            vlans = set()
                                            interfaces = []
                                            ospf_pid = ospf_area = ""
                                            ospf_networks = []
                                            eigrp_as = ""
                                            eigrp_networks = []
                                            bgp_asn = ""
                                            bgp_neighbors = []
                                            bgp_networks = []
                                            static_route_lines = []
                                            
                                            # Detect interfaces from the 'interfaces' list
                                            if "interfaces" in dev:
                                                for iface in dev["interfaces"]:
                                                    iface_name = iface.get("name", "")
                                                    ip = iface.get("ip", "")
                                                    interfaces.append(f"{iface_name} ({ip})")
                                            
                                            # Detect protocol from the model
                                            model_protocol = current_model_for_summary["network_design"].get("protocol")
                                            if model_protocol and model_protocol not in protocols:
                                                protocols.append(model_protocol)
                                            
                                            # Parse config for VLANs, static routes, etc.
                                            if config:
                                                for line in config.splitlines():
                                                    stripped = line.strip()
                                                    if "encapsulation dot1Q" in stripped:
                                                        vlan_id = stripped.split()[-1]
                                                        vlans.add(vlan_id)
                                                    elif stripped.startswith("router ospf"):
                                                        ospf_pid = stripped.split()[-1]
                                                    elif "area" in stripped and "network" in stripped:
                                                        ospf_area = stripped.split("area")[-1].strip()
                                                        ospf_networks.append(stripped.strip())
                                            
                                            # Protocol detection from config (more reliable)
                                            if "router ospf" in config:
                                                if "OSPF" not in protocols:
                                                    protocols.append("OSPF")
                                            if "router eigrp" in config: 
                                                if "EIGRP" not in protocols:
                                                    protocols.append("EIGRP")
                                            if "router bgp" in config: 
                                                if "BGP" not in protocols:
                                                    protocols.append("BGP")
                                            if "ip route" in config: 
                                                if "Static" not in protocols:
                                                    protocols.append("Static")
                                            
                                            # --- Parse EIGRP ---
                                            if "router eigrp" in config:
                                                eigrp_as_match = re.search(r"router eigrp (\d+)", config)
                                                eigrp_as = eigrp_as_match.group(1) if eigrp_as_match else ""
                                                eigrp_networks = re.findall(r"network (\d+\.\d+\.\d+\.\d+)", config)
                                            
                                            # --- Parse BGP ---
                                            if "router bgp" in config:
                                                bgp_asn_match = re.search(r"router bgp (\d+)", config)
                                                bgp_asn = bgp_asn_match.group(1) if bgp_asn_match else ""
                                                bgp_neighbors = re.findall(r"neighbor (\S+) remote-as \d+", config)
                                                bgp_network_matches = re.findall(r"network (\d+\.\d+\.\d+\.\d+) mask (\d+\.\d+\.\d+\.\d+)", config)
                                                for ip_bgp, mask_bgp in bgp_network_matches:
                                                    bgp_networks.append(f"{ip_bgp} {mask_bgp}")
                                            
                                            # --- Parse Static Routes ---
                                            static_routes = re.findall(r"ip route (\d+\.\d+\.\d+\.\d+) (\d+\.\d+\.\d+\.\d+) (\d+\.\d+\.\d+\.\d+)", config)
                                            static_route_lines = [f"{dest} {mask} {nh}" for dest, mask, nh in static_routes]
                                            
                                            # Build the row for THIS device
                                            this_device_row = {
                                                "Device": name,
                                                "Type": dev_type,
                                                "Image": definition,
                                                "VLANs": ", ".join(sorted(vlans)) if vlans else "-",
                                                "Protocols": format_protocol_badges(protocols) if protocols else "None",
                                                "OSPF PID": ospf_pid,
                                                "OSPF Area": ospf_area,
                                                "OSPF Networks": "\n".join(ospf_networks) if ospf_networks else "-",
                                                "EIGRP AS": eigrp_as,
                                                "EIGRP Networks": "\n".join(eigrp_networks) if eigrp_networks else "-",
                                                "BGP ASN": bgp_asn,
                                                "BGP Neighbors": "\n".join(bgp_neighbors) if bgp_neighbors else "-",
                                                "BGP Networks": "\n".join(bgp_networks) if bgp_networks else "-",
                                                "Static Routes": "\n".join(static_route_lines) if static_route_lines else "-",
                                            }
                                            
                                            # Add individual interface columns dynamically
                                            max_interfaces_in_row = len(interfaces)
                                            for i in range(max_interfaces_in_row):
                                                this_device_row[f"Interface {i+1}"] = interfaces[i]
                                            
                                            # Add THIS device's row to the summary data
                                            summary_data.append(this_device_row)
                                        
                                        # Determine max interfaces found across all devices for dynamic columns
                                        max_interfaces_found = 0
                                        for d in devices_for_summary:
                                            max_interfaces_found = max(max_interfaces_found, len(d.get("interfaces", [])))
                                        
                                        # Now outside the loop, process all collected rows
                                        df_summary = pd.DataFrame(summary_data)
                                        
                                        # Ensure all potential interface columns exist, filling with '-'
                                        for i in range(max_interfaces_found):
                                            col_name = f"Interface {i+1}"
                                            if col_name not in df_summary.columns:
                                                df_summary[col_name] = '-' 
                                        
                                        # Determine which protocol columns are relevant
                                        # ... (protocol column dropping logic remains the same) ...
                                        include_ospf = any("OSPF" in row.get("Protocols", "") for row in summary_data)
                                        include_eigrp = any("EIGRP" in row.get("Protocols", "") for row in summary_data)
                                        include_bgp = any("BGP" in row.get("Protocols", "") for row in summary_data)
                                        include_static = any("Static" in row.get("Protocols", "") for row in summary_data)
                                        
                                        columns_to_drop = []
                                        if not include_ospf:
                                            columns_to_drop.extend(["OSPF PID", "OSPF Area", "OSPF Networks"])
                                        if not include_eigrp:
                                            columns_to_drop.extend(["EIGRP AS", "EIGRP Networks"])
                                        if not include_bgp:
                                            columns_to_drop.extend(["BGP ASN", "BGP Neighbors", "BGP Networks"])
                                        if not include_static:
                                            columns_to_drop.extend(["Static Routes"])
                                        
                                        # Drop columns if they exist in the DataFrame
                                        actual_columns_to_drop = [col for col in columns_to_drop if col in df_summary.columns]
                                        if actual_columns_to_drop:
                                             df_summary = df_summary.drop(columns=actual_columns_to_drop)
                                        
                                        # Display as dataframe
                                        st.dataframe(df_summary, use_container_width=True)
                                    else:
                                        st.info("No devices available in the topology.")
                                else:
                                    st.info("No topology loaded. Generate a topology first.")
        except Exception as e:
            st.error(f"❌ An error occurred: {str(e)}")
            st.error("Please try again with a different description.")
            
            # Add the error to chat history
            st.session_state['chat_history'].append({
                "role": "assistant", 
                "text": f"❌ An error occurred: {str(e)}. Please try again with a different description."
            })

# Only render chat messages from history (once)
for message in st.session_state['chat_history']:
    with st.chat_message(message["role"]):
        st.markdown(message["text"])

# ----------------------
# Advanced Controls: Export, Reload, Start/Stop
# ----------------------
st.subheader("⚙️ Advanced Controls")

col1, col2, col3 = st.columns(3)

with col1:
    if 'last_mcp_model' in st.session_state and st.session_state['last_mcp_model']:
        # Find the latest generated HTML file for export
        html_files = sorted([f for f in os.listdir("saved_models") if f.startswith("network_topology_mcp_builder") and f.endswith(".html")], reverse=True)
        if html_files:
            export_filename = os.path.join("saved_models", html_files[0])
            try:
                with open(export_filename, "r") as f:
                    html_content = f.read()
                st.download_button(
                    label="📥 Export Network Diagram (HTML)",
                    data=html_content,
                    file_name=html_files[0],
                    mime="text/html"
                )
            except Exception as e:
                st.error(f"❌ Error reading diagram file: {e}")
        else:
            st.info("Generate a topology first to enable diagram export.")
    else:
        st.info("Generate a topology first to enable diagram export.")

with col2:
    saved_files = sorted([f for f in os.listdir("saved_models") if f.endswith(".json")], reverse=True)
    saved_names = [os.path.splitext(f)[0] for f in saved_files]  # Remove .json for display
    selected_file = st.selectbox("📂 Reload Saved Topology", ["Select a file..."] + saved_names)

    if selected_file != "Select a file...":
        load_path = f"saved_models/{selected_file}.json"
        try:
            with open(load_path, "r") as f:
                loaded_mcp_model = json.load(f)
            st.session_state['last_mcp_model'] = loaded_mcp_model # Load into session
            st.success(f"✅ Loaded `{selected_file}` into session.")
            # Trigger rerun to display the loaded model in tabs
            st.rerun() 
        except Exception as e:
            st.error(f"❌ Failed to load {selected_file}: {e}")

with col3:
    st.markdown("🚀 **Lab Controls**")

    if st.button("🚀 Deploy New Lab from Model"):
        try:
            cml_manager = get_cml_manager()
            if not cml_manager and not st.session_state.get("design_mode", False):
                st.warning("⚠️ CML connection not available and not in Design Mode.")
                st.stop()

            if 'last_mcp_model' in st.session_state and st.session_state['last_mcp_model'] is not None:
                if not st.session_state['lab_name']:
                    st.error("❌ Please enter a Lab ID first! (Use sidebar)")
                    st.stop()

                st.text("🛠 Creating lab...")
                # Call CML Manager to create lab
                lab, warning_msg, validation_results, health_results = cml_manager.create_lab_from_mcp(st.session_state['last_mcp_model'], st.session_state['lab_name'])
                st.success(f"✅ New Lab Created! Lab ID: {lab.id}")
                if warning_msg:
                    st.warning(warning_msg) # Show warnings from CMLConnector
                st.session_state['last_created_lab_id'] = lab.id
                # Display validation/health results after deployment
                st.session_state['validation_results'] = validation_results
                st.session_state['health_results'] = health_results
            else:
                st.error("❌ No MCP model available to deploy. Generate or load a topology first.")
        except Exception as e:
            st.error(f"❌ Failed to deploy new lab: {e}")

    # --- Queue "Last MCP Model" for Later ---
    if st.button("📦 Queue 'Last MCP Model' for Later"):
        try:
            queued_model = st.session_state.get('last_mcp_model', None)
            if not queued_model:
                st.error("❌ No MCP model found to queue.")
            else:
                queue_path = f"saved_models/queued_last_model_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.json"
                with open(queue_path, "w") as f:
                    json.dump(queued_model, f, indent=4)
                st.success(f"🕒 Queued for later deployment: `{queue_path}`")
        except Exception as e:
            st.error(f"❌ Failed to queue model: {e}")

    # Start and Stop buttons (appear only AFTER deploy)
    if 'last_created_lab_id' in st.session_state:
        lab_id = st.session_state['last_created_lab_id']
        if st.button("▶️ Start Lab"):
            try:
                cml_manager = get_cml_manager()
                if cml_manager:
                    st.text("Starting lab...")
                    cml_manager.start_lab(lab_id)
                    st.success("✅ Lab start requested!")
                else:
                     st.warning("⚠️ CML connection not available.")
            except Exception as e:
                 st.error(f"❌ Failed to start lab: {e}")

        if st.button("⏹ Stop Lab"):
            try:
                cml_manager = get_cml_manager()
                if cml_manager:
                    st.text("Stopping lab...")
                    cml_manager.stop_lab(lab_id)
                    st.success("✅ Lab stop requested!")
                else:
                     st.warning("⚠️ CML connection not available.")
            except Exception as e:
                 st.error(f"❌ Failed to stop lab: {e}")

# ----------------------
# Test CML Connection Button
# ----------------------
st.subheader("🧪 Test CML Server Connection")

# Visual connection status indicator
connection_status = st.empty()

if st.button("🔍 Test CML Connection"):
    try:
        cml_manager = get_cml_manager()
        if not cml_manager and not st.session_state.get("design_mode", False):
            connection_status.warning("⚠️ CML connection not available (or in Design Mode).")
            st.stop()
        version = cml_manager.client.system_info().get("version", "Unknown")
        connection_status.success(f"🟢 Connected to CML server (Version: {version})")
    except Exception as e:
        error_message = str(e)
        if "Errno 60" in error_message or "timed out" in error_message.lower():
            connection_status.error("🔴 Could not connect to CML server: Server unreachable (timed out after 5 seconds).")
        else:
            connection_status.error(f"🔴 Could not connect to CML server: {error_message}")

# --- Final check for session state consistency ---
# Ensure last_mcp_model exists if needed by downstream components
if 'last_mcp_model' not in st.session_state:
    st.session_state['last_mcp_model'] = None

