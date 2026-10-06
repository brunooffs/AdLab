# Chapter 14 — Helm: installing ArgoCD the more common way

## What you'll do

Install a second, independent copy of ArgoCD via Helm, compare it directly against the one this
project actually runs (installed from a raw manifest), then clean it up. Not a replacement for
anything — a deliberate side-by-side, run safely enough that it can't disturb the cluster you
already depend on.

```bash
helm repo add argo https://argoproj.github.io/argo-helm
helm repo update
helm install argocd-helm argo/argo-cd --namespace argocd-helm --create-namespace
```

## Why this chapter exists, and why it isn't "redo Chapter 11 with Helm"

Chapter 11 installed ArgoCD from `install.yaml` — one large, static file, every resource already
fully rendered. That's not wrong; it's genuinely how this project's own cluster was set up, and it
works. But it's also not the way most real teams install ArgoCD. Helm is close to the default
choice in practice now — current official-adjacent documentation for ArgoCD itself lists the Helm
path as the *recommended* method, not just an alternative.

The reason isn't really about ArgoCD specifically — it's about what Helm is *for*. A raw manifest is
one fixed answer: these exact resources, these exact values, take it or leave it. A Helm chart is a
*template* — the same manifests, but with the differences between "a tiny lab install" and "a
500-node production cluster" extracted into a `values.yaml` file you fill in, rather than hand-
edited into the YAML itself. `Chart.yaml` declares what the chart is and which version of ArgoCD it
maps to; `templates/` holds the manifests with `{{ .Values.whatever }}` placeholders; `values.yaml`
supplies the defaults. `helm install` renders all of it into exactly the same kind of resources
`kubectl apply -f install.yaml` would have created directly — Helm doesn't change *what* gets
deployed, only how the "what" gets parameterized and versioned.

This also clarifies something worth being precise about: **Helm and Kustomize aren't competing for
the same job here.** Kustomize (Chapters 10–11) templates *this project's own* manifests —
`adlab-api`, Postgres, the HPA — things you wrote and maintain. Helm, in this chapter, installs
*someone else's* infrastructure — ArgoCD itself, something you consume, not something you author.
Using both at once isn't redundant; it's the normal split in real practice: Helm for off-the-shelf
components (ArgoCD, cert-manager, ingress controllers), Kustomize or plain manifests for your own.

## Why a separate namespace, on purpose

```bash
helm install argocd-helm argo/argo-cd --namespace argocd-helm --create-namespace
```

Not `argocd` — `argocd-helm`. If this installed into the same namespace the existing ArgoCD already
runs in, Helm would be creating resources with the same names as ones already there, with no
ownership annotations telling it those resources already exist and aren't its to manage. Best case,
that's a confusing error. Worst case, it's a working installation getting silently disturbed by a
tool that doesn't know it's not supposed to touch it — and this project's cluster took real,
hard-won effort to get stable (the CRD-size limit, the stuck finalizer, the stale-namespace saga all
covered in Chapter 11). This chapter is not the place to risk any of that for the sake of a
comparison.

One more deliberate boundary: **this second ArgoCD is never pointed at the real `adlab` Application.**
Two independent ArgoCD controllers both trying to reconcile the same resources, each with
`selfHeal: true`, would fight each other exactly the way a static `replicas:` field once fought the
HPA. This installation exists to be looked at, not to do anything.

## Confirm it came up

```bash
kubectl get pods -n argocd-helm
```

Once everything shows `Running`, compare the two installations directly — same product, two
different installation methods, real resources either way:

```bash
kubectl get all -n argocd | wc -l
kubectl get all -n argocd-helm | wc -l
```

They won't match exactly — the Helm chart's defaults aren't byte-identical to upstream's
`install.yaml`, and that's expected, not a bug in either one. Worth looking at what specifically
differs:

```bash
kubectl get deployments -n argocd -o name
kubectl get deployments -n argocd-helm -o name
```

## See the chart's actual values

Everything `values.yaml` lets you override, with the defaults this install actually used:

```bash
helm show values argo/argo-cd | less
```

This is the file you'd edit for a real deployment — enabling HA mode, setting resource limits,
configuring an ingress for ArgoCD's own UI — none of which this lab needs, which is exactly why the
raw-manifest version in Chapter 11 is still the right choice for *this* project's actual cluster.
Knowing how to read a chart's values file is the actual transferable skill here, more than the
specific `helm install` command.

## Clean up

This second ArgoCD has done its job once you've looked at it — there's no reason to keep two
running:

```bash
helm uninstall argocd-helm --namespace argocd-helm
kubectl delete namespace argocd-helm
```

Confirm the real one is untouched:

```bash
kubectl get application adlab -n argocd
```

Should still show `Synced` / `Healthy`, exactly as it did before this chapter — the whole point of
the namespace isolation was making sure this step would be unremarkable.

## What I could verify, and what I couldn't

The repository URL, chart name, and the "Helm is the recommended method" framing are all confirmed
directly against current documentation, not recalled from memory — worth saying plainly, since
Helm chart repositories and recommended-install guidance do shift over time. What I *can't* confirm
from here: this exact sequence actually running against a real cluster. Every other K8s/ArgoCD
chapter in this series was written after the real commands had already been run and the real
failures already found — this one is the reverse. If something in this chapter doesn't match what
actually happens on your cluster, that gap is the next real thing to fix, the same way every other
gap in this series got fixed.

## What's next

Chapter 13, still ahead: a real bug, deliberately reintroduced, no chapter number telling you where
to look.
