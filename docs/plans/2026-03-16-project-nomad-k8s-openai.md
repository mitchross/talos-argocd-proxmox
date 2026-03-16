# Project Nomad: Kubernetes + OpenAI-Compatible LLM Provider

**Date**: 2026-03-16
**Status**: Draft
**Scope**: Full — fork changes (LLMProvider abstraction + k8s manifests + CI) + this repo (ExternalSecret + deployment updates)

---

## Overview

Add OpenAI-compatible LLM backend support to [mitchross/project-nomad](https://github.com/mitchross/project-nomad) so it works with llama-cpp (and any OpenAI-compatible server). Add Kubernetes manifests with Kustomize for modular deployment of the **full Nomad stack** (all 9 services). Every optional service supports **BYO** (bring-your-own via URL) or **deploy** (uncomment in kustomization.yaml). Update the existing deployment in this repo to use ExternalSecrets and the new configuration.

## Two Repositories, Two Workstreams

| Repo | Changes | Branch |
|------|---------|--------|
| **mitchross/project-nomad** | LLMProvider abstraction, k8s manifests, GitHub Actions | `feature/openai-k8s` |
| **talos-argocd-proxmox** | ExternalSecret, updated configmap, image reference | `claude/install-project-nomad-XmxFL` |

---

## Part 1: Fork Changes (mitchross/project-nomad)

### 1A. LLMProvider Abstraction

**Goal**: Replace direct Ollama SDK usage with a provider interface. Two implementations: OllamaProvider (existing behavior) and OpenAIProvider (llama-cpp compatible).

#### New Files

```
admin/app/services/llm/
├── llm_provider.ts          # Interface definition
├── ollama_provider.ts       # Wraps existing Ollama SDK logic
├── openai_provider.ts       # OpenAI-compatible HTTP client
└── provider_factory.ts      # Creates provider based on env config
```

#### Interface Design

```typescript
// admin/app/services/llm/llm_provider.ts
export interface ChatMessage {
  role: 'system' | 'user' | 'assistant'
  content: string
}

export interface ChatRequest {
  model: string
  messages: ChatMessage[]
  stream?: boolean
  options?: {
    temperature?: number
    num_ctx?: number
    num_predict?: number
  }
}

export interface ChatResponseChunk {
  content: string
  done: boolean
  thinking?: string  // For models that support thinking
}

export interface EmbeddingResult {
  embeddings: number[][]
}

export interface ModelInfo {
  name: string
  size?: number
  modified_at?: string
  details?: Record<string, unknown>
}

export interface LLMProvider {
  // Core capabilities (required)
  chat(request: ChatRequest): Promise<string>
  chatStream(request: ChatRequest): AsyncGenerator<ChatResponseChunk>
  embed(model: string, input: string | string[]): Promise<EmbeddingResult>
  listModels(): Promise<ModelInfo[]>

  // Model management (optional — Ollama only)
  supportsModelManagement(): boolean
  pullModel?(name: string, onProgress?: (status: string, completed?: number, total?: number) => void): Promise<void>
  deleteModel?(name: string): Promise<void>
  showModel?(name: string): Promise<Record<string, unknown> | null>

  // Provider info
  readonly providerName: string
}
```

#### Provider Factory

```typescript
// admin/app/services/llm/provider_factory.ts
export function createLLMProvider(): LLMProvider {
  const provider = env.get('LLM_PROVIDER', 'ollama') // 'ollama' | 'openai'
  const host = env.get('LLM_HOST')

  switch (provider) {
    case 'openai':
      return new OpenAIProvider({
        baseURL: host,  // e.g., http://llama-cpp:8080/v1
        apiKey: env.get('LLM_API_KEY', 'unused'),
        embeddingModel: env.get('EMBEDDING_MODEL', 'nomic-embed-text:v1.5'),
        embeddingDimensions: parseInt(env.get('EMBEDDING_DIMENSIONS', '768')),
      })
    case 'ollama':
    default:
      return new OllamaProvider({ host })
  }
}
```

#### OpenAI Provider Implementation

```typescript
// admin/app/services/llm/openai_provider.ts
// Uses fetch() — no extra npm dependency needed
// Targets /v1/chat/completions, /v1/embeddings, /v1/models
export class OpenAIProvider implements LLMProvider {
  readonly providerName = 'openai'

  constructor(private config: {
    baseURL: string
    apiKey: string
    embeddingModel: string
    embeddingDimensions: number
  }) {}

  async chat(request: ChatRequest): Promise<string> {
    const response = await fetch(`${this.config.baseURL}/chat/completions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${this.config.apiKey}` },
      body: JSON.stringify({
        model: request.model,
        messages: request.messages,
        temperature: request.options?.temperature,
        max_tokens: request.options?.num_predict,
        stream: false,
      }),
    })
    const data = await response.json()
    return data.choices[0].message.content
  }

  async *chatStream(request: ChatRequest): AsyncGenerator<ChatResponseChunk> {
    // SSE streaming via fetch + ReadableStream
    // Parse "data: {...}" lines, yield { content, done }
  }

  async embed(model: string, input: string | string[]): Promise<EmbeddingResult> {
    const response = await fetch(`${this.config.baseURL}/embeddings`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${this.config.apiKey}` },
      body: JSON.stringify({
        model: model || this.config.embeddingModel,
        input: Array.isArray(input) ? input : [input],
      }),
    })
    const data = await response.json()
    return { embeddings: data.data.map((d: any) => d.embedding) }
  }

  async listModels(): Promise<ModelInfo[]> {
    const response = await fetch(`${this.config.baseURL}/models`, {
      headers: { 'Authorization': `Bearer ${this.config.apiKey}` },
    })
    const data = await response.json()
    return data.data.map((m: any) => ({ name: m.id, size: 0 }))
  }

  supportsModelManagement(): boolean { return false }
}
```

#### Refactoring Existing Services

**OllamaService** → **LLMService**:
- Move Ollama-specific logic into `OllamaProvider`
- `LLMService` holds a `LLMProvider` instance from factory
- Docker-based service discovery moves into `OllamaProvider` only (env-based fallback)
- `LLM_HOST` env var bypasses Docker discovery entirely

**RagService** changes:
- Replace `this.ollamaService.ollama.embed(...)` with `this.llmService.provider.embed(...)`
- Make `EMBEDDING_MODEL` and `EMBEDDING_DIMENSION` configurable via env vars
- Keep Nomic-specific prefixes (`search_document:`, `search_query:`) as defaults, configurable via env

**OllamaController** changes:
- Rename to `ChatController` (or keep for backwards compat)
- Use `LLMService` instead of direct `OllamaService`
- Streaming handler adapts to unified `ChatResponseChunk` format
- Model management endpoints: return 501 if `!provider.supportsModelManagement()`

**BenchmarkService** changes:
- Use `LLMService` for inference calls
- Model detection (size parsing from name) stays as-is

#### New Environment Variables

```env
# LLM Provider Configuration
LLM_PROVIDER=openai              # 'ollama' or 'openai' (default: ollama)
LLM_HOST=http://llama-cpp:8080/v1  # Base URL for LLM API
LLM_API_KEY=unused               # API key (unused for local servers)

