# Node reboots, heat, fans, power

Everything here is read-only from the pod (Prometheus + Loki); BIOS, fans, power and Omni steps go to the user.

## Procedure

1. **Fleet sweep in one call.** Join `* on(instance,job) group_left(nodename) node_uname_info` for Talos; physical hosts carry `physical_host`.
   - uptime `(time()-node_boot_time_seconds)/86400`
   - max CPU temp 7d `max_over_time(node_hwmon_temp_celsius{chip=~".*coretemp.*|.*k10temp.*"}[7d])` vs `node_hwmon_temp_crit_celsius`
   - NVMe temp 7d `chip=~"nvme.*"`
   - throttles `increase(node_cpu_package_throttles_total[7d])` / `node_cpu_core_throttles_total`
   - OOM kills `increase(node_vmstat_oom_kill[7d])`
   - model/BIOS `node_dmi_info` (drop serial labels)
   Report one table: machine, up for, hottest, notes.
2. **Pin the reboot time.** `node_boot_time_seconds` gives boot; the last Loki line for that `host_name` before it gives last-alive. Host logs stopping minutes before boot while pod logs keep flowing is a log-shipper stall, not the crash.
3. **Classify the reboot.**
   - Boot-reason DaemonSet: `{k8s_namespace_name="boot-reason"} |= "boot-reason"` (`clean|unclean|watchdog|first-run|pod-restart`).
   - Temps/load/memory at last-alive (`node_hwmon_temp_celsius`, `node_load1`, `node_memory_MemAvailable_bytes`, PSI). Cool + idle + plenty of RAM = not thermal, not OOM.
   - Kernel lines before the gap: `|~ "(?i)panic|soft lockup|hard LOCKUP|Hardware Error|mce:|nvme.*(timeout|reset)|ata.*(reset|error)|i915.*(hang|reset)|thermal.*crit"`.
   - Debian/Proxmox with efi_pstore: `systemd-pstore ... skipped, unmet condition ConditionDirectoryNotEmpty=/sys/fs/pstore` on next boot means no panic was saved → power/hardware reset most likely. Talos can't save panics to pstore.
   - Reboots on several machines at different times rule out a whole-house outage, not each box's adapter/outlet/circuit.
   - Reboots starting right after a new accelerator workload (e.g. Frigate on iGPU/NPU) point at the driver or power draw: call it a hypothesis and offer moving the workload off for a day as the test.
4. **Heat/fan/repaste.** Repaste only if max temp nears crit or throttle counters rise. Dell/HP mini PC fans are firmware-controlled; point to BIOS (Dell: F2 → Thermal Management → Ultra Performance).
5. **Web-search** the exact `product_name` + CPU generation + "random reboot", Talos issues and the driver (i915/xe/intel_vpu). Separate hangs (need the power button) from instant reboots.
6. **Omni's view (user runs on the Pi).** Omni logs by machine **UUID**: `docker logs --since <t1> --until <t2> omni | grep <uuid> | grep -viE "token|secret|key"`. `got machine status event ... stage:"BOOTING"` marks the reboot; nothing between last-alive and BOOTING (no reboot request, no config apply) means unrequested. Back by itself in ~2-3 min = not a hang (a hang without an active watchdog stays down).
7. **Hand off** short numbered steps: BIOS event log (Power/Thermal/System) at the UTC times, adapter wattage, outlet/UPS swap. Netconsole only after warning about the Omni kernel-arg reboot-loop risk. For a BIOS visit on a Talos node, `talosctl -n <node> shutdown` drains and powers off (run it from the pod if `talosctl -n <node> version` works there); warn which pinned workloads go offline and re-check Ready/uncordoned + the workload after boot.
8. **Dell BIOS power log.** BIOS clock is UTC; each `Power On` lands ~55 s before the kernel's `Linux version` line. A clean shutdown writes `Power Off (ACPI)` first, so a `Power On` with no preceding `Power Off` is a power loss or hard reset. Confirm the log only records real power cycles (known kernel-only reboots should be absent) and ask whether buttons were pressed during the BIOS visit. Fix order: reseat both adapter ends → check wattage → swap outlet/strip or UPS → Tapo power-metering plug to catch the drop.

## Pitfalls

- Threadripper `k10temp` Tctl (`pci0000:00_0000:00:18_3 temp1`) reads ~27 °C above real die temp; subtract first.
- `changes(node_boot_time_seconds[7d])` overcounts (NTP jitter); count boot timestamps or Loki boot lines.
- Pi netconsole logs (`/var/log/netconsole/<ip>.log`) need pod→Pi SSH, which `default-deny-lan-egress` blocks without a Hermes egress rule and restricted key (hermes-agent skill, multi-machine reference). Until then the user tails them.
- `vcgencmd` on the Ubuntu Pi needs sudo; uptime + the login banner's temperature are enough.
- Harmless noise, name once: HPE SATA SSDs (`MK000480GWCEV`) make smartctl exit 4 while `smart_status`=1 and reallocated=0; Proxmox postfix failing on port 25 only means host alert mail isn't delivered.
