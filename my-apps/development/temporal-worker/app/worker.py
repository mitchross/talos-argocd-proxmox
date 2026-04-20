"""
Temporal Worker - AI News Digest Pipeline

Fetches real news from RSS feeds, uses llama-cpp to summarize
each article, then compiles a readable daily digest.

Temporal concepts demonstrated:
- Activities: Fetch RSS, summarize articles (retryable independently)
- Fan-out: Summarize all articles in parallel
- Retries: RSS feeds and LLM calls can fail - Temporal handles it
- Timeouts: LLM calls get per-activity time limits
- Durability: Kill the worker mid-digest -> restart -> resumes
- Scheduling: Can be triggered on a cron schedule for daily digests
"""
import asyncio
import json
import logging
import os
import re
import xml.etree.ElementTree as ET
from datetime import timedelta
from dataclasses import dataclass

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

# RSS feeds organized by category
FEEDS = {
    "tech": [
        "https://hnrss.org/frontpage?count=5",
        "https://www.techmeme.com/feed.xml",
    ],
    "kubernetes": [
        "https://kubernetes.io/feed.xml",
        "https://www.cncf.io/blog/feed/",
    ],
    "linux": [
        "https://www.phoronix.com/rss.php",
        "https://lwn.net/headlines/rss",
    ],
    "security": [
        "https://feeds.feedburner.com/TheHackersNews",
        "https://krebsonsecurity.com/feed/",
    ],
    "science": [
        "https://rss.nytimes.com/services/xml/rss/nyt/Science.xml",
        "https://www.nature.com/nature.rss",
    ],
    "world": [
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
    ],
}


# ──────────────────────────────────────────────
# Data Classes
# ──────────────────────────────────────────────

@dataclass
class DigestRequest:
    categories: list[str]      # e.g. ["tech", "kubernetes", "security"]
    max_articles: int = 5      # per category
    summary_style: str = "concise and informative, 2-3 sentences"

@dataclass
class Article:
    title: str
    link: str
    source: str
    description: str

@dataclass
class SummarizedArticle:
    title: str
    link: str
    source: str
    summary: str

@dataclass
class DigestResult:
    categories: dict            # category -> list of summarized articles
    headline: str               # AI-generated digest headline
    total_articles: int


# ──────────────────────────────────────────────
# Activities
# ──────────────────────────────────────────────

@activity.defn
async def fetch_feed(feed_info: dict) -> list[dict]:
    """Fetch and parse an RSS feed. Returns raw article dicts."""
    url = feed_info["url"]
    max_articles = feed_info["max_articles"]

    activity.logger.info(f"Fetching RSS: {url}")

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        resp = await client.get(url, headers={
            "User-Agent": "TemporalNewsDigest/1.0"
        })
        resp.raise_for_status()

    root = ET.fromstring(resp.text)
    articles = []

    # Handle both RSS 2.0 and Atom feeds
    for item in root.findall(".//item")[:max_articles]:
        title = item.findtext("title", "").strip()
        link = item.findtext("link", "").strip()
        desc = item.findtext("description", "").strip()
        if title:
            articles.append({
                "title": title,
                "link": link,
                "source": url.split("/")[2],
                "description": desc[:500],
            })

    # Atom: entry
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    for entry in root.findall(".//atom:entry", ns)[:max_articles]:
        title = entry.findtext("atom:title", "", ns).strip()
        link_el = entry.find("atom:link", ns)
        link = link_el.get("href", "") if link_el is not None else ""
        desc = entry.findtext("atom:summary", "", ns).strip()
        if not desc:
            desc = entry.findtext("atom:content", "", ns).strip()
        if title:
            articles.append({
                "title": title,
                "link": link,
                "source": url.split("/")[2],
                "description": desc[:500],
            })

    activity.logger.info(f"Got {len(articles)} articles from {url}")
    return articles


@activity.defn
async def summarize_article(article_info: dict) -> dict:
    """Use llama-cpp to create a clean summary of one article."""
    title = article_info["title"]
    description = article_info["description"]
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
# Workflow
# ──────────────────────────────────────────────

# versioning_behavior=AUTO_UPGRADE means: when a new worker version is
# deployed, already-running workflows migrate to the new code on their
# next workflow task. Fine for short, idempotent pipelines like this
# digest — swap to VersioningBehavior.PINNED for long-running workflows
# whose state would break if code shape changes mid-execution.
@workflow.defn(versioning_behavior=VersioningBehavior.AUTO_UPGRADE)
class NewsDigestWorkflow:
    """
    AI-powered news digest pipeline.

    Flow:
    1. Fetch RSS feeds for requested categories (parallel per feed)
    2. Deduplicate and pick top articles
    3. Summarize each article with LLM (parallel fan-out)
    4. Generate a digest headline
    5. Return compiled digest
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

        # Step 1: Fetch all RSS feeds in parallel
        workflow.logger.info(f"Step 1: Fetching feeds for {request.categories}")
        fetch_tasks = []
        for category in request.categories:
            feeds = FEEDS.get(category, [])
            for url in feeds:
                task = workflow.execute_activity(
                    fetch_feed,
                    {"url": url, "max_articles": request.max_articles},
                    start_to_close_timeout=timedelta(seconds=30),
                    retry_policy=retry_fast,
                )
                fetch_tasks.append((category, task))

        all_articles: dict[str, list[dict]] = {}
        for category, task in fetch_tasks:
            try:
                articles = await task
                all_articles.setdefault(category, []).extend(articles)
            except Exception as e:
                workflow.logger.warning(f"Feed fetch failed for {category}: {e}")

        # Deduplicate by title within each category
        for cat in all_articles:
            seen = set()
            unique = []
            for a in all_articles[cat]:
                if a["title"] not in seen:
                    seen.add(a["title"])
                    unique.append(a)
            all_articles[cat] = unique[:request.max_articles]

        total = sum(len(v) for v in all_articles.values())
        workflow.logger.info(f"Fetched {total} unique articles across {len(all_articles)} categories")

        # Step 2: Summarize all articles in parallel
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

        # Step 3: Generate digest headline
        all_titles = [a["title"] for articles in digest.values() for a in articles]
        workflow.logger.info("Step 3: Generating digest headline")
        headline = await workflow.execute_activity(
            generate_digest_headline,
            {"titles": all_titles},
            start_to_close_timeout=timedelta(minutes=1),
            retry_policy=retry_llm,
        )

        summarized_total = sum(len(v) for v in digest.values())
        workflow.logger.info(f"Digest complete: {headline} ({summarized_total} articles)")

        return DigestResult(
            categories=digest,
            headline=headline,
            total_articles=summarized_total,
        )


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
        workflows=[NewsDigestWorkflow],
        activities=[fetch_feed, summarize_article, generate_digest_headline],
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
