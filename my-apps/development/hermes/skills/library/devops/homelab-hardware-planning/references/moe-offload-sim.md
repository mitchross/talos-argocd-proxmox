# MoE tiered-offload simulation (sybil-solutions/moetier)

Use for "will GLM-5.3-Flash / Qwen3.8-Flash-Next run on host X with VRAM+RAM+NVMe offload".

## Setup
```bash
W=/opt/data/cache/scratch/moe-audit; mkdir -p $W && cd $W
git clone -q --depth 1 https://github.com/sybil-solutions/moetier
python3 -m venv venv && venv/bin/pip -q install numpy
cd moetier && ../venv/bin/python -m moetier sim glm53-rtx3090-55g-nvx4 \
  --trace traces/glm53-g002-decode.npy --segments traces/glm53-g002-decode.segments.npy
```
The baseline must reproduce the README C1 figure before you profile anything; if it doesn't, the rescaled numbers mean nothing.

## Profiling a host in Python
- `spec.load("moetier/registry")` (the registry dir, not the repo root), deep-copy, edit, then `spec.resolve(reg, recipe, **{"budget.ram_gb": N, "budget.vram_expert_slots": S, "policy.prefetch": {"depth":1,"recall":0.7}})`, then `sim.run(R, trace, conc=c)` and `sim.prefill(R, 8192)`.
- Rescale from the calibration host (EPYC 7443P, 138 GB/s practical DDR4, 22 CPU-lane threads, PCIe4 x16 ~25.5 GB/s):
  - CPU lane `avx2-exl3-cpu.per_expert_ms` = max(9.47 MB / min(91, 0.66 x host_practical_GBps), 0.104 x 22 / host_threads).
  - Zero-copy `exllamav3-cuda.zerocopy.per_expert_ms` = 0.38 x 25.5 / host_h2d.
  - Set `hardware.gpu.h2d_gbps` and `hardware.nvme.{bw_gbps,bw_qd1_gbps,latency_ms}` from measurements.
  - A second 24 GB GPU is about +2,400 VRAM slots for GLM's 9.47 MB experts, but 0xSero's GLM image pins one GPU, so label 2-GPU results a what-if.
- Several profiles take minutes; run with `background=true` and wait with `process_manage`.

## Coverage
- Only GLM-5.3 ships a routing trace. Qwen3.8-Flash-Next has a model record but no trace, and DeepSeek-V4.1 has no records: say "not simulated" and reason from expert bytes per token (Qwen ~0.9 GB vs GLM ~3.2 GB).
- Rescaled results are model outputs; the binding lane (cpu / pcie / nvme) is the useful part of the answer.
