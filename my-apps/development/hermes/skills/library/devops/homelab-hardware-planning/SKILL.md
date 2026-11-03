---
name: homelab-hardware-planning
description: Use when buying, upgrading or sizing homelab hardware.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [homelab, hardware, gpu, vram, llm, purchasing, benchmark]
    related_skills: [node-hardware-triage, homelab-ops, video-transcribe]
---

# Homelab hardware planning (buy / upgrade / fit audits)

For "is X worth buying", "how do I get 64GB+ VRAM", "which node should host model Y", "deep dive my hardware and recommend". Goal: one plain recommendation with a total cost, backed by live facts from his machines, not generic specs.

## Always-on rules (Mitch's preferences)
- Answer his stated goal (e.g. "bigger models and more KV cache") as "what each option unlocks". When he says forks, drivers or hackiness don't matter, list them as setup notes only; never argue against a buy with them again.
- Show total cost per build in one table (low / typical, host excluded or included, said explicitly). If a source (video, post) quoted a price, reconcile it first: source figure -> scaled to his ask -> today's price.
- Keep one running notes file per thread (`/opt/data/workspace/reports/local-llm-plan-notes.md` for the local-LLM thread): goals, decisions, measured facts, open TODOs. Update it whenever a decision changes, because Mitch relies on it to survive context loss.
- Abliterated models: default to stock weights. Mitch only wants refusal-removed builds if they cost no accuracy, so offer them as an A/B test, not the pick.
- Electricity cost: use Home Assistant `sensor.*_energy_last_month` kWh times `sensor.current_electricity_rate` (all-in), and say that unmetered gear (Pi, network, some mini PCs) is missing. Never annualize a live watt reading or quote the HA `*_yearly` counters, which only count since tracking started. Mitch caught an undercount of about 3x from this.
- Lead with the verdict, then one table, then a numbered pick. Keep chat to ~200 words; full evidence goes in `/opt/data/workspace/reports/<topic>-<date>.md`.
- Label every number measured / from records / estimated. Never present a simulator output or spec sheet as a measurement.
- Prefer recommendations that also fix measured bottlenecks or known-failing parts, and that keep current services (vLLM Qwen) running.
- Spend-to-save asks ("I have ~$X, will it save electricity"): rank by watts/kWh saved and what it enables. Never show payback-period math; Mitch said he doesn't care about it.
- His end state is an all-mini-PC Kubernetes cluster, plus a NAS on any box, plus one AI rig in the basement (heat is fine there; gaming-room heat is not). He wants local AI to replace paid subscriptions. Judge every option by whether it moves toward that end state.
- In the RAM shortage, a used workstation (Precision 7920/7820, Z8/Z6 G4, P920, WRX80, EPYC tower) with 256 GB+ already installed is often cheaper than buying the RAM alone. Skip blades: they need a chassis, are loud, and have no room for GPUs.
- Measured recipe pages beat simulator output. Check them first and say when a sim was optimistic. When `web_extract` can't fetch a page, `curl` it and strip the HTML in Python.

## Procedure
1. **Recall + inventory first (cheap, authoritative):**
   - `hindsight_recall` for the hosts/GPUs/prior benchmarks.
   - Talos repo docs: `git show origin/main:docs/inventory/<latest>-fleet-inventory.md` and `docs/audits/*hardware*` (host roles and standing decisions, e.g. the NAS stays storage-only).
   - Deal-scout repo `docs/inventory.md` and `docs/gpu-upgrade-scraper-prd.md` (desktop specs, buying policy).
2. **Live hardware facts from the pod (read-only)**: see `references/hardware-fact-sources.md` (Prometheus DMI/NVMe/memory, `talosctl read` of PCIe link sysfs, `talosctl get memorymodules`).
3. **Measure what you can on the node you run on** (Hermes runs on the GPU VM): AVX2 RAM-read bandwidth and fio. Check the pod's `/sys/fs/cgroup/cpu.max` first (see pitfalls).
4. **Prices:** live deal-scout pool (`curl http://deal-scout.deal-scout.svc:8000/api/deals?limit=1000`, filter by `query`/title in Python) plus web search for current used prices. Mark asking vs sold. Spawn parallel subagents (balanced) for wide price/software/perf research; give each the user's exact hardware and stack. When several subagents edit the same repo, give each its own `git worktree` path and branch in its context, because they share one checkout otherwise.
4b. **Capacity to move work off a host / fit a big pod:** use `references/cluster-offload-capacity.md`. Schedulable room is allocatable minus requests, not free RAM.
5. **Simulate when the workload is MoE offload:** `references/moe-offload-sim.md`.
6. **Write the report, retain the verdict in Hindsight, reply short.** Put commands the user must run (Proxmox `dmidecode`, `numactl`, GPU bandwidth tests) in one paste-ready block.

## Pitfalls
- The Hermes pod is cgroup-capped (check `cpu.max`): benchmark at or below that many threads and report it as a floor, because extra threads get throttled and lower the number.
- Pod seccomp blocks io_uring (fio `io_queue_init ... Operation not permitted`). Use `--ioengine=psync --numjobs=8 --group_reporting`; posixaio under-reports. Build fio from the GitHub release tarball (`./configure --disable-native && make`) if missing. fio JSON can start with a warning line; parse from the first `{`.
- `/` in the pod is the VM's virtual system disk and `/opt/data` is Longhorn; neither is the node-local model-cache NVMe. Say which one you tested.
- A VM shows 1 NUMA node even on a 2-die Threadripper; host NUMA needs the Proxmox host.
- Idle GPUs report 2.5 GT/s (power saving); width is the reliable field, and a guest's `max_link_speed` is the virtual root port, not the host slot.
- Proxmox hosts and TrueNAS don't accept SSH from the cluster network, and Omni `MachineStatus` has no DIMM speed; hand the user the command block instead of retrying.
- Check live RAM/cores before trusting a host profile someone hands you; specs in a prompt can be stale.
- When Mitch says he "added" machines, match them to `kubectl get nodes` AGE and the Omni machine list before calling anything unknown or not joined. Recently joined nodes are the new ones. HA plug names are stale: one plug can cover several hosts (e.g. "HP SFF + Optiplex" also powers newer minis). Never call a host unmetered without checking which plug it sits on.
- Shell scripts that `exec > >(tee "$OUT")` must not use a bare `wait`. It also waits on the tee process substitution and hangs. Collect background PIDs and `wait "${pids[@]}"`.
- Deal-scout queries can collect junk listings; filter titles and flag a bad query to the user.
- Mitch pushes back on server-board prices and asks about mini PC + OCuLink eGPU. Price the RAM separately: in the late-2026 shortage, 96 GB DDR5 SODIMM costs as much as the box or more. Mini PCs cap at 96 GB on dual-channel memory with an x4 link. For MoE offload they barely beat the current Threadripper, which costs $0 (moetier: ~14 vs 11–13 tok/s). Always include a $0 'use what you have' row.

## References
- `references/hardware-fact-sources.md`: query/command per fact, and what each can't tell you.
- `references/moe-offload-sim.md`: moetier simulator recipe and lane rescaling.
- `references/cluster-offload-capacity.md`: requested-vs-used per node, what's pinned, what can move, how to make room for a big pod.
