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

### Problem: 403 Forbidden Error 🚨
**This is the most common issue!**

**Symptoms**: Error in Open WebUI logs:
```
403 Client Error: Forbidden for url: https://search.vanillax.me/search?q=...&format=json
```

**Root Cause**: SearXNG's bot detection is blocking API requests from Open WebUI

**Solution**: Deploy the updated SearXNG configuration that disables bot detection:
```bash
# Redeploy SearXNG with API-friendly configuration
kubectl apply -k my-apps/privacy/searxng/

# Wait for rollout to complete
kubectl rollout status deployment/searxng -n searxng

# Test the API
bash my-apps/privacy/searxng/test-api.sh
```

**What was fixed**:
- Disabled HTTP User-Agent bot detection
- Disabled HTTP Accept header checks  
- Increased rate limits for API access
- Added proper CORS headers

### Problem: SearXNG Query URL field is empty
**Solution**: Manually enter the URL in the UI settings:
- URL: `https://search.vanillax.me/search?q=<query>&format=json`
- **Important**: Include `&format=json` at the end

### Problem: Web search not working
**Check these steps**:

1. **Test API directly** (use the provided test script):
   ```bash
   bash my-apps/privacy/searxng/test-api.sh
   ```

2. **Verify SearXNG is accessible**:
   ```bash
   curl "https://search.vanillax.me/search?q=test&format=json" \
     -H "User-Agent: OpenWebUI/1.0"
   ```

3. **Check Open WebUI logs**:
   ```bash
   kubectl logs -n ollama-webui deployment/ollama-webui -f
   ```

4. **Verify environment variables are loaded**:
   ```bash
   kubectl exec -n ollama-webui deployment/ollama-webui -- env | grep RAG
   ```

5. **Test connectivity from Open WebUI pod**:
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

### Bot Detection Configuration (Fixed! ✅)
The updated `config/limiter.toml` disables bot detection that was causing 403 errors:
```toml
[botdetection.http_user_agent]
disable = true

[botdetection.http_accept]  
disable = true

[botdetection.ip_limit]
window = 300  # 5 minutes
max_request = 1000  # Allow many requests
```

## Usage

1. **Enable per conversation**: Web search must be toggled ON for each chat session
2. **Web search indicator**: You'll see search queries and results in the chat
3. **Result integration**: Search results are automatically integrated into responses

## Quick Test Commands

```bash
# Test API from command line
curl "https://search.vanillax.me/search?q=weather&format=json" \
  -H "User-Agent: OpenWebUI/1.0"

# Run comprehensive test
bash my-apps/privacy/searxng/test-api.sh

# Check if bot detection is disabled
kubectl logs -n searxng deployment/searxng | grep -i bot
```

## Notes
- Web search is enabled per-session (reloading page disables it)
- Environment variables may not always populate UI fields automatically
- Manual UI configuration is sometimes required
- Search results count can be adjusted based on needs
- **403 errors are usually fixed by redeploying with the updated bot detection config** ✅ 