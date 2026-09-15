"""Render the release contract and run Argo's actual Lua health customization."""

import copy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]
RADAR = ROOT / "my-apps/development/radar-ng"
NEWS = ROOT / "my-apps/development/news-reader"


def render(path):
    return list(yaml.safe_load_all(subprocess.check_output(["kustomize", "build", str(path)], text=True)))


def lua(value):
    if value is None:
        return "nil"
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (str, int, float)):
        return json.dumps(value)
    if isinstance(value, list):
        return "{" + ",".join(lua(v) for v in value) + "}"
    return "{" + ",".join(f"[{lua(k)}]={lua(v)}" for k, v in value.items()) + "}"


class TemporalDeploymentTests(unittest.TestCase):
    def test_all_candidate_images_follow_release_policy_and_are_gated(self):
        workers = [obj for path in (RADAR, NEWS, ROOT / "my-apps/utility/deal-scout")
                   for obj in render(path) if obj["kind"] == "WorkerDeployment"]
        self.assertEqual(len(workers), 7)
        for worker in workers:
            with self.subTest(worker=worker["metadata"]["name"]):
                for container in worker["spec"]["template"]["spec"]["containers"]:
                    if worker["metadata"]["namespace"] == "news-reader":
                        self.assertRegex(container["image"], r"^registry\.vanillax\.me/news-reader-temporal-worker:v[0-9]+\.[0-9]+\.[0-9]+$")
                    else:
                        self.assertRegex(container["image"], r"@sha256:[a-f0-9]{64}$")
                self.assertTrue(worker["spec"]["rollout"]["gate"]["workflowType"])
        frontend = next(obj for obj in render(NEWS) if obj["kind"] == "Deployment" and obj["metadata"]["name"] == "news-reader")
        self.assertRegex(frontend["spec"]["template"]["spec"]["containers"][0]["image"], r"^registry\.vanillax\.me/news-reader:v[0-9]+\.[0-9]+\.[0-9]+$")

    def test_radar_config_changes_versioned_templates_and_keeps_legacy_config(self):
        original = render(RADAR)
        with tempfile.TemporaryDirectory() as directory:
            app = Path(directory) / "radar"
            shutil.copytree(RADAR, app)
            path = app / "temporal-workers/release-env-patch.yaml"
            patch = yaml.safe_load(path.read_text())
            next(p for p in patch if p["value"]["name"] == "BACKLOG_PER_CYCLE")["value"]["value"] = "2"
            path.write_text(yaml.safe_dump(patch))
            updated = render(app)
        old_workers = {o["metadata"]["name"]: o for o in original if o["kind"] == "WorkerDeployment"}
        new_workers = {o["metadata"]["name"]: o for o in updated if o["kind"] == "WorkerDeployment"}
        self.assertEqual(len(old_workers), 5)
        for name, old in old_workers.items():
            container = old["spec"]["template"]["spec"]["containers"][0]
            self.assertNotIn("envFrom", container)
            self.assertNotEqual(old["spec"]["template"], new_workers[name]["spec"]["template"])
            self.assertEqual(old["spec"]["rollout"]["gate"]["workflowType"], "RadarDeploymentSmokeWorkflow")
            names = [env["name"] for env in container["env"]]
            self.assertEqual(len(names), len(set(names)))
        legacy = lambda objects: next(o for o in objects if o["kind"] == "ConfigMap" and o["metadata"]["name"] == "radar-ng-temporal-config")
        self.assertEqual(legacy(original), legacy(updated))

    def test_news_retains_legacy_script_but_new_worker_needs_no_overlay(self):
        objects = render(NEWS)
        retained = [o for o in objects if o["kind"] == "ConfigMap" and o["metadata"]["name"].startswith("news-reader-llm-auth-scripts-")]
        self.assertEqual(len(retained), 1)
        self.assertIn("prepare-litellm-auth.py", retained[0]["data"])
        worker = next(o for o in objects if o["kind"] == "WorkerDeployment")
        pod = worker["spec"]["template"]["spec"]
        self.assertNotIn("initContainers", pod)
        self.assertNotIn("volumes", pod)
        self.assertEqual(worker["spec"]["rollout"]["gate"]["workflowType"], "NewsDeploymentSmokeWorkflow")

    def test_lua_health_distinguishes_failures_progress_and_stale_status(self):
        values = yaml.safe_load((ROOT / "infrastructure/controllers/argocd/values.yaml").read_text())
        script = values["configs"]["cm"]["resource.customizations.health.temporal.io_WorkerDeployment"]
        def assess(obj):
            program = "obj=" + lua(obj) + "\nlocal function health()\n" + script + "\nend\nlocal r=health(); print(r.status); print(r.message or '')\n"
            return subprocess.check_output(["lua", "-"], input=program, text=True).splitlines()
        def state(reason, ready="False", progressing="False"):
            return {"metadata": {"generation": 2}, "status": {"observedGeneration": 2, "conditions": [
                {"type": "Ready", "status": ready, "reason": reason, "observedGeneration": 2},
                {"type": "Progressing", "status": progressing, "reason": reason, "observedGeneration": 2},
            ]}}
        for reason in ("ConnectionNotFound", "AuthSecretInvalid", "TemporalClientCreationFailed", "TemporalStateFetchFailed", "PlanGenerationFailed", "PlanExecutionFailed", "InvalidSpec", "ClusterConnectionUnsupported"):
            with self.subTest(reason=reason):
                self.assertEqual(assess(state(reason))[0], "Degraded")
        for reason in ("WaitingForPollers", "WaitingForPromotion", "Ramping"):
            self.assertEqual(assess(state(reason, progressing="True"))[0], "Progressing")
        good = state("RolloutComplete", ready="True")
        self.assertEqual(assess(good)[0], "Healthy")
        stale = copy.deepcopy(good)
        stale["metadata"]["generation"] = 3
        self.assertEqual(assess(stale)[0], "Progressing")
        self.assertEqual(assess({})[0], "Progressing")
        for failure in ("Failed", "Canceled", "Terminated", "TimedOut"):
            failed = state("WaitingForPromotion", progressing="True")
            failed["status"]["targetVersion"] = {"testWorkflows": [{"workflowID": "candidate-gate", "status": failure}]}
            result = assess(failed)
            self.assertEqual(result[0], "Degraded")
            self.assertIn("candidate-gate", result[1])
