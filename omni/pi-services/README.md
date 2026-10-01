# Pi service maintenance

Runbook for the ARM64 Pi at `192.168.10.15`. Omni, its five Proxmox providers,
Technitium DNS and ProxCenter run here in Docker, outside Talos and Argo CD.
Deploy configuration from a merged PR over SSH. Existing secret files and
persistent storage stay on the Pi; do not copy them into Git.

## Version choices

The October 1, 2026 inspection found these running versions and prepared targets.
The target files are desired state until deployed and verified live.

| Service | Inspected running state | Prepared target |
| --- | --- | --- |
| Docker Engine / containerd | 29.8.1 / 2.3.5 | 29.8.2 / 2.3.6 |
| Docker Compose / Buildx | 5.5.1 / 0.37.1 | Already current in Docker's ARM64 apt repository |
| Omni | 1.12.2 | [1.12.3](https://github.com/siderolabs/omni/releases/tag/v1.12.3), pinned in [omni.env.example](../omni/omni.env.example) |
| Proxmox providers, five containers | 0.3.0 | Already latest stable; keep [existing pins](../proxmox-providers/docker-compose.yml) |
| Technitium DNS | 15.4.0 | [15.5.1](https://github.com/TechnitiumSoftware/DnsServer/releases/tag/v15.5.1), pinned in [Compose](technitium/docker-compose.yml) |
| ProxCenter frontend | Native ARM64 1.4.10, Node 26.8.2, Alpine 3.24.1 | Same stable application source; rebuild with Node 26.10.0 / Alpine 3.24.2 |
| ProxCenter PostgreSQL | 16.15, digest from September 17 | Same major/minor, refreshed image pinned in [override](proxcenter/docker-compose.override.yml) |

Upstream ProxCenter's [publishing workflow](https://github.com/adminsyspro/proxcenter-ui/blob/main/.github/workflows/docker-publish.yml)
still builds only `linux/amd64`. Its stable `v1.4.10` release resolves to
`533d8127b60fd5f5d59985109893725c80f1c687`, matching `/opt/proxcenter-src` at inspection.
Do not run its installer or pull its frontend image on this Pi.

The [build script](proxcenter/build-arm64.sh) downloads that immutable source
into a temporary directory and pins an ARM64 Node base image. Its 5120 MiB
build heap preserves the Pi workaround without changing `/opt/proxcenter-src`
or enlarging the application's runtime heap. The resulting tag is local only:
keep `pull_policy: never`, retain the previous image, and never use a registry
digest for the custom frontend tag. `APP_VERSION` and `GIT_SHA` are set at build
time so the rebuilt image identifies its application source.

## Prepare and back up

Prerequisites: SSH as `vanillax`, passwordless sudo, Docker access, at least
6 GiB available RAM for the native build and enough free disk for backups,
the existing Compose projects and their secrets, and a merged maintenance PR.
Use a checkout of that merged commit; below, `repo_dir` is its absolute path
on the Pi. The Compose projects and volumes already exist; this is not an
installation procedure.

1. Record container image IDs, package versions, health checks, DNS answers,
   and Omni machine connectivity before making changes. Check `free -h`,
   `df -h /`, and `docker ps`. Avoid a full `docker compose down`.
2. Create a root-owned `0700` dated directory under `/var/backups/pi-maintenance/`.
   Stop the ProxCenter frontend, Omni, and Technitium gracefully before copying
   their state. Arrange to start those same containers on any backup error.
   Dump ProxCenter using `docker exec proxcenter-postgres pg_dump -U proxcenter
   -d proxcenter -Fc`; keep PostgreSQL running while the frontend is stopped.
3. Archive `/etc/etcd`, `/etc/omni/sqlite`, Omni's encryption key, the Compose
   files, local env/config/secret files for all projects, Technitium's config,
   and the `proxcenter_data` volume. This backup contains secrets: do not print,
   publish or make it world-readable. Validate the archive with `gzip -t` and
   `tar -tzf`, and the database dump with `pg_restore --list`. Retain checksums.
4. Start the stopped containers and verify DNS and ProxCenter's `/api/health`
   before upgrading. The backup is a local rollback copy; protect an off-host
   copy separately.

## Update and verify one service at a time

On the Pi, after reviewing the [Docker release notes](https://docs.docker.com/engine/release-notes/29/):

```sh
sudo apt-get update
sudo apt-get -s install --only-upgrade docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin docker-ce-rootless-extras
sudo apt-get install --only-upgrade docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin docker-ce-rootless-extras
```

Expect Docker 29.8.2 and containerd 2.3.6 or the reviewed later patch targets.
Docker's package update can restart all containers. Verify `systemctl is-active
 docker containerd`, `docker ps`, LAN DNS and Omni before continuing.

Set `repo_dir` to the merged checkout, then build without replacing the live
frontend. Run detached so an SSH interruption does not kill the build:

```sh
repo_dir=/absolute/path/to/merged/checkout
sudo systemd-run --unit=proxcenter-arm64-build-20261001 --collect \
  /usr/bin/bash "$repo_dir/omni/pi-services/proxcenter/build-arm64.sh"
sudo journalctl -fu proxcenter-arm64-build-20261001
```

Watch overall RAM during the build because DNS and Omni share this Pi.
Expect `arm64` and an image ID at the end; do not deploy after a failed or
interrupted build.

Copy [Technitium's Compose file](technitium/docker-compose.yml) to
`/home/vanillax/technitium-dns/docker-compose.yml`. Keep its existing `.env`
(`HOST_LAN_IP=192.168.10.15`), `secrets/`, `config/` and `logs/`. From that project:

```sh
docker compose config --quiet
docker compose pull technitium-dns
docker compose up -d --no-deps technitium-dns
dig @192.168.10.15 grafana.vanillax.me +short
dig +tcp @192.168.10.15 grafana.vanillax.me +short
```

Both queries must retain the previous answer. Verify the admin UI on port 5380
and DNS server startup logs. This server uses `DNS_SERVER_RECURSION=Deny`, so
unrelated recursive queries are not an appropriate success check.

Update only `OMNI_IMG_TAG` in
`/home/vanillax/omni-talos-selfhosted-infrastructure/omni/omni.env` to the pin in
[omni.env.example](../omni/omni.env.example). From that project's directory:

```sh
docker compose --env-file omni.env config --quiet
docker compose --env-file omni.env pull omni
docker compose --env-file omni.env up -d --no-deps omni
```

Verify the HTTPS UI and machine connections and inspect Omni's migration log.
The provider release is already current; check that all five reconnect after
Omni restarts. Keep the workstation's `omnictl` aligned with the server.

After the ARM64 build succeeds, copy the [ProxCenter override](proxcenter/docker-compose.override.yml)
to `/opt/proxcenter/docker-compose.override.yml`. Keep the existing base Compose
and `.env`, including database credentials and application encryption keys.
From `/opt/proxcenter`:

```sh
docker compose config --quiet
docker compose pull postgres
docker compose up -d --no-deps postgres
```

Wait for `proxcenter-postgres` to be healthy, then:

```sh
docker compose up -d --no-deps frontend
docker exec proxcenter-frontend wget -qO- http://127.0.0.1:3000/api/health
docker exec proxcenter-frontend node --version
```

Expect `status: healthy`, `db: reachable` and Node `v26.10.0`. Confirm the image
is ARM64, both containers are healthy, and the five configured Proxmox
connections remain. Preserve the previous frontend image and all data volumes.

## Failure path

Stop at the first failed service check; inspect that service's logs before
updating the next one. Restore its previous Compose/env file from the private
backup and recreate only that service. Keep previous images; do not prune
images or delete volumes during maintenance.

An Omni schema migration prevents a blind image downgrade: follow
[Omni's update guidance](../omni/README.md#updating-omni) and use a coordinated
state/config/key restore if necessary. A database restore overwrites live
state and requires explicit authorization. Never run PostgreSQL 17 or later
against the existing 16 data directory; a major upgrade is separate work.
