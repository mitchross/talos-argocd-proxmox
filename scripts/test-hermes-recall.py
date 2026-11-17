"""Fetch the deployed plugin revision and run its tests plus the local recall regression."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import urllib.request


REVISION = "d952b6e655fccab4581ee0722b51c5f103873d12"
BASE = f"https://raw.githubusercontent.com/vectorize-io/hindsight/{REVISION}/hindsight-integrations/hermes/"
FILES = ("__init__.py", "embedded.py", "settings.py", "templates.py", "setup.py", "config_schema.py", "plugin.yaml",
         "tests/conftest.py", "tests/test_provider.py")
ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "my-apps/development/hermes"


def main():
    with tempfile.TemporaryDirectory(prefix="hermes-recall-test-") as directory:
        app = Path(directory) / "hindsight_hermes"
        app.mkdir()

        def fetch(name):
            target = app / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with urllib.request.urlopen(BASE + name, timeout=30) as response:
                target.write_bytes(response.read())

        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(fetch, FILES))
        shutil.copytree(APP / "config", app / "config")
        shutil.copy(APP / "tests/test_automatic_recall.py", app / "tests/")
        return subprocess.call([sys.executable, "-m", "pytest", "-q", "--tb=short", str(app / "tests")])


if __name__ == "__main__":
    sys.exit(main())
