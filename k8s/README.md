# AdLab — Kubernetes Manifests

## Structure

```
k8s/
├── kustomization.yaml         ← root — ArgoCD reads this
├── base/
│   ├── namespace.yaml         ← adlab namespace
│   ├── configmap.yaml         ← non-secret config
│   └── secrets.yaml           ← passwords and keys (base64)
├── postgres/
│   └── postgres.yaml          ← StatefulSet + Service + PVC
├── redis/
│   └── redis.yaml             ← Deployment + Service + PVC
├── elasticsearch/
│   └── elasticsearch.yaml     ← StatefulSet + Service + PVC
├── api/
│   ├── api.yaml               ← Deployment + Service + HPA
│   └── ingress.yaml           ← Nginx Ingress → adlab.local
└── argocd/
    └── argocd-app.yaml        ← ArgoCD Application definition
```

## Prerequisites

```bash
# Start minikube
minikube start --driver=docker --cpus=4 --memory=6g

# Enable ingress addon
minikube addons enable ingress

# Add to /etc/hosts
echo "$(minikube ip) adlab.local" | sudo tee -a /etc/hosts
```

## Manual deploy (without ArgoCD)

```bash
# Apply everything
kubectl apply -k k8s/

# Watch pods come up
kubectl get pods -n adlab -w

# Run Prisma migrations
kubectl exec -n adlab deploy/adlab-api -- npx prisma migrate deploy

# Access the API
curl http://adlab.local/health
curl http://adlab.local/v1/advertisers
```

## ArgoCD deploy

```bash
# Install ArgoCD
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# Wait for ArgoCD to be ready
kubectl wait --for=condition=available --timeout=300s deployment/argocd-server -n argocd

# Get initial admin password
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d

# Port-forward ArgoCD UI
kubectl port-forward svc/argocd-server -n argocd 8090:443

# Open https://localhost:8090 → login admin / <password above>

# Apply the Application definition
kubectl apply -f k8s/argocd/argocd-app.yaml

# ArgoCD will now auto-sync from GitHub on every push
```

## Useful commands

```bash
# Watch all pods
kubectl get pods -n adlab -w

# Describe a failing pod
kubectl describe pod -n adlab <pod-name>

# Check API logs
kubectl logs -n adlab deploy/adlab-api -f

# Scale API manually
kubectl scale deployment adlab-api -n adlab --replicas=3

# Check HPA status
kubectl get hpa -n adlab

# Port-forward API for local testing
kubectl port-forward -n adlab svc/adlab-api 3000:3000
```
