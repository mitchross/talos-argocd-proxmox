#!/usr/bin/env python3
"""Check Headlamp's RBAC through explicit, non-persistent SubjectAccessReviews."""
import json
import subprocess


def main():
    failures = 0
    for resource, subresource, expected in [
        ("secrets", "", False), ("pods", "", True), ("pods", "log", True)
    ]:
        attributes = {"group": "", "verb": "get", "resource": resource}
        if subresource:
            attributes["subresource"] = subresource
        review = {
            "apiVersion": "authorization.k8s.io/v1",
            "kind": "SubjectAccessReview",
            "spec": {
                "user": "system:serviceaccount:kube-system:headlamp-admin",
                "groups": ["system:serviceaccounts", "system:serviceaccounts:kube-system",
                           "system:authenticated"],
                "resourceAttributes": attributes,
            },
        }
        result = subprocess.run(
            ["kubectl", "create", "--raw",
             "/apis/authorization.k8s.io/v1/subjectaccessreviews", "-f", "-"],
            input=json.dumps(review), capture_output=True, text=True, check=True,
        )
        status = json.loads(result.stdout)["status"]
        allowed = status["allowed"]
        name = resource + ("/" + subresource if subresource else "")
        print(f"get {name}: {'allowed' if allowed else 'denied'}")
        failures += allowed != expected or bool(status.get("evaluationError"))
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
