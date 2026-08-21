# llama.cpp — Qwen3.8-27B on one RTX 3090

This is the active OpenAI-compatible chat and vision backend:

- in cluster: `http://llama-cpp-service.llama-cpp.svc.cluster.local:8080/v1`
- on the LAN: `https://llama.vanillax.me/v1` and the compatibility hostname
  `https://vllm.vanillax.me/v1`
- served model: `qwen3.8-27b`

The runtime follows `club-3090/docs/SINGLE_CARD.md` at commit `4e6c3363` and
its `llamacpp/qwen38-27b-single-iq4xs` compose. The Kubernetes profile uses
the guide's serving-grade override: symmetric `q8_0` KV at 131,072 context,
rather than the incubating `q4_0` KV / 262K exhibit.

## Pinned inputs

| Input | Pin |
|---|---|
| Engine | `ghcr.io/ggml-org/llama.cpp:server-cuda-b10236@sha256:fd68d13013141833e8214ecad6e1fbefb532db6a00b980cdecfe33603dbf2675` |
| Model repository | `unsloth/Qwen3.8-27B-GGUF` revision `4ca720788d1e01f1bff70c033e0d0028fd02e502` |
| Weights | `Qwen3.8-27B-UD-IQ4_XS.gguf`, SHA-256 `40fac4050e940397dbf13087afd50f4734a11805bf9d65ef8ddd7483470e6199` |
| Vision projector | `mmproj-F16.gguf`, SHA-256 `cbb841a9ee0636b2ec172f5bb8df2ea8dfeb01e90fe7c6126581d662a0b4e43e` |

The wave-0 Sync hook downloads and verifies both public artifacts on the
existing RWX model share. The wave-1 Deployment mounts the share read-only and
starts only after the hook succeeds.

## Runtime profile

- one whole RTX 3090, one parallel slot
- UD-IQ4_XS weights plus the F16 vision projector
- symmetric q8_0 K/V cache, 131,072-token allocation
- built-in MTP drafter at depth 2
- Flash Attention, 4,096 batch and 512 micro-batch
- native Jinja template, reasoning off by default
- non-thinking sampling: temperature 0.7, top-p 0.8, top-k 20,
  presence penalty 1.5

The guide measured its `q4_0` / 262K profile at a different power envelope.
This cluster remains capped at 200 W; do not raise the cap to chase those
numbers. Validate long-context, vision, tools, and sustained load locally.

## Rollback

Set llama.cpp to `replicas: 0`, set `my-apps/ai/vllm/deployment.yaml` to
`replicas: 1`, restore the vLLM HTTPRoute resource, and repoint consumers in the
same commit. The scheduler sequences the sole GPU; never scale both to one.
