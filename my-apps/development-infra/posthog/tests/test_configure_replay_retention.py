"""Check reconciliation boundaries without connecting to a live database."""

import contextlib
import importlib.util
import io
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/configure-replay-retention.py"
spec = importlib.util.spec_from_file_location("configure_retention", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Team:
    def __init__(self, retention, min_duration=None):
        self.session_recording_retention_period = retention
        self.session_recording_minimum_duration_milliseconds = min_duration
        self.saved_fields = []

    def save(self, *, update_fields):
        self.saved_fields.append(update_fields)


class Manager:
    def __init__(self, teams):
        self.teams = teams

    def select_for_update(self):
        return self

    def filter(self, *, pk):
        return types.SimpleNamespace(first=lambda: self.teams.get(pk))


class ConfigureReplayRetentionTests(unittest.TestCase):
    def reconcile(self, teams, *, cloud=False, dry_run=False, ids="1", min_duration=None):
        modules = {
            "django": types.SimpleNamespace(setup=lambda: None),
            "django.db": types.SimpleNamespace(transaction=types.SimpleNamespace(atomic=contextlib.nullcontext)),
            "posthog.cloud_utils": types.SimpleNamespace(is_cloud=lambda: cloud),
            "posthog.models": types.SimpleNamespace(Team=types.SimpleNamespace(objects=Manager(teams))),
        }
        with (
            patch.dict(sys.modules, modules),
            patch.dict(os.environ, {"SELF_HOSTED_REPLAY_RETENTION_TEAM_IDS": ids,
                                    "SELF_HOSTED_REPLAY_MIN_DURATION_MS": min_duration or ""}),
            patch.object(sys, "path", list(sys.path)),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            module.configure_retention(dry_run=dry_run)

    def test_only_declared_project_retention_is_saved(self):
        teams = {1: Team("5y"), 2: Team("90d")}
        self.reconcile(teams)
        self.assertEqual(teams[1].session_recording_retention_period, "30d")
        self.assertEqual(teams[1].saved_fields, [["session_recording_retention_period"]])
        self.assertEqual(teams[2].session_recording_retention_period, "90d")
        self.assertEqual(teams[2].saved_fields, [])

    def test_already_reconciled_project_is_not_saved_again(self):
        teams = {1: Team("30d")}
        self.reconcile(teams)
        self.assertEqual(teams[1].saved_fields, [])

    def test_fresh_database_does_not_block_onboarding(self):
        self.reconcile({})

    def test_dry_run_preserves_retention(self):
        teams = {1: Team("5y")}
        self.reconcile(teams, dry_run=True)
        self.assertEqual(teams[1].session_recording_retention_period, "5y")
        self.assertEqual(teams[1].saved_fields, [])

    def test_cloud_is_rejected_before_retention_changes(self):
        teams = {1: Team("5y")}
        with self.assertRaisesRegex(RuntimeError, "self-hosted"):
            self.reconcile(teams, cloud=True)
        self.assertEqual(teams[1].saved_fields, [])

    def test_min_duration_is_left_alone_when_undeclared(self):
        teams = {1: Team("30d", 5000)}
        self.reconcile(teams)
        self.assertEqual(teams[1].session_recording_minimum_duration_milliseconds, 5000)
        self.assertEqual(teams[1].saved_fields, [])

    def test_declared_min_duration_is_saved_with_only_changed_fields(self):
        teams = {1: Team("30d"), 2: Team("5y")}
        self.reconcile(teams, ids="1,2", min_duration="2000")
        self.assertEqual(teams[1].session_recording_minimum_duration_milliseconds, 2000)
        self.assertEqual(teams[1].saved_fields, [["session_recording_minimum_duration_milliseconds"]])
        self.assertEqual(teams[2].saved_fields,
                         [["session_recording_retention_period", "session_recording_minimum_duration_milliseconds"]])

    def test_matching_min_duration_is_not_saved_again(self):
        teams = {1: Team("30d", 2000)}
        self.reconcile(teams, min_duration="2000")
        self.assertEqual(teams[1].saved_fields, [])

    def test_zero_min_duration_clears_to_null(self):
        teams = {1: Team("30d", 5000)}
        self.reconcile(teams, min_duration="0")
        self.assertIsNone(teams[1].session_recording_minimum_duration_milliseconds)

    def test_negative_min_duration_is_rejected_before_saving(self):
        teams = {1: Team("5y")}
        with self.assertRaisesRegex(ValueError, ">= 0"):
            self.reconcile(teams, min_duration="-1")
        self.assertEqual(teams[1].saved_fields, [])


if __name__ == "__main__":
    unittest.main()
