# Chapter 11 — GitOps with ArgoCD

## What you'll do

Install ArgoCD, hand it the deployment from Chapter 10, and watch it take over continuous
management of something that's already running. Along the way: a debugging session that started
looking like an ArgoCD bug and turned out to be five months of untouched cluster state finally
catching up.

```bash
kubectl create namespace argocd
kubectl apply -n argocd --server-side --force-conflicts \
  -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
kubectl wait --for=condition=ready pod --all -n argocd --timeout=300s
kubectl apply -f k8s/argocd/argocd-app.yaml
```

## What ArgoCD actually does here

`argocd-app.yaml`'s `source` tells it to continuously watch this repo's `k8s/` path on `main`;
`destination` tells it to apply that into the `adlab` namespace of whatever cluster ArgoCD itself
runs in. The piece that makes this GitOps rather than just "a manifest store you apply by hand" is
`syncPolicy.automated`:

- **`prune: true`** — delete anything from the live cluster that's been removed from git. When
  `ingress.yaml` was deleted from this repo, this is the setting that would tear the live Ingress
  object down too, automatically, rather than leaving it orphaned.
- **`selfHeal: true`** — revert anything that differs from git, including changes made directly
  with `kubectl`. Try it:

  ```bash
  kubectl edit configmap adlab-config -n adlab
  # change any value, save, quit
  kubectl get application adlab -n argocd -w
  ```

  Within one reconcile cycle you should see it flip briefly to `OutOfSync` and settle back to
  `Synced` — and the ConfigMap's value will be back to exactly what git says, undone by ArgoCD, not
  by you.

## Why the Deployment has no `replicas:` field — the ArgoCD version of the answer

Chapter 10 explained the Kubernetes side of this. Here's why it matters specifically under
`selfHeal`: if git declared `replicas: 2` and the HPA scaled to 5, ArgoCD would see that as drift —
a live value disagreeing with what git says — and revert it straight back to 2, fighting the HPA
forever, every single reconcile. Omitting the field from git entirely isn't a workaround; it's the
correct fix, confirmed directly against ArgoCD's own diffing behavior: a field that's never declared
in the desired manifest is simply never part of the comparison, so there's nothing for `selfHeal` to
revert. The HPA owns that field outright, with zero conflict, and no special ArgoCD configuration
(like an `ignoreDifferences` block) is needed at all.

## A debugging session worth walking through in full

The first time this project tried the exact steps above, on a cluster that already had an ArgoCD
install on it from five months earlier, it failed — and the failure genuinely looked like an
ArgoCD bug at first:

```
ComparisonError: Failed to load target state: failed to generate manifest for source 1 of 1:
rpc error: code = Unavailable desc = connection error: desc = "transport: Error while dialing:
dial tcp 10.99.2.154:8081: connect: connection refused"
```

The real cause took several steps to uncover, and each one is worth knowing on its own:

**1. The Application's `status.sync` showed a sync from five months ago**, immediately after what
looked like a fresh `kubectl apply`. That's the giveaway that something wasn't actually fresh —
`kubectl apply -f install.yaml` layered new Deployment pods onto a namespace that was never
actually deleted, so the controllers looked new (fresh pod ages) while the `Application` custom
resource underneath still carried its old history.

**2. `argocd-applicationset-controller` was crash-looping**, with this in its logs:

```
"error":"failed to get restmapping: no matches for kind \"ApplicationSet\" in version \"argoproj.io/v1alpha1\""
```

Its own CRD had never actually installed — going all the way back to the original install, five
months prior. The reason: `kubectl apply` (client-side) stores the entire object being applied in a
`kubectl.kubernetes.io/last-applied-configuration` annotation, and Kubernetes caps any single
annotation at 262144 bytes (256 KiB). The `ApplicationSet` CRD's schema is larger than that. The fix
— confirmed against several independent, corroborating sources, not just one — is server-side
apply, which tracks changes via `metadata.managedFields` instead and never touches that annotation
at all:

```bash
kubectl apply -n argocd --server-side --force-conflicts -f <install.yaml>
```

**3. Deleting the stuck namespace hung indefinitely.** `argocd-app.yaml` declares a finalizer —
`resources-finalizer.argocd.argoproj.io` — specifically so ArgoCD cleans up the deployed resources
*before* the Application object itself can be removed. But `kubectl delete namespace argocd` tears
down everything in that namespace at once, including the very controller that's supposed to process
that finalizer. With nothing left to acknowledge it, the object — and the whole namespace deletion —
waits forever. The fix, safe because it only touches the Application's own bookkeeping, not
anything it deployed:

```bash
kubectl patch application adlab -n argocd -p '{"metadata":{"finalizers":null}}' --type=merge
```

**4. Even after all of that was fixed, one more error appeared:**

```
authentication required: Repository not found.
```

This is GitHub's deliberate behavior for an anonymous clone attempt against a *private* repository
— it returns the same ambiguous "not found" a truly nonexistent repo would give, on purpose, so a
private repo's existence can't be confirmed by an unauthorized caller. `argocd-app.yaml` has no
credentials configured anywhere, which is only correct if the repository is public.

None of these four things were related to each other on the surface. All four were real, and fixing
each one required actual evidence — a log line, a timestamp, an exact error string — not a guess.

## Confirm the loop closes end to end

```bash
kubectl get application adlab -n argocd
```

Should show `Synced` / `Healthy`. Then check whether the last CI build actually reached this
cluster:

```bash
git log --oneline -3 -- k8s/kustomization.yaml
```

A commit authored by `github-actions[bot]`, bumping the image tag, is the other half of the loop —
covered properly in Chapter 12.

## What's next

Chapter 12 is the CI side of everything just described: the workflow that builds the image, pushes
it, and writes the tag this chapter's `Synced` status depends on — plus its own share of real bugs
found the same way, one piece of evidence at a time.
