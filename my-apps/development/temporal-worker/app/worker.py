"""
Temporal Worker - AI News Digest Pipeline

Fetches real news from RSS feeds, HackerNews API, and Reddit, uses
llama-cpp to summarize each article, then compiles a readable digest.

Also runs:
- TrendDigestWorkflow: scans recent NewsDigestWorkflow runs and surfaces
  stories that recurred / were popular ("you might have missed").
- UserReadStateWorkflow: long-running per-user signal/query workflow that
  tracks which articles have been marked read. Demonstrates signals,
  queries, and continue-as-new for a bounded-history forever workflow.

Temporal concepts demonstrated:
- Activities: Fetch sources, summarize articles (retryable independently)
- Fan-out: Summarize all articles in parallel
- Retries: Sources and LLM calls can fail - Temporal handles it
- Timeouts: LLM calls get per-activity time limits
- Durability: Kill the worker mid-digest -> restart -> resumes
- Visibility: TrendDigestWorkflow lists past completed digest runs
- Signals + queries: read-state workflow accepts mark_read / answers is_read
- Continue-as-new: read-state workflow rolls history once it grows large
"""
import asyncio
import hashlib
import json
import logging
import math
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field

import httpx
from temporalio import activity, workflow
from temporalio.client import Client
from temporalio.common import RetryPolicy, VersioningBehavior
from temporalio.worker import (
    Worker,
    WorkerDeploymentConfig,
    WorkerDeploymentVersion,
)
from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner, SandboxRestrictions

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def strip_thinking(text: str) -> str:
    """Strip Qwen3.5 <think>...</think> blocks from LLM output."""
    result = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    return result if result else text.strip()

LLAMA_URL = "http://llama-cpp-service.llama-cpp.svc.cluster.local:8080/v1/chat/completions"

UA = "TemporalNewsDigest/1.0 (+https://github.com/vanillax)"

