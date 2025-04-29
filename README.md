# 🧠💻 LangGraph CML Network Builder

![Python](https://img.shields.io/badge/python-3.11%2B-blue?logo=python)
![Streamlit](https://img.shields.io/badge/built_with-Streamlit-ff4b4b?logo=streamlit)
![License](https://img.shields.io/badge/license-MIT-green?logo=open-source-initiative)

This project is an **interactive AI-assisted network design and deployment tool** built with [Streamlit](https://streamlit.io/), [LangGraph](https://github.com/langchain-ai/langgraph), and Cisco Modeling Labs (CML). It enables network engineers to **describe**, **customize**, and **deploy** topologies to CML using natural language and AI-driven automation.

![screenshot](./assets/demo-topology.png)

---

## 🔧 Features

- ✍️ **Natural Language Topology Generator** using LangGraph AI Agent
- 📚 **CCNA/CCNP Lab Templates** (Static, OSPF, EIGRP, VLANs, Multi-Site, etc.)
- 🛠️ **Interactive Pre-Deployment Editor** for devices, IPs, VLANs
- 🌐 **Visual Network Topology Renderer** using PyVis and vis.js
- 🚀 **Push-to-CML** deployment with real-time lab status feedback
- 💾 Save, reload, and edit topologies from disk
- 🧪 Test CML connectivity inline

---

## 📸 Screenshots

| MCP ➝ CML Flowchart | Template Editing | Topology Visualization |
|:--------------------|:-----------------|:------------------------|
| ![flow](./assets/flowchart.png) | ![editor](./assets/editor.png) | ![topology](./assets/topology.png) |

---

## 🗂 Directory Structure

```bash
├── Frontend.py                # Main Streamlit app
├── CMLConnector.py           # Handles interaction with CML server
├── saved_models/             # Auto-saved and exported JSON topologies
├── custom_templates/         # User-defined lab templates
├── .env                      # Secrets (e.g., CML login, OpenAI key)
├── README.md                 # This file
```

---

## ⚙️ Requirements

- Python 3.11+
- Streamlit
- LangGraph
- LangChain
- OpenAI (for LLM inference)
- pyvis
- httpx
- dotenv

Install with:

```bash
pip install -r requirements.txt
```

Or manually:

```bash
pip install streamlit langgraph langchain openai python-dotenv pyvis httpx
```

---

## 🚀 Running the App

1. Clone the repo:
   ```bash
   git clone https://github.com/calcuttin/LangGraph-CML-NetworkBuilder.git
   cd LangGraph-CML-NetworkBuilder
   ```

2. Add your secrets to `.env`:
   ```env
   CML_USERNAME=your-cml-username
   CML_PASSWORD=your-cml-password
   CML_SERVER=https://your-cml-server
   OPENAI_API_KEY=your-openai-key
   ```

3. Launch:
   ```bash
   streamlit run Frontend.py
   ```

---

## 🧠 How It Works

1. You type a network request (e.g. "3 routers in a ring using OSPF").
2. LangGraph interprets it and generates an MCP-compliant model.
3. You can customize configs (hostnames, IPs, VLANs, etc.) in the table.
4. Preview the topology visually.
5. Push to CML — it creates the lab, nodes, interfaces, and starts the simulation.

---

## 📚 Example Templates Included

- `Hub and Spoke (3 Routers)`
- `Full Mesh (STATIC)`
- `Campus LAN (VLANs & RoS)`
- `Full Mesh OSPF`
- `Full Mesh EIGRP`
- `Multi-Site WAN + LAN Mega-Lab (Multi-Area OSPF + PCs)`

---

## 🔐 Security Note

This app uses local environment variables to protect CML credentials and OpenAI keys. Never commit `.env` to version control.

---

## 🤝 Contributing

PRs welcome! Feature ideas include:
- Dynamic interface assignment by dropdown
- Visual diff for config changes
- Export to Visio or NetBox format

---

## 📜 License

MIT © 2025 [Nicholas Calcutti](https://technicalcutti.tech)

---