import os
from virl2_client import ClientLibrary
from NetworkValidator import NetworkValidator

class CMLManager:
    def __init__(self):
        """Initialize connection to CML using environment variables."""
        server = os.getenv("CML_SERVER")
        username = os.getenv("CML_USERNAME")
        password = os.getenv("CML_PASSWORD")
        if not server or not username or not password:
            raise ValueError("CML_SERVER, CML_USERNAME, and CML_PASSWORD must be set as environment variables.")
        self.client = ClientLibrary(server, username, password, ssl_verify=False)

    def create_lab_from_mcp(self, mcp_model, lab_title=None):
        """Create a new lab based on the MCP network model."""
        # Run validation before creating lab
        validator = NetworkValidator(
            mcp_model["network_design"]["devices"],
            mcp_model["network_design"]["links"]
        )
        validation_results = validator.validate_topology()
        
        if lab_title:
            lab = self.client.create_lab(title=lab_title)
        else:
            lab = self.client.create_lab()

        device_mapping = {}
        x, y = 100, 100
        x_offset = 200
        y_offset = 200
        max_per_row = 3
        count = 0

        # --- B. Node Definitions & C. Config Generation ---
        unsupported_vxlan_nodes = []
        for device in mcp_model["network_design"]["devices"]:
            label = device["name"]
            node_definition = device.get("node_definition", "iosv")
            config = device.get("config", f"hostname {label}")
            if ("vxlan" in config.lower() or "evpn" in config.lower()) and node_definition != "nxosv9000":
                unsupported_vxlan_nodes.append(label)
            if node_definition != "nxosv9000":
                config_lines = config.splitlines()
                filtered_lines = [line for line in config_lines if not any(proto in line.lower() for proto in ["vxlan", "evpn", "nve", "vn-segment", "l2vpn", "l3vni"])]
                config = "\n".join(filtered_lines)
            node = lab.create_node(label=label, node_definition=node_definition, x=x, y=y)
            node.config = config
            device_mapping[label] = node

            count += 1
            if count % max_per_row == 0:
                x = 100
                y += y_offset
            else:
                x += x_offset

        # --- A. Filter Links for CML ---
        for link in mcp_model["network_design"]["links"]:
            if link.get("is_overlay") or link.get("link_type") == "vxlan":
                continue
            node_a = device_mapping[link["endpoints"][0]]
            node_b = device_mapping[link["endpoints"][1]]
            lab.connect_two_nodes(node_a, node_b)

        lab.sync()
        lab.start()

        # Run health checks after lab is started
        health_results = validator.run_health_checks(self)

        # --- D. Validation/Warnings ---
        warning_msg = None
        if unsupported_vxlan_nodes:
            warning_msg = (
                f"⚠️ The following nodes have VXLAN/EVPN config but are not nxosv9000 and may not work in CML: "
                f"{', '.join(unsupported_vxlan_nodes)}"
            )
        
        return lab, warning_msg, validation_results, health_results

    def start_lab(self, lab_id):
        """Start an existing lab."""
        lab = self.client.join_existing_lab(lab_id)
        lab.start()
        
        # Run health checks after starting
        validator = NetworkValidator([], [])  # Empty lists since we don't have the model here
        return validator.run_health_checks(self)

    def stop_lab(self, lab_id):
        """Stop an existing lab."""
        lab = self.client.join_existing_lab(lab_id)
        lab.stop()

    def get_lab_status(self, lab_id):
        """Get the status of a lab."""
        lab = self.client.join_existing_lab(lab_id)
        return {
            "title": lab.title,
            "state": lab.state,
            "nodes": [node.label for node in lab.nodes()],
            "running_nodes": [node.label for node in lab.nodes() if node.state == "STARTED"]
        }