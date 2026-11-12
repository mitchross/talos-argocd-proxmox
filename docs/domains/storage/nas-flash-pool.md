# NAS flash pool: layout and buy list

This page is a plan, not the current state. It says which SSDs to add to the TrueNAS NAS and where they go, so the `flash` Longhorn tag gets a second copy on another host. Read it before you buy a drive or change a NAS pool. No disk has been bought or changed yet. **Every bay number below is unverified** until the iLO check.

## Why Longhorn on the NAS, not NFS

- No single node may take workloads down. An NFS or iSCSI volume stops when the NAS reboots, so the NAS would become a second exception next to the GPU worker.
- A Longhorn copy on the NAS worker VM does not. One copy sits on `ssd-flash` (GPU worker), one on the NAS mirror. Either host can reboot while the other serves.
- Both hosts have 10 GbE. The only NAS NVMe/TCP test was poor, so serving straight from the NAS stays untested for NFS and iSCSI on a mirror.

## Today

The Longhorn disk `truenas-ssd` on `truenas-worker-01` carries the `flash` tag (set live on 2026-11-11), so `flash` volumes can already put a second copy on the NAS worker. That disk is small. The `flash` mirror below stays the planned final home.

## Check before buying

The bay count is **unverified**. Open iLO, go to System Information, then Storage. Confirm 8 bays and the bay number of each disk. Do this before step 2 of the buy list. Every bay number on this page, including bays 4, 5 and 6, rests on that check.

## Target layout

Bay numbers here are **unverified**. They assume an 8-bay cage.

| Bay | Today | Target |
|---|---|---|
| 1, 2 | boot-pool mirror | unchanged |
| unknown | 850 EVO + P3-512 (`vm-ssd` mirror) | replace with 400 GB PLP drives |
| free bay (unverified) | empty | buy 2, disk A: 960 GB PLP |
| 6-8 | `ai-pool` stripe | unchanged. Bay 6 or a free SAS2308 lane (phys 1, 2, 3) takes buy 2, disk B. |

The new pool `flash` is one 2-way mirror of 960 GB, about 860 GiB usable. Keep it under 80% full. It holds a zvol for a Longhorn disk `truenas-flash` on `truenas-worker-01`, tag `flash`. That disk holds the second copy of the radar-ng `flash` volumes (about 150 GiB booked) and the database copies. Use mirrors, not RAIDZ: they write small blocks faster and grow one pair at a time.

## Buy list

| # | When | Drive | Count | Rules | Price ceiling |
|---|---|---|---|---|---|
| 1 | First | Intel DC S3710 400 GB `SSDSC2BA400G4` or S3700 400 GB `SSDSC2BA400G3` | 1 (a lot of 2 only at the lot price) | At least 400,088,457,216 bytes. 10% used or less, 0 reallocated. | Single: **$80** ([example](https://www.ebay.com/itm/198717556894)). Lot of 2: **$75** per drive, $150 total ([example](https://www.ebay.com/itm/960116259705)). |
| 2 | **Do not buy before the #3665 results** | Intel D3-S4610 960 GB `SSDSC2KG960G8` or Samsung PM883 960 GB `MZ7LH960HAJR` | 2, same model | 10% used or less, 0 reallocated, seller SMART screenshot. | S4610: **$185** each ([example](https://www.ebay.com/itm/237003950003)). PM883: **$170** each ([example](https://www.ebay.com/itm/227598672787)). |

Do not pay more than the ceiling. The example listings date from 2026-08-30 to 2026-11-05, and deal-scout rates each one as a reject on price. Prefer the S4610 when it costs within about $15 of the PM883. The S3700 is rated for 10 drive writes a day. The PM883 960 GB is rated for 1,366 TBW.

deal-scout searches for these four models use the same ceilings. The 400 GB models have a single-drive search at $80 and a `lot` search at $150. The 960 GB searches are marked "do not buy before #3665 results".

## Skip

- NVMe in PCIe slot 1: one free slot, and splitting it is unverified.
- Consumer or QLC SSDs: no power-loss protection (PLP).
- Drives of 1.92 TB or more: the need is about 190 GiB.
- SLOG or special vdev: an all-PLP mirror does not need one.
- A disk shelf or second HBA: wait for the bay check.

The DL360 runs on one 500 W PSU and the second bay is empty. With a Longhorn copy on the NAS, a PSU failure is one more node down. A second matching PSU is cheap insurance. It is not priced here.

## Not verified

- The bay count.
- The enclosure bays behind the SAS2308.
- S4610 endurance from the vendor. A retailer lists 3 DWPD.
- ZFS write amplification.
- That the new disk's byte count is at least the S3700's.

## Related

- [Disk map](disk-map.md) lists today's NAS disks.
- [Pick a StorageClass](storage-tiers.md) describes `longhorn-flash`.
- [Disk writes](disk-writes.md) lists the rules that limit SSD wear.
