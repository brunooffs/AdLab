#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  setup-kibana.sh — import the AdLab data views and dashboard into Kibana.
#  Idempotent: objects with the same id are overwritten. Called by ./start.sh
#  when the 'analytics' profile is requested; safe to run on its own.
#  Usage: bin/setup-kibana.sh        (override the target with KIBANA=http://host:port)
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail
cd "$(dirname "$0")/.."

KIBANA="${KIBANA:-http://localhost:5601}"
FILE="kibana-backup.ndjson"
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'

[ -f "$FILE" ] || { echo -e "${RED}Missing $FILE${NC}"; exit 1; }

# Fail fast when targeting the local stack and the container simply is not running.
case "$KIBANA" in
  http://localhost:*|http://127.0.0.1:*)
    if ! docker ps --format '{{.Names}}' 2>/dev/null | grep -q '^kibana$'; then
      echo -e "${RED}The kibana container is not running.${NC} Start it with:  ./start.sh analytics"
      exit 1
    fi ;;
esac

echo -e "${YELLOW}Waiting for Kibana at $KIBANA ...${NC}"
ready=0
for _ in $(seq 1 60); do
  if curl -sf "$KIBANA/api/status" 2>/dev/null | grep -Eq '"level" ?: ?"available"'; then ready=1; break; fi
  printf "."; sleep 3
done
echo
if [ "$ready" -ne 1 ]; then
  echo -e "${RED}Kibana did not become available within 3 minutes.${NC} Check:  docker logs --tail 30 kibana"
  exit 1
fi

resp=$(curl -s -X POST "$KIBANA/api/saved_objects/_import?overwrite=true" \
  -H "kbn-xsrf: true" --form "file=@$FILE" || true)
if printf '%s' "$resp" | grep -Eq '"success" ?: ?true'; then
  echo -e "${GREEN}Imported 4 data views and the dashboard.${NC}"
else
  echo -e "${RED}Import failed:${NC} ${resp:0:400}"
  exit 1
fi
echo "  Dashboard: $KIBANA/app/dashboards  →  \"AdLab — Ad Click Analytics\""
echo "  Panels fill in once events flow:  ./produce.sh 300 10   then   ./spark.sh"
