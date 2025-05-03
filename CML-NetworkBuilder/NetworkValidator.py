import ipaddress
from typing import List, Dict, Set, Tuple
import re

class NetworkValidator:
    def __init__(self, devices: List[Dict], links: List[Dict]):
        self.devices = devices
        self.links = links
        self.validation_results = []
        self.test_results = []

    def validate_topology(self) -> List[Dict]:
        """Run all validation checks and return results."""
        self.validation_results = []
        
        # Run all validation checks
        self._check_duplicate_ips()
        self._check_duplicate_device_names()
        self._check_missing_routes()
        self._check_vlan_consistency()
        self._check_interface_consistency()
        self._check_protocol_configuration()
        
        return self.validation_results

    def _check_duplicate_ips(self):
        """Check for duplicate IP addresses across devices."""
        ip_map = {}
        for device in self.devices:
            for interface in device.get("interfaces", []):
                ip = interface.get("ip")
                if ip:
                    if ip in ip_map:
                        ip_map[ip].append(f"{device['name']}:{interface['name']}")
                    else:
                        ip_map[ip] = [f"{device['name']}:{interface['name']}"]
        
        for ip, locations in ip_map.items():
            if len(locations) > 1:
                self.validation_results.append({
                    "type": "error",
                    "category": "IP Address",
                    "message": f"Duplicate IP address {ip} found on: {', '.join(locations)}"
                })

    def _check_duplicate_device_names(self):
        """Check for duplicate device names."""
        names = {}
        for device in self.devices:
            name = device.get("name")
            if name in names:
                self.validation_results.append({
                    "type": "error",
                    "category": "Device Name",
                    "message": f"Duplicate device name found: {name}"
                })
            names[name] = True

    def _check_missing_routes(self):
        """Check for missing routes in routing protocols."""
        for device in self.devices:
            config = device.get("config", "")
            if "router ospf" in config or "router eigrp" in config or "router bgp" in config:
                # Get all interfaces with IPs
                device_ips = []
                for interface in device.get("interfaces", []):
                    if "ip" in interface:
                        device_ips.append(interface["ip"].split("/")[0])
                
                # Check if all IPs are included in routing protocol
                for ip in device_ips:
                    network = ipaddress.ip_network(ip + "/24", strict=False)  # Assuming /24 for now
                    if "router ospf" in config and f"network {network.network_address}" not in config:
                        self.validation_results.append({
                            "type": "warning",
                            "category": "Routing",
                            "message": f"Device {device['name']} has OSPF enabled but network {network} is not advertised"
                        })

    def _check_vlan_consistency(self):
        """Check VLAN consistency across switches."""
        vlan_map = {}
        for device in self.devices:
            if device.get("type") == "switch":
                config = device.get("config", "")
                vlans = re.findall(r"vlan (\d+)", config)
                for vlan in vlans:
                    if vlan in vlan_map:
                        vlan_map[vlan].append(device["name"])
                    else:
                        vlan_map[vlan] = [device["name"]]
        
        # Check if VLANs are consistently defined across connected switches
        for link in self.links:
            if link.get("link_type") == "ethernet":
                endpoints = link["endpoints"]
                for device in self.devices:
                    if device["name"] in endpoints and device.get("type") == "switch":
                        config = device.get("config", "")
                        trunk_ports = re.findall(r"interface (.*?)\n.*?switchport mode trunk", config, re.DOTALL)
                        if trunk_ports:
                            self.validation_results.append({
                                "type": "info",
                                "category": "VLAN",
                                "message": f"Trunk port {trunk_ports[0]} on {device['name']} should have consistent VLANs with connected switch"
                            })

    def _check_interface_consistency(self):
        """Check interface configuration consistency."""
        for link in self.links:
            endpoints = link["endpoints"]
            for device in self.devices:
                if device["name"] in endpoints:
                    config = device.get("config", "")
                    interface = next((iface for iface in device.get("interfaces", []) 
                                   if any(endpoint in iface.get("link_to", "") for endpoint in endpoints)), None)
                    if interface and "no shutdown" not in config:
                        self.validation_results.append({
                            "type": "warning",
                            "category": "Interface",
                            "message": f"Interface {interface['name']} on {device['name']} is not enabled (no shutdown missing)"
                        })

    def _check_protocol_configuration(self):
        """Check protocol-specific configurations."""
        for device in self.devices:
            config = device.get("config", "")
            
            # Check OSPF configuration
            if "router ospf" in config:
                if not re.search(r"network \d+\.\d+\.\d+\.\d+ \d+\.\d+\.\d+\.\d+ area \d+", config):
                    self.validation_results.append({
                        "type": "warning",
                        "category": "OSPF",
                        "message": f"Device {device['name']} has OSPF enabled but no networks are configured"
                    })
            
            # Check BGP configuration
            if "router bgp" in config:
                if not re.search(r"neighbor \d+\.\d+\.\d+\.\d+ remote-as \d+", config):
                    self.validation_results.append({
                        "type": "warning",
                        "category": "BGP",
                        "message": f"Device {device['name']} has BGP enabled but no neighbors are configured"
                    })

    def run_health_checks(self, cml_manager) -> List[Dict]:
        """Run health checks on the deployed lab."""
        self.test_results = []
        
        # Get lab status
        lab_status = cml_manager.get_lab_status()
        if lab_status["state"] != "STARTED":
            self.test_results.append({
                "type": "error",
                "category": "Lab Status",
                "message": f"Lab is not running. Current state: {lab_status['state']}"
            })
            return self.test_results

        # Check node status
        for node in lab_status["nodes"]:
            if node not in lab_status["running_nodes"]:
                self.test_results.append({
                    "type": "error",
                    "category": "Node Status",
                    "message": f"Node {node} is not running"
                })

        # TODO: Implement actual connectivity tests once CML API supports it
        # This would include:
        # - Ping tests between nodes
        # - Traceroute verification
        # - BGP neighbor checks
        # - Protocol verification

        return self.test_results 