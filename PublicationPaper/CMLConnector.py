import os
from virl2_client import ClientLibrary

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

        for device in mcp_model["network_design"]["devices"]:
            label = device["name"]
            node_definition = device.get("node_definition", "iosv")  # Use provided definition or default
            node = lab.create_node(label=label, node_definition=node_definition, x=x, y=y)
            device_config = device.get("config", f"hostname {label}")
            node.config = device_config
            device_mapping[label] = node

            count += 1
            if count % max_per_row == 0:
                x = 100
                y += y_offset
            else:
                x += x_offset

        for link in mcp_model["network_design"]["links"]:
            node_a = device_mapping[link["endpoints"][0]]
            node_b = device_mapping[link["endpoints"][1]]
            lab.connect_two_nodes(node_a, node_b)

        lab.sync()  # Ensure all configurations are saved
        lab.start()
        return lab

    def start_lab(self, lab_id):
        """Start an existing lab."""
        lab = self.client.join_existing_lab(lab_id)
        lab.start()

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
            "running_nodes": sum(1 for node in lab.nodes() if node.state == "STARTED")
        }