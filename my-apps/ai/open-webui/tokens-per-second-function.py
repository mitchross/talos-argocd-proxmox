"""
title: Tokens Per Second
author: vanillax
version: 1.0.0
description: Injects response_token/s + prompt_token/s into streamed usage stats (vLLM sends only token counts).
"""

import time

from pydantic import BaseModel, Field


class Filter:
    class Valves(BaseModel):
        priority: int = Field(default=0, description="Filter processing order")

    def __init__(self):
        self.valves = self.Valves()
        self._t_start = {}  # message_id -> inlet (request start) time
        self._t_first = {}  # message_id -> first stream chunk time

    def _prune(self, now):
        # Aborted/errored streams never hit the usage chunk; drop stale entries.
        for d in (self._t_start, self._t_first):
            for k in [k for k, t in d.items() if now - t > 3600]:
                d.pop(k, None)

    def inlet(self, body: dict, __metadata__=None) -> dict:
        now = time.time()
        self._prune(now)
        mid = (__metadata__ or {}).get("message_id")
        if mid:
            self._t_start[mid] = now
            self._t_first.pop(mid, None)
        return body

    def stream(self, event: dict, __metadata__=None) -> dict:
        if not isinstance(event, dict):
            return event
        now = time.time()
        mid = (__metadata__ or {}).get("message_id") or event.get("id")
        if mid and mid not in self._t_first:
            self._t_first[mid] = now

        usage = event.get("usage")
        completion = (usage or {}).get("completion_tokens") or 0
        if usage and completion:
            t_first = self._t_first.pop(mid, None)
            t_start = self._t_start.get(mid)
            # first chunk arrives after prefill, so first->last spans the decode phase
            if t_first and now > t_first:
                usage["response_token/s"] = round(completion / (now - t_first), 2)
            prompt = usage.get("prompt_tokens") or 0
            if prompt and t_start and t_first and t_first > t_start:
                usage["prompt_token/s"] = round(prompt / (t_first - t_start), 2)
            if t_start:
                s = int(now - t_start)
                usage["approximate_total"] = f"{s // 3600}h{(s % 3600) // 60}m{s % 60}s"
        return event
