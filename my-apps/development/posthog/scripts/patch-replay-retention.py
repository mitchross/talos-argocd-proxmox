"""Allow the free 30-day replay setting when hobby deployments lack billing metadata."""

import ast
import hashlib
from pathlib import Path

# Method from PostHog 065179102ef87898ef952381080b55c453e7867d; review on upgrades.
UPSTREAM_METHOD_SHA256 = "98bda8d22670d028428be0ee2d3767bbbe31c526165a1ac60709e7541d988cce"
ANCHOR = "        highest_retention_entitlement = parse_feature_to_entitlement(retention_feature)\n"
FALLBACK = (
    "        from posthog.cloud_utils import is_cloud\n"
    "\n"
    "        if retention_feature is None and new_retention_period == '30d' and not is_cloud():\n"
    "            return\n"
    "\n"
)


def patch_source(source):
    tree = ast.parse(source)
    methods = [
        node
        for cls in tree.body
        if isinstance(cls, ast.ClassDef) and cls.name == "TeamSerializer"
        for node in cls.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_verify_update_session_recording_retention_period"
    ]
    if len(methods) != 1:
        raise RuntimeError("PostHog retention validator changed; review compatibility patch")
    method = ast.get_source_segment(source, methods[0])
    original = method.replace(FALLBACK, "", 1)
    if hashlib.sha256(original.encode()).hexdigest() != UPSTREAM_METHOD_SHA256:
        raise RuntimeError("PostHog retention validator changed; review compatibility patch")
    if FALLBACK in method:
        return source
    if method.count(ANCHOR) != 1:
        raise RuntimeError("PostHog retention anchor changed; review compatibility patch")
    patched = method.replace(ANCHOR, FALLBACK + ANCHOR, 1)
    return source.replace(method, patched, 1)


if __name__ == "__main__":
    path = Path("/code/posthog/api/team.py")
    original = path.read_text()
    patched = patch_source(original)
    if patched != original:
        path.write_text(patched)
    print("Self-hosted 30-day replay retention compatibility check passed")
