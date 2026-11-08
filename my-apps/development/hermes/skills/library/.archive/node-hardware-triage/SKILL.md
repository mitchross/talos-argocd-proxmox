---
name: node-hardware-triage
description: Use when a homelab node reboots, overheats or fans.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [homelab, talos, proxmox, hardware, reboot, thermal]
    related_skills: [homelab-ops, fork-hotfix-release]
---

# Node hardware triage (reboots, heat, fans, power)

For "why did X reboot", "check fan speeds / does it need a repaste", "any other PCs need a check". Everything is read-only from the Hermes pod (Prometheus + Loki); BIOS, fans, power and Omni steps are handed to the user.

## Endpoints
- Prometheus `http://prometheus-operated.prometheus-stack.svc:9090`. Jobs: `node-exporter` (Talos nodes and VMs, `nodename` via `node_uname_info`), `physical-node` (Proxmox hosts, Pi, TrueNAS; label `physical_host`).
- Loki `http://loki-read.loki-stack.svc:3100` with header `X-Scope-OrgID: 1`; node/host logs by `host_name`.

## Procedure
1. **Fleet sweep in one call** (join with `* on(instance,job) group_left(nodename) node_uname_info` for Talos; physical hosts carry `physical_host`):
   - uptime `(time()-node_boot_time_seconds)/86400`
   - max CPU temp 7d `max_over_time(node_hwmon_temp_celsius{chip=~".*coretemp.*|.*k10temp.*"}[7d])` and its `node_hwmon_temp_crit_celsius`
   - NVMe temp 7d `chip=~"nvme.*"`
   - throttles `increase(node_cpu_package_throttles_total[7d])` / `node_cpu_core_throttles_total`
   - kernel OOM kills `increase(node_vmstat_oom_kill[7d])`
   - model/BIOS `node_dmi_info` (drop serial labels)
   Report as one table: machine, up for, hottest, notes. Flag only real outliers.
2. **Pin a reboot time:** `node_boot_time_seconds` gives boot; the last Loki line for that `host_name` before it gives last-alive. A gap where host logs stop minutes before boot while pod logs keep flowing is a log-shipper stall, not the crash itself.
3. **Classify the reboot:**
   - Check the boot-reason DaemonSet logs: `{k8s_namespace_name="boot-reason"} |= "boot-reason"` (reasons `clean|unclean|watchdog|first-run|pod-restart`).
   - Temps/load/memory at last-alive from Prometheus (`node_hwmon_temp_celsius`, `node_load1`, `node_memory_MemAvailable_bytes`, PSI). Cool + idle + plenty of RAM = not thermal, not OOM.
   - Kernel lines before the gap: `|~ "(?i)panic|soft lockup|hard LOCKUP|Hardware Error|mce:|nvme.*(timeout|reset)|ata.*(reset|error)|i915.*(hang|reset)|thermal.*crit"`.
   - On Debian/Proxmox hosts with efi_pstore: if the next boot logs `systemd-pstore ... skipped, unmet condition ConditionDirectoryNotEmpty=/sys/fs/pstore`, no panic was saved, so power/hardware reset is most likely. Talos cannot save panics to pstore.
   - Reboots on several machines at different times rule out a whole-house outage but not each box's adapter/outlet/circuit.
   - Correlate with workload changes: reboots that start right after a new accelerator workload lands (e.g. Frigate on iGPU/NPU) point at the driver or power draw; say it is a hypothesis and offer moving the workload off for a day as the test.
4. **Answer heat/fan/repaste questions with data:** repaste only if max temp nears crit or throttle counters rise. Mini PC fans (Dell/HP) are firmware-controlled and usually not exposed to Linux; point the user to BIOS (Dell: F2 → Thermal Management → Ultra Performance).
5. **Web-search** the exact model (`product_name` from `node_dmi_info`) + CPU generation + "random reboot", Talos issues and the driver in use (i915/xe/intel_vpu); separate hangs (need power button) from instant reboots.
6. **Omni's view of the reboot (user runs on the Pi):** Omni logs machines by **UUID**, not IP or hostname, so grep `docker logs --since <t1> --until <t2> omni` for the machine UUID (`omnictl get machines` / earlier notes) and strip secrets (`grep -viE "token|secret|key"`). `got machine status event ... stage:"BOOTING"` marks the reboot; if nothing (no shutdown/reboot request, no config apply) appears between last-alive and BOOTING, the reboot was unrequested. A box that came back by itself within ~2–3 min was not a hang (a hang without an active watchdog stays down).
7. **Hand off** short numbered user steps: BIOS event log (Power/Thermal/System) at the UTC times, adapter wattage, outlet/UPS swap; netconsole only after warning about the Omni kernel-arg reboot-loop risk. For a BIOS visit on a Talos node, `talosctl -n <node> shutdown` drains and powers off; run it from the pod if `talosctl -n <node> version` works there, otherwise hand it to the user; warn which pinned workloads go offline (e.g. Frigate on the Dell) and re-check Ready/uncordoned + the workload after boot.
8. **Read the BIOS power log (Dell):** the BIOS clock is UTC; each `Power On` lands ~55 s before the kernel's `Linux version` line. A clean OS shutdown writes `Power Off (ACPI)` first, so a `Power On` with **no preceding `Power Off`** is a power loss or hard reset. Confirm the log only records real power cycles by checking whether known kernel-only reboots (Loki `"Linux version"` boot lines) are absent from it, and ask whether the user pressed buttons during the BIOS visit. Then the order of user fixes: reseat both ends of the adapter → check adapter wattage → swap outlet/strip or UPS → put a Tapo power-metering plug on it to catch the drop.

## Pitfalls
- Threadripper `k10temp` Tctl (`pci0000:00_0000:00:18_3 temp1`) reads ~27 °C above real die temp; subtract before calling it hot.
- Proxmox VM nodes (hp-micro on hp-shed, etc.) reboot when their host does; check the `physical-node` host's boot time before blaming the VM.
- hp-shed (and its hp-micro VM) run on off-grid solar; their reboots are expected. Mention them in one line at most and don't recommend power fixes for them unless asked.
- `changes(node_boot_time_seconds[7d])` overcounts (boot time jitters with NTP); use the boot-time timestamps or Loki boot lines for the real count.
- The Pi's netconsole logs (`/var/log/netconsole/<ip>.log`) need SSH from the pod, which the cluster's `default-deny-lan-egress` policy blocks unless a Hermes egress rule and a restricted Pi key exist (see the SSH-from-a-gateway-pod section of the hermes-agent skill's multi-machine reference). Until then, ask the user to `tail` them.
- When the pod can't reach a host, give the user one paste-ready **read-only** command block with a one-line "what each part tells me", rather than pushing SSH setup; the user prefers "tell me what to check, I'm SSH'd in". `vcgencmd` on the Ubuntu Pi needs sudo; uptime + the login banner's temperature are enough. If you propose pod→host SSH, recommend a restricted key (`restrict,from="<lan>",command="<read-only wrapper>"`, dedicated user) — a plain authorized_keys line on the Omni Pi is effectively full cluster control.
- Harmless noise to name once and move on: HPE enterprise SATA SSDs (`MK000480GWCEV`) make smartctl exit 4 (`Some SMART or other ATA command ... failed`) while `smart_status`=1 and reallocated=0; Proxmox postfix failing to reach port 25 only means host alert mail isn't delivered.
- Keep the reply short: verdict first, one table, then 2–3 user actions.
