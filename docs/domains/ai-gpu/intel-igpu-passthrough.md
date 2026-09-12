# Intel iGPU as a cluster resource

Intel integrated GPUs are passed through from their Proxmox hosts to the Talos
worker VMs and advertised cluster-wide as `gpu.intel.com/i915`. Any workload can
request one — Jellyfin QSV transcoding, Immich OpenVINO inference, Frigate
stream decoding.

The work splits across two layers, and only one of them is manual:

| Layer | Declarative? | How it changes |
|---|---|---|
| Proxmox host — bind the iGPU to `vfio-pci`, attach it to the VM | **No** | SSH to the host, steps below |
| Talos node — `i915` driver, node labels | Yes | `omni/cluster-template/cluster-template-prod-v2.yaml` |
| Cluster — device plugin advertising the resource | Yes | `infrastructure/controllers/intel-gpu-plugin/` |

**You never SSH into a Talos node.** There is no shell. The driver arrives as a
system extension declared in the Omni template.

## Eligible hosts

| Host | CPU | iGPU | Device ID |
|---|---|---|---|
| `192.168.10.22` hp-elite | i5-13500T (Raptor Lake) | UHD 770 | `8086:4680` |
| `192.168.10.21` hp-sff | i5-8500 (Coffee Lake) | UHD 630 | `8086:3e92` |
| `192.168.10.16` dell | i5-8500 (Coffee Lake) | UHD 630 | `8086:3e92` |

The Threadripper GPU host has no integrated graphics; it uses its RTX 3090s and
the NVIDIA path instead.

## Host setup

Confirm the iGPU sits alone in its IOMMU group before touching anything. A group
with other members drags those devices into the VM with it:

```bash
ls /sys/bus/pci/devices/0000:00:02.0/iommu_group/devices
```

One entry means you are clear to proceed.

```bash
# claim the device for vfio-pci — use the device ID from the table above
echo 'options vfio-pci ids=8086:4680 disable_vga=1' > /etc/modprobe.d/vfio-igpu.conf
printf 'blacklist i915\nblacklist xe\n' > /etc/modprobe.d/blacklist-igpu.conf
printf 'vfio\nvfio_iommu_type1\nvfio_pci\n' >> /etc/modules

# release the EFI framebuffer so vfio-pci can take the boot VGA
sed -i 's/^GRUB_CMDLINE_LINUX_DEFAULT="quiet"$/GRUB_CMDLINE_LINUX_DEFAULT="quiet initcall_blacklist=sysfb_init"/' /etc/default/grub
grep GRUB_CMDLINE_LINUX_DEFAULT /etc/default/grub    # verify before continuing

update-grub && update-initramfs -u -k all
qm set <vmid> -hostpci0 0000:00:02.0,pcie=1
reboot
```

`initcall_blacklist=sysfb_init` is required on a UEFI host. Without it the EFI
framebuffer holds `00:02.0` and `vfio-pci` silently loses the race to `i915`.

Do not add `intel_iommu=on`. It has been the kernel default since 6.8 and the
hosts already run with IOMMU active — adding it hides whether it was ever on.

Keep the VM on SeaBIOS. Compute-only passthrough works there, and switching an
installed Talos VM to OVMF is a far larger change than it appears.

**The host loses console video.** These are headless machines with no IPMI, so a
host that fails to boot after this needs a live USB to recover. Do one host at a
time and verify before starting the next.

### Verify the host

```bash
lspci -nnk -s 00:02.0 | grep -i 'kernel driver'
```

Expect `vfio-pci`. If it still reads `i915`, the framebuffer kept the device —
recheck the grub line took effect.

## Talos setup

Add the extension to the machine class in
`omni/cluster-template/cluster-template-prod-v2.yaml`:

```yaml
systemExtensions:
- siderolabs/i915 # renovate: datasource=docker depName=siderolabs/i915
```

Apply it. This rebuilds the node image and reboots the node:

```bash
omnictl cluster template sync -f omni/cluster-template/cluster-template-prod-v2.yaml
```

Use `omnictl`, never the Omni web UI. Adding machine sets through the UI wipes
the template's `ExtensionsConfigurations`.

## Cluster setup

Nothing to do per node. `infrastructure/controllers/intel-gpu-plugin/` runs a
DaemonSet selected on `feature.node.kubernetes.io/pci-0300_8086.present`, which
Node Feature Discovery applies automatically once the device reaches the guest.
The QEMU virtual VGA is vendor `1234`, so the label only appears on nodes with a
genuine passed-through iGPU — a new host needs no cluster-side change.

### Verify the cluster

```bash
kubectl get nodes -l feature.node.kubernetes.io/pci-0300_8086.present=true
kubectl -n intel-gpu-plugin get pods
kubectl get node <node> -o jsonpath='{.status.allocatable.gpu\.intel\.com/i915}'
```

The last command returns the share count once the plugin is running.

## Requesting one

```yaml
spec:
  template:
    spec:
      nodeSelector:
        feature.node.kubernetes.io/pci-0300_8086.present: "true"
      containers:
      - name: app
        resources:
          requests:
            gpu.intel.com/i915: 1
          limits:
            gpu.intel.com/i915: 1
```

The plugin advertises each physical device as 4 shares, so several pods can use
one iGPU. Shares are not isolation — concurrent transcoding and inference on the
same device contend with each other. Raise `-shared-dev-num` in the DaemonSet if
you need more slots on a node.

UHD 630 (Coffee Lake, Gen9.5) runs OpenVINO and QSV fine but has no DP4a, so
INT8 inference is markedly slower than on the Raptor Lake UHD 770. Pin
latency-sensitive inference to the 770 with a `topology.kubernetes.io/zone`
selector when it matters.
