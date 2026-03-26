import { useState } from "react";

const sections = [
  {
    id: "intro",
    title: "The Big Picture",
    icon: "🌍",
    color: "#FF6B35",
    bg: "#1a1a2e",
    content: (
      <>
        <p style={{ fontSize: 20, lineHeight: 1.8, color: "#e0e0e0" }}>
          Imagine you're living in a house between a furnace and an open window.
          The furnace is the <strong style={{ color: "#FFD700" }}>Sun</strong>.
          The open window is <strong style={{ color: "#87CEEB" }}>deep space</strong>.
          Everything you do — cooking, building, computing — produces heat.
          That heat has to leave through the window.
        </p>
        <p style={{ fontSize: 20, lineHeight: 1.8, color: "#e0e0e0" }}>
          <strong style={{ color: "#FF6B35" }}>The window is only so big.</strong>
        </p>
        <p style={{ fontSize: 18, lineHeight: 1.8, color: "#b0b0b0" }}>
          This series by Object Zero (@Object_Zero_) builds a complete framework
          showing that civilisation exists inside a thermodynamic corridor — a finite
          space between a floor (the minimum energy to keep everything from falling apart)
          and a ceiling (the maximum heat our planet can radiate away). The default path
          leads us into the ceiling. But the corridor is wide, and we've barely entered it.
        </p>
      </>
    ),
  },
  {
    id: "arena",
    title: "Part 1: The Arena",
    subtitle: "Where we actually live",
    icon: "☀️",
    color: "#FFD700",
    bg: "#1a1a2e",
    content: (
      <>
        <div style={{ display: "flex", gap: 24, flexWrap: "wrap", marginBottom: 24 }}>
          <div style={{ flex: 1, minWidth: 280, background: "#16213e", borderRadius: 16, padding: 24, border: "1px solid #FFD700" }}>
            <div style={{ fontSize: 48, marginBottom: 8 }}>☀️</div>
            <h4 style={{ color: "#FFD700", margin: "0 0 8px" }}>The Hot Source</h4>
            <p style={{ color: "#ccc", margin: 0, fontSize: 16 }}>Sun at 5,800°K sends us high-quality energy as visible light photons — few in number, each packed with energy.</p>
          </div>
          <div style={{ flex: 1, minWidth: 280, background: "#16213e", borderRadius: 16, padding: 24, border: "1px solid #87CEEB" }}>
            <div style={{ fontSize: 48, marginBottom: 8 }}>🌌</div>
            <h4 style={{ color: "#87CEEB", margin: "0 0 8px" }}>The Cold Sink</h4>
            <p style={{ color: "#ccc", margin: 0, fontSize: 16 }}>Deep space at 2.7°K. Earth re-radiates the same energy as infrared — way more photons, each carrying way less energy. The entropy difference is our "operating budget."</p>
          </div>
        </div>
        <div style={{ background: "#0f3460", borderRadius: 16, padding: 24, textAlign: "center" }}>
          <p style={{ color: "#FFD700", fontSize: 18, margin: "0 0 12px", fontWeight: 600 }}>The Key Insight</p>
          <p style={{ color: "#e0e0e0", fontSize: 17, margin: 0, maxWidth: 600, marginLeft: "auto", marginRight: "auto" }}>
            Earth doesn't create order. It borrows order from the Sun and pays for it by exporting disorder into space.
            Everything — weather, life, cities, AI — runs on this gradient. Cut the gradient, everything stops.
          </p>
        </div>
      </>
    ),
  },
  {
    id: "machine",
    title: "Part 2: The Machine",
    subtitle: "What civilisation actually is",
    icon: "⚙️",
    color: "#E94560",
    bg: "#1a1a2e",
    content: (
      <>
        <p style={{ fontSize: 18, color: "#e0e0e0", lineHeight: 1.8 }}>
          Civilisation isn't an idea or a culture. Physically, it's a giant pile of
          <strong style={{ color: "#E94560" }}> assembled stuff</strong> — roads, chips, buildings, cables —
          all fighting the universe's natural tendency to fall apart.
        </p>

        <div style={{ display: "flex", gap: 16, flexWrap: "wrap", margin: "24px 0" }}>
          {[
            { label: "The Stock (Σ)", desc: "Total accumulated ordered structure", icon: "🏗️", col: "#E94560" },
            { label: "The Decay (δ)", desc: "Everything rots at ~2-4% per year", icon: "🔧", col: "#FF9A3C" },
            { label: "The Cost (Γ)", desc: "Power needed per unit of stuff", icon: "⚡", col: "#FFD700" },
            { label: "The Ceiling", desc: "Max stuff the planet can support", icon: "🌡️", col: "#87CEEB" },
          ].map((item) => (
            <div key={item.label} style={{ flex: 1, minWidth: 200, background: "#16213e", borderRadius: 12, padding: 20, borderTop: `3px solid ${item.col}` }}>
              <div style={{ fontSize: 32 }}>{item.icon}</div>
              <h4 style={{ color: item.col, margin: "8px 0 4px", fontSize: 15 }}>{item.label}</h4>
              <p style={{ color: "#b0b0b0", margin: 0, fontSize: 14 }}>{item.desc}</p>
            </div>
          ))}
        </div>

        <div style={{ background: "linear-gradient(135deg, #1a1a3e, #0f3460)", borderRadius: 16, padding: 24, margin: "16px 0" }}>
          <p style={{ color: "#E94560", fontWeight: 700, fontSize: 16, margin: "0 0 8px" }}>The Formula That Defines Our Limits</p>
          <div style={{ fontFamily: "monospace", fontSize: 20, color: "#FFD700", textAlign: "center", padding: 16 }}>
            Σ_max = (εσAT⁴ − P_sun) / Γ
          </div>
          <p style={{ color: "#b0b0b0", margin: "8px 0 0", fontSize: 15, textAlign: "center" }}>
            Max civilisation = (planet's radiative headroom) ÷ (power cost per unit of stuff)
          </p>
        </div>

        <div style={{ background: "#16213e", borderRadius: 12, padding: 20, borderLeft: "4px solid #E94560" }}>
          <p style={{ color: "#e0e0e0", margin: 0, fontSize: 16, lineHeight: 1.7 }}>
            <strong style={{ color: "#E94560" }}>The maintenance tax is real.</strong> US infrastructure alone costs $355 billion/year just to maintain.
            For every $1 spent building new things, $1.31 goes to keeping old things from falling apart.
            This isn't a policy failure — it's the Second Law of Thermodynamics collecting its rent.
          </p>
        </div>
      </>
    ),
  },
  {
    id: "info",
    title: "The AI & Information Trap",
    subtitle: "Why 'going digital' doesn't save us",
    icon: "🤖",
    color: "#7B68EE",
    bg: "#1a1a2e",
    content: (
      <>
        <p style={{ fontSize: 18, color: "#e0e0e0", lineHeight: 1.8 }}>
          "We'll shift to an information economy and decouple from energy!" Nope.
          Information is physical. Every bit stored needs atoms. Every bit erased produces heat.
          Landauer proved this in 1961. Labs confirmed it in 2012.
        </p>

        <div style={{ background: "#16213e", borderRadius: 16, padding: 24, margin: "20px 0" }}>
          <h4 style={{ color: "#7B68EE", margin: "0 0 16px" }}>The Computation Paradox</h4>
          <div style={{ display: "flex", gap: 20, flexWrap: "wrap" }}>
            <div style={{ flex: 1, minWidth: 220, textAlign: "center" }}>
              <div style={{ fontSize: 36, color: "#50C878" }}>10,000,000,000×</div>
              <p style={{ color: "#b0b0b0", fontSize: 14, margin: "8px 0 0" }}>improvement in energy per computation since 1971</p>
            </div>
            <div style={{ flex: 1, minWidth: 220, textAlign: "center" }}>
              <div style={{ fontSize: 36, color: "#E94560" }}>100×</div>
              <p style={{ color: "#b0b0b0", fontSize: 14, margin: "8px 0 0" }}>increase in total computational energy use</p>
            </div>
            <div style={{ flex: 1, minWidth: 220, textAlign: "center" }}>
              <div style={{ fontSize: 36, color: "#FFD700" }}>130%</div>
              <p style={{ color: "#b0b0b0", fontSize: 14, margin: "8px 0 0" }}>rebound — super-Jevons backfire</p>
            </div>
          </div>
        </div>

        <p style={{ fontSize: 16, color: "#b0b0b0", lineHeight: 1.7 }}>
          We made computers a billion times more efficient. Did we use less energy? No — we computed
          a trillion times more. Each efficiency gain was immediately eaten by demand.
          AI training now consumes ~50 GWh per frontier model. Data centers may hit 1,000 TWh/year by 2030.
          The sector that was supposed to dematerialize the economy is the fastest-growing energy consumer on Earth.
        </p>
      </>
    ),
  },
  {
    id: "trajectory",
    title: "Part 3: The Trajectory",
    subtitle: "Why we keep accelerating toward the wall",
    icon: "📈",
    color: "#50C878",
    bg: "#1a1a2e",
    content: (
      <>
        <h4 style={{ color: "#50C878", margin: "0 0 16px" }}>Three Locks on the Accelerator</h4>

        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {[
            {
              num: "1",
              title: "The Evolutionary Ratchet (Tier 2 — very hard to change)",
              desc: "Competition between any energy-using systems — organisms, companies, nations — favors those that capture energy fastest, not most efficiently. This has been true since the first bacteria. The Jevons Paradox is its symptom: when we made light bulbs 3,000× more efficient over 300 years, total light consumption went up 40,000×. The world always spends ~0.72% of GDP on lighting.",
              col: "#E94560",
            },
            {
              num: "2",
              title: "The Integral Inertia (Tier 1 — physics)",
              desc: "Civilisation's energy demand isn't set by today's decisions — it's set by the accumulated weight of ALL past decisions. Time constant: 50-100 years. Even a 50% GDP crash sustained for a decade would only reduce energy demand by ~17%. You can't quickly steer a supertanker.",
              col: "#FFD700",
            },
            {
              num: "3",
              title: "The Financial Amplifiers (Tier 3 — reformable!)",
              desc: "Compound interest forces the economy to grow or collapse. Banks create money by lending, pulling future energy into the present. Political cycles (2-5 years) are way too fast to steer a system with 50-100 year time constants. The good news: these are human inventions. They've been changed before.",
              col: "#50C878",
            },
          ].map((item) => (
            <div key={item.num} style={{ background: "#16213e", borderRadius: 12, padding: 20, borderLeft: `4px solid ${item.col}`, display: "flex", gap: 16, alignItems: "flex-start" }}>
              <div style={{ background: item.col, color: "#000", borderRadius: "50%", width: 36, height: 36, display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 700, fontSize: 18, flexShrink: 0 }}>{item.num}</div>
              <div>
                <h4 style={{ color: item.col, margin: "0 0 6px", fontSize: 15 }}>{item.title}</h4>
                <p style={{ color: "#b0b0b0", margin: 0, fontSize: 14, lineHeight: 1.6 }}>{item.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </>
    ),
  },
  {
    id: "viability",
    title: "Part 4: The Viability Problem",
    subtitle: "The walls are closing in — but slowly",
    icon: "🎯",
    color: "#FF9A3C",
    bg: "#1a1a2e",
    content: (
      <>
        <p style={{ fontSize: 18, color: "#e0e0e0", lineHeight: 1.8 }}>
          Using formal viability theory (math for "can we stay alive?"), the essay maps out the
          <strong style={{ color: "#FF9A3C" }}> viability kernel</strong> — the set of states from which
          at least one path avoids all constraints forever.
        </p>

        <div style={{ background: "#16213e", borderRadius: 16, padding: 24, margin: "20px 0" }}>
          <h4 style={{ color: "#FF9A3C", margin: "0 0 16px" }}>Nested Constraints (ordered by urgency)</h4>
          {[
            { label: "Greenhouse", time: "Decades", desc: "CO₂ warming — reduces emissivity, lowers the ceiling", col: "#E94560", width: "100%" },
            { label: "Financial", time: "Decades—Century", desc: "Debt structure forces growth or triggers collapse", col: "#FFD700", width: "80%" },
            { label: "Evolutionary Ratchet", time: "Continuous", desc: "Competition drives max energy capture", col: "#FF9A3C", width: "60%" },
            { label: "Waste Heat Ceiling", time: "~300 years", desc: "Stefan-Boltzmann limit — the hard wall", col: "#87CEEB", width: "40%" },
          ].map((c) => (
            <div key={c.label} style={{ marginBottom: 12, display: "flex", alignItems: "center", gap: 12 }}>
              <div style={{ width: c.width, background: `linear-gradient(90deg, ${c.col}44, ${c.col}11)`, borderRadius: 8, padding: "10px 16px", borderLeft: `3px solid ${c.col}`, transition: "all 0.3s" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ color: c.col, fontWeight: 600, fontSize: 14 }}>{c.label}</span>
                  <span style={{ color: "#888", fontSize: 12 }}>{c.time}</span>
                </div>
                <p style={{ color: "#999", margin: "4px 0 0", fontSize: 12 }}>{c.desc}</p>
              </div>
            </div>
          ))}
          <p style={{ color: "#b0b0b0", fontSize: 14, margin: "12px 0 0", fontStyle: "italic" }}>
            Each unaddressed constraint tightens the ones below it. Failure cascades downward.
          </p>
        </div>

        <div style={{ background: "#0f3460", borderRadius: 12, padding: 20 }}>
          <p style={{ color: "#FF9A3C", fontWeight: 600, margin: "0 0 8px", fontSize: 15 }}>
            The competitive viability result (the math behind why this is so hard):
          </p>
          <p style={{ color: "#ccc", margin: 0, fontSize: 15, lineHeight: 1.7 }}>
            N agents competing for shares of a finite energy gradient will generically saturate that gradient.
            Unused capacity is unstable — any agent that grabs it expands its survival odds and shrinks everyone else's.
            This is a Nash equilibrium. You can't opt out unilaterally. You need everyone to agree, simultaneously, to leave energy on the table.
          </p>
        </div>
      </>
    ),
  },
  {
    id: "implications",
    title: "Part 5: The Implications",
    subtitle: "It's not hopeless — it's a navigation problem",
    icon: "🚀",
    color: "#87CEEB",
    bg: "#1a1a2e",
    content: (
      <>
        <div style={{ background: "#16213e", borderRadius: 16, padding: 24, marginBottom: 20 }}>
          <h4 style={{ color: "#87CEEB", margin: "0 0 12px" }}>Fermi's Paradox, Explained</h4>
          <p style={{ color: "#ccc", margin: 0, fontSize: 16, lineHeight: 1.7 }}>
            The galaxy is silent not because survival is impossible, but because the viable strategy space is small
            and most civilisations never develop the analytical tools to see the walls before hitting them.
            A civilisation that briefly brightens in infrared and then goes silent is indistinguishable from one
            that expanded without restraint. The "strategy of ignorance" is probably the most common outcome galaxy-wide.
          </p>
        </div>

        <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginBottom: 20 }}>
          <div style={{ flex: 1, minWidth: 280, background: "#0f3460", borderRadius: 16, padding: 24, border: "1px solid #50C878" }}>
            <h4 style={{ color: "#50C878", margin: "0 0 8px" }}>What Works</h4>
            <p style={{ color: "#ccc", margin: 0, fontSize: 15, lineHeight: 1.6 }}>
              Reduce Γ (the power-per-stuff coupling): build durable, maintain efficiently,
              lower overhead. Reform financial architecture. Extend governance timescales.
              Expand radiating area (space infrastructure, long-term). All require civilisation-scale coordination.
            </p>
          </div>
          <div style={{ flex: 1, minWidth: 280, background: "#0f3460", borderRadius: 16, padding: 24, border: "1px solid #E94560" }}>
            <h4 style={{ color: "#E94560", margin: "0 0 8px" }}>What Doesn't</h4>
            <p style={{ color: "#ccc", margin: 0, fontSize: 15, lineHeight: 1.6 }}>
              Efficiency alone (gets eaten by Jevons). Switching to clean energy alone (solves carbon, not waste heat).
              Hoping the information economy dematerializes (it's the fastest-growing energy consumer).
              Ignoring the problem (the default — and it's lethal).
            </p>
          </div>
        </div>

        <div style={{ background: "linear-gradient(135deg, #1a1a3e, #0a2a4e)", borderRadius: 16, padding: 28, border: "1px solid #87CEEB", textAlign: "center" }}>
          <div style={{ fontSize: 48, marginBottom: 12 }}>💡</div>
          <h3 style={{ color: "#87CEEB", margin: "0 0 12px" }}>The Punchline</h3>
          <p style={{ color: "#e0e0e0", fontSize: 18, lineHeight: 1.8, maxWidth: 640, margin: "0 auto" }}>
            We currently use <strong style={{ color: "#FFD700" }}>less than 1%</strong> of the thermodynamic corridor
            that physics permits on this planet. More than <strong style={{ color: "#50C878" }}>99%</strong> of the
            civilisation Earth can sustain lies in the future. The batteries are loaded. The instruments now exist
            to see the walls. The corridor is open. The goal isn't "less" — it's <strong style={{ color: "#87CEEB" }}>"more, durably."</strong>
          </p>
        </div>
      </>
    ),
  },
  {
    id: "tiers",
    title: "The Three-Tier Framework",
    subtitle: "The essay's key innovation",
    icon: "🔑",
    color: "#DA70D6",
    bg: "#1a1a2e",
    content: (
      <>
        <p style={{ fontSize: 17, color: "#e0e0e0", lineHeight: 1.7, marginBottom: 20 }}>
          The most powerful idea in the series: not everything is equally hard to change.
          The ceiling is physics. The timeline to the ceiling is partly convention.
          Knowing the difference is everything.
        </p>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {[
            {
              tier: "Tier 1 — Physics",
              tag: "IMMUTABLE",
              tagCol: "#E94560",
              items: "Second Law, Stefan-Boltzmann, stuff decays (δ>0), maintenance costs energy (ξ>0), no perfect efficiency (η<1)",
              verdict: "Can't change. Don't try. Respect it.",
              bg: "#2d1a1a",
              border: "#E94560",
            },
            {
              tier: "Tier 2 — Evolution",
              tag: "VERY STIFF",
              tagCol: "#FFD700",
              items: "Maximum power principle, Jevons recycling, competitive gradient saturation",
              verdict: "Requires coordinated multi-agent departure. No precedent, but physics doesn't forbid it.",
              bg: "#2d2a1a",
              border: "#FFD700",
            },
            {
              tier: "Tier 3 — Convention",
              tag: "REFORMABLE",
              tagCol: "#50C878",
              items: "Interest rates, debt architecture, governance horizons, the metabolic multiplier μ",
              verdict: "Changed repeatedly in history. Debt jubilees, Bretton Woods, negative interest rates — all happened.",
              bg: "#1a2d1a",
              border: "#50C878",
            },
          ].map((t) => (
            <div key={t.tier} style={{ background: t.bg, borderRadius: 12, padding: 20, borderLeft: `4px solid ${t.border}` }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
                <h4 style={{ color: t.border, margin: 0, fontSize: 16 }}>{t.tier}</h4>
                <span style={{ background: t.tagCol, color: "#000", fontSize: 11, padding: "2px 8px", borderRadius: 4, fontWeight: 700 }}>{t.tag}</span>
              </div>
              <p style={{ color: "#b0b0b0", margin: "0 0 6px", fontSize: 14 }}>{t.items}</p>
              <p style={{ color: "#ddd", margin: 0, fontSize: 14, fontStyle: "italic" }}>{t.verdict}</p>
            </div>
          ))}
        </div>
      </>
    ),
  },
  {
    id: "numbers",
    title: "By the Numbers",
    icon: "📊",
    color: "#FFD700",
    bg: "#1a1a2e",
    content: (
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 16 }}>
        {[
          { val: "~20 TW", label: "Current global power consumption", col: "#87CEEB" },
          { val: "~120,000 TW", label: "Absorbed solar flux", col: "#FFD700" },
          { val: "~7,000 TW", label: "Waste heat ceiling (4°K rise)", col: "#E94560" },
          { val: "<1%", label: "Of corridor currently occupied", col: "#50C878" },
          { val: "~250-300 yr", label: "Time to ceiling at 2.3% growth", col: "#FF9A3C" },
          { val: "8-10", label: "Doublings remaining to ceiling", col: "#DA70D6" },
          { val: "5.9 mW/$", label: "Power-wealth coupling (50yr stable)", col: "#87CEEB" },
          { val: "99%+", label: "Of possible civilisation lies ahead", col: "#50C878" },
        ].map((n) => (
          <div key={n.label} style={{ background: "#16213e", borderRadius: 12, padding: 20, textAlign: "center", borderTop: `3px solid ${n.col}` }}>
            <div style={{ fontSize: 28, fontWeight: 700, color: n.col, fontFamily: "monospace" }}>{n.val}</div>
            <p style={{ color: "#999", margin: "8px 0 0", fontSize: 13 }}>{n.label}</p>
          </div>
        ))}
      </div>
    ),
  },
];

export default function ThermodynamicCorridor() {
  const [active, setActive] = useState("intro");

  return (
    <div style={{ minHeight: "100vh", background: "#0d0d1a", color: "#e0e0e0", fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" }}>
      <div style={{ background: "linear-gradient(135deg, #1a1a3e 0%, #0d0d2a 50%, #0a1628 100%)", padding: "48px 24px 32px", textAlign: "center", borderBottom: "1px solid #333" }}>
        <div style={{ fontSize: 14, color: "#FF6B35", letterSpacing: 3, textTransform: "uppercase", marginBottom: 12 }}>
          A Visual Summary
        </div>
        <h1 style={{ fontSize: 36, fontWeight: 700, margin: "0 0 12px", background: "linear-gradient(90deg, #FFD700, #FF6B35, #E94560)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
          Civilisation's Thermodynamic Corridor
        </h1>
        <p style={{ color: "#888", fontSize: 16, maxWidth: 600, margin: "0 auto 8px" }}>
          by Object Zero — a physics-first framework for civilisational survival
        </p>
        <p style={{ color: "#666", fontSize: 13 }}>
          Original series: 5 parts, 18 articles on X/Twitter (March 2026)
        </p>
      </div>

      <div style={{ maxWidth: 900, margin: "0 auto", padding: "24px 16px" }}>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 24, justifyContent: "center" }}>
          {sections.map((s) => (
            <button
              key={s.id}
              onClick={() => setActive(s.id)}
              style={{
                background: active === s.id ? `${s.color}22` : "#16213e",
                border: active === s.id ? `2px solid ${s.color}` : "2px solid #333",
                color: active === s.id ? s.color : "#888",
                padding: "8px 16px",
                borderRadius: 8,
                cursor: "pointer",
                fontSize: 13,
                fontWeight: active === s.id ? 700 : 400,
                transition: "all 0.2s",
              }}
            >
              {s.icon} {s.title.replace(/Part \d+: /, "")}
            </button>
          ))}
        </div>

        {sections
          .filter((s) => s.id === active)
          .map((s) => (
            <div key={s.id} style={{ background: "#111128", borderRadius: 20, padding: 32, border: `1px solid ${s.color}33` }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 8 }}>
                <span style={{ fontSize: 32 }}>{s.icon}</span>
                <div>
                  <h2 style={{ margin: 0, color: s.color, fontSize: 24 }}>{s.title}</h2>
                  {s.subtitle && <p style={{ margin: "2px 0 0", color: "#888", fontSize: 14 }}>{s.subtitle}</p>}
                </div>
              </div>
              <div style={{ marginTop: 20 }}>{s.content}</div>
            </div>
          ))}

        <div style={{ textAlign: "center", padding: "32px 0 16px", color: "#555", fontSize: 12 }}>
          Summary of "Civilisation's Thermodynamic Corridor" by @Object_Zero_ (March 2026)
          <br />
          Original articles available on X/Twitter
        </div>
      </div>
    </div>
  );
}