# Embedding Configuration
EMBEDDING_MODEL=nomic-embed-text:v1.5  # Model name for embeddings
EMBEDDING_DIMENSIONS=768               # Vector dimensions (must match Qdrant collection)

# Legacy (still works, maps to LLM_HOST if LLM_PROVIDER not set)
OLLAMA_HOST=http://ollama:11434   # Backwards compatible

# Optional Service URLs (BYO pattern — set URL to use external, leave empty to use in-cluster)
KIWIX_URL=                       # e.g., http://my-kiwix:8080 or leave empty for in-cluster
KOLIBRI_URL=                     # e.g., http://my-kolibri:8080 or leave empty for in-cluster
PROTOMAPS_URL=                   # e.g., http://my-protomaps:8080 or leave empty for in-cluster
CYBERCHEF_URL=                   # e.g., http://my-cyberchef:8080 or leave empty for in-cluster
FLATNOTES_URL=                   # e.g., http://my-flatnotes:8080 or leave empty for in-cluster
```

**BYO pattern**: If the URL env var is set, Nomad's UI links/iframes point to that external URL. If empty and the service is deployed in-cluster, it auto-resolves to `<service>.project-nomad.svc.cluster.local`.

**Backwards compatibility**: If `LLM_PROVIDER` is not set but `OLLAMA_HOST` is, default to Ollama provider with that host.

### 1B. Kubernetes Manifests

**Location**: `k8s/` directory in the fork

#### Full Service Matrix

| Service | Image | Required? | BYO Config | Ports | Storage |
|---------|-------|-----------|------------|-------|---------|
| **Nomad** (admin) | `ghcr.io/mitchross/project-nomad:main` | Yes | — | 8080 | PVC 10Gi (uploads/ZIM) |
| **MySQL** | `mysql:8.0` | Yes | `DB_HOST`, `DB_PORT`, `DB_USER` | 3306 | PVC 10Gi |
| **Redis** | `redis:7-alpine` | Yes | `REDIS_HOST`, `REDIS_PORT` | 6379 | — |
| **Qdrant** | `qdrant/qdrant:latest` | Yes (RAG) | `QDRANT_HOST` | 6333, 6334 | PVC 5Gi |
| **Kiwix** | `ghcr.io/kiwix/kiwix-serve:3.8.1` | Optional | `KIWIX_URL` | 8080 | PVC (shares Nomad's ZIM dir) |
| **Kolibri** | `learningequality/kolibri:latest` | Optional | `KOLIBRI_URL` | 8080 | PVC 10Gi |
| **ProtoMaps** | `protomaps/go-pmtiles:latest` | Optional | `PROTOMAPS_URL` | 8080 | PVC (map tiles) |
| **CyberChef** | `ghcr.io/gchq/cyberchef:latest` | Optional | `CYBERCHEF_URL` | 8080 | — |
| **FlatNotes** | `dullage/flatnotes:latest` | Optional | `FLATNOTES_URL` | 8080 | PVC 1Gi |

#### BYO vs Deploy Pattern

For **every** service, the user has two choices:

1. **BYO** — Already have it running? Set the URL env var in the ConfigMap. Don't include the service in kustomization.yaml.
2. **Deploy** — Don't have it? Include the service directory in kustomization.yaml. The ConfigMap defaults point to the in-cluster service.

The ConfigMap always has the URL vars. The Nomad app always reads them. The only question is: does the URL point to an external service or an in-cluster one?

```yaml
# configmap.yaml — service URLs section
data:
  # Required services (in-cluster defaults shown)
  DB_HOST: "mysql"                    # Override for BYO MySQL
  REDIS_HOST: "redis"                 # Override for BYO Redis
  QDRANT_HOST: "http://qdrant:6333"   # Override for BYO Qdrant

  # Optional services — empty = disabled, URL = BYO, in-cluster service name = deployed
  KIWIX_URL: ""                       # "http://kiwix:8080" if deployed, or external URL
  KOLIBRI_URL: ""                     # "http://kolibri:8080" if deployed, or external URL
  PROTOMAPS_URL: ""                   # "http://protomaps:8080" if deployed, or external URL
  CYBERCHEF_URL: ""                   # "http://cyberchef:8080" if deployed, or external URL
  FLATNOTES_URL: ""                   # "http://flatnotes:8080" if deployed, or external URL
