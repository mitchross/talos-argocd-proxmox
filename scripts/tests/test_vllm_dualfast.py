"""Guard that Strata stays parked while vLLM owns both GPUs."""
from pathlib import Path
import subprocess

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_strata_replica_override_is_parked():
    docs = list(yaml.safe_load_all(subprocess.check_output(
        ['kubectl', 'kustomize', str(ROOT / 'my-apps/ai/strata')], text=True)))
    assert next(d for d in docs if d['kind'] == 'Deployment')['spec']['replicas'] == 0
