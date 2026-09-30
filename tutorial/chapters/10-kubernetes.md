# Chapter 10 — Kubernetes and Kustomize

## What you'll do

Deploy the API tier to a real cluster in two phases — plain `kubectl` first, ArgoCD later — and
see exactly what a live apiserver checks that a static YAML renderer can't.

```bash
minikube start --driver=docker --cpus=4 --memory=6g
minikube addons enable metrics-server
kubectl apply -k k8s/
kubectl get pods -n adlab -w
```

## Why manual apply first

It's tempting to go straight to the full GitOps setup — install ArgoCD, point it at the repo, let
it do everything. Resist that. When something fails, you want to know immediately whether the
problem is in your manifests or in ArgoCD's own machinery, and those are two very different classes
of problem with two very different fixes. This project's own K8s manifests were verified with
`kustomize build` — a pure, offline YAML transformation — for months before anyone actually ran
`kubectl apply` against a live cluster. That static check catches a lot, but not everything: it
can't tell you whether a `secretKeyRef` actually resolves, whether an image can actually be pulled,
or whether an initContainer actually completes. Only a real apiserver can tell you that.

## Watch the migration happen live

```
adlab-api-777888fbb8-4tpc6   0/1     Init:0/4   0          9s
adlab-api-777888fbb8-4tpc6   0/1     Init:1/4   0          13s
adlab-api-777888fbb8-4tpc6   0/1     Init:2/4   0          15s
adlab-api-777888fbb8-4tpc6   0/1     Init:3/4   0          40s
adlab-api-777888fbb8-4tpc6   0/1     PodInitializing   0     42s
adlab-api-777888fbb8-4tpc6   0/1     Running           0     43s
```

Four init containers run in order before the API container ever starts: three `busybox` checks
waiting for Postgres, Redis, and Elasticsearch to answer on their ports, then a fourth —
`run-migrations` — that runs `npx prisma migrate deploy` for real, against real Postgres, using a
`DATABASE_URL` pulled live from a Secret via `secretKeyRef`. `Init:3/4` completing is the single
most informative line in that whole sequence: it's proof the Secret actually resolved correctly.

That matters because it used to be broken in a way `kustomize build` couldn't catch. The Deployment
originally had `DATABASE_URL` and `MONGO_URL` hardcoded as plaintext `value:` strings — even though
the Secret already declared `POSTGRES_PASSWORD` and `MONGO_PASSWORD` keys sitting there unused. Only
`JWT_SECRET` was ever actually wired through `secretKeyRef`. A static YAML check has no opinion on
whether a value *should* come from a Secret instead of being typed in plain — it's a design
decision, not a syntax error, and design decisions like that hide in files that otherwise look
completely reasonable.

```bash
kubectl get deployment adlab-api -n adlab -o jsonpath='{.spec.template.spec.containers[0].env}' | python3 -m json.tool
```

Look for `DATABASE_URL` — it should show `valueFrom.secretKeyRef`, not a plain `value`.

## The HPA and the missing `replicas:` field

```bash
kubectl get hpa -n adlab
```

```
NAME            REFERENCE              TARGETS                       MINPODS   MAXPODS   REPLICAS
adlab-api-hpa   Deployment/adlab-api   cpu: 7%/70%, memory: 58%/80%  2         5         2
```

`api.yaml`'s Deployment has no `replicas:` field at all — deliberately. Kubernetes defaults an
omitted `replicas` to 1 on creation, and the HPA (with `minReplicas: 2`) takes over from there
almost immediately; watching the pod list right after `kubectl apply` usually shows this happen too
fast to see as two separate steps. The reason it's omitted rather than set to a fixed number: a
Deployment that declares `replicas: 2` in git and an HPA that wants to scale it to 5 are fighting
over the same field. You'll see exactly how that fight plays out under ArgoCD in Chapter 11 — it's
a much bigger problem there than it is here.

## Why there's a gap where MongoDB should be

```bash
curl http://localhost:3000/health   # after kubectl port-forward -n adlab svc/adlab-api 3000:3000
```

This comes back healthy even though nothing in `k8s/` runs MongoDB — no Deployment, no Service, no
PVC. `MONGO_URL` in the Secret points at a hostname (`mongodb`) that simply doesn't exist in this
cluster. The API doesn't crash because `mongo.ts`'s connection plugin is written to catch that
failure, log a warning, and continue — a design choice made for exactly this situation, where Mongo
is genuinely optional infrastructure. It's worth checking the logs once to see that warning for
yourself rather than just trusting it's there:

```bash
kubectl logs -n adlab deploy/adlab-api | grep -i mongo
```

## Why there's no Ingress

Earlier versions of this manifest set included one, routing `adlab.local` through minikube's
ingress-nginx addon. It's gone now — Kubernetes retired ingress-nginx (no further releases, bug
fixes, or security patches), and a fresh minikube's own ingress addon can fail its own admission
webhook before you've changed anything yourself. `kubectl port-forward` covers local access without
depending on any of that. If you want Ingress or Gateway API for something beyond a lab, that's a
deliberate addition you'd make yourself, not something this project defaults to.

## Try it

```bash
kubectl scale deployment adlab-api -n adlab --replicas=4
kubectl get pods -n adlab -w
```

Watch it settle back toward what the HPA actually wants based on current load, not toward 4. Nothing
enforced that *here* — no ArgoCD is watching yet — it's purely the HPA's own controller loop
correcting a manual override it disagrees with. Chapter 11 adds a second layer on top of this same
mechanism.

## What's next

Chapter 11 installs ArgoCD and hands it this exact, already-running deployment — and covers a debugging
session that turned out to be less about Kubernetes and more about five months of accumulated state
nobody had actually looked at closely until today.
