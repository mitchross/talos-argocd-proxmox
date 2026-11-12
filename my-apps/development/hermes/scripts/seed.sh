#!/bin/sh
# Init container, runs as root before s6 starts: apply the Git-owned config, skill and cron job; install plugins and hooks once.
set -eu
HERMES_HOME=/opt/data
HOME=/opt/data
REPO_URL=https://github.com/mitchross/talos-argocd-proxmox.git
REPO_DIR="$HERMES_HOME/workspace/talos-argocd-proxmox"
export HERMES_HOME HOME PATH="/command:${PATH}"
as_hermes() { s6-setuidgid hermes env HOME="$HOME" "$@"; }

mkdir -p "$HERMES_HOME/workspace" "$HERMES_HOME/skills/devops/homelab-ops" "$HERMES_HOME/.local/bin" "$HERMES_HOME/.hindsight" "$HERMES_HOME/hindsight"
install -o 10000 -g 10000 -m 0644 /etc/hermes-config/config.yaml "$HERMES_HOME/config.yaml"
install -o 10000 -g 10000 -m 0644 /etc/hermes-config/SOUL.md "$HERMES_HOME/SOUL.md"
install -o 10000 -g 10000 -m 0644 /etc/hermes-skills/SKILL.md "$HERMES_HOME/skills/devops/homelab-ops/SKILL.md"
install -D -o 10000 -g 10000 -m 0644 /etc/hermes-skills/hermes-change-placement.md "$HERMES_HOME/skills/devops/hermes-change-placement/SKILL.md"
chown 10000:10000 "$HERMES_HOME/skills/devops/hermes-change-placement"
# Hermes memory plugin settings; this file replaces the env-derived config, the API key still comes from HINDSIGHT_API_KEY.
install -o 10000 -g 10000 -m 0644 /etc/hermes-config/hindsight-hermes.json "$HERMES_HOME/hindsight/config.json"
# Hook configs for claude and codex in this pod; the token comes from the mounted Secret, never from Git.
for f in claude-code codex; do
  sed "s|__HINDSIGHT_API_KEY__|${HINDSIGHT_API_KEY}|" "/etc/hermes-config/hindsight-$f.json" > "$HERMES_HOME/.hindsight/$f.json"
  chown 10000:10000 "$HERMES_HOME/.hindsight/$f.json"; chmod 0600 "$HERMES_HOME/.hindsight/$f.json"
done
rm -f "$HERMES_HOME/.local/bin/kubectl"  # pre-image leftover; it shadowed /usr/local/bin/kubectl
chown 10000:10000 "$HERMES_HOME" "$HERMES_HOME/hindsight" "$HERMES_HOME/workspace" "$HERMES_HOME/skills" "$HERMES_HOME/skills/devops" "$HERMES_HOME/skills/devops/homelab-ops" "$HERMES_HOME/.local" "$HERMES_HOME/.local/bin" "$HERMES_HOME/.hindsight"

for plugin in hindsight homeassistant advanced-delegation; do
  if [ ! -d "$HERMES_HOME/plugins/$plugin" ]; then
    echo "[seed] installing plugin $plugin"
    # A failed install (e.g. GitHub down) must not stop the pod; the next start retries.
    as_hermes /opt/hermes/bin/hermes plugins install "$plugin" --enable --yes-deps || echo "[seed] plugin install failed: $plugin"
  fi
done
if ! grep -qs '"homelab-digest"' "$HERMES_HOME/cron/jobs.json"; then
  echo "[seed] creating cron job homelab-digest"
  as_hermes /opt/hermes/bin/hermes cron create "every day at 08:00" \
    "Load the homelab-ops skill, run all six checks, and write the digest in the skill's format." \
    --skill homelab-ops --name homelab-digest
fi
# Git-owned cron jobs: rewrite each script from Git, create a missing job. A job deleted in the dashboard returns unless Git drops it too.
mkdir -p "$HERMES_HOME/scripts"; chown 10000:10000 "$HERMES_HOME/scripts"
for src in /etc/hermes-scripts/cron-*.py; do
  dst="$HERMES_HOME/scripts/${src##*/cron-}"
  install -o 10000 -g 10000 -m 0644 "$src" "$dst"
