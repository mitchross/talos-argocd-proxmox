# Paseo: agent map

Read this before you change Paseo, its image, or any Pi/LiteLLM wiring it uses.
Human steps and concepts live in [docs/domains/ai-gpu/paseo.md](../../../docs/domains/ai-gpu/paseo.md).

## Which repo owns which change

| Change | Owner | Path |
|---|---|---|
| Deployment, env, volumes, route, backups | `mitchross/talos-argocd-proxmox` | `my-apps/development/paseo/` |
| Pi model list inside the pod | talos | `config/pi-models.json` (copy of the JSON in `docs/domains/ai-gpu/pi-agent-local-dev.md`, with the in-cluster URL) |
| Qwen sampler hook inside the pod | talos | `config/qwen-sampling.ts` (copy of `scripts/pi/qwen-sampling.ts`) |
| LiteLLM routes and model names | talos | `my-apps/ai/litellm/config.yaml` |
| Image: tools, agent CLI versions, bash aliases, first-boot seeds | `mitchross/homelab-images` | `images/paseo-dev/` |
| Image digest that the cluster runs | talos | `deployment.yaml` `image:` |
| Pi on the user's PC, zsh launchers, global agent rules | `mitchross/dotfiles` (chezmoi) | `~/.pi/agent/`, `~/.zshrc` |
| Secret values | 1Password vault `homelab-prod` | items `paseo`, `litellm` |
| Upstream Paseo behavior | `getpaseo/paseo` | read the tagged source; do not fork |

`scripts/tests/test_qwen_reasoning.py` fails when either talos copy drifts. Update both sides in one PR.
An image change needs two PRs: homelab-images first, then a digest bump here.

## Three runtimes, three permission sets

| Runtime | Can | Cannot |
|---|---|---|
| User's PC (CachyOS) | `kubectl`, `talosctl`, `omnictl`, `gh`, `op`; reach `litellm.vanillax.me` | — |
| Paseo pod (`paseo` ns, uid 1000) | `gh` and `git push` as the user's account; Claude, Codex, Pi; LiteLLM via `litellm-service.litellm:4000`; reach most cluster services | Kubernetes API (no service-account token), Talos, Omni, Proxmox |
| Argo CD | apply `main` of the talos repo | — |

Claude Code auto mode on the PC blocks commands that write inside pods. Ask the user, or change Git.

## Rules

- Change Paseo through Git. Never edit files in the pod or on its volumes to fix configuration.
- Keep secrets out of the image and Git. Add them to 1Password and an `ExternalSecret`.
- Leave logins as runtime state: `gh`, `claude`, and `codex` logins live in `/home/paseo`.
- Write Pi `apiKey` as `"$LITELLM_API_KEY"`. A bare name is sent literally; LiteLLM answers `400 No connected db`.
- Keep `PASEO_HOSTNAMES` equal to the route hostname, or requests fail with `403 Host not allowed`.
- Keep `PASEO_TRUSTED_PROXIES`; without it the web UI gets `useTls:false` and cannot auto-connect.
- The relay is off. Do not suggest QR or pairing-link setup.
- In the pod, never run `mink init` or `mink refresh-hooks`; restore any change they make to `.claude/` or `.pi/` files.
- Keep the image's `MINK_VERSION` equal to the workstations' Mink version.

## Open risks (deferred by the user)

- One password guards a public URL, and Paseo has no login rate limit.
- The pod's `gh` login can push to every repo, and talos `main` has no branch protection.
- The shared Cilium policy does not isolate this namespace.

Raise these only when a change touches them.
