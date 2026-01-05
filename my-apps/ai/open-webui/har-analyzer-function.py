"""
title: HAR File Analyzer (Full)
author: Claude
version: 2.0.0
description: Comprehensive HAR analyzer - WebSockets, WebRTC, caching, security, performance, third-party, and more.
requirements:
"""

import json
import re
from typing import Optional, Dict, List, Any
from pydantic import BaseModel, Field
from urllib.parse import urlparse


class Tools:
    class Valves(BaseModel):
        max_slow_requests: int = Field(default=20, description="Maximum slow requests to show")
        max_errors: int = Field(default=30, description="Maximum errors to show")
        max_websocket_messages: int = Field(default=20, description="Maximum WebSocket messages to show")
        slow_threshold_ms: int = Field(default=1000, description="Threshold for 'slow' requests (ms)")
        large_response_kb: int = Field(default=500, description="Threshold for 'large' responses (KB)")

    def __init__(self):
        self.valves = self.Valves()

    def analyze_har(self, har_content: str) -> str:
        """
        Comprehensive HAR file analysis including WebSockets, WebRTC, caching, security, and performance.

        :param har_content: The raw JSON content of a HAR file
        :return: A detailed structured analysis report
        """
        try:
            har = json.loads(har_content)
        except json.JSONDecodeError as e:
            return f"Error parsing HAR file: {e}"

        entries = har.get("log", {}).get("entries", [])
        if not entries:
            return "No entries found in HAR file"

        # Initialize collectors
        analysis = {
            "total_requests": len(entries),
            "total_time": 0,
            "total_size": 0,
            "errors": [],
            "slow_requests": [],
            "large_responses": [],
            "redirects": [],
            "websockets": [],
            "webrtc": [],
            "domains": {},
            "status_codes": {},
            "content_types": {},
            "methods": {},
            "caching_issues": [],
            "security_issues": [],
            "third_party": [],
            "cors_issues": [],
            "compression": {"compressed": 0, "uncompressed": 0, "savings": 0},
            "cookies": {"sent": 0, "received": 0, "insecure": []},
            "timing_breakdown": {"blocked": 0, "dns": 0, "connect": 0, "ssl": 0, "send": 0, "wait": 0, "receive": 0},
            "protocols": {},
            "initiators": {},
        }

        # Detect first-party domain from first request
        first_party_domain = ""
        if entries:
            first_url = entries[0].get("request", {}).get("url", "")
            try:
                first_party_domain = urlparse(first_url).netloc
            except:
                pass

        for entry in entries:
            self._analyze_entry(entry, analysis, first_party_domain)

        return self._build_report(analysis, first_party_domain)

    def _analyze_entry(self, entry: Dict, analysis: Dict, first_party_domain: str):
        """Analyze a single HAR entry."""
        request = entry.get("request", {})
        response = entry.get("response", {})
        timings = entry.get("timings", {})

        url = request.get("url", "")
        method = request.get("method", "")
        status = response.get("status", 0)
        time_ms = entry.get("time", 0) or 0

        # Response size
        content = response.get("content", {})
        response_size = content.get("size", 0) or 0

        # Parse URL
        try:
            parsed = urlparse(url)
            domain = parsed.netloc
            path = parsed.path
            scheme = parsed.scheme
        except:
            domain = "unknown"
            path = url
            scheme = ""

        # Track totals
        analysis["total_time"] += time_ms
        analysis["total_size"] += response_size

        # Track methods
        analysis["methods"][method] = analysis["methods"].get(method, 0) + 1

        # Track status codes
        analysis["status_codes"][status] = analysis["status_codes"].get(status, 0) + 1

        # Track content types
        mime_type = content.get("mimeType", "unknown")
        base_mime = mime_type.split(";")[0].strip()
        analysis["content_types"][base_mime] = analysis["content_types"].get(base_mime, 0) + 1

        # Track protocols (HTTP/1.1, HTTP/2, etc.)
        http_version = response.get("httpVersion", "unknown")
        analysis["protocols"][http_version] = analysis["protocols"].get(http_version, 0) + 1

        # Track domains
        if domain not in analysis["domains"]:
            analysis["domains"][domain] = {
                "count": 0, "total_time": 0, "total_size": 0, "errors": 0,
                "is_third_party": domain != first_party_domain and first_party_domain != ""
            }
        analysis["domains"][domain]["count"] += 1
        analysis["domains"][domain]["total_time"] += time_ms
        analysis["domains"][domain]["total_size"] += response_size

        # Track timing breakdown
        for key in ["blocked", "dns", "connect", "ssl", "send", "wait", "receive"]:
            val = timings.get(key, 0)
            if val and val > 0:
                analysis["timing_breakdown"][key] += val

        # Get headers as dict for easier lookup
        req_headers = {h.get("name", "").lower(): h.get("value", "") for h in request.get("headers", [])}
        res_headers = {h.get("name", "").lower(): h.get("value", "") for h in response.get("headers", [])}

        # === WebSocket Detection ===
        if scheme in ["ws", "wss"] or res_headers.get("upgrade", "").lower() == "websocket":
            ws_entry = {
                "url": url[:150],
                "status": status,
                "messages": [],
            }
            # WebSocket messages in HAR
            ws_messages = entry.get("_webSocketMessages", [])
            for msg in ws_messages[:self.valves.max_websocket_messages]:
                ws_entry["messages"].append({
                    "type": msg.get("type", ""),
                    "time": msg.get("time", ""),
                    "data": str(msg.get("data", ""))[:200]
                })
            analysis["websockets"].append(ws_entry)

        # === WebRTC Detection ===
        webrtc_patterns = [
            r"stun:", r"turn:", r"\.twilio\.com", r"\.xirsys\.com",
            r"webrtc", r"rtc\.", r"\.peerjs\.", r"signaling",
            r"ice.*candidate", r"sdp", r"peer.*connection"
        ]
        is_webrtc = any(re.search(p, url.lower()) for p in webrtc_patterns)
        is_webrtc = is_webrtc or "application/sdp" in mime_type.lower()

        if is_webrtc:
            analysis["webrtc"].append({
                "url": url[:150],
                "type": self._detect_webrtc_type(url, mime_type),
                "method": method,
                "status": status,
                "time_ms": round(time_ms, 2)
            })

        # === Errors (4xx, 5xx) ===
        if status >= 400:
            analysis["domains"][domain]["errors"] += 1
            analysis["errors"].append({
                "url": url[:150],
                "method": method,
                "status": status,
                "status_text": response.get("statusText", ""),
                "time_ms": round(time_ms, 2),
                "content_type": base_mime
            })

        # === Slow Requests ===
        if time_ms > self.valves.slow_threshold_ms:
            analysis["slow_requests"].append({
                "url": url[:150],
                "method": method,
                "time_ms": round(time_ms, 2),
                "wait_ms": round(timings.get("wait", 0) or 0, 2),
                "status": status,
                "size_kb": round(response_size / 1024, 2),
                "timings": {k: round(v, 2) if v and v > 0 else 0 for k, v in timings.items()}
            })

        # === Large Responses ===
        if response_size > self.valves.large_response_kb * 1024:
            analysis["large_responses"].append({
                "url": url[:150],
                "size_kb": round(response_size / 1024, 2),
                "content_type": base_mime,
                "compressed": "content-encoding" in res_headers
            })

        # === Redirects ===
        if 300 <= status < 400:
            location = res_headers.get("location", "")
            analysis["redirects"].append({
                "from": url[:100],
                "to": location[:100],
                "status": status
            })

        # === Caching Analysis ===
        self._analyze_caching(url, path, base_mime, res_headers, analysis)

        # === Security Analysis ===
        self._analyze_security(url, domain, scheme, req_headers, res_headers, analysis)

        # === Compression Analysis ===
        content_encoding = res_headers.get("content-encoding", "")
        if content_encoding in ["gzip", "br", "deflate"]:
            analysis["compression"]["compressed"] += 1
            original_size = content.get("size", 0) or 0
            compressed_size = response.get("bodySize", 0) or 0
            if original_size > compressed_size > 0:
                analysis["compression"]["savings"] += (original_size - compressed_size)
        elif response_size > 1024 and base_mime in ["text/html", "text/css", "text/javascript", "application/javascript", "application/json"]:
            analysis["compression"]["uncompressed"] += 1

        # === Cookie Analysis ===
        req_cookies = request.get("cookies", [])
        res_cookies = response.get("cookies", [])
        analysis["cookies"]["sent"] += len(req_cookies)
        analysis["cookies"]["received"] += len(res_cookies)

        for cookie in res_cookies:
            if not cookie.get("secure", False) and scheme == "https":
                analysis["cookies"]["insecure"].append({
                    "name": cookie.get("name", "")[:30],
                    "domain": domain
                })

        # === Third-Party Detection ===
        if domain != first_party_domain and first_party_domain:
            if not any(tp["domain"] == domain for tp in analysis["third_party"]):
                analysis["third_party"].append({
                    "domain": domain,
                    "type": self._categorize_third_party(domain, url)
                })

        # === CORS Issues ===
        origin = req_headers.get("origin", "")
        acao = res_headers.get("access-control-allow-origin", "")
        if origin and not acao and status >= 200 and status < 300:
            analysis["cors_issues"].append({
                "url": url[:100],
                "origin": origin,
                "status": status
            })

        # === Initiator Tracking ===
        initiator = entry.get("_initiator", {}).get("type", "other")
        analysis["initiators"][initiator] = analysis["initiators"].get(initiator, 0) + 1

    def _detect_webrtc_type(self, url: str, mime_type: str) -> str:
        """Categorize WebRTC request type."""
        url_lower = url.lower()
        if "stun:" in url_lower or "stun." in url_lower:
            return "STUN"
        elif "turn:" in url_lower or "turn." in url_lower:
            return "TURN"
        elif "signaling" in url_lower or "signal" in url_lower:
            return "Signaling"
        elif "sdp" in url_lower or "application/sdp" in mime_type:
            return "SDP"
        elif "ice" in url_lower:
            return "ICE"
        return "WebRTC"

    def _categorize_third_party(self, domain: str, url: str) -> str:
        """Categorize third-party by type."""
        domain_lower = domain.lower()

        # Analytics
        if any(x in domain_lower for x in ["google-analytics", "analytics", "mixpanel", "segment", "hotjar", "heap"]):
            return "Analytics"
        # Ads
        if any(x in domain_lower for x in ["doubleclick", "googlesyndication", "adsense", "adnxs", "criteo", "facebook.com/tr"]):
            return "Advertising"
        # CDN
        if any(x in domain_lower for x in ["cloudflare", "cdn", "akamai", "fastly", "cloudfront", "jsdelivr", "unpkg"]):
            return "CDN"
        # Fonts
        if any(x in domain_lower for x in ["fonts.googleapis", "fonts.gstatic", "typekit", "fontawesome"]):
            return "Fonts"
        # Social
        if any(x in domain_lower for x in ["facebook", "twitter", "linkedin", "instagram"]):
            return "Social"
        # Video/Media
        if any(x in domain_lower for x in ["youtube", "vimeo", "twitch", "wistia"]):
            return "Video"
        # Chat/Support
        if any(x in domain_lower for x in ["intercom", "zendesk", "drift", "crisp", "tawk"]):
            return "Chat/Support"

        return "Other"

    def _analyze_caching(self, url: str, path: str, mime_type: str, headers: Dict, analysis: Dict):
        """Analyze caching headers and issues."""
        cache_control = headers.get("cache-control", "")
        etag = headers.get("etag", "")
        last_modified = headers.get("last-modified", "")
        expires = headers.get("expires", "")

        # Static assets that should be cached
        static_extensions = [".js", ".css", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".woff", ".woff2", ".ttf", ".ico"]
        is_static = any(path.lower().endswith(ext) for ext in static_extensions)
        is_static = is_static or mime_type in ["text/css", "application/javascript", "image/png", "image/jpeg", "font/woff2"]

        if is_static:
            issues = []

            if not cache_control and not expires:
                issues.append("No caching headers")
            elif "no-cache" in cache_control or "no-store" in cache_control:
                issues.append("Caching disabled")
            elif "max-age=" in cache_control:
                # Extract max-age
                match = re.search(r"max-age=(\d+)", cache_control)
                if match:
                    max_age = int(match.group(1))
                    if max_age < 86400:  # Less than 1 day
                        issues.append(f"Short max-age ({max_age}s)")

            if not etag and not last_modified:
                issues.append("No validation headers (ETag/Last-Modified)")

            if issues:
                analysis["caching_issues"].append({
                    "url": url[:100],
                    "type": mime_type,
                    "issues": issues,
                    "cache_control": cache_control[:50] if cache_control else "none"
                })

    def _analyze_security(self, url: str, domain: str, scheme: str, req_headers: Dict, res_headers: Dict, analysis: Dict):
        """Analyze security headers and issues."""
        issues = []

        # Mixed content (HTTP on HTTPS page)
        if scheme == "http":
            # Check if it's a sensitive resource
            issues.append("HTTP (not HTTPS)")

        # Missing security headers on HTML responses
        if "text/html" in res_headers.get("content-type", ""):
            security_headers = {
                "strict-transport-security": "Missing HSTS",
                "x-content-type-options": "Missing X-Content-Type-Options",
                "x-frame-options": "Missing X-Frame-Options",
                "content-security-policy": "Missing CSP",
            }
            for header, message in security_headers.items():
                if header not in res_headers:
                    issues.append(message)

        # CORS wildcard
        acao = res_headers.get("access-control-allow-origin", "")
        if acao == "*":
            issues.append("CORS allows all origins (*)")

        if issues and len(analysis["security_issues"]) < 20:
            analysis["security_issues"].append({
                "url": url[:80],
                "domain": domain,
                "issues": issues[:3]
            })

    def _build_report(self, analysis: Dict, first_party_domain: str) -> str:
        """Build the final report string."""
        report = []

        # === SUMMARY ===
        report.append("# HAR Analysis Report\n")
        report.append("## Summary")
        report.append(f"- **Total Requests:** {analysis['total_requests']}")
        report.append(f"- **Total Load Time:** {round(analysis['total_time'] / 1000, 2)}s")
        report.append(f"- **Total Data Transferred:** {self._format_size(analysis['total_size'])}")
        report.append(f"- **First-Party Domain:** {first_party_domain}")
        report.append(f"- **Third-Party Domains:** {len(analysis['third_party'])}")
        report.append(f"- **Errors (4xx/5xx):** {len(analysis['errors'])}")
        report.append(f"- **WebSocket Connections:** {len(analysis['websockets'])}")
        report.append(f"- **WebRTC Requests:** {len(analysis['webrtc'])}")
        report.append("")

        # === STATUS CODES ===
        report.append("## Status Code Distribution")
        for code, count in sorted(analysis["status_codes"].items()):
            pct = round(count / analysis["total_requests"] * 100, 1)
            emoji = self._status_emoji(code)
            report.append(f"- {emoji} **{code}:** {count} ({pct}%)")
        report.append("")

        # === CONTENT TYPES ===
        report.append("## Content Types")
        sorted_types = sorted(analysis["content_types"].items(), key=lambda x: x[1], reverse=True)[:10]
        for ctype, count in sorted_types:
            report.append(f"- **{ctype}:** {count}")
        report.append("")

        # === TIMING BREAKDOWN ===
        report.append("## Timing Breakdown (Total)")
        total_timing = sum(analysis["timing_breakdown"].values())
        if total_timing > 0:
            for phase, ms in analysis["timing_breakdown"].items():
                if ms > 0:
                    pct = round(ms / total_timing * 100, 1)
                    report.append(f"- **{phase.capitalize()}:** {round(ms, 0)}ms ({pct}%)")
        report.append("")

        # === DOMAINS ===
        report.append("## Top Domains by Load Time")
        report.append("| Domain | Requests | Time | Size | Errors | Type |")
        report.append("|--------|----------|------|------|--------|------|")
        sorted_domains = sorted(analysis["domains"].items(), key=lambda x: x[1]["total_time"], reverse=True)[:15]
        for domain, stats in sorted_domains:
            dtype = "3rd Party" if stats["is_third_party"] else "1st Party"
            report.append(f"| {domain[:35]} | {stats['count']} | {round(stats['total_time']/1000, 2)}s | {self._format_size(stats['total_size'])} | {stats['errors']} | {dtype} |")
        report.append("")

        # === WEBSOCKETS ===
        if analysis["websockets"]:
            report.append("## WebSocket Connections")
            for i, ws in enumerate(analysis["websockets"][:10], 1):
                report.append(f"\n### WS {i}: {ws['url']}")
                report.append(f"- **Status:** {ws['status']}")
                report.append(f"- **Messages:** {len(ws['messages'])}")
                if ws["messages"]:
                    report.append("- **Sample Messages:**")
                    for msg in ws["messages"][:5]:
                        report.append(f"  - [{msg['type']}] {msg['data'][:80]}...")
            report.append("")

        # === WEBRTC ===
        if analysis["webrtc"]:
            report.append("## WebRTC Activity")
            report.append("| Type | URL | Method | Status | Time |")
            report.append("|------|-----|--------|--------|------|")
            for rtc in analysis["webrtc"][:15]:
                report.append(f"| {rtc['type']} | {rtc['url'][:50]} | {rtc['method']} | {rtc['status']} | {rtc['time_ms']}ms |")
            report.append("")

        # === SLOW REQUESTS ===
        if analysis["slow_requests"]:
            report.append(f"## Slowest Requests (>{self.valves.slow_threshold_ms}ms)")
            sorted_slow = sorted(analysis["slow_requests"], key=lambda x: x["time_ms"], reverse=True)[:self.valves.max_slow_requests]
            for i, req in enumerate(sorted_slow, 1):
                report.append(f"\n### {i}. {req['method']} {req['url']}")
                report.append(f"- **Total:** {req['time_ms']}ms | **TTFB (wait):** {req['wait_ms']}ms | **Size:** {req['size_kb']}KB")

                # Identify bottleneck
                timings = req["timings"]
                if timings.get("wait", 0) > req["time_ms"] * 0.5:
                    report.append(f"- **Bottleneck:** Server processing (wait={timings['wait']}ms)")
                elif timings.get("dns", 0) > 100:
                    report.append(f"- **Bottleneck:** DNS lookup ({timings['dns']}ms)")
                elif timings.get("ssl", 0) > 200:
                    report.append(f"- **Bottleneck:** SSL handshake ({timings['ssl']}ms)")
                elif timings.get("receive", 0) > req["time_ms"] * 0.4:
                    report.append(f"- **Bottleneck:** Download time ({timings['receive']}ms)")
            report.append("")

        # === ERRORS ===
        if analysis["errors"]:
            report.append("## Errors")
            report.append("| Status | Method | URL | Time |")
            report.append("|--------|--------|-----|------|")
            for err in analysis["errors"][:self.valves.max_errors]:
                report.append(f"| {err['status']} {err['status_text'][:15]} | {err['method']} | {err['url'][:60]} | {err['time_ms']}ms |")
            report.append("")

        # === LARGE RESPONSES ===
        if analysis["large_responses"]:
            report.append(f"## Large Responses (>{self.valves.large_response_kb}KB)")
            report.append("| Size | Type | Compressed | URL |")
            report.append("|------|------|------------|-----|")
            sorted_large = sorted(analysis["large_responses"], key=lambda x: x["size_kb"], reverse=True)[:15]
            for resp in sorted_large:
                compressed = "Yes" if resp["compressed"] else "No"
                report.append(f"| {resp['size_kb']}KB | {resp['content_type'][:20]} | {compressed} | {resp['url'][:50]} |")
            report.append("")

        # === CACHING ISSUES ===
        if analysis["caching_issues"]:
            report.append("## Caching Issues")
            for issue in analysis["caching_issues"][:15]:
                report.append(f"- **{issue['url']}**")
                report.append(f"  - Issues: {', '.join(issue['issues'])}")
            report.append("")

        # === SECURITY ISSUES ===
        if analysis["security_issues"]:
            report.append("## Security Issues")
            for issue in analysis["security_issues"][:15]:
                report.append(f"- **{issue['domain']}** - {', '.join(issue['issues'])}")
            report.append("")

        # === THIRD PARTY ===
        if analysis["third_party"]:
            report.append("## Third-Party Services")
            by_type = {}
            for tp in analysis["third_party"]:
                t = tp["type"]
                if t not in by_type:
                    by_type[t] = []
                by_type[t].append(tp["domain"])

            for t, domains in sorted(by_type.items()):
                report.append(f"\n### {t}")
                for d in domains[:10]:
                    report.append(f"- {d}")
            report.append("")

        # === COMPRESSION ===
        report.append("## Compression")
        report.append(f"- **Compressed Responses:** {analysis['compression']['compressed']}")
        report.append(f"- **Uncompressed (should compress):** {analysis['compression']['uncompressed']}")
        report.append(f"- **Compression Savings:** {self._format_size(analysis['compression']['savings'])}")
        report.append("")

        # === REDIRECTS ===
        if analysis["redirects"]:
            report.append("## Redirects")
            for r in analysis["redirects"][:10]:
                report.append(f"- **{r['status']}** {r['from']} -> {r['to']}")
            report.append("")

        # === COOKIES ===
        report.append("## Cookies")
        report.append(f"- **Cookies Sent:** {analysis['cookies']['sent']}")
        report.append(f"- **Cookies Received:** {analysis['cookies']['received']}")
        if analysis["cookies"]["insecure"]:
            report.append(f"- **Insecure Cookies:** {len(analysis['cookies']['insecure'])}")
            for c in analysis["cookies"]["insecure"][:5]:
                report.append(f"  - {c['name']} ({c['domain']})")
        report.append("")

        # === PROTOCOLS ===
        report.append("## HTTP Protocols")
        for proto, count in sorted(analysis["protocols"].items(), key=lambda x: x[1], reverse=True):
            report.append(f"- **{proto}:** {count}")

        return "\n".join(report)

    def _format_size(self, bytes_size: int) -> str:
        """Format bytes to human readable."""
        if bytes_size < 1024:
            return f"{bytes_size}B"
        elif bytes_size < 1024 * 1024:
            return f"{round(bytes_size / 1024, 1)}KB"
        else:
            return f"{round(bytes_size / (1024 * 1024), 2)}MB"

    def _status_emoji(self, code: int) -> str:
        """Return emoji for status code."""
        if code < 300:
            return "✅"
        elif code < 400:
            return "↪️"
        elif code < 500:
            return "⚠️"
        else:
            return "❌"
