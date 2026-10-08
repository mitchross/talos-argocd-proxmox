# Paseo

Argo CD syncs this directory as `my-apps-paseo`. It runs Paseo at `https://paseo.vanillax.me`.

**How to connect, log in, verify, and change it:** [docs/domains/ai-gpu/paseo.md](../../../docs/domains/ai-gpu/paseo.md).
**Which repo owns which change:** [CLAUDE.md](CLAUDE.md).

| File | Holds |
|---|---|
| `deployment.yaml` | Pod, image digest, env vars, mounts |
| `externalsecret.yaml` | `PASEO_PASSWORD` and `LITELLM_API_KEY` from 1Password |
| `pvc.yaml`, `kopiur/` | `paseo-home` and `paseo-workspace`, with daily backups |
| `service.yaml`, `httproute.yaml` | Port `6767` behind `gateway-internal-technitium`; remote clients use Tailscale |
| `config/pi-models.json` | Pi model list, CI-checked against the Pi agent guide |
| `config/qwen-sampling.ts` | Pi sampler hook, CI-checked against `scripts/pi/qwen-sampling.ts` |
| `vpa.yaml` | Request sizing |

Never delete this directory as a rollback: Argo CD can prune the volumes.