```

#### Directory Structure

```
k8s/
├── base/
│   ├── nomad/
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   ├── configmap.yaml          # All env vars including service URLs
│   │   └── kustomization.yaml
│   ├── mysql/
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   ├── pvc.yaml
│   │   └── kustomization.yaml
│   ├── redis/
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   └── kustomization.yaml
│   ├── qdrant/
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   ├── pvc.yaml
│   │   └── kustomization.yaml
│   ├── kiwix/                      # Optional — offline Wikipedia
│   │   ├── deployment.yaml         # Serves ZIM files on port 8080
│   │   ├── service.yaml
│   │   └── kustomization.yaml      # NOTE: shares Nomad's storage PVC for ZIM files
│   ├── kolibri/                    # Optional — Khan Academy
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   ├── pvc.yaml
│   │   └── kustomization.yaml
│   ├── protomaps/                  # Optional — offline maps
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   ├── pvc.yaml
│   │   └── kustomization.yaml
│   ├── cyberchef/                  # Optional — data tools (stateless)
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   └── kustomization.yaml
│   ├── flatnotes/                  # Optional — note-taking
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   ├── pvc.yaml
│   │   └── kustomization.yaml
│   ├── namespace.yaml
│   └── kustomization.yaml          # Toggle services here
└── overlays/
    └── production/                 # Example production overlay
        ├── kustomization.yaml      # Patches for production
        └── patches/
            └── nomad-config.yaml   # Override service URLs for BYO
