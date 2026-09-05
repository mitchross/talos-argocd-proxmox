import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("cache_paths", Path(__file__).parents[1] / "validate-argocd-cache-paths.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def app(hint, source="my-apps/ai/example"):
    return {"kind": "Application", "metadata": {"name": "example", "annotations": {module.ANNOTATION: hint}}, "spec": {"source": {"path": source}}}


def appset(hint):
    template = app(hint, "{{ .path.path }}")
    return {"kind": "ApplicationSet", "metadata": {"name": "my-apps"}, "spec": {"template": template}}


class CachePathsTest(unittest.TestCase):
    def test_app_local_change_is_covered(self):
        self.assertFalse(module.validate([app(".")]))

    def test_old_double_prefixed_path_fails(self):
        self.assertTrue(module.validate([app("my-apps/ai/example")]))

    def test_absolute_paths_are_repo_relative(self):
        self.assertFalse(module.validate([app("/my-apps/ai/example")]))

    def test_shared_component_is_required(self):
        self.assertTrue(module.validate([appset(".")]))
        self.assertFalse(module.validate([appset(".;/my-apps/common")]))

    def test_unrelated_app_does_not_match(self):
        paths = module.resolve_paths("my-apps/ai/example", ".;/my-apps/common")
        self.assertFalse(any(module.covers(p, "my-apps/home/unrelated/deployment.yaml") for p in paths))
        self.assertTrue(any(module.covers(p, "my-apps/common/kopiur-backup/kustomization.yaml") for p in paths))

    def test_prefix_is_not_directory_match(self):
        self.assertFalse(module.covers("my-apps/ai/example", "my-apps/ai/example-other/file.yaml"))

    def test_seed_root_and_empty_input(self):
        self.assertFalse(module.validate([app(".", "infrastructure/controllers/argocd/apps")]))
        self.assertTrue(module.validate([]))


if __name__ == "__main__":
    unittest.main()
