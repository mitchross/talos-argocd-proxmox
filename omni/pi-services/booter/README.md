# booter: PXE boot for bare-metal Talos

[`siderolabs/booter`](https://github.com/siderolabs/booter) network-boots bare-metal
machines into Omni. A machine with an empty disk boots Talos from the network and
appears in **Omni → Machines** as an available machine. No USB stick is needed.

booter does not add a machine to a cluster, label it or wipe its disks. The
cluster template does that.

## How it works

1. A machine's firmware tries its disk first. With no bootable disk, it falls
   back to network boot and broadcasts a DHCP request.
2. The Firewalla (`192.168.10.1`) answers with the IP address, as it does for
   every client.
3. booter answers **only PXE clients**, with boot-file information
   (proxy-DHCP). It never hands out addresses, so normal clients are unaffected.
4. The machine fetches iPXE from booter over TFTP. iPXE then loads the Talos
   kernel from Image Factory, with the Omni join arguments from `booter.env`.
5. Talos starts in maintenance mode and connects to Omni over SideroLink.

## Ports on the Pi (`192.168.10.15`)

| Port | Use |
|---|---|
| UDP 67, UDP 4011 | Proxy-DHCP |
| UDP 69 | TFTP (iPXE binaries) |
| TCP 50084 | booter API (iPXE script) |

booter needs `network_mode: host`. Nothing else on the Pi may listen on these
ports. Technitium publishes only 53 and 5380, and its DHCP server stays off.

## Settings

| Setting | Where | Rule |
|---|---|---|
| Talos version | `--talos-version` in `docker-compose.yml` | Keep equal to `talos.version` in `omni/cluster-template/cluster-template-prod-v2.yaml`. |
| Extensions | `--extensions` | Boot-time only. Per-machine extensions come from the cluster template. |
| Omni join arguments | `EXTRA_KERNEL_ARGS` in `booter.env` | Secret. Keep it on the Pi only. |

## Deploy

Use a checkout of the merged PR on the Pi. The project lives in
`/home/vanillax/booter/`.

1. Copy `docker-compose.yml` to `/home/vanillax/booter/`.
2. Create `booter.env` from `booter.env.example`. Paste the value from
   **Omni UI → Overview → Copy Kernel Parameters**, then run
   `chmod 600 booter.env`.
3. Check the config without printing the secret:
   `docker compose config --quiet`.
4. Run in the foreground once: `docker compose up`. Expect log lines for the
   DHCP proxy, TFTP and the API on port 50084, with no errors. Stop it with
   Ctrl-C.
5. Start it in the background: `docker compose up -d`.
6. Check the other Pi services: `docker ps`, DNS on `192.168.10.15`, and
   Omni's machine connections.

## Verify with a machine

Power on a machine that has an empty disk and network boot enabled. Then run
`docker logs -f booter`. Expect a boot response, a TFTP transfer and an iPXE
request. The machine then appears in **Omni → Machines**.

Some UEFI firmware ignores proxy-DHCP offers. If a machine never gets a boot
response, check its BIOS network-boot settings. Do not change the Firewalla's
DHCP options.

## Change the Talos version

1. Change `--talos-version` in a PR.
2. After merge, copy the file to the Pi.
3. Run `docker compose up -d`.

## Rotate the join token

1. Create a new join token in Omni.
2. Copy the new kernel parameters into `booter.env`.
3. Run `docker compose up -d --force-recreate`.

## Stop

Run `docker compose down` in `/home/vanillax/booter/`. Machines that are
already installed keep working. Only network boot stops.
