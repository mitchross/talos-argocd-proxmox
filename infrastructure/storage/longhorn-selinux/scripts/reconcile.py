"""Reconcile mount options for explicitly selected existing Longhorn claims."""

import json
from pathlib import Path
import re
import ssl
import sys
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


MOUNT_OPTION = "context=system_u:object_r:ephemeral_t:s0"
STORAGE_CLASSES = {
    "longhorn", "longhorn-flash", "longhorn-wired-ha", "longhorn-kopiur-staging-local"
}
SELINUX_OPTIONS = {"context", "fscontext", "defcontext", "rootcontext"}


def emit(event, **fields):
    print(json.dumps({"event": event, **fields}), flush=True)


class KubernetesAPI:
    def __init__(self):
        self.credentials = Path("/var/run/secrets/kubernetes.io/serviceaccount")
        self.tls = ssl.create_default_context(cafile=str(self.credentials / "ca.crt"))

    def request(self, path, patch=None):
        headers = {"Authorization": "Bearer " + (self.credentials / "token").read_text().strip()}
        if patch is not None:
            headers["Content-Type"] = "application/json-patch+json"
        request = Request(
            "https://kubernetes.default.svc" + path,
            data=json.dumps(patch).encode() if patch is not None else None,
            headers=headers,
            method="PATCH" if patch is not None else "GET",
        )
        with urlopen(request, context=self.tls, timeout=30) as response:
            return json.load(response)

    def list_volumes(self):
        volumes = []
        continuation = ""
        while True:
            query = urlencode({"limit": 500, "continue": continuation})
            page = self.request("/api/v1/persistentvolumes?" + query)
            volumes.extend(page["items"])
            continuation = page.get("metadata", {}).get("continue", "")
            if not continuation:
                return volumes

    def patch_volume(self, name, operations):
        return self.request("/api/v1/persistentvolumes/" + quote(name, safe=""), operations)


def make_plan(volumes, policy):
    mode = policy.get("mode")
    claims = policy.get("claims")
    if mode not in {"plan", "apply", "remove"}:
        raise ValueError("mode must be plan, apply, or remove")
    if not isinstance(claims, list) or not claims or any(
        not isinstance(c, str) or not re.fullmatch(r"[a-z0-9][a-z0-9.-]*/[a-z0-9][a-z0-9.-]*", c)
        for c in claims
    ):
        raise ValueError("claims must explicitly list namespace/name; wildcards are not supported")

    plan = []
    found = set()
    for pv in volumes:
        metadata = pv["metadata"]
        spec = pv["spec"]
        ref = spec.get("claimRef", {})
        claim = ref.get("namespace", "") + "/" + ref.get("name", "")
        if claim not in claims:
            continue
        if metadata.get("deletionTimestamp") or pv.get("status", {}).get("phase") != "Bound":
            emit("skipped", claim=claim, pv=metadata["name"], reason="not a live Bound PV")
            continue
        if claim in found:
            raise ValueError(f"Multiple Bound PVs found for {claim}")
        found.add(claim)
        csi = spec.get("csi", {})
        if (
            csi.get("driver") != "driver.longhorn.io"
            or csi.get("fsType") != "ext4"
            or spec.get("storageClassName") not in STORAGE_CLASSES
            or spec.get("volumeMode", "Filesystem") != "Filesystem"
            or spec.get("accessModes") not in [["ReadWriteOnce"], ["ReadWriteOncePod"]]
        ):
            raise ValueError(f"{claim}: target must be an ext4 Longhorn RWO/RWOP filesystem in a reviewed class")

        existing = spec.get("mountOptions") or []
        if not isinstance(existing, list) or any(not isinstance(o, str) for o in existing):
            raise ValueError(f"{claim}: invalid mountOptions")
        for option in existing:
            # A mount option may contain comma-separated flags; reject hidden context overrides too.
            for flag in option.split(","):
                if flag.strip().split("=", 1)[0] in SELINUX_OPTIONS and option != MOUNT_OPTION:
                    raise ValueError(f"{claim}: conflicting SELinux mount option {option!r}")
        desired = [o for o in existing if o != MOUNT_OPTION]
        if mode != "remove":
            desired.append(MOUNT_OPTION)
        if desired == existing:
            emit("unchanged", claim=claim, pv=metadata["name"])
            continue

        operations = [
            {"op": "test", "path": "/metadata/uid", "value": metadata["uid"]},
            {"op": "test", "path": "/metadata/resourceVersion", "value": metadata["resourceVersion"]},
        ]
        if desired:
            operations.append({"op": "add", "path": "/spec/mountOptions", "value": desired})
        else:
            operations.append({"op": "remove", "path": "/spec/mountOptions"})
        plan.append({"pv": metadata["name"], "claim": claim, "before": existing, "after": desired, "patch": operations})
    for claim in sorted(set(claims) - found):
        emit("skipped", claim=claim, reason="no live Bound PV; new volumes inherit their StorageClass options")
    return plan


def reconcile(api, policy):
    # Validate every selected target before sending the first write; retries re-read resource versions.
    plan = make_plan(api.list_volumes(), policy)
    for change in plan:
        emit("planned", **{key: value for key, value in change.items() if key != "patch"})
    if policy["mode"] != "plan":
        for change in plan:
            api.patch_volume(change["pv"], change["patch"])
            emit("updated", pv=change["pv"], claim=change["claim"], remount_required=True)
    emit("complete", mode=policy["mode"], changes=len(plan))
    return plan


if __name__ == "__main__":
    try:
        reconcile(KubernetesAPI(), json.loads(Path(sys.argv[1]).read_text()))
    except Exception as error:
        emit("failed", error=str(error))
        sys.exit(1)