```

**Design principles**:
- Each service is a separate Kustomize component in `base/`
- Required services are always included; optional services are commented out by default
- ConfigMap always has URL vars — deploying a service just means the URL points to the in-cluster name
- BYO = set URL in overlay patch, don't include the service directory
- `base/` uses generic defaults (no cluster-specific values)
- `overlays/production/` shows how to customize for a specific cluster
- No Helm — pure Kustomize as requested

**Base kustomization.yaml**:
```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: project-nomad

resources:
  - namespace.yaml
  # Core (required)
  - nomad/
  - mysql/                # Or set DB_HOST for BYO MySQL
  - redis/                # Or set REDIS_HOST for BYO Redis
  - qdrant/               # Or set QDRANT_HOST for BYO Qdrant
  # Optional — uncomment to deploy, or set URL in configmap for BYO
  # - kiwix/              # Offline Wikipedia — set KIWIX_URL
  # - kolibri/            # Khan Academy — set KOLIBRI_URL
  # - protomaps/          # Offline maps — set PROTOMAPS_URL
  # - cyberchef/          # Data tools — set CYBERCHEF_URL
  # - flatnotes/          # Note-taking — set FLATNOTES_URL
```

**Example BYO overlay** (user has external Kiwix + Redis, deploys everything else):
```yaml
# overlays/production/patches/nomad-config.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: project-nomad-config
data:
  KIWIX_URL: "http://192.168.10.50:8080"   # BYO Kiwix on LAN
  REDIS_HOST: "redis.my-other-namespace.svc.cluster.local"  # BYO Redis
```

**Qdrant deployment** (new — currently not in Docker compose for management, but Nomad uses it for RAG):
- Image: `qdrant/qdrant:latest`
- Port: 6333 (HTTP) + 6334 (gRPC)
- PVC: 5Gi for vector storage
- No GPU needed

### 1C. GitHub Actions

```
.github/workflows/
├── build.yaml          # Build + push Docker image on push/PR
└── test.yaml           # Run tests (existing or new)
```

**build.yaml**:
```yaml
name: Build and Push Docker Image

on:
  push:
    branches: [main, develop, 'feature/**']
    tags: ['v*']
  pull_request:
    branches: [main]

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  build:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write

    steps:
      - uses: actions/checkout@v4

      - uses: docker/setup-buildx-action@v3

      - uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - uses: docker/metadata-action@v5
        id: meta
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
          tags: |
            type=ref,event=branch
            type=ref,event=pr
            type=semver,pattern={{version}}
            type=sha

      - uses: docker/build-push-action@v5
        with:
          context: ./admin
          push: ${{ github.event_name != 'pull_request' }}
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

**Result**: Images published to `ghcr.io/mitchross/project-nomad:<tag>`

---

## Part 2: This Repo (talos-argocd-proxmox)

### 2A. ExternalSecret Migration

Replace `my-apps/home/project-nomad/secret.yaml` with `externalsecret.yaml`:

```yaml
# my-apps/home/project-nomad/externalsecret.yaml
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: project-nomad-secrets
  namespace: project-nomad
spec:
  refreshInterval: "1h"
  secretStoreRef:
    kind: ClusterSecretStore
    name: 1password
  target:
    name: project-nomad-secrets
    creationPolicy: Owner
  data:
    - secretKey: APP_KEY
      remoteRef:
        key: project-nomad        # 1Password item name
        property: app_key
    - secretKey: DB_PASSWORD
      remoteRef:
        key: project-nomad
        property: db_password
    - secretKey: MYSQL_ROOT_PASSWORD
      remoteRef:
        key: project-nomad
        property: db_password     # Same value for both
```

**1Password item to create**: `project-nomad` in `homelab-prod` vault with fields:
- `app_key` — random 32+ char string
- `db_password` — MySQL root password

### 2B. Updated ConfigMap

