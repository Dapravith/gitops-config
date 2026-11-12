#!/usr/bin/env python3
"""Policy gate for rendered Kustomize output (JSON list of manifests on stdin).

Usage: yq -o=json ... rendered.yaml | python3 policy_check.py <env>

Rules are deliberately few and each maps to a requirement of this project.
Exit 1 with a list of violations if any rule fails.
"""

from __future__ import annotations

import json
import re
import sys

DIGEST_RE = re.compile(r"^ghcr\.io/[a-z0-9-]+/[a-z0-9._-]+@sha256:[0-9a-f]{64}$")
FORBIDDEN_KINDS = {"Secret"}  # only SealedSecret may carry secret material
EXPECTED_NS = {"dev": "gitops-dev", "staging": "gitops-staging", "prod": "gitops-prod"}
MIN_REPLICAS = {"dev": 1, "staging": 2, "prod": 3}


def pod_specs(obj: dict):
    if obj.get("kind") in {"Deployment", "StatefulSet", "DaemonSet", "Job"}:
        yield obj["spec"]["template"]["spec"]
    elif obj.get("kind") == "Pod":
        yield obj["spec"]


def check(env: str, objs: list[dict]) -> list[str]:
    errs: list[str] = []
    ns = EXPECTED_NS[env]
    kinds = {o["kind"] for o in objs}

    for o in objs:
        kind, name = o["kind"], o["metadata"]["name"]
        ref = f"{kind}/{name}"

        if kind in FORBIDDEN_KINDS:
            errs.append(f"{ref}: plaintext {kind} must not be committed (use SealedSecret)")

        if kind == "Namespace":
            labels = o["metadata"].get("labels", {})
            if name != ns:
                errs.append(f"{ref}: expected namespace {ns}")
            if labels.get("pod-security.kubernetes.io/enforce") != "restricted":
                errs.append(f"{ref}: must enforce Pod Security 'restricted'")
        elif o["metadata"].get("namespace") != ns:
            errs.append(f"{ref}: namespace is {o['metadata'].get('namespace')!r}, expected {ns}")

        if kind == "Deployment":
            replicas = o["spec"].get("replicas", 1)
            if replicas < MIN_REPLICAS[env]:
                errs.append(f"{ref}: replicas {replicas} < {MIN_REPLICAS[env]} for {env}")

        for spec in pod_specs(o):
            if spec.get("automountServiceAccountToken") is not False:
                errs.append(f"{ref}: automountServiceAccountToken must be false")
            psc = spec.get("securityContext", {})
            if psc.get("runAsNonRoot") is not True:
                errs.append(f"{ref}: pod runAsNonRoot must be true")
            if psc.get("seccompProfile", {}).get("type") != "RuntimeDefault":
                errs.append(f"{ref}: seccompProfile must be RuntimeDefault")
            for c in spec.get("initContainers", []) + spec["containers"]:
                cref = f"{ref}[{c['name']}]"
                if not DIGEST_RE.match(c["image"]):
                    errs.append(f"{cref}: image {c['image']!r} is not ghcr.io/...@sha256:<digest>")
                sc = c.get("securityContext", {})
                if sc.get("allowPrivilegeEscalation") is not False:
                    errs.append(f"{cref}: allowPrivilegeEscalation must be false")
                if sc.get("readOnlyRootFilesystem") is not True:
                    errs.append(f"{cref}: readOnlyRootFilesystem must be true")
                if "ALL" not in sc.get("capabilities", {}).get("drop", []):
                    errs.append(f"{cref}: capabilities.drop must include ALL")
                res = c.get("resources", {})
                for field in ("cpu", "memory"):
                    if field not in res.get("requests", {}):
                        errs.append(f"{cref}: missing requests.{field}")
                if "memory" not in res.get("limits", {}):
                    errs.append(f"{cref}: missing limits.memory")
                for probe in ("readinessProbe", "livenessProbe"):
                    if probe not in c:
                        errs.append(f"{cref}: missing {probe}")

    if "NetworkPolicy" not in kinds:
        errs.append("no NetworkPolicy rendered (default-deny required)")
    if env in {"staging", "prod"} and "PodDisruptionBudget" not in kinds:
        errs.append(f"{env}: PodDisruptionBudget required")
    return errs


def main() -> int:
    env = sys.argv[1]
    data = json.load(sys.stdin)
    objs = [d for d in (data if isinstance(data, list) else [data]) if d]
    errs = check(env, objs)
    for e in errs:
        print(f"  POLICY FAIL [{env}] {e}")
    if not errs:
        print(f"  policy OK [{env}]: {len(objs)} objects")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
