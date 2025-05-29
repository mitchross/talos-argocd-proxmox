#!/bin/bash

echo "=== SearXNG API Test Script ==="
echo

# Test 1: Direct external access
echo "1. Testing external API access..."
curl -s -w "Status: %{http_code}\n" \
  "https://search.vanillax.me/search?q=test&format=json" \
  -H "Accept: application/json" \
  -H "User-Agent: OpenWebUI/1.0" | head -5
echo

# Test 2: From Open WebUI pod (if available)
echo "2. Testing from Open WebUI pod..."
kubectl exec -n ollama-webui deployment/ollama-webui -- \
  curl -s -w "Status: %{http_code}\n" \
  "https://search.vanillax.me/search?q=test&format=json" \
  -H "Accept: application/json" \
  -H "User-Agent: OpenWebUI/1.0" 2>/dev/null | head -5 || echo "Could not test from Open WebUI pod"
echo

# Test 3: Check SearXNG logs for errors
echo "3. Recent SearXNG logs..."
kubectl logs -n searxng deployment/searxng --tail=10
echo

# Test 4: Check if SearXNG service is accessible internally
echo "4. Testing internal service access..."
kubectl run test-pod --rm -i --image=curlimages/curl --restart=Never -- \
  curl -s -w "Status: %{http_code}\n" \
  "http://searxng.searxng.svc.cluster.local:8080/search?q=test&format=json" \
  -H "Accept: application/json" \
  -H "User-Agent: OpenWebUI/1.0" 2>/dev/null | head -5 || echo "Could not test internal access"
echo

echo "=== End of tests ==="
echo
echo "If you see 403 errors, redeploy SearXNG with: kubectl apply -k my-apps/privacy/searxng/"
echo "If you see 200 status, the API is working and the issue may be in Open WebUI configuration." 