# AdLab — Kubernetes Manifests

This covers the API tier only (PostgreSQL, Redis, Elasticsearch, the API) — not Kafka, Spark, or
the rest of the analytics pipeline. See the root [README](../README.md) for why.

## Structure

```
k8s/
├── kustomization.yaml         ← root — ArgoCD reads this
├── base/
│   ├── namespace.yaml         ← adlab namespace
│   ├── configmap.yaml         ← non-secret config
│   ├── secrets.yaml           ← passwords and keys, plaintext (see "Secrets" below)
│   └── sealed-secrets.yaml    ← appears after you run bin/k8s-seal-secrets.sh
├── postgres/
│   └── postgres.yaml          ← StatefulSet + Service + PVC
├── redis/
│   └── redis.yaml             ← Deployment + Service + PVC
├── elasticsearch/
│   └── elasticsearch.yaml     ← StatefulSet + Service + PVC
├── api/
│   └── api.yaml                ← Deployment + Service + HorizontalPodAutoscaler
└── argocd/
    └── argocd-app.yaml        ← ArgoCD Application definition
```

There is deliberately no `ingress.yaml`. minikube's ingress addon depends on ingress-nginx, which
Kubernetes has retired — no further releases, bug fixes, or security patches. `kubectl
port-forward` (below) covers local access without depending on that; bring your own Ingress or
Gateway API setup if you need one for something beyond this lab.

## Prerequisites

This is a separate path from the root README's Quick Start — everything here needs its own tools,
installed on your host, not something `start.sh` sets up for you:

