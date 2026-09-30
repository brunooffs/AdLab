#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  k8s-seal-secrets.sh — one-time migration from plaintext k8s/base/secrets.yaml
#  to a SealedSecret that's safe to commit to a public repo.
#
#  Run this AFTER:
#    1. The Sealed Secrets controller is installed in your cluster:
#         kubectl apply -f https://github.com/bitnami/sealed-secrets/releases/download/v0.40.0/controller.yaml
#    2. It's actually running:
#         kubectl get pods -n kube-system -l app.kubernetes.io/name=sealed-secrets
#    3. kubeseal is installed locally — brew install kubeseal, or see k8s/README.md
#
#  This script only WRITES a new file (k8s/base/sealed-secrets.yaml). It does
#  NOT delete the plaintext secrets.yaml, edit kustomization.yaml, or commit
#  anything — review the output first. The steps that follow are printed at
#  the end, not automated, on purpose: once the plaintext is gone, undoing a
#  bad seal means re-deriving it from memory or a backup.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail
cd "$(dirname "$0")/.."

RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'; NC='\033[0m'

if ! command -v kubeseal >/dev/null 2>&1; then
  echo -e "${RED}kubeseal not found.${NC} Install: brew install kubeseal (or see k8s/README.md)"
  exit 1
fi

if ! kubectl get pods -n kube-system -l app.kubernetes.io/name=sealed-secrets 2>/dev/null | grep -q Running; then
  echo -e "${RED}The sealed-secrets controller isn't running in kube-system.${NC}"
  echo "  Install it:  kubectl apply -f https://github.com/bitnami/sealed-secrets/releases/download/v0.40.0/controller.yaml"
  echo "  Then wait for it:  kubectl get pods -n kube-system -l app.kubernetes.io/name=sealed-secrets -w"
  exit 1
fi

if [ ! -f k8s/base/secrets.yaml ]; then
  echo -e "${RED}k8s/base/secrets.yaml not found${NC} — already migrated?"
  exit 1
fi

echo -e "${YELLOW}Sealing k8s/base/secrets.yaml -> k8s/base/sealed-secrets.yaml ...${NC}"
kubeseal --format yaml < k8s/base/secrets.yaml > k8s/base/sealed-secrets.yaml

echo -e "\n${GREEN}Wrote k8s/base/sealed-secrets.yaml${NC} — encrypted to THIS cluster's key only."
echo "Safe to commit as-is: without this exact cluster's private key, the values in it are unreadable."
echo ""
echo -e "${YELLOW}Next steps — review the output above, then do these yourself:${NC}"
echo "  1. Back up the controller's private key NOW, before anything else:"
echo "       kubectl get secret -n kube-system -l sealedsecrets.bitnami.com/sealed-secrets-key -o yaml \\"
echo "         > sealed-secrets-key-backup.yaml"
echo "     Store that file somewhere OUTSIDE git — a password manager, an encrypted volume."
echo "     Losing it means every sealed secret you ever create becomes permanently undecryptable."
echo "     ('sealed-secrets-key-backup.yaml' is already in .gitignore for exactly this reason.)"
echo "  2. git add k8s/base/sealed-secrets.yaml"
echo "  3. git rm k8s/base/secrets.yaml"
echo "  4. In k8s/kustomization.yaml, replace the 'base/secrets.yaml' line with 'base/sealed-secrets.yaml'"
echo "  5. git add k8s/kustomization.yaml && git commit -m 'k8s: move secrets to SealedSecret'"