done
while IFS='|' read -r name schedule script prompt; do
  case "$name" in '' | '#'*) continue ;; esac
  grep -qs "\"$name\"" "$HERMES_HOME/cron/jobs.json" && continue
  echo "[seed] creating cron job $name"
  as_hermes /opt/hermes/bin/hermes cron create "$schedule" "$prompt" --name "$name" --script "$script" --no-agent --deliver local </dev/null \
    || echo "[seed] cron create failed: $name"
done < /etc/hermes-scripts/cron-jobs.txt
# A profile-scoped config load reads ${env:...} from .env, not the pod env; without this the Cloudflare MCP sends the literal placeholder.
if [ -n "${CLOUDFLARE_API_TOKEN:-}" ]; then
  touch "$HERMES_HOME/.env"
  { grep -v '^CLOUDFLARE_API_TOKEN=' "$HERMES_HOME/.env" || true; printf 'CLOUDFLARE_API_TOKEN=%s\n' "$CLOUDFLARE_API_TOKEN"; } > "$HERMES_HOME/.env.seed"
  install -o 10000 -g 10000 -m 0600 "$HERMES_HOME/.env.seed" "$HERMES_HOME/.env"; rm -f "$HERMES_HOME/.env.seed"
fi

# Hermes runs its terminal tool with HOME=/opt/data/home and a login-shell PATH. Point that home at the
# real tool state and put /opt/agents/bin on PATH, or claude, codex and the gh/codex logins are invisible to it.
TERM_HOME="$HERMES_HOME/home"
mkdir -p "$TERM_HOME/.config" "$HERMES_HOME/.config/gh" "$HERMES_HOME/.codex" "$HERMES_HOME/.claude"
touch "$HERMES_HOME/.claude.json" "$HERMES_HOME/.gitconfig"
# Global rules for claude and codex; the pod has no workstation dotfiles.
for f in .codex/AGENTS.md .claude/CLAUDE.md; do install -o 10000 -g 10000 -m 0644 /etc/hermes-config/agent-rules.md "$HERMES_HOME/$f"; done
# OpenSSH reads ~/.ssh from the passwd home (/opt/data), not $HOME. Move the Pi-authorized key there once.
mkdir -p "$HERMES_HOME/.ssh"
if [ ! -f "$HERMES_HOME/.ssh/id_ed25519" ] && [ -f "$TERM_HOME/.ssh/id_ed25519" ] && [ ! -L "$TERM_HOME/.ssh" ]; then
  mv "$TERM_HOME/.ssh/id_ed25519" "$TERM_HOME/.ssh/id_ed25519.pub" "$HERMES_HOME/.ssh/"
fi
for d in .codex .claude .hindsight .claude.json .gitconfig .ssh; do
  [ -L "$TERM_HOME/$d" ] || { rm -rf "${TERM_HOME:?}/$d"; ln -s "$HERMES_HOME/$d" "$TERM_HOME/$d"; }
done
[ -L "$TERM_HOME/.config/gh" ] || { rm -rf "${TERM_HOME:?}/.config/gh"; ln -s "$HERMES_HOME/.config/gh" "$TERM_HOME/.config/gh"; }
# shellcheck disable=SC2016 # Preserve $PATH for the terminal's login shell.
printf '%s\n' 'export PATH=/opt/agents/bin:/opt/rust/cargo/bin:/usr/local/go/bin:$PATH' \
  'export RUSTUP_HOME=/opt/data/tools/rustup RUSTUP_AUTO_INSTALL=1 CARGO_HOME=/opt/data/.cargo' \
  'export CARGO_BUILD_BUILD_DIR=/opt/scratch/cargo-build/{workspace-path-hash} XDG_CACHE_HOME=/opt/scratch/cache' \
  'export BUN_INSTALL_CACHE_DIR=/opt/scratch/bun npm_config_cache=/opt/scratch/npm YARN_CACHE_FOLDER=/opt/scratch/yarn' > "$TERM_HOME/.profile"
