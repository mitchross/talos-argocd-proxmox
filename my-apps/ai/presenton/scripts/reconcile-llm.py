"""Reconcile only Git-owned LLM fields before Presenton opens its SQLite store."""
import json
import os
from pathlib import Path
import sqlite3
import tempfile


def reconcile(directory: Path, api_key: str) -> None:
    if not api_key:
        raise ValueError("LiteLLM credential must not be empty")
    policy = {
        "LLM": "custom",
        "CUSTOM_LLM_URL": "http://litellm-service.litellm.svc.cluster.local:4000/v1",
        "CUSTOM_MODEL": "qwen3.8-27b",
        "CUSTOM_LLM_API_KEY": api_key,
    }
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "userConfig.json"
    backup = directory / "userConfig.json.bak"
    source = path if path.exists() else backup
    data = json.loads(source.read_text()) if source.exists() else {}
    if not isinstance(data, dict):
        raise ValueError("Presenton user config must be an object")
    database = directory / "fastapi.db"
    if database.exists():
        with sqlite3.connect(database) as connection:
            exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='provider_settings'"
            ).fetchone()
            if exists:
                row = connection.execute("SELECT config FROM provider_settings WHERE id=1").fetchone()
                if row:
                    config = json.loads(row[0])
                    if not isinstance(config, dict):
                        raise ValueError("Presenton provider settings must be an object")
                    config.update(policy)
                    connection.execute(
                        "UPDATE provider_settings SET config=?, updated_at=CURRENT_TIMESTAMP WHERE id=1",
                        (json.dumps(config),),
                    )
    data.update(policy)
    # Keep the recovery copy aligned so a later fallback cannot restore the old endpoint.
    for destination in [path, backup]:
        with tempfile.NamedTemporaryFile(mode="w", dir=directory, delete=False) as output:
            json.dump(data, output, indent=2)
            output.write("\n")
        os.chmod(output.name, 0o600)
        os.replace(output.name, destination)
    print("Presenton LLM settings reconciled; unrelated preferences preserved.")


if __name__ == "__main__":
    reconcile(Path(os.environ.get("APP_DATA_DIRECTORY", "/app_data")), os.environ["LITELLM_API_KEY"])
