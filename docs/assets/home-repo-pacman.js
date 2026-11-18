/* Pac-Man walk for the home-repo page: draws into each .pacman-demo; the static list below it stays for GitHub and reduced motion. */
(function () {
  "use strict";
  var NS = "http://www.w3.org/2000/svg";
  var NODES = [
    { x: 110, y: 270, t: "radar-ng", s: "where you are" },
    { x: 330, y: 80, t: "home", s: "repo-map.md" },
    { x: 580, y: 250, t: "talos", s: "AGENTS.md + CLAUDE.md" },
    { x: 800, y: 90, t: "deploy folder", s: "my-apps/…/radar-ng" },
  ];
  var CAPS = [
    "The agent starts in <b>radar-ng</b>. Its rules say: <b>cross-repo work? Read home first.</b>",
    "It reads the map in <b>home</b>: <b>talos is the cluster; radar-ng deploys from my-apps/personal-projects/radar-ng.</b>",
    "It reads the rules in <b>talos</b>: <b>pull requests only; Argo CD deploys.</b>",
    "It goes straight to <b>the deploy folder</b>. It does not search every repo or ask you.",
    "It bumps the image and opens a pull request. <b>Done.</b> The map cost about 40 lines of reading.",
  ];
  var W = 150, H = 64;

  function el(tag, attrs) {
    var e = document.createElementNS(NS, tag);
    for (var k in attrs) e.setAttribute(k, attrs[k]);
    return e;
  }

  function build(root) {
    if (root.dataset.ready) return;
    root.dataset.ready = "1";
    var step = document.createElement("div"); step.className = "pm-step";
    var cap = document.createElement("div"); cap.className = "pm-cap";
    var svg = el("svg", { viewBox: "0 0 900 360", role: "img", "aria-label": "An agent moves from radar-ng to home, then talos, then the deploy folder" });
    var pg = el("g", {}), ng = el("g", {}), pac = el("path", { class: "pm-pac" });
    svg.appendChild(pg); svg.appendChild(ng); svg.appendChild(pac);
    var btn = document.createElement("button"); btn.type = "button"; btn.className = "md-button pm-btn"; btn.textContent = "▶ Replay";
    root.appendChild(step); root.appendChild(cap); root.appendChild(svg); root.appendChild(btn);

    NODES.forEach(function (n) {
      n.r = el("rect", { class: "pm-box", x: n.x - W / 2, y: n.y - H / 2, width: W, height: H, rx: 12 });
      var l = el("text", { class: "pm-lbl", x: n.x, y: n.y - 3 }); l.textContent = n.t;
      var s = el("text", { class: "pm-sub", x: n.x, y: n.y + 17 }); s.textContent = n.s;
      ng.appendChild(n.r); ng.appendChild(l); ng.appendChild(s);
    });
    var legs = [], pels = [];
    for (var i = 0; i < 3; i++) {
      var a = NODES[i], b = NODES[i + 1];
      legs.push([[a.x + W / 2, a.y], [b.x, a.y], [b.x, b.y + (b.y < a.y ? H / 2 : -H / 2)]]);
    }
    legs.forEach(function (pts) {
      for (var k = 0; k < pts.length - 1; k++) {
        var p = pts[k], q = pts[k + 1], d = Math.hypot(q[0] - p[0], q[1] - p[1]);
        for (var s = 12; s < d - 6; s += 24) {
          var c = el("circle", { class: "pm-pel", cx: p[0] + (q[0] - p[0]) * s / d, cy: p[1] + (q[1] - p[1]) * s / d, r: 4 });
          pg.appendChild(c); pels.push(c);
        }
      }
    });

    function pacAt(x, y, ang, m) {
      var r = 20, o = m * 0.7;
      pac.setAttribute("d", "M" + x + "," + y + " L" + (x + r * Math.cos(ang + o)) + "," + (y + r * Math.sin(ang + o)) +
        " A" + r + "," + r + " 0 1 1 " + (x + r * Math.cos(ang - o)) + "," + (y + r * Math.sin(ang - o)) + " Z");
    }
    function show(i) {
      step.textContent = i < 0 ? "Step 0 of 5" : "Step " + (i + 1) + " of 5";
      cap.innerHTML = i < 0 ? "You ask: <b>deploy my radar-ng change.</b>" : CAPS[i];
      NODES.forEach(function (n, j) { n.r.classList.toggle("pm-on", i >= 0 && j === Math.min(i, 3)); });
    }
    var run = 0;
    function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }
    function walk(pts, id) {
      var chain = Promise.resolve();
      for (var k = 0; k < pts.length - 1; k++) (function (p, q) {
        chain = chain.then(function () {
          return new Promise(function (res) {
            var d = Math.hypot(q[0] - p[0], q[1] - p[1]), ang = Math.atan2(q[1] - p[1], q[0] - p[0]), t0 = performance.now();
            function f(t) {
              if (id !== run || !root.isConnected) return res();
              var u = Math.min(1, (t - t0) / (d * 6)), x = p[0] + (q[0] - p[0]) * u, y = p[1] + (q[1] - p[1]) * u;
              pacAt(x, y, ang, Math.abs(Math.sin(t / 70)));
              pels.forEach(function (c) { if (Math.hypot(c.cx.baseVal.value - x, c.cy.baseVal.value - y) < 14) c.style.opacity = "0"; });
              u < 1 ? requestAnimationFrame(f) : res();
            }
            requestAnimationFrame(f);
          });
        });
      })(pts[k], pts[k + 1]);
      return chain;
    }
    async function play() {
      var id = ++run;
      pels.forEach(function (c) { c.style.opacity = "1"; });
      pacAt(NODES[0].x + W / 2, NODES[0].y, 0, 0.5); show(-1);
      await sleep(1500);
      for (var i = 0; i < 3; i++) {
        if (id !== run) return; show(i); await sleep(2600);
        if (id !== run) return; await walk(legs[i], id);
      }
      if (id !== run) return; show(3); await sleep(2600);
      if (id !== run) return; show(4);
    }
    btn.addEventListener("click", play);
    play();
  }

  function init() {
    if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    document.querySelectorAll(".pacman-demo").forEach(build);
  }
  if (window.document$ && window.document$.subscribe) window.document$.subscribe(init);
  else if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
