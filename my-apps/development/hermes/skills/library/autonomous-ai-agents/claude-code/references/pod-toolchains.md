# Pinned toolchains in the Hermes pod (no root)

The pod's system dirs (`/opt/rust/rustup`, `/opt/rust/cargo`) are root-owned. Put toolchains under `/opt/data/tools/` (the PVC), so they survive restarts, and source one env file before any build.

## Rust: match `rust-toolchain.toml`

```bash
export RUSTUP_HOME=/opt/data/tools/rustup CARGO_HOME=/opt/data/tools/cargo
mkdir -p $CARGO_HOME
rustup toolchain install <channel> --profile minimal -c clippy,rustfmt   # proxies in /opt/rust/cargo/bin still work
```

When the prompt tells the child to *create* a `rust-toolchain.toml`, pick the channel and pre-install it first, because rustup otherwise downloads mid-run. Check `rustup toolchain list` first: a channel may already be on the PVC.

Run clippy with the pinned channel, not the image default. A newer clippy adds lints that fail `-D warnings` in crates you didn't touch.

## protoc with the well-known types

The Temporal SDK and other prost/tonic builds need `google/protobuf/*.proto`. A bare `/usr/bin/protoc` without `libprotobuf-dev` fails on `field_mask.proto`. Use the release zip instead, because it ships `include/`:

```bash
V=$(curl -fsSL https://api.github.com/repos/protocolbuffers/protobuf/releases/latest | python3 -c 'import json,sys;print(json.load(sys.stdin)["tag_name"])')
curl -fsSLo protoc.zip https://github.com/protocolbuffers/protobuf/releases/download/$V/protoc-${V#v}-linux-x86_64.zip
# unzip into /opt/data/tools/protoc (python zipfile works if unzip is absent); chmod +x bin/protoc
export PROTOC=/opt/data/tools/protoc/bin/protoc PROTOC_INCLUDE=/opt/data/tools/protoc/include
```

## Bun: match `packageManager` / the CI `bun-version`

The `bun.sh/install` script installs the latest version, even when you pass a version argument. To pin, download the release zip and copy the binary in:

```bash
curl -fsSLo bun.zip https://github.com/oven-sh/bun/releases/download/bun-v<ver>/bun-linux-x64.zip
# extract; install -m755 bun-linux-x64/bun /opt/data/tools/bun/bin/bun; bun --version
```

## Env file

Keep one file per stack (for example `/opt/data/tools/<repo>-env.sh`) that exports `RUSTUP_HOME`, `CARGO_HOME`, `PROTOC`, `PROTOC_INCLUDE`, and a `PATH` with `/opt/rust/cargo/bin`, the bun and protoc bins. For a port, also put the old language's test venv (`/opt/data/tools/venvs/<repo>-*/bin`) on PATH, so the child can run the old suite and the golden generator. Run the old suite once yourself before the hand-off, to record the baseline count for the prompt. Tell the coding child to `source` it, and source it in your own gate runner too.

## Gate runner

Run the frontend and Rust gates as two parallel subshells in one background script. Write one log per gate plus `summary.txt` lines (`== name: cmd` / `exit=N`). Print the toolchain versions at the top, so the PR evidence shows which versions ran. Run `bun install --frozen-lockfile` first, and check `git status -s` at the end to prove no lockfile drift.
