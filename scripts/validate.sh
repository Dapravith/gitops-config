#!/usr/bin/env bash
# Validate every overlay WITHOUT touching a cluster:
#   1. render with Kustomize (kubectl's built-in)
#   2. schema-validate with kubeconform (strict, K8s 1.36 schemas)
#   3. enforce project policy (scripts/policy_check.py)
# Tools other than kubectl/python3/docker run as digest-pinned containers.
# Rendered output is written to ${OUT_DIR:-.rendered}/<env>.yaml (gitignored).
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
out="${OUT_DIR:-${root}/.rendered}"
envs=("${@:-dev staging prod}")
read -r -a envs <<< "${envs[*]}"

KUBECONFORM_IMAGE="ghcr.io/yannh/kubeconform:v0.8.0@sha256:faffaf43f95aa6425306e1ab8d6fcad72acb9049158f38e574c085ea1ec0f64e"
YQ_IMAGE="mikefarah/yq:4.54.1@sha256:4b3d9475d65571d28cbb19544d3820ec2945e4c8b2f18279394282b8dc3a592e"
K8S_VERSION="1.36.0"

mkdir -p "${out}"
fail=0
for env in "${envs[@]}"; do
  echo "== ${env}"
  file="${out}/${env}.yaml"
  if ! kubectl kustomize "${root}/apps/gitops-api/overlays/${env}" > "${file}"; then
    echo "  RENDER FAIL [${env}]"; fail=1; continue
  fi
  echo "  rendered $(grep -c '^kind:' "${file}") objects -> ${file#"${root}"/}"

  if ! docker run --rm -i "${KUBECONFORM_IMAGE}" \
        -strict -summary -kubernetes-version "${K8S_VERSION}" \
        -schema-location default - < "${file}" | sed 's/^/  /'; then
    echo "  SCHEMA FAIL [${env}]"; fail=1
  fi

  if ! docker run --rm -i "${YQ_IMAGE}" -o=json -I=0 'select(. != null)' - < "${file}" \
        | python3 -c 'import sys,json; print(json.dumps([json.loads(l) for l in sys.stdin if l.strip()]))' \
        | python3 "${root}/scripts/policy_check.py" "${env}"; then
    fail=1
  fi
done

if [[ ${fail} -ne 0 ]]; then echo "VALIDATION FAILED"; exit 1; fi
echo "ALL OVERLAYS VALID"