# Rebuildable caches and Rust intermediates live on hermes-scratch, which has no snapshots or backups.
install -d -o 10000 -g 10000 /opt/scratch /opt/scratch/cargo-build /opt/scratch/cache /opt/scratch/bun /opt/scratch/npm /opt/scratch/yarn
# The image's Rust is read-only; a volume RUSTUP_HOME defaults to it via a link and installs repo-pinned toolchains once.
mkdir -p "$HERMES_HOME/tools/rustup"; chown 10000:10000 "$HERMES_HOME/tools" "$HERMES_HOME/tools/rustup"
for tc in /opt/rust/rustup/toolchains/*-x86_64-unknown-linux-gnu; do
  as_hermes env RUSTUP_HOME="$HERMES_HOME/tools/rustup" /opt/rust/cargo/bin/rustup toolchain link hermes-image "$tc" >/dev/null \
    && as_hermes env RUSTUP_HOME="$HERMES_HOME/tools/rustup" /opt/rust/cargo/bin/rustup default hermes-image >/dev/null \
    || echo "[seed] rustup link failed, continuing"
done
# Craft Anything MCP binary, pinned by release and sha256; bump with the craft-anything library skill.
CA_VER=0.5.0 CA_SHA=d18c54ef05e5c7ef50f8c4959fee8983c0a4a1f141edc488d11f7029973c885b
CA_DIR="$HERMES_HOME/tools/craft-anything-$CA_VER"
if [ ! -x "$CA_DIR/bin/craft-anything-cli" ]; then
  ca_tgz=/tmp/craft-anything.tar.gz
  if curl -fsSL -o "$ca_tgz" "https://github.com/storytold/craft-anything/releases/download/v$CA_VER/craft-anything-$CA_VER-linux-x86_64.tar.gz" \
    && echo "$CA_SHA  $ca_tgz" | sha256sum -c - >/dev/null; then
    mkdir -p "$CA_DIR" && tar -xzf "$ca_tgz" -C "$CA_DIR" --strip-components=1 && chown -R 10000:10000 "$CA_DIR" \
      && echo "[seed] installed craft-anything $CA_VER"
  else
    echo "[seed] craft-anything download failed, continuing"
  fi
  rm -f "$ca_tgz"
fi
# SSH targets and pinned host keys come from Git; the private key stays on the volume and is never regenerated.
mkdir -p "$TERM_HOME/.talos"
install -m 0600 /etc/hermes-config/ssh_config "$HERMES_HOME/.ssh/config"
install -m 0644 /etc/hermes-config/known_hosts "$HERMES_HOME/.ssh/known_hosts"
chmod 0700 "$HERMES_HOME/.ssh"
if [ -f "$HERMES_HOME/.ssh/id_ed25519" ]; then chmod 0600 "$HERMES_HOME/.ssh/id_ed25519"; else echo "[seed] no SSH key in $HERMES_HOME/.ssh; ssh pi will fail"; fi
# talosctl reaches nodes through Omni with the Operator service account from 1Password.
if [ -n "${OMNI_SERVICE_ACCOUNT_KEY:-}" ] && command -v omnictl >/dev/null 2>&1; then
  # omnictl caches under $HOME/.talos; as root at /opt/data that dir was unreadable and failed every backup.
  HOME="$TERM_HOME" omnictl talosconfig --cluster talos-prod-cluster-v2 --force --merge=false "$TERM_HOME/.talos/config" \
    || echo "[seed] talosconfig failed, continuing"
fi
# Drop only the localhost stub old omnictl runs left as root; rmdir keeps anything else.
rm -f "$HERMES_HOME/.talos/omni/config"; rmdir "$HERMES_HOME/.talos/omni" "$HERMES_HOME/.talos" 2>/dev/null || true
# Only what this script writes as root; a recursive chown of $TERM_HOME walked ~900k worktree and cache files.
chown 10000:10000 "$TERM_HOME" "$TERM_HOME/.profile"
chown -R 10000:10000 "$TERM_HOME/.config" "$TERM_HOME/.talos" "$HERMES_HOME/.ssh" "$HERMES_HOME/.config" "$HERMES_HOME/.codex" "$HERMES_HOME/.claude" "$HERMES_HOME/.claude.json" "$HERMES_HOME/.gitconfig"

# Coding agents: repo checkout, git identity, shared-memory hooks. gh and codex logins are done once by hand (docs).
as_hermes git config --global user.name "Hermes Agent"
as_hermes git config --global user.email "mitchross@users.noreply.github.com"
as_hermes git config --global init.defaultBranch main
export HERMES_SKILLS_OFFLINE=0
if [ ! -e "$REPO_DIR/.git" ]; then
  echo "[seed] cloning talos-argocd-proxmox"
  as_hermes git clone --quiet "$REPO_URL" "$REPO_DIR" || { export HERMES_SKILLS_OFFLINE=1; echo "[seed] clone failed, continuing"; }
else
  as_hermes git -C "$REPO_DIR" fetch --quiet --prune origin || { export HERMES_SKILLS_OFFLINE=1; echo "[seed] fetch failed, continuing"; }
fi
if as_hermes gh auth status >/dev/null 2>&1; then
  as_hermes gh auth setup-git >/dev/null 2>&1 || true
fi
if ! grep -qs hindsight-memory "$HERMES_HOME/.claude/plugins/installed_plugins.json"; then
  echo "[seed] installing Claude Code plugin hindsight-memory"
  as_hermes claude plugin marketplace add vectorize-io/hindsight >/dev/null 2>&1 || true
  as_hermes claude plugin install hindsight-memory || echo "[seed] claude plugin install failed, continuing"
fi
# Codex defaults for every run in this pod; the hooks installer appends its own [features] block below.
if ! grep -qs '^model_reasoning_effort' "$HERMES_HOME/.codex/config.toml"; then
  mkdir -p "$HERMES_HOME/.codex"
  printf 'model = "gpt-6.1-sol"\nmodel_reasoning_effort = "high"\n' | cat - "$HERMES_HOME/.codex/config.toml" 2>/dev/null > "$HERMES_HOME/.codex/config.toml.new"
  mv "$HERMES_HOME/.codex/config.toml.new" "$HERMES_HOME/.codex/config.toml"
  chown 10000:10000 "$HERMES_HOME/.codex" "$HERMES_HOME/.codex/config.toml"
fi
if [ ! -f "$HERMES_HOME/.codex/hooks.json" ]; then
  echo "[seed] installing Codex Hindsight hooks"
  # --mode local only writes hooks; cloud mode would overwrite .hindsight/codex.json.
  as_hermes sh -c 'curl -fsSL https://hindsight.vectorize.io/get-codex | bash -s -- --mode local' || echo "[seed] codex hooks install failed, continuing"
fi
# Git inventory, missing-only library restore, last-good fallback and informational drift.
as_hermes /opt/hermes/.venv/bin/python /etc/hermes-scripts/seed-skills.py "$REPO_DIR" \
  || echo "[seed] skills: seed failed; keeping installed skills"
as_hermes /opt/hermes/.venv/bin/python /etc/hermes-scripts/reconcile-kanban.py \
  || echo "[seed] Kanban reconciliation failed; inspect task diagnostics"
# Qwen Lab profiles (qwen-lab, qwen-worker, ...) and their Kanban board; never writes the default profile.
as_hermes /opt/hermes/.venv/bin/python /etc/hermes-scripts/seed-qwen-lab.py \
  || echo "[seed] qwen-lab seed failed; default profile unaffected"
# Hermes reads this file to see what a rebuild from Git would lose.
/bin/sh /etc/hermes-scripts/report-drift.sh | tee "$HERMES_HOME/logs/seed-drift.log" || true
echo "[seed] done"
