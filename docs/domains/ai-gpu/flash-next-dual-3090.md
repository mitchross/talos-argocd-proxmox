# Qwen3.8 Flash Next on two RTX 3090s

**Status: researched candidate, 2026-09-06. GPU expansion is implemented;
Flash Next is not deployed or benchmarked on this restored two-card system.**
This study answers whether the Threadripper Talos worker can serve a Q4-class
Flash Next with 96 GiB system RAM, and records the prerequisites for a trial.
The [model catalog](model-catalog.md) remains the serving source of truth.

## Answer

**Yes, Unsloth UD-Q4_K_XL fits the hardware memory budget with expert offload.**
It cannot run entirely in 48 GiB VRAM. Keep attention and other non-expert
computation on the GPUs, distribute CPU-resident experts across both GPUs'
layer ranges, and keep the n-gram embedding table in host memory with NVMe
backing. This is a calculated feasibility conclusion, not a throughput promise.

The current shared-node scheduling must change before a reliable production
trial. Other pods already reserve about 35 GiB, and the existing inference
container's 48 GiB memory limit is insufficient for the proposed CPU weights.
The second card alone does not solve those constraints.

## Verified local state

Read through Proxmox, Omni, Kubernetes and the existing NVIDIA utility pod:

| Item | Observed |
|---|---|
| Proxmox host | Threadripper host `192.168.10.14`; approximately 125.67 GiB RAM |
| GPU VM | VM 103, 30 vCPU, 102400 MiB = 100 GiB configured RAM |
| Talos capacity / allocatable | Approximately 98.14 / 97.67 GiB, below configured guest RAM |
| GPUs | Two RTX 3090s; 24576 MiB each; 220 W cap per card |
| Guest PCIe observation | Both links x8; Gen3 maximum, idle second GPU downshifts to Gen1 |
| Guest interconnect | `PHB`, no NVLink; peer read/write queries report `NS` |
| Kubernetes | GPU node Ready, capacity and allocatable `nvidia.com/gpu: 2` |
| Serving | Qwen3.8-27B remains healthy, one whole GPU requested; second spare |
| Scheduling | No node taint; PostHog, Radar and Prometheus pods also assigned here |

The request mentioned 96 GB. Calculations below conservatively assume **96 GiB
allocated to the guest**, while the observed VM actually has 100 GiB. Even
96 decimal GB is about 89.4 GiB: still above the illustrated 83 GiB budget,
but with less margin. System RAM and VRAM are separate pools; they are not a
single interchangeable 144 GiB allocation. Guest topology does not prove
physical slot lane wiring; x8 and P2P results are the current guest-visible
path, not a recommendation to change BIOS/ACS settings.

The node had 51.36 GiB total memory requests at inspection, including 16 GiB
for the current server: about **35.36 GiB for other workloads**. Increasing the
server request to 76 GiB would require approximately 111 GiB, exceeding the
97.67 GiB allocatable. Relocate at least about 14 GiB of other requests just to
schedule that pod, and leave additional operating margin. The 7.4 GiB usage
sample immediately after boot is not steady-state evidence; several heavy
pods were still Pending.

## Which Q4 actually qualifies?