- [minikube](https://minikube.sigs.k8s.io/docs/start/)
- [kubectl](https://kubernetes.io/docs/tasks/tools/#kubectl)
- Docker (already required for the rest of this repo — minikube uses it as its driver)

```bash
bin/k8s-preflight.sh   # confirms all three are actually on PATH before you start
```

```bash
minikube start --driver=docker --cpus=4 --memory=6g
minikube addons enable metrics-server   # the HPA needs this to read CPU/memory usage
```

Everything from here on is deliberately manual, run one command at a time — not something this
repo automates into a single script. [Chapter 10](../tutorial/chapters/10-kubernetes.md) and
[Chapter 11](../tutorial/chapters/11-gitops-argocd.md) explain why: doing each layer by hand is
what makes it possible to tell, when something fails, whether the problem is in the manifests or
in ArgoCD's own machinery.

## Manual deploy (without ArgoCD)

```bash
# Apply everything
kubectl apply -k k8s/

# Watch pods come up
kubectl get pods -n adlab -w

# Access the API (migrations already ran automatically — see "Migrations" below)
kubectl port-forward -n adlab svc/adlab-api 3000:3000
# in another terminal:
curl http://localhost:3000/health
curl http://localhost:3000/v1/advertisers
```

## Migrations

`api.yaml`'s Deployment runs `prisma migrate deploy` in an `initContainer` before the API container
starts — there's no separate manual migration step here, unlike the Compose stack's one-shot
`migrate` service. If a migration fails, the pod never reaches Ready; check it with:

```bash
kubectl logs -n adlab deploy/adlab-api -c run-migrations
```

## Secrets

`base/secrets.yaml` currently holds plaintext, base64-encoded lab-default credentials
(`lab`/`labpass`, a hardcoded dev JWT string) — fine to look at, not fine to treat as a real
secrets-management pattern once this goes further than a lab. Moving it to a
[Sealed Secret](https://github.com/bitnami/sealed-secrets) is a good next step and a genuinely
useful piece of DevOps practice to have exercised:

```bash
# 1. Install the controller (once per cluster)
kubectl apply -f https://github.com/bitnami/sealed-secrets/releases/download/v0.40.0/controller.yaml
kubectl get pods -n kube-system -l app.kubernetes.io/name=sealed-secrets -w   # wait for Running

# 2. Install kubeseal locally
brew install kubeseal   # macOS; see the project's README for other platforms

# 3. Seal it
../bin/k8s-seal-secrets.sh
```

The script writes `k8s/base/sealed-secrets.yaml` and stops — it deliberately does not delete the
plaintext file, edit `kustomization.yaml`, or commit anything. It prints the remaining steps,
including backing up the controller's private key *before* anything else. That backup matters: lose
it, and every secret you've ever sealed with it becomes permanently undecryptable. This is a real,
common trade-off of this pattern, not a hypothetical — worth internalizing before you rely on it for
anything that isn't a lab.

Once the plaintext file is `git rm`'d, `kustomize build k8s/` will only show sealed, encrypted
values for `adlab-secrets` — the actual passwords never appear in the repository again. The
`SealedSecret` object itself is safe to keep public; it's only decryptable by the controller's
private key, which lives only in your cluster.

## ArgoCD deploy

```bash
# Install ArgoCD
kubectl create namespace argocd
# --server-side is required, not optional: ArgoCD's ApplicationSet CRD is
# large enough that plain `kubectl apply` (client-side) fails with
# "metadata.annotations: Too long: may not be more than 262144 bytes" — that
# annotation stores the whole object, and this CRD's schema is bigger than
# the 256 KiB Kubernetes allows for any single annotation. Server-side apply
# tracks changes via managedFields instead, so the limit never applies.
# --force-conflicts only matters on a second install over an existing one
# (harmless, and necessary, on a first install too).
kubectl apply -n argocd --server-side --force-conflicts \
  -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# Wait for EVERY ArgoCD pod, not just argocd-server — argocd-repo-server is
# what actually clones and renders your manifests, and a comparison attempt
# that beats it to Ready fails with a misleading "connection refused" that
# then sits cached until the next refresh.
kubectl wait --for=condition=ready pod --all -n argocd --timeout=300s

# Get initial admin password
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d

# Port-forward ArgoCD UI
kubectl port-forward svc/argocd-server -n argocd 8090:443
# Open https://localhost:8090 → login admin / <password above>

# Apply the Application definition
kubectl apply -f k8s/argocd/argocd-app.yaml
```

ArgoCD will now auto-sync from GitHub on every push to `main` — including the image tag that
`.github/workflows/ci.yml` commits back to `kustomization.yaml` on every successful API build. That
auto-commit is what makes the tag actually mean something: `git log -- k8s/kustomization.yaml`
shows exactly which build is running in the cluster at any point, rather than everyone silently
running whatever `:latest` happened to resolve to at pull time.

`api.yaml`'s Deployment intentionally has no `replicas:` field — the `HorizontalPodAutoscaler`
alongside it owns that number. Declaring a static count in git would fight the HPA every time
ArgoCD's `selfHeal` runs, since selfHeal reverts anything that differs from what git declares, and
an HPA-driven replica change looks exactly like drift from git's point of view.

## Installing ArgoCD via Helm (alternative)

The manual steps above install ArgoCD from its raw manifest — direct, no extra tooling, and what
this project's own cluster actually runs. Helm is genuinely the more common way to do this in
practice, though, and worth knowing: it packages the same manifests as a versioned, parameterized
chart instead of one large static YAML file. [Chapter 14](../tutorial/chapters/14-helm-argocd.md)
covers this as a real, deliberate comparison between the two.

```bash
helm repo add argo https://argoproj.github.io/argo-helm
helm repo update
helm install argocd-helm argo/argo-cd --namespace argocd-helm --create-namespace
```

A separate namespace (`argocd-helm`, not `argocd`) and release name on purpose — this installs
*alongside* the existing ArgoCD, not in place of it, so there's no risk of Helm colliding with
resources it doesn't know it doesn't own. It's meant as a side-by-side comparison, not a
replacement; see the chapter for why, and for cleaning it up afterward with `helm uninstall`.

## Watching it from the dashboard

`node dashboard/server.js`'s Infrastructure tab shows a read-only ArgoCD status strip — sync
status, health status, and which `kubectl` context it's reading, polled every 20 seconds. It's
read-only on purpose: a sync or rollback button is a real action with real consequences, and
would need the same kind of confirmation the Spark Start/Stop buttons already have, not something
bundled in as a side effect of a status check. It also degrades gracefully — if `kubectl` isn't
installed, or no cluster is running, or ArgoCD was never set up on whatever cluster is current, it
just says so plainly rather than erroring. That's the expected state for most clones of this repo.

## Useful commands

```bash
# Watch all pods
kubectl get pods -n adlab -w

# Describe a failing pod
kubectl describe pod -n adlab <pod-name>

# Check API logs (the running container, not the migration initContainer)
kubectl logs -n adlab deploy/adlab-api -f

# Check HPA status (needs metrics-server — see Prerequisites)
kubectl get hpa -n adlab

# Port-forward the API for local testing
kubectl port-forward -n adlab svc/adlab-api 3000:3000
```
