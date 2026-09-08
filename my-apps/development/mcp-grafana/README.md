# mcp-grafana

Grafana Labs' official [MCP server](https://github.com/grafana/mcp-grafana).
It lets an MCP client (Claude Code, Claude Desktop) query this cluster's
Grafana — and through it, Prometheus — in plain language, instead of opening a
dashboard.

Every Tapo plug's power, energy and cost already lands in Prometheus as
`homeassistant_sensor_*` with `friendly_name` labels, so questions like "which
box cost the most this month" are answerable without building a panel first.

## Before it will start

Two values must exist in the 1Password `homelab-prod` vault, in an item named
**`mcp-grafana`**. The ExternalSecret will stay unresolved and the pod will not
start until both are there.

| Property | What it is |
|---|---|
| `grafana_service_account_token` | Grafana → Administration → Users and access → Service accounts. **Viewer** role is enough |
| `server_token` | Any long random string you invent, e.g. `openssl rand -hex 32`. Callers must present it |

Viewer is deliberate: the server also runs `--disable-write`, so the token
cannot be used to change dashboards even if it leaks.

## Connecting a client

```bash
claude mcp add --transport http mcp-grafana \
  https://mcp-grafana.vanillax.me/mcp \
  --header "Authorization: Bearer $(op read 'op://homelab-prod/mcp-grafana/server_token')"
```

The path matters: the server serves MCP at **`/mcp`**, not at the root. A bare
hostname returns 404 and the client reports only that it could not connect.

## Why it is shaped this way

**Internal route only.** This hands out query access to every Grafana
datasource. It is parented to `gateway-internal-technitium` and must never be
moved to `gateway-external`.

**`--address=0.0.0.0:8000`.** The binary defaults to `localhost:8000`, which in
a pod accepts nothing. Without this flag the readiness probe never passes.

**`command` is overridden.** The image bakes `--transport sse --address
0.0.0.0:8000` into its ENTRYPOINT, so setting `args` alone appends a second,
conflicting `--transport`. Owning the whole argv avoids relying on which
duplicate flag Go's parser happens to keep.

**`--allowed-hosts` is enumerated.** The server validates the `Host` header.
Adding a new hostname for this service means adding it to that list too, or
requests arrive and are rejected.

**Origin validation is left at its default** (reject anything sending an
`Origin` header). MCP clients are not browsers; if a browser-based client is
ever needed, that is when `--allowed-origins` gets set.
