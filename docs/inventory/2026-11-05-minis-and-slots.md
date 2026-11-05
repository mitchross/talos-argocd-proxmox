# Mini PCs, RAM and M.2 slots — November 5, 2026

**Purpose:** what is inside each office mini, which M.2 storage slots are still free across the
fleet, and what to buy next.
**Status:** dated snapshot. It adds to the [November 3 inventory](2026-11-03-fleet-inventory.md),
which stays the main page for power, PCIe links and speeds.

How it was collected, on November 5:

- **Bare-metal minis:** `talosctl get systeminformation`, `memorymodules`, `pcidevices` and `disks`
  through Omni.
- **Proxmox hosts:** Prometheus `node_dmi_info`, `node_nvme_info` and `node_disk_info`. Talos only
  sees virtual disks inside those VMs.
- **Slot counts:** the vendor spec pages linked below. Software cannot see an empty slot, so the
  total per machine comes from the spec, not from a measurement.

## What changed since November 3

- `hp-elite-gen13` (Elite Mini 600 G9) is now at **`.141`**, not `.88`.
- The Dell's Apple SSD is an **Apple AHCI blade on a passive M.2 adapter**, wired straight to a CPU
  PCIe port. It is not an M.2-to-SATA controller card.
- The Dell's two DIMMs don't match: one runs at 5600 and the other at 4800, so both run at 4800.
- All three minis have a Wi-Fi card in their M.2 2230 WLAN slot.

## Office minis

| Node | Model (SKU) | CPU | RAM | M.2 storage | WLAN slot |
|---|---|---|---|---|---|
| `hp-elite-gen12` `.82` | HP Elite Mini 800 G9 (`7B7V4UC#ABA`) | i5-12500T | 2× Micron 8 GB DDR5-4800 (slots full) | **1 of 2**: Samsung PM9A1 256 GB (boot). **One Gen4 x4 2280 slot free.** | Intel CNVi Wi-Fi |
| `hp-elite-gen13` `.141` | HP Elite Mini 600 G9 (`86Y68UT#ABA`) | i5-13500T | 1× Samsung 16 GB DDR5-4800, **one slot empty** (single channel) | 2 of 2: Intel 660p 512 GB QLC, **76% worn**, holds Longhorn + WD SN530 256 GB (boot) | Intel CNVi Wi-Fi |
| `mini-pc-dell-ultra-worker` `.181` | Dell Pro Micro QCM1250 | Core Ultra 5 245T, iGPU + NPU | Samsung 16 GB DDR5-4800 + Micron 16 GB DDR5-5600, both at 4800 | 2 of 2: Kioxia BG7 256 GB (boot) + Apple SM0256 blade on an adapter (Longhorn) | Qualcomm QCA6174 |

Spec sources: [HP Elite Mini 800 G9](https://support.hp.com/us-en/document/ish_5868444-5868508-16),
[HP Elite Mini 600 G9](https://support.hp.com/us-en/document/ish_5868243-5868287-16)
(both: 2 DDR5 SO-DIMM slots, 64 GB max, 2× M.2 Gen4 x4 2280, 2.5" bay with kit `13L70AA`),
[Dell Pro Micro QCM1250 storage](https://www.dell.com/support/manuals/en-us/dell-pro-qcm1250-micro/dell_pro_micro_qcm1250_om/storage)
(2× M.2 2230/2280; two SSDs need thermal pads, sold separately; no 2.5" bay).

## Free M.2 storage slots across the fleet

| Machine | Used | Free | In use now |
|---|---|---|---|
| HP Elite Mini 800 G9 `.82` | 1 of 2 | **1** | Samsung PM9A1 256 GB |
| HP Elite Mini 600 G9 `.141` | 2 of 2 | 0 | Intel 660p 512 GB, WD SN530 256 GB |
| Dell Pro Micro `.181` | 2 of 2 | 0 | Kioxia BG7 256 GB, Apple blade |
| HP ProDesk 600 G4 SFF `.21` | 0 of 1 | **1** | its 3 drives are all SATA |
| HP ProDesk 600 G4 DM (shed) `.20` | 1 of 2 | **1** | SK hynix BC501 256 GB, plus a 2.5" SATA SSD in the bay |
| Threadripper (X399 Taichi) `.14` | 2 of 3 | **1** (`M2_3`) | 2× EDILOCA EN605 512 GB |

Four M.2 storage slots are free. Specs: [ProDesk 600 G4 SFF](https://support.hp.com/us-en/document/c06055178),
[X399 Taichi](https://www.asrock.com/MB/AMD/X399%20Taichi/index.asp).

## Buy list

Deal Scout watches these. The Lab tab shows the operator inventory and the matching listings.

1. **M.2 2280 NVMe with power-loss protection** (Micron 7400/7450 PRO, Kingston DC2000B or
   similar), two of them:
   - one for the 800 G9's free slot, as a Longhorn disk;
   - one to replace the 600 G9's worn Intel 660p.
2. **One 16 GB DDR5-4800+ SO-DIMM** for the 600 G9's empty slot. It gets the node to dual channel.
3. **2× 32 GB DDR5 SO-DIMM kits** later, for any mini that should reach 64 GB.
4. **Optional:** an Intel i226-V 2.5 GbE card for the M.2 WLAN slot, or an E-key to M-key adapter
   for a 2230 boot SSD. Both replace the Wi-Fi card.

Skip M.2-to-SATA controller cards in the minis. They use up one of only two NVMe slots, and the
chassis has neither SATA power nor room to mount drives.
