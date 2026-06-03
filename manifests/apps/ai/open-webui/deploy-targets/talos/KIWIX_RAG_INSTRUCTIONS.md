# Kiwix RAG Setup Instructions

Your Kiwix RAG (Retrieval-Augmented Generation) setup is configured using the Model Context Protocol (MCP).

## Components
1.  **Kiwix Server**: Hosting your ZIM files (e.g., Wikipedia).
2.  **MCP Kiwix Bridge (`mcpo-kiwix`)**: A service that exposes a `fetch` tool to the LLM, allowing it to query the Kiwix server.
3.  **Open WebUI**: Configured to see `mcpo-kiwix` as an external tool provider.

## Prerequisites
*   **ZIM Files**: Ensure you have downloaded `.zim` files (like Wikipedia) into the `kiwix-data` PVC mounted by the Kiwix deployment.
    *   The Kiwix server is accessible at: `http://kiwix.kiwix.svc.cluster.local:8080`

## Usage in Open WebUI

To enable the LLM to use Kiwix effectively, you should use a **System Prompt** that instructs it on how to search and navigate the offline encyclopedia.

### Recommended System Prompt

Copy and paste this into your Model settings or System Prompt configuration in Open WebUI:

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
*   **No Tools Used**: Ensure `ENABLE_TOOLS` is True in Open WebUI settings and the model you are using supports tool calling (e.g., Llama 3.1, GPT-4o-mini).
*   **Fetch Error**: Check if the Kiwix service is running and if the URL is correct.
*   **Empty Results**: Verify ZIM files are loaded in the Kiwix server.
