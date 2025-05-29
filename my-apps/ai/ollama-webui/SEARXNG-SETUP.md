# SearXNG Integration with Open WebUI

## Quick Setup Steps

### 1. Deploy Updated Configuration
```bash
kubectl apply -k my-apps/ai/ollama-webui/
```

### 2. Manual UI Configuration (if environment variables don't work)
1. Open Open WebUI: https://ollama-webui.vanillax.me
2. Go to **Settings** → **Web Search**
3. Enable **Web Search** toggle
4. Set **Web Search Engine** to `searxng`
5. Set **Searxng Query URL** to: 
   ```
   https://search.vanillax.me/search?q=<query>&format=json
   ```
6. Set **Search Result Count**: `5`
7. Set **Concurrent Requests**: `10`
8. **Save** the settings

### 3. Test Web Search
1. Create a new chat
2. Click the **+** button next to the message input
3. Toggle **Web Search** ON
4. Ask a question that requires current information
5. You should see search results being integrated

## Troubleshooting

### Problem: SearXNG Query URL field is empty
**Solution**: Manually enter the URL in the UI settings:
- URL: `https://search.vanillax.me/search?q=<query>&format=json`
- **Important**: Include `&format=json` at the end

### Problem: Web search not working
**Check these steps**:

1. **Verify SearXNG is accessible**:
   ```bash
   # Test SearXNG directly
   curl "https://search.vanillax.me/search?q=test&format=json"
   ```

2. **Check Open WebUI logs**:
   ```bash
   kubectl logs -n ollama-webui deployment/ollama-webui -f
   ```

3. **Verify environment variables are loaded**:
   ```bash
   kubectl exec -n ollama-webui deployment/ollama-webui -- env | grep RAG
   ```

4. **Test connectivity from Open WebUI pod**:
   ```bash
   kubectl exec -n ollama-webui deployment/ollama-webui -- \
     curl "https://search.vanillax.me/search?q=test&format=json"
   ```

### Problem: Search returns empty results
**Possible causes**:
- SearXNG JSON format not enabled (already configured ✅)
- Network connectivity issues
- SSL certificate problems

**Solutions**:
- Check SearXNG logs: `kubectl logs -n searxng deployment/searxng`
- Test manual search in SearXNG web interface
- Verify JSON format in SearXNG settings

## Configuration Files

### Environment Variables (ConfigMap)
Key variables for SearXNG integration:
```yaml
ENABLE_RAG_WEB_SEARCH: "True"
RAG_WEB_SEARCH_ENGINE: "searxng"
SEARXNG_QUERY_URL: "https://search.vanillax.me/search?q=<query>&format=json"
RAG_WEB_SEARCH_TRUST_ENV: "True"  # Important for proxy support
```

### SearXNG Requirements
Your SearXNG must have JSON format enabled in `config/settings.yaml`:
```yaml
search:
  formats:
    - html
    - json  # ← This is required
```

## Usage

1. **Enable per conversation**: Web search must be toggled ON for each chat session
2. **Web search indicator**: You'll see search queries and results in the chat
3. **Result integration**: Search results are automatically integrated into responses

## Notes
- Web search is enabled per-session (reloading page disables it)
- Environment variables may not always populate UI fields automatically
- Manual UI configuration is sometimes required
- Search results count can be adjusted based on needs 