# Source registry: each category maps to a list of source specs. The
# workflow dispatches to a per-kind activity ("rss" | "hn" | "reddit").
# Native APIs (HN/Reddit) carry a numeric `score` so the trend workflow
# can rank them; RSS sources fall back to score=0 and rely on recurrence.
SOURCES: dict[str, list[dict]] = {
    "tech": [
        {"kind": "hn",     "params": {"limit": 5}},
        {"kind": "rss",    "params": {"url": "https://www.techmeme.com/feed.xml", "name": "techmeme"}},
        {"kind": "reddit", "params": {"subreddit": "technology", "limit": 5}},
    ],
    "kubernetes": [
        {"kind": "rss",    "params": {"url": "https://kubernetes.io/feed.xml", "name": "kubernetes.io"}},
        {"kind": "rss",    "params": {"url": "https://www.cncf.io/blog/feed/", "name": "cncf"}},
        {"kind": "reddit", "params": {"subreddit": "kubernetes", "limit": 5}},
    ],
    "linux": [
        {"kind": "rss",    "params": {"url": "https://www.phoronix.com/rss.php", "name": "phoronix"}},
        {"kind": "rss",    "params": {"url": "https://lwn.net/headlines/rss", "name": "lwn"}},
        {"kind": "reddit", "params": {"subreddit": "linux", "limit": 5}},
    ],
    "security": [
        {"kind": "rss",    "params": {"url": "https://feeds.feedburner.com/TheHackersNews", "name": "thehackernews"}},
        {"kind": "rss",    "params": {"url": "https://krebsonsecurity.com/feed/", "name": "krebs"}},
        {"kind": "reddit", "params": {"subreddit": "netsec", "limit": 5}},
    ],
    "programming": [
        {"kind": "hn",     "params": {"limit": 5}},
        {"kind": "rss",    "params": {"url": "https://feed.infoq.com/", "name": "infoq"}},
        {"kind": "reddit", "params": {"subreddit": "programming", "limit": 5}},
        {"kind": "rss",    "params": {"url": "https://lobste.rs/rss", "name": "lobste.rs"}},
    ],
    "science": [
        {"kind": "rss", "params": {"url": "https://rss.nytimes.com/services/xml/rss/nyt/Science.xml", "name": "nyt"}},
        {"kind": "rss", "params": {"url": "https://www.nature.com/nature.rss", "name": "nature"}},
    ],
    "world": [
        {"kind": "rss", "params": {"url": "https://feeds.bbci.co.uk/news/world/rss.xml", "name": "bbc"}},
        {"kind": "rss", "params": {"url": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml", "name": "nyt"}},
    ],
}


# ──────────────────────────────────────────────
# Data Classes
# ──────────────────────────────────────────────

@dataclass
class DigestRequest:
    categories: list[str]
    max_articles: int = 5
    summary_style: str = "concise and informative, 2-3 sentences"

@dataclass
class Article:
    title: str
    link: str
    source: str
    description: str
    score: int = 0
    published_at: str = ""

@dataclass
class SummarizedArticle:
    title: str
    link: str
    source: str
    summary: str
    score: int = 0
    published_at: str = ""

@dataclass
class DigestResult:
    categories: dict
    headline: str
    total_articles: int

@dataclass
class TrendRequest:
    lookback_hours: int = 168   # 7 days
    top_n: int = 12

@dataclass
class TrendItem:
    title: str
    link: str
    source: str
    summary: str
    category: str
    recurrence: int          # how many digest runs included this story
    score: int               # native score (HN points / Reddit upvotes / 0)
    trend_score: float       # blended ranking score
    first_seen: str          # ISO ts of earliest digest run that included it
    last_seen: str

@dataclass
class TrendResult:
    items: list
    generated_at: str
    lookback_hours: int
    digests_scanned: int
    total_articles_seen: int

@dataclass
class ReadStateInit:
    user_id: str
    initial: dict = field(default_factory=dict)


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def article_key(link: str) -> str:
    """Stable per-article identifier; used as the read-state key."""
    return hashlib.sha256(link.strip().lower().encode("utf-8")).hexdigest()[:16]


def parse_rss(xml_text: str, max_articles: int, source_name: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    out: list[dict] = []

    for item in root.findall(".//item")[:max_articles]:
        title = item.findtext("title", "").strip()
        link = item.findtext("link", "").strip()
        desc = item.findtext("description", "").strip()
        pub = item.findtext("pubDate", "").strip()
        if title:
            out.append({
                "title": title,
                "link": link,
                "source": source_name,
                "description": desc[:500],
                "score": 0,
                "published_at": pub,
            })

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    for entry in root.findall(".//atom:entry", ns)[:max_articles]:
        title = entry.findtext("atom:title", "", ns).strip()
        link_el = entry.find("atom:link", ns)
        link = link_el.get("href", "") if link_el is not None else ""
        desc = entry.findtext("atom:summary", "", ns).strip()
        if not desc:
            desc = entry.findtext("atom:content", "", ns).strip()
        pub = entry.findtext("atom:published", "", ns).strip()
        if title:
            out.append({
                "title": title,
                "link": link,
                "source": source_name,
                "description": desc[:500],
                "score": 0,
                "published_at": pub,
            })

    return out


# ──────────────────────────────────────────────
# Activities — sources
# ──────────────────────────────────────────────

@activity.defn
async def fetch_feed(feed_info: dict) -> list[dict]:
    """Fetch and parse a generic RSS/Atom feed."""
    url = feed_info["url"]
    max_articles = feed_info["max_articles"]
    source_name = feed_info.get("name") or url.split("/")[2]

    activity.logger.info(f"Fetching RSS: {url}")
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        resp = await client.get(url, headers={"User-Agent": UA})
        resp.raise_for_status()

    articles = parse_rss(resp.text, max_articles, source_name)
    activity.logger.info(f"Got {len(articles)} articles from {url}")
    return articles


@activity.defn
async def fetch_hackernews(params: dict) -> list[dict]:
    """Fetch top stories from the HackerNews Firebase API.

    Returns articles enriched with `score` (HN points) and `published_at`.
    """
    limit = int(params.get("limit", 5))
    max_articles = int(params.get("max_articles", limit))
    n = min(limit, max_articles)

    base = "https://hacker-news.firebaseio.com/v0"
    activity.logger.info(f"Fetching HN top {n}")

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        ids_resp = await client.get(f"{base}/topstories.json", headers={"User-Agent": UA})
        ids_resp.raise_for_status()
        ids = ids_resp.json()[:n]

        async def fetch_one(item_id: int) -> dict | None:
            r = await client.get(f"{base}/item/{item_id}.json", headers={"User-Agent": UA})
            r.raise_for_status()
            return r.json()

        items = await asyncio.gather(*(fetch_one(i) for i in ids), return_exceptions=True)

    out: list[dict] = []
    for item in items:
        if isinstance(item, Exception) or not item or item.get("dead") or item.get("deleted"):
            continue
        title = (item.get("title") or "").strip()
        if not title:
            continue
        item_id = item.get("id")
        link = item.get("url") or f"https://news.ycombinator.com/item?id={item_id}"
        # `text` is present on Ask HN/self posts; otherwise HN gives no body.
        desc = re.sub(r"<[^>]+>", " ", item.get("text") or "").strip()[:500]
        ts = item.get("time")
        published = (
            datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
            if isinstance(ts, (int, float)) else ""
        )
        out.append({
            "title": title,
            "link": link,
            "source": "hackernews",
            "description": desc or f"HN discussion · {item.get('descendants', 0)} comments",
            "score": int(item.get("score") or 0),
            "published_at": published,
        })

    activity.logger.info(f"Got {len(out)} HN stories")
    return out


@activity.defn
async def fetch_reddit(params: dict) -> list[dict]:
    """Fetch top posts from a subreddit using Reddit's public JSON.

    `score` is upvote count; `published_at` is the post creation time.
    """
    subreddit = params["subreddit"]
    limit = int(params.get("limit", 5))
    max_articles = int(params.get("max_articles", limit))
    n = min(limit, max_articles)
    timeframe = params.get("time", "day")  # hour, day, week, month, year, all

    url = f"https://www.reddit.com/r/{subreddit}/top.json?t={timeframe}&limit={n}"
    activity.logger.info(f"Fetching reddit: r/{subreddit} top/{timeframe} ({n})")

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        resp = await client.get(url, headers={"User-Agent": UA, "Accept": "application/json"})
        resp.raise_for_status()
        data = resp.json()

    out: list[dict] = []
    for child in data.get("data", {}).get("children", [])[:n]:
        post = child.get("data", {})
        if post.get("stickied"):
            continue
        title = (post.get("title") or "").strip()
        if not title:
            continue
        # Prefer the linked URL for link posts; fall back to the reddit thread.
        link = post.get("url_overridden_by_dest") or post.get("url") or ""
        if not link or link.startswith("/r/"):
            link = f"https://www.reddit.com{post.get('permalink', '')}"
        body = (post.get("selftext") or "").strip()[:500]
        ts = post.get("created_utc")
        published = (
            datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
            if isinstance(ts, (int, float)) else ""
        )
        out.append({
            "title": title,
            "link": link,
            "source": f"r/{subreddit}",
            "description": body or f"r/{subreddit} · {post.get('num_comments', 0)} comments",
            "score": int(post.get("score") or 0),
            "published_at": published,
        })

    activity.logger.info(f"Got {len(out)} reddit posts from r/{subreddit}")
    return out


# ──────────────────────────────────────────────
# Activities — summarization
# ──────────────────────────────────────────────

@activity.defn
async def summarize_article(article_info: dict) -> dict:
    """Use llama-cpp to create a clean summary of one article."""
    title = article_info["title"]
    description = article_info.get("description", "")
    style = article_info.get("style", "concise, 2-3 sentences")

    activity.logger.info(f"Summarizing: {title}")
    clean_desc = re.sub(r"<[^>]+>", "", description).strip()

    prompt = (
        f"Summarize this news article in {style}.\n\n"
        f"Title: {title}\n"
        f"Content: {clean_desc}\n\n"
        f"Write a clear, readable summary. No preamble, just the summary."
    )

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(LLAMA_URL, json={
            "model": "general",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 512,
            "chat_template_kwargs": {"enable_thinking": False},
        })
        resp.raise_for_status()
        summary = strip_thinking(resp.json()["choices"][0]["message"]["content"])

    activity.logger.info(f"Summarized: {title} ({len(summary)} chars)")
    return {
        "title": title,
        "link": article_info["link"],
        "source": article_info["source"],
        "summary": summary,
        "score": int(article_info.get("score") or 0),
        "published_at": article_info.get("published_at", ""),
    }


@activity.defn
async def generate_digest_headline(digest_info: dict) -> str:
    """Generate a catchy headline for the entire digest."""
    titles = digest_info["titles"]
    activity.logger.info(f"Generating digest headline from {len(titles)} articles")

    prompt = (
        f"Based on these news headlines from today, write ONE short catchy "
        f"digest title (under 15 words) that captures the theme:\n\n"
        + "\n".join(f"- {t}" for t in titles[:10])
        + "\n\nReturn only the title, nothing else."
    )

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(LLAMA_URL, json={
            "model": "general",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": 100,
            "chat_template_kwargs": {"enable_thinking": False},
        })
        resp.raise_for_status()
        return strip_thinking(resp.json()["choices"][0]["message"]["content"]).strip('"')


# ──────────────────────────────────────────────
# Activities — trend
# ──────────────────────────────────────────────

@activity.defn
async def list_recent_digest_results(params: dict) -> list[dict]:
    """List completed NewsDigestWorkflow runs over a lookback window and
    materialize their results.

    Activities are not sandboxed, so it's fine to spin up a Temporal
    client here. Returns a list of {workflow_id, run_id, start_time, result}.
    """
    lookback_hours = int(params.get("lookback_hours", 168))
    max_runs = int(params.get("max_runs", 50))

    address = os.environ["TEMPORAL_ADDRESS"]
    namespace = os.environ["TEMPORAL_NAMESPACE"]
    client = await Client.connect(address, namespace=namespace)

    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    # Visibility queries want RFC3339 timestamps quoted as strings.
    cutoff_iso = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")
    query = (
        f'WorkflowType="NewsDigestWorkflow" '
        f'AND ExecutionStatus="Completed" '
        f'AND StartTime > "{cutoff_iso}"'
    )

    activity.logger.info(f"Listing past digests: {query}")

    out: list[dict] = []
    async for wf in client.list_workflows(query):
        if len(out) >= max_runs:
            break
        try:
            handle = client.get_workflow_handle(wf.id, run_id=wf.run_id)
            result = await handle.result()
            # Untyped handle.result() decodes dataclasses to plain dicts.
            if not isinstance(result, dict):
                # Defensive: if SDK returns a dataclass, convert.
                try:
                    result = result.__dict__  # type: ignore[attr-defined]
                except Exception:
                    result = {}
            out.append({
                "workflow_id": wf.id,
                "run_id": wf.run_id,
                "start_time": wf.start_time.isoformat() if wf.start_time else "",
                "result": result,
            })
        except Exception as e:
            activity.logger.warning(f"Skipping {wf.id}: {e}")

    activity.logger.info(f"Listed {len(out)} past digests")
    return out


# ──────────────────────────────────────────────
# Workflows
# ──────────────────────────────────────────────

@workflow.defn(versioning_behavior=VersioningBehavior.AUTO_UPGRADE)
class NewsDigestWorkflow:
    """AI-powered news digest pipeline.

    1. Fetch sources for requested categories (parallel per source)
    2. Deduplicate within category
    3. Summarize each article with LLM (parallel fan-out)
    4. Generate a digest headline
    """

    @workflow.run
    async def run(self, request: DigestRequest) -> DigestResult:
        retry_fast = RetryPolicy(
            initial_interval=timedelta(seconds=2),
            backoff_coefficient=2.0,
            maximum_attempts=3,
        )
        retry_llm = RetryPolicy(
            initial_interval=timedelta(seconds=5),
            backoff_coefficient=2.0,
            maximum_attempts=3,
        )

        workflow.logger.info(f"Step 1: Fetching sources for {request.categories}")
        fetch_tasks = []
        for category in request.categories:
            for spec in SOURCES.get(category, []):
                kind = spec["kind"]
                params = {**spec["params"], "max_articles": request.max_articles}
                if kind == "rss":
                    act = fetch_feed
                elif kind == "hn":
                    act = fetch_hackernews
                elif kind == "reddit":
                    act = fetch_reddit
                else:
                    workflow.logger.warning(f"Unknown source kind: {kind}")
                    continue
                task = workflow.execute_activity(
                    act,
                    params,
                    start_to_close_timeout=timedelta(seconds=45),
                    retry_policy=retry_fast,
                )
                fetch_tasks.append((category, task))

        all_articles: dict[str, list[dict]] = {}
        for category, task in fetch_tasks:
            try:
                articles = await task
                all_articles.setdefault(category, []).extend(articles)
            except Exception as e:
                workflow.logger.warning(f"Source fetch failed for {category}: {e}")

        # Dedupe by link within category, then by title as fallback. Keep
        # the highest-scoring duplicate so HN/Reddit beats lower-signal RSS.
        for cat in all_articles:
            by_key: dict[str, dict] = {}
            for a in all_articles[cat]:
                k = a.get("link") or a.get("title")
                if not k:
                    continue
                existing = by_key.get(k)
                if existing is None or int(a.get("score") or 0) > int(existing.get("score") or 0):
                    by_key[k] = a
            ranked = sorted(by_key.values(), key=lambda x: int(x.get("score") or 0), reverse=True)
            all_articles[cat] = ranked[: request.max_articles]

        total = sum(len(v) for v in all_articles.values())
        workflow.logger.info(f"Fetched {total} unique articles across {len(all_articles)} categories")

        workflow.logger.info(f"Step 2: Summarizing {total} articles with LLM")
        summary_tasks = []
        for category, articles in all_articles.items():
            for article in articles:
                article["style"] = request.summary_style
                task = workflow.execute_activity(
                    summarize_article,
                    article,
                    start_to_close_timeout=timedelta(minutes=3),
                    retry_policy=retry_llm,
                )
                summary_tasks.append((category, task))

        digest: dict[str, list] = {}
        for category, task in summary_tasks:
            try:
                result = await task
                digest.setdefault(category, []).append(result)
            except Exception as e:
                workflow.logger.warning(f"Summarization failed: {e}")

        all_titles = [a["title"] for articles in digest.values() for a in articles]
        workflow.logger.info("Step 3: Generating digest headline")
        headline = (
            await workflow.execute_activity(
                generate_digest_headline,
                {"titles": all_titles},
                start_to_close_timeout=timedelta(minutes=1),
                retry_policy=retry_llm,
            )
            if all_titles else ""
        )

        summarized_total = sum(len(v) for v in digest.values())
        workflow.logger.info(f"Digest complete: {headline} ({summarized_total} articles)")
        return DigestResult(
            categories=digest,
            headline=headline,
            total_articles=summarized_total,
        )


@workflow.defn(versioning_behavior=VersioningBehavior.AUTO_UPGRADE)
class TrendDigestWorkflow:
    """Surface stories that recurred across recent digest runs.

    Demonstrates Temporal visibility: the workflow itself stays trivial
    (one activity call + pure scoring), with all the heavy lifting
    (listing past workflows + fetching their results) happening inside a
    single activity that can use the Temporal client.
    """

    @workflow.run
    async def run(self, request: TrendRequest) -> TrendResult:
        retry_fast = RetryPolicy(
            initial_interval=timedelta(seconds=2),
            backoff_coefficient=2.0,
            maximum_attempts=3,
        )

        runs = await workflow.execute_activity(
            list_recent_digest_results,
            {"lookback_hours": request.lookback_hours, "max_runs": 50},
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=retry_fast,
        )

        # Aggregate by article link (sha-stable key). Track first/last
        # seen, recurrence count, max native score.
        agg: dict[str, dict] = {}
        total_seen = 0
        for run in runs:
            start_time = run.get("start_time", "")
            result = run.get("result") or {}
            categories = result.get("categories") or {}
            for category, articles in categories.items():
                for a in articles or []:
                    link = a.get("link") or ""
                    if not link:
                        continue
                    total_seen += 1
                    key = article_key(link)
                    rec = agg.get(key)
                    if rec is None:
                        agg[key] = {
                            "title": a.get("title", ""),
                            "link": link,
                            "source": a.get("source", ""),
                            "summary": a.get("summary", ""),
                            "category": category,
                            "recurrence": 1,
                            "score": int(a.get("score") or 0),
                            "first_seen": start_time,
                            "last_seen": start_time,
                        }
                    else:
                        rec["recurrence"] += 1
                        rec["score"] = max(rec["score"], int(a.get("score") or 0))
                        if start_time:
                            if not rec["first_seen"] or start_time < rec["first_seen"]:
                                rec["first_seen"] = start_time
                            if not rec["last_seen"] or start_time > rec["last_seen"]:
                                rec["last_seen"] = start_time

        # Trend score = recurrence (log-damped) + native-score (log-damped)
        # + recency (newer last_seen ranks higher). Weights are tuned by
        # vibe — recurrence dominates, score is supporting signal, recency
        # is a tiebreaker.
        now = workflow.now()  # deterministic time inside workflow
        for rec in agg.values():
            recur = math.log1p(rec["recurrence"]) * 1.4
            score_signal = math.log1p(max(rec["score"], 0)) * 0.25
            recency = 0.0
            try:
                if rec["last_seen"]:
                    last = datetime.fromisoformat(rec["last_seen"].replace("Z", "+00:00"))
                    age_h = max((now - last).total_seconds() / 3600.0, 0.1)
                    recency = max(0.0, 1.0 - math.log1p(age_h) / 6.0) * 0.4
            except Exception:
                pass
            rec["trend_score"] = round(recur + score_signal + recency, 4)

        ranked = sorted(agg.values(), key=lambda r: r["trend_score"], reverse=True)
        items = ranked[: request.top_n]

        workflow.logger.info(
            f"Trend complete: {len(runs)} digests, "
            f"{total_seen} articles seen, {len(agg)} unique, "
            f"top {len(items)} returned"
        )

        return TrendResult(
            items=items,
            generated_at=now.isoformat(),
            lookback_hours=request.lookback_hours,
            digests_scanned=len(runs),
            total_articles_seen=total_seen,
        )


# Long-running per-user read-state workflow. Use signal-with-start from
# the client to ensure existence; it loops forever, taking signals, and
# continues-as-new when the server says history is getting heavy.
#
# Versioning is PINNED here because a code-shape change while running
# would clobber in-flight state. New build IDs run new instances.
@workflow.defn(versioning_behavior=VersioningBehavior.PINNED)
class UserReadStateWorkflow:
    def __init__(self) -> None:
        # article_key -> read_at (epoch ms)
        self._read: dict[str, int] = {}

    @workflow.run
    async def run(self, init: ReadStateInit) -> None:
        if init and init.initial:
            for k, v in init.initial.items():
                try:
                    self._read[str(k)] = int(v)
                except Exception:
                    continue
        workflow.logger.info(
            f"ReadState online for user={init.user_id} "
            f"with {len(self._read)} pre-existing keys"
        )
        # Wait until the server tells us history is large enough that we
        # should continue-as-new. wait_condition wakes on every signal,
        # so this is effectively an "idle until threshold" loop.
        await workflow.wait_condition(lambda: workflow.info().is_continue_as_new_suggested())
        workflow.logger.info(
            f"ReadState rolling history (continue-as-new): {len(self._read)} keys"
        )
        workflow.continue_as_new(
            args=[ReadStateInit(user_id=init.user_id, initial=dict(self._read))]
        )

    @workflow.signal
    def mark_read(self, key: str, read_at: int) -> None:
        if not key:
            return
        self._read[str(key)] = int(read_at)

    @workflow.signal
    def mark_unread(self, key: str) -> None:
        self._read.pop(str(key), None)

    @workflow.query
    def get_read_keys(self) -> list[str]:
        return list(self._read.keys())

    @workflow.query
    def get_read_state(self) -> dict:
        return dict(self._read)

    @workflow.query
    def is_read(self, key: str) -> bool:
        return str(key) in self._read

    @workflow.query
    def size(self) -> int:
        return len(self._read)


# ──────────────────────────────────────────────
# Worker
# ──────────────────────────────────────────────

async def main():
    # The Temporal Worker Controller (infrastructure/controllers/
    # temporal-worker-controller/) injects these env vars into every Pod
    # it creates. We require them — if you run this worker outside the
    # controller (e.g. local dev), set them manually:
    #
    #   export TEMPORAL_ADDRESS=127.0.0.1:7233
    #   export TEMPORAL_NAMESPACE=default
    #   export TEMPORAL_DEPLOYMENT_NAME=news-digest
    #   export TEMPORAL_WORKER_BUILD_ID=local-dev
    address = os.environ["TEMPORAL_ADDRESS"]
    namespace = os.environ["TEMPORAL_NAMESPACE"]
    deployment_name = os.environ["TEMPORAL_DEPLOYMENT_NAME"]
    build_id = os.environ["TEMPORAL_WORKER_BUILD_ID"]

    logger.info(
        f"Connecting to Temporal at {address} (namespace={namespace}, "
        f"deployment={deployment_name}, build={build_id})"
    )
    client = await Client.connect(address, namespace=namespace)

    logger.info("Starting worker on task queue: news-digest")
    worker = Worker(
        client,
        task_queue="news-digest",
        workflows=[
            NewsDigestWorkflow,
            TrendDigestWorkflow,
            UserReadStateWorkflow,
        ],
        activities=[
            fetch_feed,
            fetch_hackernews,
            fetch_reddit,
            summarize_article,
            generate_digest_headline,
            list_recent_digest_results,
        ],
        workflow_runner=SandboxedWorkflowRunner(
            restrictions=SandboxRestrictions.default.with_passthrough_modules("httpx"),
        ),
        # Enrolls this worker in Temporal Worker Versioning. The controller
        # manages version registration + traffic routing on the server side;
        # all this code does is declare "I am version <build_id> of deployment
        # <deployment_name>".
        deployment_config=WorkerDeploymentConfig(
            version=WorkerDeploymentVersion(
                deployment_name=deployment_name,
                build_id=build_id,
            ),
            use_worker_versioning=True,
        ),
    )

    logger.info("Worker ready! Waiting for digest requests...")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
