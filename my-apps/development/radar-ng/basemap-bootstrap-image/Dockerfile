# Self-healing basemap bootstrap image for radar-ng.
#
# Why this exists (do not "simplify" back to a pinned date):
#   build.protomaps.com serves date-stamped planet builds (YYYYMMDD.pmtiles)
#   with a ~6-day retention window and NO `latest` alias. A date hardcoded
#   in the Job manifest rots in ~6 days, and the rot is invisible until the
#   Job is recreated (cluster DR / namespace rebuild) — i.e. it detonates at
#   the worst possible moment with an HTTP 404. The upstream go-pmtiles image
#   is distroless (no shell), so the newest-build date cannot be resolved
#   from a plain Kubernetes manifest. This thin wrapper adds a shell that
#   resolves "newest build that actually exists" at run time, so the date is
#   never pinned anywhere and the Job survives any rebuild unattended.
#
# Bases are digest-pinned (repo rule: never float on a tag alone).

# go-pmtiles binary source (distroless upstream; we only want the binary).
FROM protomaps/go-pmtiles:v1.31.0@sha256:7497c3b4274b57902b45f741d25ca495a8a245f6bece93444ad3cecbcad8b202 AS pmtiles

FROM alpine:3@sha256:28bd5fe8b56d1bd048e5babf5b10710ebe0bae67db86916198a6eec434943f8b

# curl: probe + download. coreutils: GNU `date -d "-N days"` (busybox date
# cannot do relative-day arithmetic reliably).
RUN apk add --no-cache curl coreutils

# The upstream entrypoint binary. Path verified against the distroless
# image's ENTRYPOINT (/go-pmtiles).
COPY --from=pmtiles /go-pmtiles /usr/local/bin/pmtiles

COPY resolve-and-extract.sh /usr/local/bin/resolve-and-extract.sh
RUN chmod +x /usr/local/bin/resolve-and-extract.sh

USER 1000:1000
ENTRYPOINT ["/usr/local/bin/resolve-and-extract.sh"]
