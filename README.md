# Graph2Lab: AI-Powered Network Lab Builder

Graph2Lab helps you **build, validate, customize, and deploy** network labs using AI-generated topologies.

![Graph2Lab Logo](assets/graph2lab_logo.png)

## 🚀 Features

- 🧠 **Natural Language Input**: Describe your desired network and let the AI generate the topology.
- 🛠 **Interactive Editing**: Customize interface configs, IP addresses, and protocol settings.
- 🧪 **Validation & Health Checks**: Instantly check for duplicate IPs, config errors, and lab health before and after deployment.
- 🛰 **Protocol Support**: Configure Static, OSPF, EIGRP, and BGP protocols with interface-level control.
- 💡 **Design Mode**: Offline mode lets you work with templates without needing CML access.
- 📈 **Visual Tools**: Network topology viewer, flowchart diagrams, and summary tables.
- 🚀 **One-Click Deployment**: Deploy your custom lab to Cisco Modeling Labs or queue it for later.

## 🔄 Workflow

Graph2Lab implements a dual-path workflow to generate network topologies:

```
┌─────────────────┐
│   User Input    │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────────┐
│                                             │
│  ┌───────────────┐         ┌──────────────┐ │
│  │ Template Path │         │   Chat Path  │ │
│  └───────┬───────┘         └──────┬───────┘ │
│          │                        │         │
│          ▼                        ▼         │
│  ┌───────────────┐         ┌──────────────┐ │
│  │Load Template  │         │LLM Topology  │ │
│  │  Structure    │         │   Parser     │ │
│  └───────┬───────┘         └──────┬───────┘ │
│          │                        │         │
│          ▼                        ▼         │
│  ┌───────────────┐         ┌──────────────┐ │
│  │ Ready-to-Use  │         │   Parser     │ │
│  │   MCP Model   │         │  Success?    │ │
│  └───────┬───────┘         └──────┬───────┘ │
│          │                        │         │
│          │        ┌───────────────┴─────┐   │
│          │        │                     │   │
│          │        ▼                     ▼   │
│          │  ┌──────────────┐    ┌──────────────┐
│          │  │ Pattern      │    │ Use Parser   │
│          │  │ Detection    │    │ Output       │
│          │  └──────┬───────┘    └──────┬───────┘
│          │         │                   │
│          │         ▼                   │
│          │  ┌──────────────┐           │
│          │  │ Generate     │           │
│          │  │ Template     │           │
│          │  └──────┬───────┘           │
│          │         │                   │
└────────────────────┼───────────────────┘
                     │                   │
                     ▼                   ▼
         ┌────────────────────────────────────────┐
         │        IP Address Assignment           │
         └─────────────────┬──────────────────────┘
                           │
                           ▼
         ┌────────────────────────────────────────┐
         │  Protocol Configuration (OSPF/EIGRP)   │
         └─────────────────┬──────────────────────┘
                           │
                           ▼
         ┌────────────────────────────────────────┐
         │  Interactive Device & Interface Editing │
         └─────────────────┬──────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────┐
│                                                     │
│ ┌─────────────────────┐     ┌─────────────────────┐ │
│ │ Topology            │     │ Pre-Deployment      │ │
│ │ Visualization       │     │ Validation          │ │
│ └─────────────────────┘     └─────────────────────┘ │
│                                                     │
└───────────────────────┬─────────────────────────────┘
                        │
                        ▼
            ┌────────────────────────┐
            │     Deploy to CML      │
            └────────────┬───────────┘
                         │
                         ▼
            ┌────────────────────────┐
            │  Running Lab with      │
            │  Health Monitoring     │
            └────────────────────────┘
```

### Workflow Explanation

1. **Input Methods**:
   - **Template Path**: Choose from predefined network topologies
   - **Chat Path**: Describe your network in natural language

2. **Topology Generation**:
   - Templates are directly loaded as MCP models
   - Chat descriptions are parsed by an LLM 
   - Pattern detection provides fallback when parsing fails

3. **Network Configuration**:
   - IP addresses are automatically assigned
   - Routing protocols (OSPF, EIGRP, BGP) are configured
   - Interactive device and interface editing is available

4. **Validation & Deployment**:
   - Pre-deployment validation catches configuration errors
   - Interactive Plotly visualization shows the topology
   - One-click deployment to Cisco Modeling Labs
   - Health monitoring after deployment

## 🚦 Project Status

- **Version**: 3.0
- **Phase**: Network Validation & Health Checks

## 📋 Recent Updates

- Added built-in network validation tools (duplicate IPs, device names, VLAN, routing, protocol config)
- Added lab health check tab (lab state, node status, pre/post-deployment validation)
- UI: New "Validation & Health" tab for real-time feedback
- Foundation for automated connectivity tests (ping, traceroute, BGP neighbor checks)
- Improved visualization with Plotly interactive network diagrams

## 🏗️ Next Steps

- Automated connectivity and protocol tests (ping, traceroute, BGP neighbor checks)
- Advanced topology and protocol validation
- Traffic generation and simulation tools
- Lab scheduling, snapshots, and resource monitoring
- Enhanced documentation and learning tools
- Collaboration and sharing features

## 💻 Setup & Installation

1. Clone this repository
2. Set up a Python virtual environment:
   ```bash
   python -m venv MCP_ENV
   source MCP_ENV/bin/activate  # On Windows: MCP_ENV\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Configure your CML environment in a `.env` file:
   ```
   CML_SERVER=your-cml-server
   CML_USERNAME=your-username
   CML_PASSWORD=your-password
   OPENAI_API_KEY=your-openai-key
   ```
5. Run the application:
   ```bash
   streamlit run Frontend.py
   ```

## 📚 Usage Examples

- "Create a network with 5 routers connected in a ring topology with OSPF"
- "Build a VXLAN fabric with 2 spine switches and 4 leaf switches"
- "Generate a hub and spoke WAN with 1 hub and 4 remote sites"
- "Create a campus network with core-distribution-access layers and VLANs"

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.