This is **Qwen3.8-Flash-Next**, not Qwen3-Next-80B or the dense Qwen3.8-27B.
It has a large expert model plus a separate 51.2-billion-parameter n-gram
lookup table. The table's precision materially affects file size without
changing expert precision. [Qwen model](https://huggingface.co/Qwen/Qwen3.8-Flash-Next)

Artifact bytes were read from Hugging Face metadata at Unsloth revision
`38bb39ee97821de2c9009abb7e93950eec396e66`; GGUF headers distinguish the table
from ordinary tensors. GiB means bytes divided by 2^30. Sizes exclude the
separate vision projector.

| Unsloth quant | Exact file bytes | Total GiB | N-gram GiB | Other weights/metadata GiB |
|---|---:|---:|---:|---:|
| UD-IQ4_XS | 93,682,584,224 | 87.249 | 26.822 | 60.426 |
| **UD-Q4_K_XL** | **111,334,654,784** | **103.688** | **26.822** | **76.866** |
| UD-Q5_K_XL | 158,286,406,650 | 147.416 | 50.664 | 96.752 |

[Unsloth pinned artifact inventory](https://huggingface.co/unsloth/Qwen3.8-Flash-Next-GGUF/tree/38bb39ee97821de2c9009abb7e93950eec396e66)

Q4_K_XL's expert gate/up weights are Q4_K with one layer promoted to Q5_K;
expert-down tensors are Q5_1/Q8_0. The n-gram table is IQ4_NL. This is a
reasonable interpretation of “at least Q4” for the compute weights. IQ4_XS is
a smaller 4-bit-family alternative, but not the same quality tier.
[Q4 files](https://huggingface.co/unsloth/Qwen3.8-Flash-Next-GGUF/tree/38bb39ee97821de2c9009abb7e93950eec396e66/UD-Q4_K_XL)

**Do not choose AtomicChat's Q4/Q5 names on the label alone.** Its AD-4.27
Q4_K_M uses mostly IQ2_S gate/up experts, with selected IQ3_S layers. Its
AD-5.00 increases n-gram precision while retaining the same core file sizes.
These are mixed-precision average-bits labels, not conventional Q4/Q5 expert
precision. Actual Q4 files total 88.034 GiB, of which the isolated table shard
is 35.763 GiB; the current model-card summary table differs from the artifact
inventory. The previous Atomic trial's rationale is historical, not this
study's recommendation. [Atomic model card and inventory](https://huggingface.co/AtomicChat/Qwen3.8-Flash-Next-GGUF)

Q5_K_XL is not the sensible first target: its larger table and core exceed
combined nominal 96+48 GiB before overhead if all weights are resident. Lazy
table paging may permit loading, but introduces disk-pressure risk.

## A conservative Q4 memory budget

Q4 routed experts total approximately 71.73 GiB, plus 5.13 GiB of other model
tensors. Placing approximately 28 of 48 expert layers on the CPU gives this
**illustrative estimate**; real layer sizes differ:

| Allocation | Estimated GiB |
|---|---:|
| CPU expert weights | 41.94 |
| Entire host n-gram table | 26.82 |
| Host model subtotal | **68.77** |
| Illustrative allowance for OS, remaining pods, loader and working memory | 14 |
| Host total | **82.77 of 96** |
| GPU model weights, both cards combined | **34.91 of 48** |
| Optional BF16 vision projector | 0.85 |
| Conventional q8_0 K/V at 131072 tokens | Approximately 1.59 |

The 14 GiB host allowance is a planning reservation, not a measurement of
current competing pods. GPU figures also need indexer state, Gated DeltaNet
state, CUDA graphs, scratch space and fragmentation headroom. The K/V estimate
uses 12 attention layers, two KV heads and dimension 256, with q8_0 block
scales; it is **not total context memory**. Sparse attention's indexer and
prefill buffers still grow with workload.
[Official model configuration](https://huggingface.co/Qwen/Qwen3.8-Flash-Next/blob/main/config.json)

At 26 CPU expert layers the approximate split becomes 39.01 GiB CPU experts
and 37.84 GiB GPU weights. Start with more headroom and measure before moving
experts back to CUDA. Load logs must show sufficient space on **each** card;
aggregate free VRAM can conceal an OOM on GPU 1.

## What real benchmarks establish

A firsthand repository publishes scripts and raw logs for **two 3090s without
NVLink**, 64 GB DDR5 and a Ryzen 9800X3D with PCIe4 x16 links. Its Unsloth IQ4_XS
results include 39.5 generated tokens/s on short prompts. A separate 131K
profile reached 21.9 tokens/s at 64K and completed a 119,482-token prompt.
That proves this model family can work on two cards with host offload; it
does not predict Q4_K_XL speed on a 2950X/DDR4/Gen3 x8 VM.

The useful placement finding is stronger than the speed analogy: first-N
CPU MoE offload left one GPU at 5.3 GiB and the other at 23.2 GiB. Offloading
expert bands from both halves balanced them. Short-prompt success was also
insufficient to establish long-prompt stability.
[Reproducible dual-3090 Flash Next benchmark](https://github.com/ruashots/flashnext-2x3090)

This repository's earlier one-card trials already documented paging stalls
and very slow CPU-offloaded inference. The current dense 27B measured about
42–43 tokens/s here. Keep that as the local baseline; doubling card count is
not evidence of doubling generation speed.
[Historical trial](../../superpowers/specs/2026-08-29-qwen38-flash-next-atomic-quant-design.md)
· [current measured backend](model-catalog.md)

### How the supplied club-3090 guide applies

[DUAL_CARD.md](https://github.com/noonghunna/club-3090/blob/master/docs/DUAL_CARD.md)
is mainly a guide to smaller GPU-resident models, particularly the dense
Qwen3.8-27B and Qwen3.6 variants. Its roughly 7 GB of weights per card and
262K context discussion do not describe Flash Next. Its useful lessons here
are to inspect interconnect topology, distinguish allocated context from
actually tested context, and benchmark prefill separately from decode.
The guide's vLLM/NCCL flags and Compose auto-detection are not automatically
part of this Talos llama.cpp Deployment. The local `PHB`/`NS` result also means
we cannot assume its NVLink or PCIe P2P performance.

## Proposed trial, not applied

Keep the pinned stock CUDA llama.cpp b10752 baseline. Its **live binary help
was checked**: use `--load-mode mmap --lazy-mode on`. The older
`--tensor-read-lazy` flag is absent. It supports layer splitting and tensor
placement overrides.
[b10752 argument implementation](https://github.com/ggml-org/llama.cpp/blob/b96806d96061049a5b574269b049bf6241d63d46/common/arg.cpp)

Start text-only, one slot, 65K context, symmetric q8_0 KV, no MTP, moderate
prefill batches. This command illustrates candidate arguments for the serving
container after staging all four verified Q4 shards. It is **not a tested
launch recipe** and must go through the owning GitOps manifests:

```bash
/app/llama-server \
  --model /models/Qwen3.8-Flash-Next-UD-Q4_K_XL-00001-of-00004.gguf \
  --host 0.0.0.0 --port 8080 --alias qwen38-flash-next-q4 \
  --n-gpu-layers 99 --split-mode layer --fit off \
  --load-mode mmap --lazy-mode on \
  --ctx-size 65536 --parallel 1 --flash-attn on \
  --cache-type-k q8_0 --cache-type-v q8_0 \
  --batch-size 1024 --ubatch-size 512 \
  --threads 12 --threads-batch 12 --jinja \
  --override-tensor '^per_layer_token_embd\.weight$=CPU' \
  --override-tensor 'blk\.([0-9]|1[0-3]|2[5-9]|3[0-8])\.ffn_(up|down|gate|gate_up)_(ch|)exps=CPU'
```

The two regex bands select expert layers 0–13 and 25–38. This intentionally
starts with 28 CPU layers; verify the actual GPU layer boundary and tensor
placement before narrowing either band. Thread counts are trial values:
measure 8/12/16 on this 30-vCPU VM instead of assuming all vCPUs are faster.
Do not retain the dense model's MTP arguments or reuse its projector.

Deployment prerequisites:

1. Relocate competing memory requests through GitOps and verify steady-state
   usage. An initial 76 GiB request / 84 GiB limit is a candidate, not a
   guarantee; tune against measured peaks and the actual remaining node budget.
   Keep the documented VPA exemption: prior uncapped VPA recommendations
   encouraged unsafe VM growth. Do not raise the 100 GiB guest ceiling.
2. Request and limit **two** `nvidia.com/gpu` cards. Keep `Recreate`, NVIDIA
   runtime and whole-card scheduling. Park the one-card production server via
   the [scale-swap procedure](gpu-scale-swap.md).
3. Verify NFS archive and local NVMe capacity; pin model revision, exact bytes
   and SHA-256 digests in download/hydration hooks. Model shard totals exceed
   111 GB before retaining rollback files. Serve from local storage, not NFS.
4. Inspect load-time per-card placement, host memory pressure and file refaults.
   Stop on OOM, paging thrash, missing tensors or incoherent output.
5. Record cold startup and two warmups, then fresh-prefix pp512/tg128 and
   8K/32K/near-65K prompts, TTFT, decode, peak memory and major faults. Keep
   competing load and sampling fixed. A useful initial acceptance target is
   15 tokens/s warm short decode, explicitly a target rather than a prediction.
6. Only after text stability, add the correct Flash Next vision projector and
   test tools/vision. Then test 131K; do not assume a configured window is safe.

For runtime rollback, restore the existing dense 27B manifests, one-card
request, its memory settings and original artifact stamps in Git. Keep its
cached files so rollback needs no large transfer. No live Flash Next switch
was performed during this study.

## Omni/Talos expansion and verification

The committed [MachineClass](https://github.com/mitchross/talos-argocd-proxmox/blob/e6da43e3/omni/machine-classes/threadripper-gpu-worker.yaml)
now references both `gpu-1` and `gpu-2`; the same file was applied to Omni and
read back successfully. MachineClass changes affect future allocations;
existing VM PCI attachment remains a Proxmox operation, now owned by the user.
Both mappings resolve to NVIDIA devices, one at host `09:00` and one at
`43:00`. Names can be reassigned by the operator; do not infer CUDA ordering
from them. An accidental AMD `00:00` root-complex entry was observed to block
startup with `Cannot open iommu_group`; removing it allowed VM start.

Talos already loads `nvidia`, `nvidia_uvm`, `nvidia_drm` and `nvidia_modeset`.
Those modules support both cards; duplicating entries adds nothing. Existing
DHCP is independent of interface names, avoiding PCI-renumbering problems.
The GPU Operator detected the second card automatically, and the existing
power-limit DaemonSet capped both cards at 220 W. That is per-card, up to
440 W combined GPU power under dual load, excluding the rest of the machine.

From a workstation with Kubernetes credentials:

```bash
kubectl get node talos-prod-cluster-v2-gpu-workers-7ct4kq -o wide
kubectl get node talos-prod-cluster-v2-gpu-workers-7ct4kq \
  -o jsonpath='{.status.allocatable.nvidia\.com/gpu}{"\n"}'
kubectl -n gpu-operator exec ds/nvidia-powerlimit -- \
  nvidia-smi --query-gpu=index,name,memory.total,power.limit --format=csv
kubectl -n gpu-operator exec ds/nvidia-powerlimit -- nvidia-smi topo -m
kubectl -n llama-cpp get deploy,pods
```

Expected: Ready, `2`, two 24576 MiB / 220 W rows, and the existing server Ready.
A one-GPU application correctly sees only one allocated card. Utility
DaemonSet visibility is the appropriate check for both. Before physically
removing a card, restore single-card workload allocations in Git and the
MachineClass, then have the Proxmox operator remove that VM PCI attachment
with the guest stopped. Preserve the VM and storage; do not reprovision it to
change GPU count.

## Evidence boundary

Research covered exact model identity, artifact bytes and tensor precision,
CPU/GPU budgets, runtime-version compatibility, the supplied dual-card guide,
firsthand Flash Next benchmarks and live device/scheduler state. Primary
sources were accessed 2026-09-06. Further generic searches would not resolve
the remaining questions: **this machine's Q4 throughput and peak memory require
the controlled trial above**, after its competing memory reservations are
addressed. GPU expansion and the existing endpoint were verified live; the
proposed model configuration was not run.
