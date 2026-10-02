"""Reconcile the declared replay settings (retention, minimum duration) through PostHog's Team model."""

import argparse
import os
import sys


def desired_settings():
    settings = {"session_recording_retention_period": "30d"}
    min_duration = os.environ.get("SELF_HOSTED_REPLAY_MIN_DURATION_MS", "").strip()
    if min_duration:
        value = int(min_duration)
        if value < 0:
            raise ValueError("SELF_HOSTED_REPLAY_MIN_DURATION_MS must be >= 0")
        # PostHog stores "no minimum" as NULL, not 0.
        settings["session_recording_minimum_duration_milliseconds"] = value or None
    return settings


def configure_retention(*, dry_run=False):
    # ConfigMap scripts live outside the image's /code Python package root.
    sys.path.insert(0, "/code")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "posthog.settings")
    import django

    django.setup()

    from django.db import transaction

    from posthog.cloud_utils import is_cloud
    from posthog.models import Team

    if is_cloud():
        raise RuntimeError("Replay retention reconciliation is for self-hosted PostHog only")

    settings = desired_settings()
    team_ids = [int(value) for value in os.environ["SELF_HOSTED_REPLAY_RETENTION_TEAM_IDS"].split(",")]
    with transaction.atomic():
        for team_id in team_ids:
            team = Team.objects.select_for_update().filter(pk=team_id).first()
            if team is None:
                print(f"Project {team_id}: not created yet; replay settings will reconcile on the next sync")
                continue
            changed = [field for field, value in settings.items() if getattr(team, field) != value]
            if not changed:
                print(f"Project {team_id}: replay settings already reconciled")
                continue
            summary = ", ".join(f"{field}={settings[field]!r}" for field in changed)
            if dry_run:
                print(f"Project {team_id}: would set {summary}")
                continue
            for field in changed:
                setattr(team, field, settings[field])
            team.save(update_fields=changed)
            print(f"Project {team_id}: set {summary}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    configure_retention(dry_run=parser.parse_args().dry_run)
