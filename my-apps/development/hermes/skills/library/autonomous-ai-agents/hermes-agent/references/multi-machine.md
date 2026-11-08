# Multi-machine Hermes: where the agent runs, and reaching other machines

## First: identify where *this* agent executes
The desktop app is only a UI. It can be attached to a remote gateway (e.g. a Kubernetes pod), and then every tool call runs on that remote host, not the PC the user is looking at.

Before saying anything about "your desktop", "your files" or "your machine", check:
```bash
hostname; uname -r; grep -A2 '^terminal:' "$HERMES_HOME/config.yaml"
```
- A pod-style hostname (`hermes-<hash>-<id>`) or a cluster kernel (e.g. `*-talos`) means the agent runs on the cluster. `terminal.backend: local` means local *to the gateway host*, not to the desktop app.
- Explain the split plainly: the window is on the PC, the agent runs on the server. Users often assume they are the same machine.
- Other in-cluster tool backends (e.g. Paseo terminals or workspaces) run on the cluster too. Check `hostname` inside them before assuming they reach the desktop.
- Desktop-UI tools (`read_terminal`, `read_window_below`, `desktop_preview`) only work while this chat is open in a Desktop window. On failure, ask the user to open the chat there; don't treat it as proof the desktop is unreachable.
- If `read_terminal` fails while the chat IS open in Desktop, compare the status bar's `client vX` and `backend vY`. An older client may lack the bridge, so tell the user to update the app. `read_terminal` only reads the in-app terminal pane; it never types into it.
- The status bar's gateway name (e.g. a cluster hostname vs "This device") tells you which agent the window is attached to. A result from an earlier session showing the desktop's own kernel came from the local runtime, not from this agent.
- Chat tabs on the same gateway share memory notes, Hindsight, skills and the workspace, but **not conversation**. A new tab knows only what was stored. When a user splits one project across tabs (or across Hermes and a local coding agent), check GitHub/recent PRs for what the other tab did before acting, and keep one written record (a tracking issue) as the handoff. Read an old tab's transcript with the chat-history tool when asked.

## Reaching files or commands on other machines (decision table)
| Need | Mechanism | Setup |
|---|---|---|
| User chats with agents on several PCs from one app | Desktop **Settings → Gateways** connections registry (Local / Remote gateway / SSH / Cloud) | Install Hermes on each PC (`curl -fsSL https://hermes-agent.nousresearch.com/install.sh \| bash`); its local runtime is the built-in "This device" entry; remote ones need a `hermes serve` URL + token, or `user@host` for SSH |
| Cluster agent asks a desktop agent something, only while the app is open | Bot Mode `@mention` / `message_agent(target="name@<connection>")` | Same as above; the Desktop relays the message (works only while the app runs) |
| Always-on agent-to-agent messaging between machines, no app needed | `hermes peer` | On each target: `.env` with `API_SERVER_ENABLED=true`, `API_SERVER_HOST=0.0.0.0`, `API_SERVER_KEY=$(openssl rand -hex 32)`; run the gateway as a service (api_server port 8642). On the caller: `hermes peer add <name> --url http://<host>:8642 --key <key>`, then `hermes peer dm <name> "…"` or `message_agent(target="<name>")`; use `peer run` / `peer status` for long turns |
| **One agent only** (e.g. the cluster agent), occasionally pulling a file or `git status` from desktops | Plain `ssh`/`scp` run from the agent's normal terminal: `ssh cachy 'ls ~/programming'`, `scp mac:~/x .` | Key in the agent's persistent `$HOME/.ssh` (check it sits on a persistent volume), `~/.ssh/config` host aliases, desktop `sshd` on, pubkey in `authorized_keys` restricted with `from="<cluster node subnet>"` (plus `restrict` + forced `command=` on sensitive hosts, see below); pod egress allowed to host:22; stable IPs or Tailscale names. No Hermes install, model config or token cost on the desktops. **Default recommendation when the user wants a single agent.** |
| Agent's whole shell should live on one remote box | `terminal.backend: ssh` (`TERMINAL_SSH_HOST/USER/KEY` in `.env`) | Moves *all* commands there, so it is wrong when the agent must keep working on its own host or reach several machines |

### SSH from a gateway pod: network and key hardening
- Every SSH path (plain `ssh`, `terminal.backend: ssh`, the `hermes-ssh` Desktop plugin) dials from wherever the gateway runs. With a remote gateway in Kubernetes that is the pod, so pod egress rules apply.
- An SSH **timeout** (not "permission denied") from a pod usually means a network policy: `kubectl get ciliumclusterwidenetworkpolicy,networkpolicy -A` and look for a default-deny LAN egress. If another port on the same host also times out, it is the policy, not sshd. The fix is a namespaced `CiliumNetworkPolicy` selecting only the Hermes pod, `toCIDR: <host>/32`, `toPorts: 22/TCP`, shipped by PR in the app directory.
- Pod traffic to the LAN is masqueraded to the node IP, so `from=` must cover the node subnet, not the pod CIDR.
- For sensitive hosts (anything running Omni, etcd, Docker, secrets), don't hand out a plain shell key. Best practice (NIST IR 7966, OpenSSH forced commands): a dedicated user (e.g. `hermes-ro`), and an `authorized_keys` line `restrict,from="<node subnet>",command="/usr/local/bin/hermes-ro" <pubkey>` where the wrapper allowlists read-only commands from `$SSH_ORIGINAL_COMMAND` and refuses the rest. `from=` alone limits where, not what. Writes stay with the user or get added to the allowlist deliberately.
- When the user asks "is this safe / best practice", say plainly which part is fine and which part grants too much, then give the hardened version.

Explaining Gateways vs SSH to a user: Gateways switches *which agent the window talks to* (each has its own memory, skills and model config). SSH lets *one agent* reach other machines. Recommend SSH when the user wants a single always-on agent. If they decline SSH for now, give copy-paste commands or a ready-made prompt for a local coding agent instead.

Notes:
- Peer links are direct gateway-to-gateway. A cluster has to be able to route to the desktops (LAN or Tailscale). NAT blocks the inbound direction.
- Peer and Bot Mode replies are text. To "retrieve files", have the remote agent read the files and reply with the contents, or push them to a shared place (git, NAS, S3). There is no built-in file-transfer channel.
- An API_SERVER_KEY grants command execution on that machine. Use a strong key and don't expose the port publicly.

## macOS targets (any mechanism)
- Service: `hermes gateway install` creates a launchd agent (starts at login). For plain SSH, enable System Settings → General → Sharing → **Remote Login**.
- TCC: background processes and SSH sessions cannot read `~/Desktop`, `~/Documents`, `~/Downloads` until granted **Full Disk Access** (the gateway, or Remote Login's "allow full disk access" box); otherwise reads fail with "Operation not permitted".
- The macOS firewall prompts on the first inbound listener (port 8642); deny = unreachable.
- A sleeping laptop is unreachable; Desktop **Settings → Advanced → Keep computer awake** or `caffeinate` for desktops-as-servers. Expect timeouts and report them rather than retrying.
- Pin the address (DHCP reservation or Tailscale name) so peer URLs / ssh aliases don't rot.
