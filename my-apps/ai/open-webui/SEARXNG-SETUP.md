# SearXNG integration with Open WebUI

## Quick setup steps

### 1. Deploy updated configuration
```bash
kubectl apply -k my-apps/ai/open-webui/
```

### 2. Manual UI configuration (if environment variables don't work)
1. Open Open WebUI: https://open-webui.vanillax.me
2. Go to **Settings** → **Web Search**
3. Enable **Web Search** toggle
4. Set **Web Search Engine** to `searxng`
5. Set **Searxng Query URL** to: 
   ```
   https://search.vanillax.me/search?q=<query>&format=json
   ```
6. Set **Search Result Count** to `5`
7. Set **Concurrent Requests** to `10`
8. **Save** the settings

### 3. Test web search
1. Create a new chat
2. Click the **+** button next to the message input
3. Toggle **Web Search** ON
4. Ask a question that requires current information
5. You should see search results in the response

## Troubleshooting

### Problem: 403 Forbidden error
This is the most common issue.

**Symptoms.** Open WebUI logs this error:
```
403 Client Error: Forbidden for url: https://search.vanillax.me/search?q=...&format=json
```

**Root cause.** SearXNG's bot detection blocks API requests from Open WebUI.

**Solution.** Deploy the updated SearXNG configuration that disables bot detection:
```bash
# Redeploy SearXNG with API-friendly configuration
kubectl apply -k my-apps/knowledge/searxng/

# Wait for rollout to complete
kubectl rollout status deployment/searxng -n searxng

# Test the API
bash my-apps/knowledge/searxng/test-api.sh
```

**What was fixed:**
- Disabled HTTP User-Agent bot detection
- Disabled HTTP Accept header checks
- Increased rate limits for API access
- Added CORS headers

### Problem: SearXNG Query URL field is empty
**Solution.** Enter the URL manually in the UI settings:
- URL: `https://search.vanillax.me/search?q=<query>&format=json`
- **Important.** Include `&format=json` at the end

### Problem: Web search not working
Check these steps:

1. Test the API directly (use the provided test script):
   ```bash
   bash my-apps/knowledge/searxng/test-api.sh
   ```

2. Verify SearXNG is accessible:
   ```bash
   curl "https://search.vanillax.me/search?q=test&format=json" \
     -H "User-Agent: OpenWebUI/1.0"
   ```

3. Check Open WebUI logs:
   ```bash
   kubectl logs -n open-webui deployment/open-webui -f
   ```

4. Verify environment variables are loaded:
   ```bash
   kubectl exec -n open-webui deployment/open-webui -- env | grep RAG
   ```

5. Test connectivity from the Open WebUI pod:
   ```bash
   kubectl exec -n open-webui deployment/open-webui -- \
     curl "https://search.vanillax.me/search?q=test&format=json"
   ```

### Problem: Search returns empty results
Possible causes:
- SearXNG JSON format not enabled (already configured)
- Network connectivity issues
- SSL certificate problems

Solutions:
- Check SearXNG logs: `kubectl logs -n searxng deployment/searxng`
- Test manual search in SearXNG web interface
- Verify JSON format in SearXNG settings

## Configuration files

### Environment variables (ConfigMap)
Key variables for SearXNG integration:
```yaml
ENABLE_RAG_WEB_SEARCH: "True"
RAG_WEB_SEARCH_ENGINE: "searxng"
SEARXNG_QUERY_URL: "https://search.vanillax.me/search?q=<query>&format=json"
RAG_WEB_SEARCH_TRUST_ENV: "True"  # Important for proxy support
```

### SearXNG requirements
Your SearXNG must have JSON format enabled in `config/settings.yaml`:
```yaml
search:
  formats:
    - html
    - json  # ← This is required
```

### Bot detection configuration
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

1. **Enable per conversation.** Toggle web search ON for each chat session
2. **Web search indicator.** The chat shows search queries and results
3. **Result integration.** Open WebUI adds search results to responses automatically

## Quick test commands

```bash
# Test API from command line
curl "https://search.vanillax.me/search?q=weather&format=json" \
  -H "User-Agent: OpenWebUI/1.0"

# Run comprehensive test
bash my-apps/knowledge/searxng/test-api.sh

# Check if bot detection is disabled
kubectl logs -n searxng deployment/searxng | grep -i bot
```

## Notes
- Web search is enabled per-session (reloading page disables it)
- Environment variables may not always populate UI fields automatically
- Manual UI configuration is sometimes required
- Adjust the search result count as needed
- 403 errors are usually fixed by redeploying with the updated bot detection config 