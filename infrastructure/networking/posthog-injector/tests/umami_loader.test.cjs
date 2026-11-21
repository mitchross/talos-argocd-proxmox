// Run with: node --test infrastructure/networking/posthog-injector/tests/umami_loader.test.cjs
// Executes the Umami loader exactly as default.conf would inject it, in a fake browser.
const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const conf = fs.readFileSync(path.join(__dirname, "..", "default.conf"), "utf8");
const snippet = conf.match(/map \$umami_website_id \$umami_snippet \{[^]*?default '(.*?)';\n\}/)[1];
const ID = crypto.randomUUID();
const code = snippet.replace("$umami_website_id", ID).match(/<script>(.*)<\/script>/)[1];

function storage(seed = {}, broken = false) {
  const data = { ...seed };
  const fail = () => { if (broken) throw new Error("SecurityError"); };
  return {
    data,
    get length() { fail(); return Object.keys(data).length; },
    key: i => { fail(); return Object.keys(data)[i] ?? null; },
    getItem: k => { fail(); return k in data ? data[k] : null; },
    setItem: (k, v) => { fail(); data[k] = String(v); },
    removeItem: k => { fail(); delete data[k]; },
  };
}

function run({ seed, broken, search = "", nav = {}, existing = false } = {}) {
  const appended = [];
  const ls = storage(seed, broken);
  const win = {
    navigator: nav,
    get localStorage() { if (broken) throw new Error("SecurityError"); return ls; },
  };
  const document = {
    head: { appendChild: el => appended.push(el) },
    querySelector: () => (existing ? {} : null),
    createElement: () => {
      const attrs = {};
      return { attrs, setAttribute: (k, v) => { attrs[k] = v; } };
    },
  };
  const location = { search, hostname: "deals.vanillax.me", reloaded: 0, reload() { this.reloaded++; } };
  win.window = win;
  vm.runInNewContext(code, { window: win, document, location });
  return { win, ls, appended, location };
}

test("nothing loads without affirmative consent", () => {
  assert.equal(run().appended.length, 0);
});

test("grant loads one tracker with privacy attributes and no recorder", () => {
  const r = run();
  r.win.umamiConsent.grant();
  r.win.umamiConsent.grant();
  assert.equal(r.appended.length, 1);
  const t = r.appended[0];
  assert.equal(t.src, "https://ingest-umami.vanillax.me/script.js");
  assert.deepEqual(t.attrs, {
    "data-website-id": ID,
    "data-do-not-track": "true",
    "data-domains": "deals.vanillax.me",
    "data-before-send": "__umamiBeforeSend",
  });
  assert.equal(r.ls.data["umami.consent"], "granted");
});

test("stored consent loads on the next page", () => {
  assert.equal(run({ seed: { "umami.consent": "granted" } }).appended.length, 1);
});

test("do-not-track and global privacy control deny", () => {
  for (const nav of [{ doNotTrack: "1" }, { doNotTrack: "yes" }, { msDoNotTrack: "1" }, { globalPrivacyControl: true }]) {
    const r = run({ seed: { "umami.consent": "granted" }, nav });
    r.win.umamiConsent.grant();
    assert.equal(r.appended.length, 0, JSON.stringify(nav));
  }
});

test("localStorage failure denies without throwing", () => {
  const r = run({ broken: true });
  r.win.umamiConsent.grant();
  assert.equal(r.appended.length, 0);
  assert.equal(r.win.__umamiBeforeSend("event", { x: 1 }), null);
});

test("?ph_optout=1 denies and persists for both providers", () => {
  const r = run({ seed: { "umami.consent": "granted" }, search: "?ph_optout=1" });
  assert.equal(r.appended.length, 0);
  assert.equal(r.ls.data["umami.disabled"], "1");
  assert.equal(r.ls.data["umami.consent"], "denied");
  const next = run({ seed: r.ls.data });
  next.win.umamiConsent.grant();
  assert.equal(next.appended.length, 0);
});

test("an existing PostHog opt-out denies", () => {
  const r = run({ seed: { "umami.consent": "granted", "__ph_opt_in_out_phc_test": "0" } });
  r.win.umamiConsent.grant();
  assert.equal(r.appended.length, 0);
});

test("a page that already loads Umami gets no second tracker", () => {
  assert.equal(run({ seed: { "umami.consent": "granted" }, existing: true }).appended.length, 0);
});

test("revoke stops sends and reloads", () => {
  const r = run({ seed: { "umami.consent": "granted" } });
  assert.deepEqual(r.win.__umamiBeforeSend("event", { x: 1 }), { x: 1 });
  r.win.umamiConsent.revoke();
  assert.equal(r.win.__umamiBeforeSend("event", { x: 1 }), null);
  assert.equal(r.location.reloaded, 1);
  assert.equal(r.ls.data["umami.disabled"], "1");
});
