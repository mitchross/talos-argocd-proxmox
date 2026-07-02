/* kopiur playground — a dependency-free simulation of the kopiur/volume-populator
 * state machine (backup, restore-before-bind, backend-down hold, DR gap, nuke).
 * Mounts into #kopiur-playground; safe under Material instant navigation. */
(function () {
  "use strict";

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  function mount(root) {
    root.innerHTML = `
      <div class="kp">
        <div class="kp-cols">
          <div class="kp-panel" data-panel="git">
            <h4>📂 Git (survives everything)</h4>
            <div class="kp-row"><label><input type="checkbox" id="kp-dsr" checked>
              PVC has <code>dataSourceRef → Restore</code></label></div>
            <div class="kp-row kp-dim">namespace label · stub (SnapshotPolicy /
              Schedule / Restore) · <code>components: [kopiur-backup]</code></div>
          </div>
          <div class="kp-panel" data-panel="cluster">
            <h4>☸️ Cluster (cattle)</h4>
            <div class="kp-row">pod/open-webui <span class="kp-chip" id="kp-pod">absent</span></div>
            <div class="kp-row">pvc/storage <span class="kp-chip" id="kp-pvc">absent</span></div>
            <div class="kp-row">volume contents <span class="kp-chip" id="kp-vol">—</span></div>
            <div class="kp-row">mover job <span class="kp-chip" id="kp-mover">idle</span></div>
          </div>
          <div class="kp-panel" data-panel="s3">
            <h4>💾 RustFS S3 <code>s3://kopiur</code> <span class="kp-chip" id="kp-s3">online</span></h4>
            <div id="kp-snaps" class="kp-snaps kp-dim">(no snapshots yet)</div>
          </div>
        </div>
        <div class="kp-actions">
          <button id="kp-deploy">Sync app from Git</button>
          <button id="kp-backup">Run backup now</button>
          <button id="kp-delpvc">Delete the PVC 😱</button>
          <button id="kp-nuke">Nuke the cluster ☠️</button>
          <button id="kp-s3toggle">Take S3 offline</button>
          <button id="kp-reset" class="kp-secondary">Reset</button>
        </div>
        <pre class="kp-log" id="kp-log" aria-live="polite"></pre>
      </div>`;

    const $ = (id) => root.querySelector("#" + id);
    const chips = { pod: $("kp-pod"), pvc: $("kp-pvc"), vol: $("kp-vol"), mover: $("kp-mover"), s3: $("kp-s3") };
    const logEl = $("kp-log");

    const st = { s3Up: true, snaps: [], pvc: "absent", pod: "absent", vol: "none", mover: "idle", busy: false, epoch: 0 };

    const CHIP_STYLE = {
      absent: "off", pending: "warn", "bound (empty)": "ok", "bound + DATA": "good",
      running: "good", waiting: "warn", terminating: "warn", idle: "off",
      "backing up": "warn", restoring: "warn", "retrying…": "err",
      online: "good", OFFLINE: "err", "—": "off", empty: "off",
      "chat-history ✓": "good", "chat-history (NOT backed up yet)": "warn",
      "EMPTY (DR GAP!)": "err",
    };
    function chip(el, text) { el.textContent = text; el.dataset.kind = CHIP_STYLE[text] || "off"; }
    function render() {
      chip(chips.pod, st.pod);
      chip(chips.pvc, st.pvc);
      chip(chips.vol, st.vol);
      chip(chips.mover, st.mover);
      chip(chips.s3, st.s3Up ? "online" : "OFFLINE");
      $("kp-s3toggle").textContent = st.s3Up ? "Take S3 offline" : "Bring S3 back online";
      const snapsEl = $("kp-snaps");
      snapsEl.className = "kp-snaps" + (st.snaps.length ? "" : " kp-dim");
      snapsEl.innerHTML = st.snaps.length
        ? st.snaps.slice().reverse().map((s) =>
            `<div>📦 snap #${s.n} · ${s.files} files${s.files < 5 ? " ⚠️ (empty-ish!)" : ""}</div>`).join("")
        : "(no snapshots yet)";
    }
    function log(msg, kind) {
      const line = document.createElement("span");
      line.className = "kp-l-" + (kind || "info");
      line.textContent = msg + "\n";
      logEl.appendChild(line);
      logEl.scrollTop = logEl.scrollHeight;
    }

    // Wait until S3 is up — this IS the "hold Pending, never bind empty" behavior.
    async function waitForS3(what, epoch) {
      let n = 0;
      while (!st.s3Up) {
        if (st.epoch !== epoch) return false;
        if (n++ % 3 === 0) log(`   ${what}: backend unreachable — error + retry (attempt ${n})`, "err");
        await sleep(700);
      }
      return st.epoch === epoch;
    }

    async function populate(epoch) {
      // The kubernetes volume-populator handshake, simulated faithfully.
      st.pvc = "pending"; render();
      log("→ PVC created with dataSourceRef → Restore/storage-restore");
      log("→ Kubernetes withholds binding: PVC = Pending ⏳");
      await sleep(600);
      if (!st.s3Up) {
        log("→ kopiur populator contacts the repo…");
        if (!(await waitForS3("Restore populator", epoch))) return;
        log("→ S3 is back — populator resumes (the PVC never bound empty ✅)", "good");
      }
      if (st.epoch !== epoch) return;
      const latest = st.snaps[st.snaps.length - 1];
      if (latest) {
        st.mover = "restoring"; render();
        log(`→ snapshot exists: restoring snap #${latest.n} (${latest.files} files, mover runs as uid 568)…`);
        await sleep(1400);
        if (st.epoch !== epoch) return;
        st.mover = "idle";
        st.pvc = "bound + DATA";
        st.vol = latest.files < 5 ? "empty" : "chat-history ✓";
        render();
        log(`→ PVC Bound WITH data from snap #${latest.n} ✅`, "good");
        if (latest.files < 5) log("   …but the latest snapshot was of an EMPTY volume. Restores give you back exactly what you last backed up.", "warn");
      } else {
        log("→ repo reachable but NO snapshot for this identity");
        log("→ onMissingSnapshot: Continue → bind EMPTY, back up forward (deploy-or-restore) ⚪", "warn");
        await sleep(500);
        if (st.epoch !== epoch) return;
        st.pvc = "bound (empty)"; st.vol = "empty"; render();
      }
      await startPod(epoch);
    }

    async function startPod(epoch) {
      st.pod = "waiting"; render();
      await sleep(500);
      if (st.epoch !== epoch) return;
      st.pod = "running"; render();
      log("→ pod starts. ArgoCD: app Progressing → Healthy (this is what gates the sync wave)", "good");
      if (st.vol === "empty") {
        await sleep(900);
        if (st.epoch !== epoch || st.pod !== "running") return;
        st.vol = "chat-history (NOT backed up yet)"; render();
        log("→ the app writes real data… which no snapshot protects yet. Run a backup!", "warn");
      }
    }

    async function act(fn) {
      if (st.busy) return;
      st.busy = true;
      const epoch = st.epoch;
      try { await fn(epoch); } finally { if (st.epoch === epoch) st.busy = false; render(); }
    }

    $("kp-deploy").addEventListener("click", () => act(async (epoch) => {
      if (st.pvc !== "absent") { log("app already synced — delete the PVC or nuke the cluster to re-run the flow", "warn"); return; }
      log("── ArgoCD sync: rendering kustomization (stub + component → full CRs) ──");
      await sleep(500);
      if ($("kp-dsr").checked) { await populate(epoch); }
      else {
        st.pvc = "bound (empty)"; st.vol = "EMPTY (DR GAP!)"; render();
        log("→ PVC has NO dataSourceRef → Longhorn provisions it EMPTY, instantly", "err");
        log("   The backup may exist in the repo — nothing tells Kubernetes to use it. This is the #1 rule.", "err");
        await startPod(epoch);
      }
    }));

    $("kp-backup").addEventListener("click", () => act(async (epoch) => {
      if (!st.pvc.startsWith("bound")) { log("no bound PVC to back up — sync the app first", "warn"); return; }
      log("── SnapshotSchedule fires → Snapshot CR created ──");
      st.mover = "backing up"; render();
      log("→ 1. CSI VolumeSnapshot (longhorn-snapclass): point-in-time copy frozen");
      await sleep(600);
      if (!st.s3Up) {
        st.mover = "retrying…"; render();
        log("→ 2. mover starts… repo unreachable. Snapshot Job FAILS and retries — nothing garbage is written.", "err");
        if (!(await waitForS3("Snapshot job", epoch))) return;
        log("→ S3 is back — mover retry succeeds:", "good");
      }
      if (st.epoch !== epoch) return;
      await sleep(900);
      if (st.epoch !== epoch) return;
      const files = st.vol.startsWith("chat-history") ? 128 : 3;
      const n = (st.snaps[st.snaps.length - 1]?.n || 0) + 1;
      st.snaps.push({ n, files });
      st.mover = "idle";
      if (st.vol === "chat-history (NOT backed up yet)") st.vol = "chat-history ✓";
      render();
      log(`→ 2. mover (uid 568) read the snapshot → kopia: encrypt + dedup → snap #${n} Completed (${files} files) ✅`, "good");
      if (files < 5) log("   you just backed up an (almost) empty volume — snap #" + n + " is now 'latest'. Careful what you restore.", "warn");
    }));

    $("kp-delpvc").addEventListener("click", () => act(async (epoch) => {
      if (st.pvc === "absent") { log("no PVC to delete — sync the app first", "warn"); return; }
      log("── kubectl delete pvc storage ── (the scary part)");
      st.pod = "terminating"; render();
      await sleep(500);
      st.pod = "absent"; st.pvc = "absent"; st.vol = "—"; render();
      log("→ PVC and its data are GONE from the cluster");
      await sleep(700);
      if (st.epoch !== epoch) return;
      log("→ ArgoCD notices drift vs Git → recreates the PVC…");
      if ($("kp-dsr").checked) { await populate(epoch); }
      else {
        st.pvc = "bound (empty)"; st.vol = "EMPTY (DR GAP!)"; render();
        log("→ no dataSourceRef in Git → recreated EMPTY. Your data is still in the repo; nothing restored it.", "err");
        await startPod(epoch);
      }
    }));

    $("kp-nuke").addEventListener("click", () => act(async (epoch) => {
      log("── omnictl cluster delete … ── ☠️");
      st.pod = "absent"; st.pvc = "absent"; st.vol = "—"; st.mover = "idle"; render();
      log("→ every Kubernetes object destroyed. Git ✅ and the Kopia repo ✅ survive (the pets).");
      await sleep(900);
      if (st.epoch !== epoch) return;
      log("── bootstrap-argocd.sh → sync waves walk ──");
      log("   wave 0-1: CNI, secrets, Longhorn · wave 2: kopiur operator · wave 3: repo + creds");
      await sleep(1100);
      if (st.epoch !== epoch) return;
      log("── wave 6: my-apps AppSet re-renders the app from Git ──");
      if ($("kp-dsr").checked) { await populate(epoch); }
      else {
        st.pvc = "bound (empty)"; st.vol = "EMPTY (DR GAP!)"; render();
        log("→ rebuilt EMPTY — this is what an unprotected PVC looks like after DR", "err");
        await startPod(epoch);
      }
    }));

    $("kp-s3toggle").addEventListener("click", () => {
      st.s3Up = !st.s3Up;
      log(st.s3Up ? "💾 RustFS back ONLINE" : "💾 RustFS OFFLINE — watch what refuses to go wrong", st.s3Up ? "good" : "err");
      render();
    });

    $("kp-reset").addEventListener("click", () => {
      st.epoch++; st.busy = false;
      st.s3Up = true; st.snaps = []; st.pvc = "absent"; st.pod = "absent"; st.vol = "—"; st.mover = "idle";
      logEl.textContent = "";
      log("reset. Suggested tour: Sync → Backup → Delete PVC → (S3 offline + Delete PVC) → Nuke.");
      render();
    });

    log("👋 This is the exact state machine your PVCs live in. Start with “Sync app from Git”.");
    render();
  }

  function boot() {
    const root = document.getElementById("kopiur-playground");
    if (root && !root.dataset.kpMounted) { root.dataset.kpMounted = "1"; mount(root); }
  }
  // document$ fires on every page load under Material's instant navigation.
  if (window.document$ && window.document$.subscribe) window.document$.subscribe(boot);
  else if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
