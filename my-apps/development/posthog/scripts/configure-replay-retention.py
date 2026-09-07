"""Reconcile the declared replay retention through PostHog's Team model."""

import argparse
import os
import sys


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

    team_ids = [int(value) for value in os.environ["SELF_HOSTED_REPLAY_RETENTION_TEAM_IDS"].split(",")]
    with transaction.atomic():
        for team_id in team_ids:
            team = Team.objects.select_for_update().filter(pk=team_id).first()
            if team is None:
                print(f"Project {team_id}: not created yet; retention will reconcile on the next sync")
                continue
            if team.session_recording_retention_period != "30d":
                if dry_run:
                    print(f"Project {team_id}: would set replay retention to 30d")
                    continue
                team.session_recording_retention_period = "30d"
                team.save(update_fields=["session_recording_retention_period"])
                print(f"Project {team_id}: replay retention set to 30d")
            else:
                print(f"Project {team_id}: replay retention already 30d")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    configure_retention(dry_run=parser.parse_args().dry_run)
