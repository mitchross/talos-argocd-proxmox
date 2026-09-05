#!/usr/bin/env python3
"""Prepare the repository's collector alert rules and fixtures for promtool."""
import argparse
from pathlib import Path
import sys

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = REPO_ROOT / "infrastructure/controllers/opentelemetry-operator-observability"


def prepare_tests(source_dir: Path, output_dir: Path) -> None:
    manifest = yaml.safe_load((source_dir / "collector-alerts.yaml").read_text(encoding="utf-8"))
    rules = manifest.get("spec") if isinstance(manifest, dict) else None
    if not isinstance(rules, dict) or not isinstance(rules.get("groups"), list) or not rules["groups"]:
        raise ValueError("collector-alerts.yaml must contain a non-empty spec.groups list")
    fixtures = (source_dir / "tests/collector-alerts.test.yaml").read_bytes()

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "collector.rules.yaml").write_text(yaml.safe_dump(rules), encoding="utf-8")
    (output_dir / "collector-alerts.test.yaml").write_bytes(fixtures)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path, help="Directory for promtool input files")
    args = parser.parse_args()
    try:
        prepare_tests(SOURCE_DIR, args.output_dir)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"ERROR: could not prepare telemetry rule tests: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
