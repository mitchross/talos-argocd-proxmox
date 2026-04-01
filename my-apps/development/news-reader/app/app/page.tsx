"use client";

import { useCallback, useEffect, useState } from "react";

interface Article {
  title: string;
  link: string;
  source: string;
  summary: string;
}

interface DigestResult {
  categories: Record<string, Article[]>;
  headline: string;
  total_articles: number;
}

interface DigestInfo {
  workflowId: string;
  runId: string;
  status: string;
  startTime: string;
  result: DigestResult | null;
}

const CATEGORY_LABELS: Record<string, { label: string; color: string }> = {
  tech: { label: "Tech", color: "bg-blue-500/20 text-blue-400 border-blue-500/30" },
  security: { label: "Security", color: "bg-red-500/20 text-red-400 border-red-500/30" },
  kubernetes: { label: "Kubernetes", color: "bg-purple-500/20 text-purple-400 border-purple-500/30" },
  linux: { label: "Linux", color: "bg-amber-500/20 text-amber-400 border-amber-500/30" },
  science: { label: "Science", color: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30" },
  world: { label: "World", color: "bg-cyan-500/20 text-cyan-400 border-cyan-500/30" },
};

const ALL_CATEGORIES = Object.keys(CATEGORY_LABELS);

export default function Home() {
  const [digests, setDigests] = useState<DigestInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [triggering, setTriggering] = useState(false);
  const [selectedCategories, setSelectedCategories] = useState<string[]>(["tech", "security"]);
  const [activeDigest, setActiveDigest] = useState<DigestInfo | null>(null);

  const fetchDigests = useCallback(async () => {
    try {
      const res = await fetch("/api/digests");
      const data = await res.json();
      if (Array.isArray(data)) {
        setDigests(data);
        if (!activeDigest && data.length > 0) {
          const completed = data.find((d: DigestInfo) => d.status === "COMPLETED" && d.result);
          if (completed) setActiveDigest(completed);
        }
      }
    } catch (e) {
      console.error("Failed to fetch digests:", e);
    } finally {
      setLoading(false);
    }
  }, [activeDigest]);

  useEffect(() => {
    fetchDigests();
    const interval = setInterval(fetchDigests, 15000);
    return () => clearInterval(interval);
  }, [fetchDigests]);

  const triggerNewDigest = async () => {
    setTriggering(true);
    try {
      await fetch("/api/trigger", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ categories: selectedCategories, maxArticles: 3 }),
      });
      setTimeout(fetchDigests, 2000);
    } catch (e) {
      console.error("Failed to trigger:", e);
    } finally {
      setTriggering(false);
    }
  };

  const toggleCategory = (cat: string) => {
    setSelectedCategories((prev) =>
      prev.includes(cat) ? prev.filter((c) => c !== cat) : [...prev, cat]
    );
  };

  const formatTime = (iso: string) => {
    if (!iso) return "";
    const d = new Date(iso);
    return d.toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  };

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <header className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight">Daily Digest</h1>
        <p className="text-zinc-500 mt-1">AI-powered news summaries from your homelab</p>
      </header>

      <div className="mb-8 p-4 rounded-xl bg-zinc-900 border border-zinc-800">
        <div className="flex flex-wrap gap-2 mb-3">
          {ALL_CATEGORIES.map((cat) => {
            const meta = CATEGORY_LABELS[cat];
            const active = selectedCategories.includes(cat);
            return (
              <button
                key={cat}
                onClick={() => toggleCategory(cat)}
                className={`px-3 py-1 rounded-full text-sm border transition-all ${
                  active ? meta.color : "bg-zinc-800 text-zinc-500 border-zinc-700"
                }`}
              >
                {meta.label}
              </button>
            );
          })}
        </div>
        <button
          onClick={triggerNewDigest}
          disabled={triggering || selectedCategories.length === 0}
          className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed text-sm font-medium transition-colors"
        >
          {triggering ? "Generating..." : "Generate New Digest"}
        </button>
      </div>

      {digests.length > 1 && (
        <div className="mb-6 flex gap-2 overflow-x-auto pb-2">
          {digests
            .filter((d) => d.status === "COMPLETED" && d.result)
            .map((d) => (
              <button
                key={d.workflowId}
                onClick={() => setActiveDigest(d)}
                className={`shrink-0 px-3 py-1.5 rounded-lg text-xs border transition-all ${
                  activeDigest?.workflowId === d.workflowId
                    ? "bg-zinc-800 border-zinc-600 text-zinc-200"
                    : "bg-zinc-900 border-zinc-800 text-zinc-500 hover:border-zinc-700"
                }`}
              >
                {formatTime(d.startTime)}
              </button>
            ))}
        </div>
      )}

      {digests.some((d) => d.status === "RUNNING") && (
        <div className="mb-6 p-4 rounded-xl bg-blue-950/30 border border-blue-900/50 flex items-center gap-3">
          <div className="h-3 w-3 rounded-full bg-blue-500 animate-pulse" />
          <span className="text-sm text-blue-300">Generating digest...</span>
        </div>
      )}

      {loading && (
        <div className="text-center py-20 text-zinc-500">Loading digests...</div>
      )}

      {activeDigest?.result && (
        <div>
          {activeDigest.result.headline && (
            <h2 className="text-xl font-semibold mb-1">{activeDigest.result.headline}</h2>
          )}
          <p className="text-zinc-500 text-sm mb-6">
            {formatTime(activeDigest.startTime)} &middot; {activeDigest.result.total_articles} articles
          </p>

          <div className="space-y-8">
            {Object.entries(activeDigest.result.categories).map(([category, articles]) => (
              <section key={category}>
                <div className="flex items-center gap-2 mb-4">
                  <span
                    className={`px-2.5 py-0.5 rounded-full text-xs font-medium border ${
                      CATEGORY_LABELS[category]?.color ?? "bg-zinc-800 text-zinc-400 border-zinc-700"
                    }`}
                  >
                    {CATEGORY_LABELS[category]?.label ?? category}
                  </span>
                  <div className="h-px flex-1 bg-zinc-800" />
                </div>

                <div className="space-y-4">
                  {articles.map((article, i) => (
                    <article
                      key={i}
                      className="p-4 rounded-xl bg-zinc-900 border border-zinc-800 hover:border-zinc-700 transition-colors"
                    >
                      <a
                        href={article.link}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-base font-medium text-zinc-100 hover:text-blue-400 transition-colors"
                      >
                        {article.title}
                      </a>
                      <p className="text-xs text-zinc-600 mt-1">{article.source}</p>
                      {article.summary && (
                        <p className="text-sm text-zinc-400 mt-2 leading-relaxed">{article.summary}</p>
                      )}
                    </article>
                  ))}
                </div>
              </section>
            ))}
          </div>
        </div>
      )}

      {!loading && !activeDigest?.result && (
        <div className="text-center py-20">
          <p className="text-zinc-500 mb-4">No digests yet</p>
          <p className="text-zinc-600 text-sm">Select categories above and hit Generate</p>
        </div>
      )}
    </div>
  );
}
