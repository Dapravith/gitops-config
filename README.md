# gitops-config

Desired state for `gitops-api` in every environment. **Argo CD is the only thing that
applies this repo to the cluster.** Nobody runs `kubectl apply` by hand.

```
bootstrap/kind/                       local cluster: kind-config.yaml + create-cluster.sh (phase 5)
apps/gitops-api/base/                 shared manifests: Deployment, Service, SA, NetworkPolicies, ConfigMap
apps/gitops-api/components/pdb/       PodDisruptionBudget, used by staging + prod
apps/gitops-api/overlays/dev/         auto-sync; image digest bumped by CI PR
apps/gitops-api/overlays/staging/     auto-sync; digest promoted from dev via reviewed PR
apps/gitops-api/overlays/prod/        MANUAL sync; digest promoted from staging via reviewed PR
argocd/projects/                      AppProject restricting sources/destinations (phase 7)
argocd/applications/                  one Application per environment (phase 7)
sealed-secrets/                       SealedSecret manifests only; never plaintext (phase 7)
scripts/validate.sh                   offline gate: render + kubeconform + policy_check.py
docs/PROMOTION.md                     promotion procedure (phase 9–12)
```

Rules:

1. Images are referenced by digest (`@sha256:`), never by tag.
2. Promotion copies the exact digest from the previous environment.
3. No `Secret` objects, kubeconfigs or tokens are committed — only `SealedSecret`.

## Local cluster

```bash
bootstrap/kind/create-cluster.sh
```

```bash
export KUBECONFIG="$HOME/.kube/gitops-lab.kubeconfig"
```

`create-cluster.sh` also starts `gitops-lab-registry` on 127.0.0.1:5001, which the node uses as a pull
mirror for `ghcr.io`, so overlays can pin GHCR digests before CI has published.

## Validate (no cluster needed)

```bash
scripts/validate.sh
```