```yaml
# my-apps/home/project-nomad/configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: project-nomad-config
  namespace: project-nomad
data:
  PORT: "8080"
  HOST: "0.0.0.0"
  LOG_LEVEL: "info"
  NODE_ENV: "production"
  SESSION_DRIVER: "cookie"
  DB_HOST: "mysql"
  DB_PORT: "3306"
  DB_USER: "root"
  DB_DATABASE: "nomad"
  DB_NAME: "nomad"
  DB_SSL: "false"
  REDIS_HOST: "redis-master.redis-instance.svc.cluster.local"
  REDIS_PORT: "6379"
  NOMAD_STORAGE_PATH: "/opt/project-nomad/storage"
  URL: "https://nomad.vanillax.me"
  # LLM Provider Configuration
  LLM_PROVIDER: "openai"
  LLM_HOST: "http://llama-cpp-service.llama-cpp.svc.cluster.local:8080/v1"
  LLM_API_KEY: "unused"
  # Embedding (uses llama-cpp server)
  EMBEDDING_MODEL: ""               # Use server default
  EMBEDDING_DIMENSIONS: "768"
  # Qdrant
  QDRANT_HOST: "http://qdrant.project-nomad.svc.cluster.local:6333"
  # Optional services — set URL for BYO, or point to in-cluster service if deployed
  KIWIX_URL: ""                  # Set if you have external Kiwix, e.g., "http://my-kiwix:8080"
  KOLIBRI_URL: ""                # Set if you have external Kolibri
  PROTOMAPS_URL: ""              # Set if you have external ProtoMaps
  CYBERCHEF_URL: ""              # Set if you have external CyberChef
  FLATNOTES_URL: ""              # Set if you have external FlatNotes
```

### 2C. Updated Deployment

- Change image from `ghcr.io/crosstalk-solutions/project-nomad:latest` to `ghcr.io/mitchross/project-nomad:main`
- Remove `OLLAMA_HOST` from configmap (replaced by `LLM_HOST`)
- Add `QDRANT_HOST` env var

### 2D. Kustomization Update

```yaml
# my-apps/home/project-nomad/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: project-nomad

resources:
  - namespace.yaml
  - externalsecret.yaml    # Was: secret.yaml
  - configmap.yaml
  - pvc.yaml
  - mysql-deployment.yaml
  - mysql-service.yaml
  - deployment.yaml
  - service.yaml
  - httproute.yaml
```

---

## Implementation Order

### Phase 1: Fork — LLMProvider Abstraction
1. Create `admin/app/services/llm/` directory with interface + factory
2. Implement `OllamaProvider` (extract from existing `OllamaService`)
3. Implement `OpenAIProvider` (new, fetch-based)
4. Refactor `OllamaService` → `LLMService` to use provider
5. Update `RagService` to use `LLMService` + configurable embedding model
6. Update `OllamaController` streaming to use unified format
7. Update `BenchmarkService` to use `LLMService`
8. Add new env vars to `.env.example`
9. Update Docker service discovery to be optional (env-based fallback)

### Phase 2: Fork — K8s Manifests + CI
10. Create `k8s/base/` core services: nomad, mysql, redis, qdrant (+ configmap with all service URLs)
11. Create `k8s/base/` optional services: kiwix, kolibri, protomaps, cyberchef, flatnotes
12. Create `k8s/overlays/production/` example with BYO patch
13. Add Dockerfile improvements if needed (multi-stage, etc.)
14. Add `.github/workflows/build.yaml` for GHCR publishing
15. Test image build

### Phase 3: This Repo — Deployment Updates
16. Create 1Password item `project-nomad`
17. Replace `secret.yaml` with `externalsecret.yaml`
18. Update `configmap.yaml` with LLM env vars + all service URLs (pointing to in-cluster defaults)
19. Update `deployment.yaml` image to `ghcr.io/mitchross/project-nomad:main`
20. Update `kustomization.yaml`
21. Commit and push

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Embedding model mismatch | Knowledge base vectors incompatible | Make embedding model configurable; document that changing models requires re-embedding |
| llama-cpp doesn't serve embeddings | RAG broken | llama-cpp supports `/v1/embeddings` — verify model is loaded with embedding support |
| Streaming format differences | Chat broken | Unified `ChatResponseChunk` type + thorough testing of both providers |
| Ollama-specific features (thinking, model show) | Feature regression | Graceful degradation — return null/empty when provider doesn't support |
| Qdrant not deployed | RAG broken | Include Qdrant in k8s base manifests; make RAG optional if Qdrant not reachable |

---

## Not In Scope

- Changing the upstream project-nomad (only fork changes)
- CNPG migration for MySQL (stays as simple deployment for now)
- GPU support for Nomad itself (it calls external LLM services)
- Automated vector migration tooling (manual re-embed if model changes)
- Modifying Nomad's Docker-based service management code to use K8s APIs (we bypass it entirely via env vars)
