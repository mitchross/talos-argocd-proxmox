# Open WebUI with SearXNG and MCP Support

Enhanced Open WebUI deployment with internet search capabilities and Model Context Protocol (MCP) support.

## Features

### 🔍 Web Search Integration
- **SearXNG Integration**: Privacy-focused web search using your existing SearXNG instance
- **Real-time Results**: Get current information directly in your AI conversations
- **Configurable**: Adjustable result count and concurrent requests

### 🛠️ MCP Tool Support
- **Time Server**: Get current time and date information
- **Multi-Tool Server**: Advanced MCP capabilities including:
  - Filesystem operations
  - Memory management
  - SQLite database interactions

## Deployment

Apply all configurations:
```bash
kubectl apply -k my-apps/ai/ollama-webui/
```

Optional advanced MCP features:
```bash
kubectl apply -f my-apps/ai/ollama-webui/mcp-config.yaml
```

## Configuration

### Web Search
Web search is automatically enabled with SearXNG integration. Click the '+' button in chat to enable web search for specific queries.

### MCP Tools
Add MCP tools in Open WebUI:
1. Go to **Settings → Tools**
2. Add endpoint: `http://mcpo.ollama-webui.svc.cluster.local:8000`
3. API Key: `mcp-demo-key`

## Access

Open WebUI: https://ollama-webui.vanillax.me

## Files

- `configmap.yaml` - Main configuration with SearXNG and MCP settings
- `mcpo-deployment.yaml` - MCP server deployment
- `mcp-config.yaml` - Advanced MCP configuration (optional)
- `kustomization.yaml` - Kustomize configuration 