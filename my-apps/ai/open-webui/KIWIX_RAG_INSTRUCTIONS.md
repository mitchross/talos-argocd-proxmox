# Kiwix RAG setup instructions

The Kiwix RAG (Retrieval-Augmented Generation) setup uses the Model Context Protocol (MCP).

## Components
1.  **Kiwix server.** Hosts your ZIM files, such as Wikipedia.
2.  **MCP Kiwix bridge (`mcpo-kiwix`).** Exposes a `fetch` tool that the LLM uses to query the Kiwix server.
3.  **Open WebUI.** Uses `mcpo-kiwix` as an external tool provider.

## Prerequisites
*   **ZIM files.** Download `.zim` files (like Wikipedia) into the `kiwix-data` PVC mounted by the Kiwix deployment.
    *   The Kiwix server URL is: `http://kiwix.kiwix.svc.cluster.local:8080`

## Usage in Open WebUI

Give the LLM a system prompt that tells it how to search and navigate the offline encyclopedia.

### Recommended system prompt

Paste this into the model settings or system prompt configuration in Open WebUI:

```text
You have access to an offline encyclopedia (Kiwix) via the 'fetch' tool.
The Kiwix server is located at: http://kiwix.kiwix.svc.cluster.local:8080

To search for information:
1. Use the 'fetch' tool to search: "http://kiwix.kiwix.svc.cluster.local:8080/search?pattern=YOUR_SEARCH_QUERY"
2. The result will be an HTML page containing search results. Read the links from this page.
3. To read an article, use 'fetch' again on the article URL found in the search results (e.g., "http://kiwix.kiwix.svc.cluster.local:8080/content/wikipedia_en_all_maxi_2025-08/Article_Name").

When asked about general knowledge or historical facts, ALWAYS check the offline encyclopedia first using these steps.
CITE your sources by referencing the article title.
```

### Verification
1.  Open a new chat in Open WebUI.
2.  Ensure "Tools" are enabled for the model.
3.  Ask a question: "Who won the World Cup in 2018? Search the offline encyclopedia."
4.  You should see the model use the `fetch` tool to query Kiwix and then retrieve the answer.

## Troubleshooting
*   **No tools used.** Ensure `ENABLE_TOOLS` is True in Open WebUI settings and the model you are using supports tool calling (e.g., Llama 3.1, GPT-4o-mini).
*   **Fetch error.** Check if the Kiwix service is running and if the URL is correct.
*   **Empty results.** Verify ZIM files are loaded in the Kiwix server.
