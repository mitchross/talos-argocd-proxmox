"""Run against the deployed Hindsight plugin and its upstream fake-client fixtures."""

import json
from pathlib import Path

import yaml
from conftest import FakeClient


ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "config/hindsight-hermes.json").read_text())


def test_fresh_chat_recalls_current_project_before_any_tool(provider):
    instance, client = provider(CONFIG, client=FakeClient(recall_texts=["Radar NG replay PR needs review"]))
    try:
        block = instance.prefetch("What is unfinished in Radar NG?", session_id="fresh")
        assert "Radar NG replay PR needs review" in block
        assert client.recalls[0]["query"] == "What is unfinished in Radar NG?"
        assert instance.recall_status().count == 1
        assert client.retains == []
    finally:
        instance.shutdown()


def test_project_switch_uses_current_query_and_preserves_server_order(provider):
    instance, client = provider(CONFIG, client=FakeClient(recall_texts=["rank one", "rank two"]))
    try:
        instance.prefetch("What is unfinished in Radar NG?")
        instance.queue_prefetch("What is unfinished in Radar NG?")
        block = instance.prefetch("What is unfinished in ProxCenter?")
        assert [call["query"] for call in client.recalls] == [
            "What is unfinished in Radar NG?", "What is unfinished in ProxCenter?"
        ]
        assert block.index("rank one") < block.index("rank two")
        assert client.recalls[0]["types"] == ["observation", "world", "experience"]
        assert client.recalls[0]["budget"] == "mid"
    finally:
        instance.shutdown()


def test_empty_recall_does_not_inject_old_project_context(provider):
    instance, client = provider(CONFIG, client=FakeClient(recall_texts=["Radar NG history"]))
    try:
        assert "Radar NG history" in instance.prefetch("Radar NG history")
        client._recall_texts = []
        assert instance.prefetch("Unrelated project") == ""
        assert instance.recall_status() is None
    finally:
        instance.shutdown()


def test_outer_deadline_exceeds_the_plugin_api_deadline():
    memory = yaml.safe_load((ROOT / "config/config.yaml").read_text())["memory"]
    assert memory["external_prefetch_timeout"] > CONFIG["timeout"]


def test_default_async_mode_reproduces_the_missing_first_turn(provider):
    original = {key: value for key, value in CONFIG.items() if key != "recall_sync"}
    instance, client = provider(original, client=FakeClient(recall_texts=["Radar NG history"]))
    try:
        assert instance.prefetch("Radar NG history") == ""
        assert client.recalls == []
    finally:
        instance.shutdown()
