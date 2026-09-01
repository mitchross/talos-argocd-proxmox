#!/usr/bin/env python3
import sys
import os
import asyncio

sys.path.insert(0, "/app/backend")
os.environ.setdefault("DATA_DIR", "/app/backend/data")

FUNCTIONS = [
    {
        "id": "har_forensics_analyzer",
        "name": "HAR Forensics Analyzer",
        "path": "/functions/har-analyzer-function.py",
        "description": "Filter: preprocesses uploaded .har files into forensic reports for LLM analysis",
    },
    {
        "id": "tokens_per_second",
        "name": "Tokens Per Second",
        "path": "/functions/tokens-per-second-function.py",
        "description": "Filter: injects response_token/s + prompt_token/s into streamed usage stats",
    },
    {
        "id": "qwen_non_thinking_default",
        "name": "Qwen3.8 Non-Thinking Default",
        "path": "/functions/qwen-no-think-filter.py",
        "description": "Filter: forces qwen3.8-27b requests to use enable_thinking=false",
    },
]

from open_webui.models.functions import Functions, FunctionForm, FunctionMeta
from open_webui.models.users import Users


def _maybe_await(value):
    """Await `value` if it is a coroutine, else return as-is.
    Open-WebUI converted these ORM methods from sync to async; this
    keeps the script working across both shapes."""
    import inspect
    if inspect.iscoroutine(value):
        return value
    async def _wrap():
        return value
    return _wrap()


def _extract_users_list(users_data):
    """get_users() may return a dict {"users": [...]}, a list, or a
    Pydantic model with a `.users` attribute. Normalize all three."""
    if users_data is None:
        return []
    if isinstance(users_data, dict) and "users" in users_data:
        return users_data["users"]
    if isinstance(users_data, list):
        return users_data
    if hasattr(users_data, "users"):
        return users_data.users
    return []


async def load_function(admin_id, spec):
    with open(spec["path"]) as f:
        code = f.read()

    existing = await _maybe_await(Functions.get_function_by_id(spec["id"]))

    if existing:
        result = await _maybe_await(
            Functions.update_function_by_id(
                spec["id"],
                {
                    "name": spec["name"],
                    "type": "filter",
                    "content": code,
                    "meta": {"description": spec["description"]},
                    "is_active": True,
                    "is_global": True,
                },
            )
        )
        if result is None:
            print(f"ERROR: Failed to update function {spec['id']}")
            sys.exit(1)
        print(f"Updated function: {result.id}")
    else:
        form = FunctionForm(
            id=spec["id"],
            name=spec["name"],
            type="filter",
            content=code,
            meta=FunctionMeta(description=spec["description"]),
        )
        result = await _maybe_await(
            Functions.insert_new_function(admin_id, "filter", form)
        )
        if result is None:
            print(f"ERROR: Failed to create function {spec['id']}")
            sys.exit(1)
        await _maybe_await(
            Functions.update_function_by_id(
                spec["id"], {"is_active": True, "is_global": True}
            )
        )
        print(f"Created function: {result.id}")

    # Re-read to confirm the active/global flags actually stuck.
    final = await _maybe_await(Functions.get_function_by_id(spec["id"]))
    if final is not None:
        print(
            f"{spec['id']} Active: {getattr(final, 'is_active', '?')}, "
            f"Global: {getattr(final, 'is_global', '?')}"
        )


async def main():
    # Find first admin user
    users_data = await _maybe_await(Users.get_users())
    admin_id = None
    for u in _extract_users_list(users_data):
        if getattr(u, "role", None) == "admin":
            admin_id = u.id
            break

    if not admin_id:
        print("WARNING: No admin user found, using placeholder ID")
        admin_id = "system"

    for spec in FUNCTIONS:
        await load_function(admin_id, spec)

    print("Done!")


asyncio.run(main())

