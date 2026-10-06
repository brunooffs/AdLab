#!/usr/bin/env bash
# k8s-preflight.sh — checks the Kubernetes/ArgoCD path's prerequisites
# before you start the manual steps in k8s/README.md. Deliberately a check,
# not an installer or an orchestrator: unlike bin/preflight.sh for the
# Compose side, this project's K8s/GitOps chapters are built around doing
# each step by hand, one layer at a time (see tutorial/chapters/10 and 11
# for why) — this script just makes sure you're not eight commands deep
# before discovering something's missing.
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()  { echo -e "  ${GREEN}✓${NC} $1"; }
bad() { echo -e "  ${RED}✗${NC} $1"; FAILED=1; }
opt() { echo -e "  ${YELLOW}○${NC} $1"; }
FAILED=0

echo "K8s/ArgoCD preflight:"
echo

if command -v minikube >/dev/null 2>&1; then
  ok "minikube ($(minikube version --short 2>/dev/null || minikube version | head -1))"
else
  bad "minikube not found. Install: https://minikube.sigs.k8s.io/docs/start/"
fi

if command -v kubectl >/dev/null 2>&1; then
  ok "kubectl ($(kubectl version --client -o json 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin)["clientVersion"]["gitVersion"])' 2>/dev/null || echo 'version unknown'))"
else
  bad "kubectl not found. Install: https://kubernetes.io/docs/tasks/tools/#kubectl"
fi

if command -v docker >/dev/null 2>&1; then
  ok "docker (minikube's default driver)"
else
  bad "docker not found — needed as minikube's driver (see bin/preflight.sh for the Compose-side Docker checks)"
fi

if command -v helm >/dev/null 2>&1; then
  ok "helm ($(helm version --short 2>/dev/null || echo 'version unknown'))"
else
  opt "helm not found — only needed for the Helm-based ArgoCD install (Chapter 14). Install: https://helm.sh/docs/intro/install/"
fi

echo
if [ "$FAILED" -eq 1 ]; then
  echo -e "${YELLOW}Install what's missing above, then see k8s/README.md for the manual setup steps.${NC}"
  exit 1
else
  echo -e "${GREEN}All set.${NC} Manual setup steps are in k8s/README.md — minikube start, apply the base manifests, install ArgoCD."
fi
