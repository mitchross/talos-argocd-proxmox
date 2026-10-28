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
# Hermes memory plugin settings; this file replaces the env-derived config, the API key still comes from HINDSIGHT_API_KEY.
install -o 10000 -g 10000 -m 0644 /etc/hermes-config/hindsight-hermes.json "$HERMES_HOME/hindsight/config.json"
# Hook configs for claude and codex in this pod; the token comes from the mounted Secret, never from Git.
for f in claude-code codex; do
  sed "s|__HINDSIGHT_API_KEY__|${HINDSIGHT_API_KEY}|" "/etc/hermes-config/hindsight-$f.json" > "$HERMES_HOME/.hindsight/$f.json"
  chown 10000:10000 "$HERMES_HOME/.hindsight/$f.json"; chmod 0600 "$HERMES_HOME/.hindsight/$f.json"
done
# Third-party skills pinned by commit in external-skills.txt; a changed sha reinstalls that skill.
grep -v '^#' /etc/hermes-scripts/external-skills.txt | while read -r repo sha path category; do
  [ -n "$repo" ] || continue
  dest="$HERMES_HOME/skills/$category/$(basename "$path")"
  [ "$(cat "$dest/.source-sha" 2>/dev/null)" = "$sha" ] && continue
  src="/tmp/skills-$(echo "$repo" | tr / -)-$sha"
  if [ ! -d "$src" ]; then
    mkdir -p "$src"
    curl -fsSL "https://codeload.github.com/$repo/tar.gz/$sha" | tar -xz -C "$src" --strip-components=1 \
      || { echo "[seed] skill fetch failed: $repo"; rm -rf "$src"; continue; }
  fi
  rm -rf "$dest"; mkdir -p "$(dirname "$dest")"
  cp -R "$src/$path" "$dest" && echo "$sha" > "$dest/.source-sha" && echo "[seed] installed skill $(basename "$path")"
  chown -R 10000:10000 "$HERMES_HOME/skills/$category"
done
rm -rf /tmp/skills-*
rm -f "$HERMES_HOME/.local/bin/kubectl"  # pre-image leftover; it shadowed /usr/local/bin/kubectl
chown 10000:10000 "$HERMES_HOME" "$HERMES_HOME/hindsight" "$HERMES_HOME/workspace" "$HERMES_HOME/skills" "$HERMES_HOME/skills/devops" "$HERMES_HOME/skills/devops/homelab-ops" "$HERMES_HOME/.local" "$HERMES_HOME/.local/bin" "$HERMES_HOME/.hindsight"

for plugin in hindsight homeassistant; do
  if [ ! -d "$HERMES_HOME/plugins/$plugin" ]; then
    echo "[seed] installing plugin $plugin"
    as_hermes /opt/hermes/bin/hermes plugins install "$plugin" --enable --yes-deps
  fi
done
if ! grep -qs '"homelab-digest"' "$HERMES_HOME/cron/jobs.json"; then
  echo "[seed] creating cron job homelab-digest"
  as_hermes /opt/hermes/bin/hermes cron create "every day at 08:00" \
    "Load the homelab-ops skill, run all six checks, and write the digest in the skill's format." \
    --skill homelab-ops --name homelab-digest
fi

# Hermes runs its terminal tool with HOME=/opt/data/home and a login-shell PATH. Point that home at the
# real tool state and put /opt/agents/bin on PATH, or claude, codex and the gh/codex logins are invisible to it.
TERM_HOME="$HERMES_HOME/home"
mkdir -p "$TERM_HOME/.config" "$HERMES_HOME/.config/gh" "$HERMES_HOME/.codex" "$HERMES_HOME/.claude"
touch "$HERMES_HOME/.claude.json" "$HERMES_HOME/.gitconfig"
# OpenSSH reads ~/.ssh from the passwd home (/opt/data), not $HOME. Move the Pi-authorized key there once.
mkdir -p "$HERMES_HOME/.ssh"
if [ ! -f "$HERMES_HOME/.ssh/id_ed25519" ] && [ -f "$TERM_HOME/.ssh/id_ed25519" ] && [ ! -L "$TERM_HOME/.ssh" ]; then
  mv "$TERM_HOME/.ssh/id_ed25519" "$TERM_HOME/.ssh/id_ed25519.pub" "$HERMES_HOME/.ssh/"
fi
for d in .codex .claude .hindsight .claude.json .gitconfig .ssh; do
  [ -L "$TERM_HOME/$d" ] || { rm -rf "${TERM_HOME:?}/$d"; ln -s "$HERMES_HOME/$d" "$TERM_HOME/$d"; }
done
[ -L "$TERM_HOME/.config/gh" ] || { rm -rf "${TERM_HOME:?}/.config/gh"; ln -s "$HERMES_HOME/.config/gh" "$TERM_HOME/.config/gh"; }
printf '%s\n' 'export PATH=/opt/agents/bin:/opt/rust/cargo/bin:/usr/local/go/bin:$PATH' \
  'export RUSTUP_HOME=/opt/rust/rustup CARGO_HOME=/opt/data/.cargo' > "$TERM_HOME/.profile"
# SSH targets and pinned host keys come from Git; the private key stays on the volume and is never regenerated.
mkdir -p "$TERM_HOME/.talos"
install -m 0600 /etc/hermes-config/ssh_config "$HERMES_HOME/.ssh/config"
install -m 0644 /etc/hermes-config/known_hosts "$HERMES_HOME/.ssh/known_hosts"
chmod 0700 "$HERMES_HOME/.ssh"
if [ -f "$HERMES_HOME/.ssh/id_ed25519" ]; then chmod 0600 "$HERMES_HOME/.ssh/id_ed25519"; else echo "[seed] no SSH key in $HERMES_HOME/.ssh; ssh pi will fail"; fi
# talosctl reaches nodes through Omni with the Operator service account from 1Password.
if [ -n "${OMNI_SERVICE_ACCOUNT_KEY:-}" ] && command -v omnictl >/dev/null 2>&1; then
  omnictl talosconfig --cluster talos-prod-cluster-v2 --force --merge=false "$TERM_HOME/.talos/config" \
    || echo "[seed] talosconfig failed, continuing"
fi
chown -R 10000:10000 "$TERM_HOME" "$HERMES_HOME/.ssh" "$HERMES_HOME/.config" "$HERMES_HOME/.codex" "$HERMES_HOME/.claude" "$HERMES_HOME/.claude.json" "$HERMES_HOME/.gitconfig"

# Coding agents: repo checkout, git identity, shared-memory hooks. gh and codex logins are done once by hand (docs).
as_hermes git config --global user.name "Hermes Agent"
as_hermes git config --global user.email "mitchross@users.noreply.github.com"
as_hermes git config --global init.defaultBranch main
if [ ! -d "$REPO_DIR/.git" ]; then
  echo "[seed] cloning talos-argocd-proxmox"
  as_hermes git clone --quiet "$REPO_URL" "$REPO_DIR" || echo "[seed] clone failed, continuing"
else
  as_hermes git -C "$REPO_DIR" fetch --quiet --prune origin || echo "[seed] fetch failed, continuing"
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
echo "[seed] done"
