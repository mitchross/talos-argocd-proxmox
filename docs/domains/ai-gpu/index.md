# Local AI starter kit

**Purpose:** explain the parts of a self-hosted AI setup, what each part does,
and the order to build them. This homelab is the worked example.
**Status:** current state. Every part below runs here today.

## The idea in one paragraph

Run a large language model (LLM) on your own graphics cards, so everyday work
is free and stays private. Put one proxy in front of it. Every app and agent
calls the proxy, never the model. The proxy can send hard work to a paid cloud
model, and it records every request so you can see what ran and what it cost.

```mermaid
flowchart LR
    subgraph People and tools
        Chat[Chat UI]
        Pi[Desk agent: Pi]
        Hermes[Background agent: Hermes]
        Apps[Other apps]
    end
    Proxy[Proxy: LiteLLM]
    Router{{Router: pi-auto<br/>easy or hard?}}
    Local[Model server: vLLM<br/>Qwen on 2x RTX 3090<br/>free, private]
    Cloud[Cloud model: DeepSeek Flash<br/>via OpenRouter, paid]
    Metrics[Metrics: Prometheus + Grafana]
    Traces[Traces: Langfuse]
    Chat --> Proxy
    Pi --> Proxy
    Hermes --> Proxy
    Apps --> Proxy
    Proxy --> Router
    Router -->|easy| Local
    Router -->|hard| Cloud
    Proxy -.-> Metrics
    Proxy -.-> Traces
    Local -.-> Metrics
```

## The parts

