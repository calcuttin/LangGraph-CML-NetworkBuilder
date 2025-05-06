import re
from langchain_core.tools import tool

@tool
def parse_network_request(text: str) -> dict:
    """
    Parses a natural language network request and attempts to infer a topology.
    Supports arbitrary routers, switches, firewalls, servers, and common routing protocols.
    Now also supports hierarchical requests like '6 switches connected to a distribution switch connected to 2 routers'.
    Upgraded to robustly handle numeric device counts and mesh topologies, and to support 'site' as a synonym for a router+switch pair.
    Now supports 'N sites in a ring topology' (with routers and switches per site, and routers in a ring).
    Now supports 'N sites connected by routers via ethernet' as a ring of routers with a switch per site.
    """
    text = text.lower().replace("-", " ").replace("_", " ")
    devices = []
    links = []
    protocol = None
    vlan_ids = set()

    # --- New: N sites in a mesh topology ---
    mesh_site_match = re.search(r'(\d+)\s+sites?.*mesh', text)
    if mesh_site_match:
        n = int(mesh_site_match.group(1))
        for i in range(n):
            router = {"name": f"Router{i+1}", "type": "router"}
            switch = {"name": f"SiteSwitch{i+1}", "type": "switch"}
            devices.append(router)
            devices.append(switch)
            links.append({"endpoints": [router["name"], switch["name"]], "link_type": "ethernet"})
        # Full mesh between routers
        for i in range(n):
            for j in range(i+1, n):
                links.append({"endpoints": [f"Router{i+1}", f"Router{j+1}"], "link_type": "ethernet"})
        return {"devices": devices, "links": links}

    # --- Existing: N sites in a ring topology ---
    ring_site_match = re.search(r'(\d+)\s+sites?\s+.*ring\s+topology', text)
    if not ring_site_match:
        ring_site_match = re.search(r'(\d+)\s+sites?\s+topology\s+connected\s+in\s+a\s+ring', text)
    if not ring_site_match:
        ring_site_match = re.search(r'(\d+)\s+sites?.*ring', text)
    if ring_site_match:
        n = int(ring_site_match.group(1))
        for i in range(n):
            router = {"name": f"Router{i+1}", "type": "router"}
            switch = {"name": f"SiteSwitch{i+1}", "type": "switch"}
            devices.append(router)
            devices.append(switch)
            links.append({"endpoints": [router["name"], switch["name"]], "link_type": "ethernet"})
        # Connect routers in a ring
        for i in range(n):
            next_idx = (i + 1) % n
            links.append({"endpoints": [f"Router{i+1}", f"Router{next_idx+1}"], "link_type": "ethernet"})
        return {"devices": devices, "links": links}

    # --- Existing: N sites connected by routers via ethernet (treat as ring) ---
    ring_site_flexible = re.search(r'(\d+)\s+sites?\s+connected\s+by\s+routers?\s+via\s+ethernet', text)
    if ring_site_flexible:
        n = int(ring_site_flexible.group(1))
        for i in range(n):
            router = {"name": f"Router{i+1}", "type": "router"}
            switch = {"name": f"SiteSwitch{i+1}", "type": "switch"}
            devices.append(router)
            devices.append(switch)
            links.append({"endpoints": [router["name"], switch["name"]], "link_type": "ethernet"})
        # Connect routers in a ring
        for i in range(n):
            next_idx = (i + 1) % n
            links.append({"endpoints": [f"Router{i+1}", f"Router{next_idx+1}"], "link_type": "ethernet"})
        return {"devices": devices, "links": links}

    # --- Existing: Full mesh N routers/sites ---
    mesh_match = re.search(r'(\d+)\s+(sites?|routers?)\s+.*full\s+mesh', text)
    if mesh_match:
        n = int(mesh_match.group(1))
        entity = mesh_match.group(2)
        router_names = [f"Router{i+1}" for i in range(n)]
        if 'site' in entity:
            for i in range(n):
                router = {"name": f"Router{i+1}", "type": "router"}
                switch = {"name": f"SiteSwitch{i+1}", "type": "switch"}
                devices.append(router)
                devices.append(switch)
                links.append({"endpoints": [router["name"], switch["name"]], "link_type": "ethernet"})
            for i in range(n):
                for j in range(i+1, n):
                    links.append({"endpoints": [f"Router{i+1}", f"Router{j+1}"], "link_type": "ethernet"})
        else:
            for i in range(n):
                devices.append({"name": f"Router{i+1}", "type": "router"})
            for i in range(n):
                for j in range(i+1, n):
                    links.append({"endpoints": [f"Router{i+1}", f"Router{j+1}"], "link_type": "ethernet"})
        return {"devices": devices, "links": links}

    # --- New: N sites connected via [protocol] (default to ring) ---
    site_conn_proto = re.search(r'(\d+)\s+sites?\s+connected\s+via\s+([a-z0-9]+)', text)
    if site_conn_proto:
        n = int(site_conn_proto.group(1))
        proto = site_conn_proto.group(2).upper()
        for i in range(n):
            router = {"name": f"Router{i+1}", "type": "router"}
            switch = {"name": f"SiteSwitch{i+1}", "type": "switch"}
            devices.append(router)
            devices.append(switch)
            links.append({"endpoints": [router["name"], switch["name"]], "link_type": "ethernet"})
        # Connect routers in a ring
        for i in range(n):
            next_idx = (i + 1) % n
            links.append({"endpoints": [f"Router{i+1}", f"Router{next_idx+1}"], "link_type": "ethernet"})
        return {
            "devices": devices,
            "links": links,
            "protocol": proto,
            "sites": n,
            "topology": "ring",
            "routers_per_site": 1,
            "switches_per_site": 1
        }

    # --- Legacy: Explicit device names and connections ---
    device_types = {
        "router": ["router", "core router", "edge router", "wan router"],
        "switch": ["switch", "core switch", "access switch", "distribution switch"],
        "firewall": ["firewall", "asa", "security appliance"],
        "server": ["server", "pc", "host", "workstation"],
        "ext-server": ["external server", "cloud server", "vm"]
    }
    found_devices = set()
    for dtype, synonyms in device_types.items():
        for syn in synonyms:
            matches = re.findall(rf"{syn}\s*(named|called)?\s*([a-z0-9_]+)?", text)
            for match in matches:
                name = match[1] if match[1] else f"{dtype.capitalize()}{len(found_devices)+1}"
                found_devices.add((name.capitalize(), dtype))
            matches = re.findall(rf"([a-z0-9_]+)\s*{syn}", text)
            for match in matches:
                found_devices.add((match.capitalize(), dtype))
    for match in re.findall(r'\b(router|switch|firewall|server|pc|host)[\s\-]?([a-z0-9]+)\b', text):
        dtype, name = match
        dtype = dtype if dtype != "pc" and dtype != "host" else "server"
        found_devices.add((f"{dtype.capitalize()}{name}", dtype))
    for name, dtype in found_devices:
        devices.append({"name": name, "type": dtype})

    link_patterns = [
        r'connect\s+([a-z0-9_]+)\s+(?:to|with|and)\s+([a-z0-9_]+)',
        r'([a-z0-9_]+)\s+uplinks?\s+to\s+([a-z0-9_]+)',
        r'link\s+([a-z0-9_]+)\s+(?:to|with|and)\s+([a-z0-9_]+)',
        r'([a-z0-9_]+)\s+is\s+connected\s+to\s+([a-z0-9_]+)',
        r'([a-z0-9_]+)\s+and\s+([a-z0-9_]+)\s+are\s+connected'
    ]
    for pattern in link_patterns:
        for match in re.findall(pattern, text):
            if isinstance(match, tuple):
                links.append({"endpoints": [match[0].capitalize(), match[1].capitalize()], "link_type": "ethernet"})
            else:
                links.append({"endpoints": [m.capitalize() for m in match], "link_type": "ethernet"})

    for proto in ["bgp", "ospf", "eigrp", "static"]:
        if proto in text:
            protocol = proto.upper()
            break
    vlan_matches = re.findall(r'vlan\s*(\d+)', text)
    for vlan in vlan_matches:
        vlan_ids.add(vlan)
        
    # Create output, prioritizing parsed devices/links but including protocol if detected
    if devices and links:
        output = {
            "devices": devices,
            "links": links,
        }
        if protocol:
            output["protocol"] = protocol
        if vlan_ids:
            output["vlans"] = list(vlan_ids)
    elif protocol:
        output = {"protocol": protocol}
        if vlan_ids:
            output["vlans"] = list(vlan_ids)
    else:
        output = {"error": "Unable to parse enough topology information. Please include device names and connections."}

    return output 