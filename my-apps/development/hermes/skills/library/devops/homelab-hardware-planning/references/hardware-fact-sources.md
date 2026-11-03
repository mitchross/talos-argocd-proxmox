# Where each hardware fact comes from (from the Hermes pod)

| Fact | Command / query | Limits |
|---|---|---|
| Host model, board | Prometheus `node_dmi_info` (`product_name`, `board_name`, `system_vendor`; instance = `<ip>:9100`) | VMs show `Standard PC (Q35...)` |
| RAM total, threads | `node_memory_MemTotal_bytes{instance=...}`, `count(node_cpu_seconds_total{mode="idle",instance=...})` | No DIMM layout/speed |
| NVMe / disks | `node_nvme_info` (model, firmware), `node_disk_info` (model, `rotational`) | No link width |
| GPU PCIe link | `talosctl -n <gpu-node-ip> read /sys/bus/pci/devices/0000:01:00.0/current_link_width` (+ `_speed`, `max_link_*`) | Speed drops at idle; max is virtual in a VM |
| Bare-metal DIMMs | `talosctl -n <ip> get memorymodules -o yaml` (size, speed, vendor) | Proxmox/TrueNAS hosts not covered |
| Node allocatable, GPU | `kubectl get nodes` capacity columns; NFD/GFD labels (`nvidia.com/gpu.*`, `cuda.driver-version`) | |
| Which machines exist | `omnictl get machines` / `machinestatus -o json` (skip the version warning; output is concatenated JSON docs), `kubectl get nodes` AGE, Prometheus `up` job targets, Loki `host_name` label values, `ssh pi 'ip neigh'` for VLAN 10 | All of them should agree; one source alone can mislead |
| Power / cost per host | Home Assistant `sensor.*_energy_last_month` (kWh), `sensor.current_electricity_rate`; Prometheus `homeassistant_sensor_power_w` (many label-split series per sensor, so don't sum blindly) | Plug names may cover several hosts |
| GPU live metrics | `dcgm-exporter.prometheus-stack.svc:9400/metrics` | No PCIe gen/width or H2D bandwidth |
| Live used prices | deal-scout `GET /api/deals?limit=1000` in-cluster (public mode; inventory/lab routes are 403; limit 5000 returns 422) | asking prices only |

**Needs the user (paste-ready):**
- Proxmox/TrueNAS host facts: give one read-only script that writes `/tmp/hwtest-<host>.txt`. It should cover `dmidecode -t 16/17/39/9`, `lscpu`, `numactl --hardware`, `lspci -vv` LnkCap/LnkSta for GPU and NVMe, `lsblk`, smartctl wear, and `qm config` per VM.
- Raw-NVMe fio with `--readonly` (record-size randread, e.g. 9M, plus 1M seq and 16k rand).
- RAM bandwidth: compiled AVX2 if gcc exists, otherwise parallel `dd` from /dev/shm as a floor. Abort the RAM test if MemAvailable < 12 GiB.
- Skip disk tests on TrueNAS, because ZFS ARC makes them meaningless.
- Inside a GPU pod: `nvidia-smi -q` link info and a pinned H2D/D2H bandwidth test.

**DL360 Gen9 memory rule:** speed falls with DIMMs per channel. At 3 per channel quad-rank runs 1600 MT/s, and 2 per channel runs the DIMM rating. Populate both CPUs at ≤2 per channel before considering faster CPUs; these workloads are memory-bound. HPE's per-server "Configuring Memory" pages have the tables.

**RAM bandwidth probe:** AVX2 XOR-read over a 4 GiB `aligned_alloc` buffer with OpenMP, best of 5, at 1/4/8 threads (`gcc -O3 -mavx2 -fopenmp`).