| Part | What it does | Here | Lives in |
|---|---|---|---|
| **GPUs** | Do the math that runs the model | 2x RTX 3090, 24 GB each, 220 W cap | GPU worker node |
| **Model** | The weights: a large file of numbers that produces answers | Qwen3.8 27B, FP8 | NAS, copied to local disk |
| **Model server** | Loads the model on the GPUs and answers over an OpenAI-style API | vLLM | [`my-apps/ai/vllm/`](https://github.com/mitchross/talos-argocd-proxmox/tree/main/my-apps/ai/vllm) |
| **Proxy** | One URL and key for every client; maps model names to backends; holds cloud keys; records requests | LiteLLM | [`my-apps/ai/litellm/`](https://github.com/mitchross/talos-argocd-proxmox/tree/main/my-apps/ai/litellm) |
| **Cloud model** | A stronger model for work the local one gets wrong | DeepSeek Flash via OpenRouter | OpenRouter account, key in 1Password |
| **Router** | Grades each request and picks local or cloud | LiteLLM `pi-auto` route | [`litellm/config.yaml`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/ai/litellm/config.yaml) |
| **Chat UI** | A ChatGPT-style web page for people | Open WebUI | [`my-apps/ai/open-webui/`](https://github.com/mitchross/talos-argocd-proxmox/tree/main/my-apps/ai/open-webui) |
| **Desk agent** | Codes with you in a terminal: reads files, runs commands, edits | Pi | `~/.pi/agent/` on each PC |
| **Background agent** | Runs without you: checks, daily digest, chat, opens PRs | Hermes | [`my-apps/development/hermes/`](https://github.com/mitchross/talos-argocd-proxmox/tree/main/my-apps/development/hermes) |
| **Memory** | Lets an agent remember across sessions | Hindsight | [`my-apps/knowledge/hindsight/`](https://github.com/mitchross/talos-argocd-proxmox/tree/main/my-apps/knowledge/hindsight) |
| **Metrics** | Counts and trends: requests, local vs paid, speed, GPU power | Prometheus + Grafana | [`dashboards/ai/`](https://github.com/mitchross/talos-argocd-proxmox/tree/main/monitoring/metrics/prometheus-stack/dashboards/ai) |
| **Traces** | One record per request: prompt, answer, tokens, cost, routing reason | Langfuse | [`my-apps/ai/langfuse/`](https://github.com/mitchross/talos-argocd-proxmox/tree/main/my-apps/ai/langfuse) |
| **Secrets** | Delivers keys to pods without putting them in Git | 1Password + External Secrets | `ExternalSecret` per namespace |

The proxy is the centre. Every other part either sits behind it (models) or in
front of it (people, apps, agents), and it feeds both measurement tools.

## Build order

Build in this order. Each step needs the one before it, and each ends with a
check that proves it works.

### 1. Run the model

Put the model server on the GPUs and load the model.

| Choice | Why |
|---|---|
| 27B model in FP8 | Fits two 24 GB cards with a 262,144-token context window |
| vLLM | Serves many requests at once; speaks the OpenAI API every tool expects |
| Two cards (TP=2) | One card works; two read long prompts faster ([one vs two](single-vs-dual-3090.md)) |
| 220 W per card | Less heat and noise for a small speed loss |

**Done when:**

```bash
curl -s https://vllm.vanillax.me/v1/models | jq -r '.data[].id'
```

prints `qwen3.8-27b`.

**Gotcha:** one app owns a card at a time. To give the cards to image
generation, follow the [GPU scale-swap runbook](gpu-scale-swap.md).

### 2. Put the proxy in front

Point LiteLLM at vLLM and give it a master key. From now on, nothing calls vLLM
directly.

| Who calls | URL |
|---|---|
| Apps in the cluster | `http://litellm-service.litellm.svc.cluster.local:4000/v1` |
| People's PCs | `https://litellm.vanillax.me/v1` |

**Done when:** a request with `"model":"qwen3.8-27b"` to the proxy URL answers.

**Gotcha:** a client that calls vLLM directly still works, but skips every
record in step 4. Make the proxy the only documented URL.

### 3. Connect the first users

Point the chat UI and apps at the proxy. Each namespace gets the proxy key from
1Password through an `ExternalSecret`, never from a file in Git.

**Done when:** Open WebUI answers a chat message.

### 4. Measure before you add the cloud

Turn on the proxy's `prometheus` and `langfuse_otel` callbacks, and load the
Grafana dashboards. Do this before step 5, so the first paid request is visible.

| Question | Tool |
|---|---|
| How many requests? How fast? Any errors? | Grafana `/d/ai-gateway-analytics` |
| Is the model server busy? | Grafana `/d/vllm-inference` |
| Are the cards hot or at full power? | Grafana `/d/gpu-overview` |
| What did one request say, and why did it go where it did? | Langfuse |

**Done when:** the step 3 chat message appears in Grafana and as a trace in
Langfuse. Details: [AI gateway and analytics](ai-observability.md).

### 5. Add the cloud model and the router

Add the cloud model to the proxy, then the `pi-auto` route that chooses per
request:

1. A short local call, the *classifier*, grades the request as `SIMPLE`,
   `MEDIUM`, `COMPLEX` or `REASONING`.
2. `SIMPLE` and `MEDIUM` go to the local model. The others go to the cloud.
3. These cases also go to the cloud: the classifier fails, the agent repeats
   the same tool call, the prompt is too big, or the model server is down.

Only clients that ask for `pi-auto` can reach the cloud. Every other client
stays local and fails instead of paying when the model server is down.

**Done when:** one easy and one hard request go to different models:

```bash
K=$(cat ~/.pi/agent/litellm-api-key)
for p in "What is 2+2?" "Design a lock-free MPMC queue in Rust and prove it linearizable."; do
  curl -s -D - -o /dev/null https://litellm.vanillax.me/v1/chat/completions \
    -H "Authorization: Bearer $K" -H 'Content-Type: application/json' \
    -d "{\"model\":\"pi-auto\",\"max_tokens\":256,\"messages\":[{\"role\":\"user\",\"content\":\"$p\"}]}" \
    | grep -i x-litellm-model-name
done
```

Expect `openai/qwen3.8-27b`, then `openrouter/~deepseek/deepseek-flash-latest`.
Grafana `/d/pi-routing` then shows the local/paid split.
Details: [Model catalog](model-catalog.md).

**Gotcha:** one conversation can move between local and cloud message by
message. Prompts sent to the cloud leave the building.

### 6. Give people agents

An agent works in a loop: ask the model, run a tool, send back the result,
repeat. One task can make dozens of requests, which is why the router in step 5
pays off.

| | Desk agent (Pi) | Background agent (Hermes) |
|---|---|---|
| Runs | on each person's PC | one pod in the cluster, all day |
| Use it for | coding with someone at the keyboard | health checks, a daily digest, chat, PRs while nobody watches |
| Models | the person picks local, cloud or `pi-auto` | Claude Sonnet as the brain; Qwen as a free choice |
| Memory | the current session | Hindsight, across sessions |
| Limits | what the person's PC can reach | read-only cluster access; humans merge its PRs |

**Done when:** Pi answers "what does this repo do?" and Hermes's Status page
shows the gateway running.
Details: [Pi and Hermes agents](pi-agent-local-dev.md),
[Hermes in the cluster](hermes.md), [Hermes on another cluster](hermes-other-clusters.md).

### 7. Run it day to day

| Task | Where |
|---|---|
| Check the local/paid split and spend weekly | Grafana `/d/pi-routing` |
| Find why a request went to the cloud | Langfuse, `routing_decision.cause` |
| Change models, router tiers or limits | PR to `litellm/config.yaml` |
| Tune context and speed | [3090 LLM optimization](3090-llm-optimization.md) |
| Swap the cards to another app | [GPU scale-swap runbook](gpu-scale-swap.md) |

## Words you need

| Word | Means here |
|---|---|
| **LLM** | A large language model: reads a prompt, writes an answer |
| **token** | A piece of a word, about 4 characters. Limits and prices count tokens |
| **context window** | The most tokens one request can hold, prompt plus answer |
| **inference** | Running the model to get an answer, not training it |
| **FP8** | Weights stored at 8 bits each, so a bigger model fits the cards |
| **tier** | The router's grade: `SIMPLE`, `MEDIUM`, `COMPLEX`, `REASONING` |
| **reasoning effort** | How long the model "thinks" first: off, low, medium, high, xhigh, max |
| **agent** | An LLM that can also run tools |
| **Pi** | A terminal coding agent from [pi.dev](https://pi.dev). Not Raspberry Pi |

## Rules that keep it safe

- Use one model server. Here that is vLLM; do not add Ollama beside it.
- Give each graphics card to one app at a time.
- Make every client call the proxy, never the model server.
- Keep private work on the local model: use `pi-qwen-only`, not `pi-auto`.
- Change everything through Git and ArgoCD. Do not edit the cluster by hand.
