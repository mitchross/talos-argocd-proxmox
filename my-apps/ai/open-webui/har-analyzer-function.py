"""
title: HAR Forensics Analyzer
author: Claude
version: 4.0.0
description: >
    Filter that intercepts uploaded .har files and preprocesses them into a
    forensic report before the LLM sees them. Handles ANY file size — Python
    crunches the entire HAR into a dense report that fits in context. The report
    stays in conversation history so you can ask follow-up questions naturally.
    Preserves headers, cookies, JS/HTML snippets, API patterns, security
    findings, and timing data.
required_open_webui_version: 0.4.0
"""

import json
import re
import hashlib
from typing import Optional, Dict, List, Any
from pydantic import BaseModel, Field
from urllib.parse import urlparse
from collections import Counter, defaultdict


class Filter:
    class Valves(BaseModel):
        enabled: bool = Field(default=True, description="Enable HAR preprocessing")
        max_report_chars: int = Field(
            default=350000,
            description="Max report size in chars (~87K tokens). Tune to your context window."
        )
        max_body_chars: int = Field(
            default=8000,
            description="Max chars per response body (JS/HTML/CSS) to include"
        )
        max_entries_detail: int = Field(
            default=400,
            description="Max entries with full headers/bodies (rest get stats only)"
        )
        slow_threshold_ms: int = Field(default=500, description="Threshold for slow requests")
        include_response_bodies: bool = Field(
            default=True,
            description="Include JS/HTML/CSS/JSON response bodies"
        )
        include_all_headers: bool = Field(
            default=True,
            description="Include all request/response headers"
        )
        include_cookies: bool = Field(
            default=True,
            description="Include full cookie details"
        )
        priority_domains: str = Field(
            default="",
            description="Comma-separated domains to prioritize (get more detail)"
        )

    def __init__(self):
        self.valves = self.Valves()

    async def inlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
        """Intercept HAR uploads, preprocess into forensic report."""
        if not self.valves.enabled:
            return body

        messages = body.get("messages", [])
        if not messages:
            return body

        last_message = messages[-1]
        if last_message.get("role") != "user":
            return body

        files = last_message.get("files", [])
        content = last_message.get("content", "")

        har_data = None
        har_filename = ""

        # Check attached files for .har
        for f in files:
            name = f.get("name", "") or f.get("filename", "")
            if name.lower().endswith(".har"):
                file_content = f.get("data", {}).get("content", "") or f.get("content", "")
                if file_content:
                    try:
                        har_data = json.loads(file_content)
                        har_filename = name
                        break
                    except json.JSONDecodeError:
                        pass

        # Check if message content itself is pasted HAR JSON
        if not har_data and content.strip().startswith('{"log"'):
            try:
                har_data = json.loads(content)
                if "log" in har_data and "entries" in har_data.get("log", {}):
                    har_filename = "pasted-har"
                else:
                    har_data = None
            except json.JSONDecodeError:
                pass

        if not har_data:
            return body

        entries = har_data.get("log", {}).get("entries", [])
        if not entries:
            return body

        # Build the forensic report
        report = self._build_report(entries)

        # User's question (or default)
        user_question = content.strip() if content.strip() and har_filename != "pasted-har" else ""
        if not user_question:
            user_question = "Perform a thorough forensic analysis of this HAR traffic capture."

        new_content = (
            f"I've uploaded a HAR file ({har_filename}, {len(entries)} requests). "
            f"My question: {user_question}\n\n"
            f"Below is the full preprocessed forensic report. Use this data to answer my "
            f"question and any follow-up questions I ask.\n\n"
            f"{report}"
        )

        last_message["content"] = new_content
        # Remove HAR from file list (already processed)
        last_message["files"] = [
            f for f in files
            if not (f.get("name", "") or f.get("filename", "")).lower().endswith(".har")
        ]

        return body

    # =========================================================================
    # Report Builder
    # =========================================================================

    def _build_report(self, entries: list) -> str:
        first_domain = urlparse(entries[0].get("request", {}).get("url", "")).netloc if entries else ""
        priority = set()
        if self.valves.priority_domains:
            priority = set(d.strip() for d in self.valves.priority_domains.split(","))

        sections = [
            self._overview(entries, first_domain),
            self._domain_table(entries, first_domain),
            self._cookie_analysis(entries),
            self._security_findings(entries),
            self._performance(entries),
            self._api_surface(entries),
            self._redirects(entries),
            self._detailed_entries(entries, first_domain, priority),
        ]

        report = "\n\n".join(s for s in sections if s)

        if len(report) > self.valves.max_report_chars:
            report = report[:self.valves.max_report_chars] + "\n\n[Report truncated to fit context]"

        return report

    # =========================================================================
    # Section: Overview
    # =========================================================================

    def _overview(self, entries: list, first_domain: str) -> str:
        status_counts = Counter()
        mime_counts = Counter()
        methods = Counter()
        protocols = Counter()
        total_bytes = 0
        total_time = 0
        third_party = set()

        for e in entries:
            req, resp = e.get("request", {}), e.get("response", {})
            url = req.get("url", "")
            s = resp.get("status", 0)
            body = resp.get("bodySize", 0) or resp.get("content", {}).get("size", 0) or 0
            mime = resp.get("content", {}).get("mimeType", "unknown").split(";")[0].strip()
            elapsed = e.get("time", 0) or 0
            domain = urlparse(url).netloc

            status_counts[s] += 1
            mime_counts[mime] += 1
            methods[req.get("method", "")] += 1
            protocols[resp.get("httpVersion", "?")] += 1
            total_bytes += max(body, 0)
            total_time += elapsed

            if first_domain and domain != first_domain:
                if ".".join(first_domain.split(".")[-2:]) != ".".join(domain.split(".")[-2:]):
                    third_party.add(domain)

        lines = [
            "# HAR FORENSIC REPORT\n",
            "## Overview",
            f"- Total requests: {len(entries)}",
            f"- Total transfer: {total_bytes / (1024*1024):.1f} MB",
            f"- Total time: {total_time/1000:.1f}s",
            f"- First-party: {first_domain}",
            f"- Third-party domains: {len(third_party)}",
            f"- Errors (4xx/5xx): {sum(c for s, c in status_counts.items() if s >= 400)}",
            "\n### Status Codes",
        ]
        for code, count in sorted(status_counts.items()):
            lines.append(f"- {code}: {count}")
        lines.append("\n### Methods")
        for m, c in methods.most_common():
            lines.append(f"- {m}: {c}")
        lines.append("\n### Protocols")
        for p, c in protocols.most_common():
            lines.append(f"- {p}: {c}")
        lines.append("\n### Content Types")
        for m, c in mime_counts.most_common(15):
            lines.append(f"- {m}: {c}")
        lines.append(f"\n### Third-Party Domains ({len(third_party)})")
        for d in sorted(third_party):
            lines.append(f"- {d} ({self._categorize(d)})")

        return "\n".join(lines)

    # =========================================================================
    # Section: Domain Table
    # =========================================================================

    def _domain_table(self, entries: list, first_domain: str) -> str:
        domains = defaultdict(lambda: {"count": 0, "size": 0, "time": 0, "errors": 0})
        for e in entries:
            url = e.get("request", {}).get("url", "")
            domain = urlparse(url).netloc
            body = e.get("response", {}).get("bodySize", 0) or e.get("response", {}).get("content", {}).get("size", 0) or 0
            domains[domain]["count"] += 1
            domains[domain]["size"] += max(body, 0)
            domains[domain]["time"] += e.get("time", 0) or 0
            if e.get("response", {}).get("status", 0) >= 400:
                domains[domain]["errors"] += 1

        lines = [
            "## Domains",
            "| Domain | Reqs | Size | Time | Errors | Type |",
            "|--------|------|------|------|--------|------|",
        ]
        base_fp = ".".join(first_domain.split(".")[-2:]) if first_domain else ""
        for domain, info in sorted(domains.items(), key=lambda x: -x[1]["count"])[:30]:
            base_c = ".".join(domain.split(".")[-2:])
            dtype = "1P" if base_fp == base_c else "3P"
            cat = f" {self._categorize(domain)}" if dtype == "3P" else ""
            lines.append(
                f"| {domain[:45]} | {info['count']} | "
                f"{info['size']/(1024*1024):.1f}MB | "
                f"{info['time']/1000:.1f}s | "
                f"{info['errors']} | {dtype}{cat} |"
            )
        return "\n".join(lines)

    # =========================================================================
    # Section: Cookie & Session
    # =========================================================================

    def _cookie_analysis(self, entries: list) -> str:
        sent = defaultdict(lambda: {"domains": set(), "values": set(), "count": 0})
        set_cookies = defaultdict(list)

        for e in entries:
            req, resp = e.get("request", {}), e.get("response", {})
            domain = urlparse(req.get("url", "")).netloc
            for c in req.get("cookies", []):
                name = c.get("name", "")
                sent[name]["domains"].add(domain)
                sent[name]["values"].add(c.get("value", "")[:60])
                sent[name]["count"] += 1
            for h in resp.get("headers", []):
                if h.get("name", "").lower() == "set-cookie":
                    set_cookies[domain].append(h.get("value", ""))

        cross = {n: i for n, i in sent.items() if len(i["domains"]) > 1}

        lines = ["## Cookie & Session Analysis"]

        if cross:
            lines.append(f"\n### Cross-Domain Cookies ({len(cross)} — tracking indicators)")
            for name, info in sorted(cross.items(), key=lambda x: -len(x[1]["domains"]))[:25]:
                val = next(iter(info["values"]), "")[:40]
                lines.append(f"- **{name}**: {len(info['domains'])} domains — "
                           f"{', '.join(sorted(info['domains']))} val=`{val}`")

        lines.append(f"\n### Cookies Sent ({len(sent)} unique names)")
        for name, info in sorted(sent.items(), key=lambda x: -x[1]["count"])[:50]:
            domains_str = ", ".join(sorted(info["domains"])[:5])
            marker = " [CROSS-DOMAIN]" if len(info["domains"]) > 1 else ""
            lines.append(f"- **{name}**: {info['count']}x to [{domains_str}]{marker}")

        lines.append(f"\n### Set-Cookie Headers by Domain")
        for domain, cookies in sorted(set_cookies.items(), key=lambda x: -len(x[1]))[:15]:
            lines.append(f"\n**{domain}** ({len(cookies)} cookies):")
            for c in cookies[:10]:
                issues = []
                lower = c.lower()
                if "secure" not in lower: issues.append("no-Secure")
                if "httponly" not in lower: issues.append("no-HttpOnly")
                if "samesite" not in lower: issues.append("no-SameSite")
                elif "samesite=none" in lower: issues.append("SameSite=None")
                issue_str = f" — {', '.join(issues)}" if issues else ""
                lines.append(f"  - `{c[:150]}`{issue_str}")

        return "\n".join(lines)

    # =========================================================================
    # Section: Security
    # =========================================================================

    def _security_findings(self, entries: list) -> str:
        lines = ["## Security Findings"]
        findings = []
        seen = set()

        for e in entries:
            req, resp = e.get("request", {}), e.get("response", {})
            url = req.get("url", "")
            domain = urlparse(url).netloc
            scheme = urlparse(url).scheme
            req_h = {h["name"].lower(): h.get("value", "") for h in req.get("headers", [])}
            res_h = {h["name"].lower(): h.get("value", "") for h in resp.get("headers", [])}

            if scheme == "http" and f"http-{domain}" not in seen:
                findings.append(f"- **HTTP (no TLS)**: {domain}")
                seen.add(f"http-{domain}")

            if "text/html" in res_h.get("content-type", "") and f"sec-{domain}" not in seen:
                missing = [l for hdr, l in [
                    ("strict-transport-security", "HSTS"),
                    ("content-security-policy", "CSP"),
                    ("x-content-type-options", "X-CTO"),
                    ("x-frame-options", "XFO"),
                ] if hdr not in res_h]
                if missing:
                    findings.append(f"- **Missing headers** ({domain}): {', '.join(missing)}")
                seen.add(f"sec-{domain}")

            if res_h.get("access-control-allow-origin") == "*" and f"cors-{url[:60]}" not in seen:
                findings.append(f"- **CORS wildcard**: {url[:100]}")
                seen.add(f"cors-{url[:60]}")

            if re.search(r'(api[_-]?key|token|secret|password|auth)=', url, re.I):
                findings.append(f"- **Sensitive param in URL**: {url[:120]}")

            auth = req_h.get("authorization", "")
            if auth.startswith("Bearer eyJ") and f"jwt-{domain}" not in seen:
                try:
                    import base64
                    hdr_b64 = auth.split(".")[0].replace("Bearer ", "")
                    hdr_b64 += "=" * (4 - len(hdr_b64) % 4)
                    jwt_h = json.loads(base64.b64decode(hdr_b64))
                    findings.append(f"- **JWT** to {domain}: alg={jwt_h.get('alg')}")
                except Exception:
                    findings.append(f"- **JWT** sent to {domain}")
                seen.add(f"jwt-{domain}")

        lines.extend(findings[:60] if findings else ["No significant security issues detected."])
        return "\n".join(lines)

    # =========================================================================
    # Section: Performance
    # =========================================================================

    def _performance(self, entries: list) -> str:
        lines = ["## Performance"]

        slow = sorted(entries, key=lambda e: -(e.get("time", 0) or 0))[:30]
        lines.append("\n### Slowest Requests")
        for e in slow:
            url = e.get("request", {}).get("url", "")[:100]
            method = e.get("request", {}).get("method", "")
            status = e.get("response", {}).get("status", 0)
            elapsed = e.get("time", 0) or 0
            t = e.get("timings", {})
            wait = t.get("wait", 0) or 0
            note = f" [TTFB={wait:.0f}ms]" if wait > elapsed * 0.5 else ""
            lines.append(f"- {elapsed:.0f}ms [{status}] {method} {url}{note}")

        large = sorted(entries, key=lambda e: -(e.get("response", {}).get("content", {}).get("size", 0) or 0))[:15]
        lines.append("\n### Largest Responses")
        for e in large:
            url = e.get("request", {}).get("url", "")[:80]
            size = e.get("response", {}).get("content", {}).get("size", 0) or 0
            mime = e.get("response", {}).get("content", {}).get("mimeType", "")[:25]
            lines.append(f"- {size/1024:.0f}KB [{mime}] {url}")

        totals = defaultdict(float)
        for e in entries:
            for k, v in e.get("timings", {}).items():
                if isinstance(v, (int, float)) and v > 0:
                    totals[k] += v
        if totals:
            total_all = sum(totals.values())
            lines.append("\n### Timing Breakdown")
            for phase, ms in sorted(totals.items(), key=lambda x: -x[1]):
                pct = ms / total_all * 100 if total_all > 0 else 0
                lines.append(f"- {phase}: {ms:.0f}ms ({pct:.0f}%)")

        return "\n".join(lines)

    # =========================================================================
    # Section: API Surface
    # =========================================================================

    def _api_surface(self, entries: list) -> str:
        endpoints = defaultdict(lambda: {"methods": set(), "statuses": set(), "count": 0})
        for e in entries:
            mime = e.get("response", {}).get("content", {}).get("mimeType", "")
            method = e.get("request", {}).get("method", "")
            if "json" in mime or method in ("POST", "PUT", "PATCH", "DELETE"):
                url = e.get("request", {}).get("url", "")
                parsed = urlparse(url)
                path = re.sub(r'/\d+', '/{id}', parsed.path)
                path = re.sub(r'/[0-9a-f-]{32,}', '/{uuid}', path)
                key = f"{parsed.netloc}{path}"
                endpoints[key]["methods"].add(method)
                endpoints[key]["statuses"].add(e.get("response", {}).get("status", 0))
                endpoints[key]["count"] += 1

        if not endpoints:
            return ""

        lines = [f"## API Surface ({len(endpoints)} endpoints)"]
        for ep, info in sorted(endpoints.items(), key=lambda x: -x[1]["count"])[:35]:
            m = ", ".join(sorted(info["methods"]))
            s = ", ".join(str(x) for x in sorted(info["statuses"]))
            lines.append(f"- [{m}] {ep} — {info['count']}x (statuses: {s})")
        return "\n".join(lines)

    # =========================================================================
    # Section: Redirects
    # =========================================================================

    def _redirects(self, entries: list) -> str:
        redir = []
        for e in entries:
            status = e.get("response", {}).get("status", 0)
            if 300 <= status < 400:
                url = e.get("request", {}).get("url", "")[:100]
                loc = next((h["value"] for h in e.get("response", {}).get("headers", [])
                           if h.get("name", "").lower() == "location"), "?")[:100]
                redir.append(f"- {status}: {url} -> {loc}")
        if not redir:
            return ""
        lines = [f"## Redirects ({len(redir)})"]
        lines.extend(redir[:25])
        return "\n".join(lines)

    # =========================================================================
    # Section: Detailed Entries
    # =========================================================================

    def _detailed_entries(self, entries: list, first_domain: str, priority: set) -> str:
        """Full entry data with headers, cookies, bodies. Priority-sorted."""

        def sort_key(e):
            url = e.get("request", {}).get("url", "")
            domain = urlparse(url).netloc
            status = e.get("response", {}).get("status", 0)
            time_ms = e.get("time", 0) or 0
            mime = e.get("response", {}).get("content", {}).get("mimeType", "")

            score = 0
            if domain in priority: score -= 10000
            if status >= 400: score -= 5000
            if time_ms > self.valves.slow_threshold_ms: score -= 1000
            if any(t in mime for t in ["javascript", "html"]): score -= 500
            if "json" in mime: score -= 300
            return score

        sorted_entries = sorted(entries, key=sort_key)
        limit = min(len(sorted_entries), self.valves.max_entries_detail)

        lines = [f"## Detailed Entries ({limit} of {len(entries)})", ""]

        for i, entry in enumerate(sorted_entries[:limit]):
            req, resp = entry.get("request", {}), entry.get("response", {})
            url = req.get("url", "")
            status = resp.get("status", 0)
            method = req.get("method", "")
            elapsed = entry.get("time", 0) or 0
            timings = entry.get("timings", {})

            lines.append(f"### [{i+1}] {method} {url[:250]}")
            lines.append(f"Status: {status} | Time: {elapsed:.0f}ms")

            if timings:
                parts = [f"{k}={v:.0f}ms" for k, v in timings.items()
                        if isinstance(v, (int, float)) and v > 0]
                if parts:
                    lines.append(f"Timings: {', '.join(parts)}")

            if self.valves.include_all_headers and req.get("headers"):
                lines.append("Request Headers:")
                for h in req["headers"]:
                    lines.append(f"  {h['name']}: {h.get('value', '')[:250]}")

            if self.valves.include_all_headers and resp.get("headers"):
                lines.append("Response Headers:")
                for h in resp["headers"]:
                    lines.append(f"  {h['name']}: {h.get('value', '')[:250]}")

            if self.valves.include_cookies and req.get("cookies"):
                lines.append("Cookies:")
                for c in req["cookies"]:
                    lines.append(f"  {c.get('name', '')}: {c.get('value', '')[:120]}")

            if req.get("queryString"):
                lines.append("Query Params:")
                for p in req["queryString"][:20]:
                    lines.append(f"  {p['name']}: {p.get('value', '')[:200]}")

            post = req.get("postData", {})
            if post.get("text"):
                text = post["text"]
                lines.append(f"POST Body ({post.get('mimeType', '')}, {len(text)} chars):")
                lines.append(f"```\n{text[:3000]}\n```")
            if post.get("params"):
                lines.append("POST Params:")
                for p in post["params"][:20]:
                    lines.append(f"  {p['name']}: {p.get('value', '')[:200]}")

            if self.valves.include_response_bodies:
                content = resp.get("content", {})
                mime = content.get("mimeType", "")
                body = content.get("text", "")
                if body:
                    if any(t in mime for t in ["javascript", "html", "css", "json", "xml", "text"]):
                        lines.append(f"Response Body ({mime}, {len(body)} chars):")
                        lines.append(f"```\n{body[:self.valves.max_body_chars]}\n```")
                        if len(body) > self.valves.max_body_chars:
                            lines.append(f"[Truncated, full: {len(body)} chars]")
                    else:
                        h = hashlib.sha256(body.encode(errors="replace")).hexdigest()[:16]
                        lines.append(f"Response: binary ({mime}, {len(body)}B, hash:{h})")

            lines.append("")

        if limit < len(entries):
            lines.append(f"[{len(entries) - limit} entries omitted]")

        return "\n".join(lines)

    # =========================================================================
    # Helpers
    # =========================================================================

    def _categorize(self, domain: str) -> str:
        d = domain.lower()
        for cat, kws in {
            "Analytics": ["analytics", "mixpanel", "segment", "hotjar", "heap", "plausible"],
            "Ads": ["doubleclick", "googlesyndication", "adsense", "adnxs", "criteo", "taboola"],
            "CDN": ["cloudflare", "cdn", "akamai", "fastly", "cloudfront", "jsdelivr"],
            "Fonts": ["fonts.googleapis", "fonts.gstatic", "typekit", "fontawesome"],
            "Social": ["facebook", "twitter", "linkedin", "tiktok"],
            "Video": ["youtube", "vimeo", "twitch"],
            "Auth": ["auth0", "okta", "cognito", "firebase"],
            "Chat": ["intercom", "zendesk", "drift", "crisp"],
        }.items():
            if any(k in d for k in kws):
                return cat
        return "Other"
