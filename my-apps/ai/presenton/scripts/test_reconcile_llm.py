import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("reconcile_llm", Path(__file__).with_name("reconcile-llm.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ReconcileTests(unittest.TestCase):
    def test_existing_database_and_recovery_copy_preserve_other_settings(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / "userConfig.json").write_text(json.dumps({"CUSTOM_LLM_URL": "old", "AUTH_USERNAME": "owner", "IMAGE_PROVIDER": "pexels"}))
            with sqlite3.connect(root / "fastapi.db") as db:
                db.execute("CREATE TABLE provider_settings (id INTEGER PRIMARY KEY, config TEXT, updated_at TEXT)")
                db.execute("INSERT INTO provider_settings VALUES (1, ?, '')", (json.dumps({"CUSTOM_LLM_URL": "old", "IMAGE_PROVIDER": "pexels"}),))
            for _ in range(2):
                module.reconcile(root, "synthetic-key")
            config = json.loads((root / "userConfig.json").read_text())
            self.assertEqual(config["AUTH_USERNAME"], "owner")
            self.assertEqual(config["CUSTOM_LLM_API_KEY"], "synthetic-key")
            self.assertEqual(config, json.loads((root / "userConfig.json.bak").read_text()))
            self.assertEqual((root / "userConfig.json").stat().st_mode & 0o777, 0o600)
            with sqlite3.connect(root / "fastapi.db") as db:
                saved = json.loads(db.execute("SELECT config FROM provider_settings WHERE id=1").fetchone()[0])
            self.assertEqual(saved["CUSTOM_MODEL"], "qwen3.8-27b")
            self.assertEqual(saved["IMAGE_PROVIDER"], "pexels")
            self.assertIn("litellm-service", saved["CUSTOM_LLM_URL"])

    def test_fresh_install_does_not_create_database_or_accept_empty_secret(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            with self.assertRaises(ValueError):
                module.reconcile(root, "")
            module.reconcile(root, "synthetic-key")
            self.assertFalse((root / "fastapi.db").exists())

    def test_malformed_existing_config_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            path = root / "userConfig.json"
            path.write_text("malformed")
            with self.assertRaises(json.JSONDecodeError):
                module.reconcile(root, "synthetic-key")
            self.assertEqual(path.read_text(), "malformed")


if __name__ == "__main__":
    unittest.main()
