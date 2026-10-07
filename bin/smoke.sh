#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  smoke.sh — end-to-end check of a running AdLab (the core profile is enough).
#  Creates a few uniquely named records on every run. Exits non-zero on failure.
#  Usage: bin/smoke.sh          (override the target with BASE=http://host:port)
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

BASE="${BASE:-http://localhost:3000}"
GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'
failures=0
pass() { echo -e "  ${GREEN}✓${NC} $1"; }
fail() { echo -e "  ${RED}✗${NC} $1"; failures=$((failures + 1)); }

TMP=$(mktemp); trap 'rm -f "$TMP"' EXIT
CODE=""; BODY=""

# http METHOD PATH [JSON_BODY]  →  sets CODE and BODY
http() {
  local method=$1 path=$2 data=${3:-}
  if [ -n "$data" ]; then
    CODE=$(curl -s -m 15 -o "$TMP" -w '%{http_code}' -X "$method" \
      -H 'Content-Type: application/json' -d "$data" "$BASE$path" || true)
  else
    CODE=$(curl -s -m 15 -o "$TMP" -w '%{http_code}' -X "$method" "$BASE$path" || true)
  fi
  BODY=$(cat "$TMP" 2>/dev/null || true)
}

# expect2xx NAME METHOD PATH [JSON_BODY]
expect2xx() {
  http "$2" "$3" "${4:-}"
  case "$CODE" in
    2??) pass "$1 ($CODE)" ;;
    *)   fail "$1 → HTTP $CODE: ${BODY:0:200}" ;;
  esac
}

json_field() {
  printf '%s' "$BODY" | python3 -c '
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get(sys.argv[1], "") if isinstance(d, dict) else "")
except Exception:
    print("")
' "$1"
}

# $(date +%s) alone is second-resolution — two invocations within the same
# second (this script calls itself from e2e.sh right after a standalone CI
# run of it) produce the same TS and collide on the unique email below.
# $RANDOM is reseeded per process and makes that collision practically
# impossible, on both GNU and BSD bash — no dependency on a `date` extension
# that macOS's date doesn't support.
TS="$(date +%s)-$RANDOM"
echo "AdLab smoke test → $BASE"

http GET /health
if [ "$CODE" = "000" ]; then
  echo -e "  ${RED}✗${NC} API not reachable at $BASE — is the stack up? (./start.sh)"
  exit 1
fi
case "$CODE" in
  2??) pass "GET /health ($CODE)" ;;
  *)   fail "GET /health → HTTP $CODE: ${BODY:0:200}" ;;
esac

http GET /v1/metrics/health
if [ "$CODE" = "200" ] && printf '%s' "$BODY" | grep -q '"elasticsearch":"ok"' \
                       && printf '%s' "$BODY" | grep -q '"redis":"ok"'; then
  pass "Elasticsearch and Redis reachable from the API"
else
  fail "GET /v1/metrics/health → HTTP $CODE: ${BODY:0:200}"
fi

# Classic CRUD (Postgres)
http POST /v1/advertisers "{\"name\":\"Smoke $TS\",\"email\":\"smoke+$TS@example.com\",\"tier\":\"PREMIUM\"}"
case "$CODE" in
  2??) pass "POST /v1/advertisers ($CODE)"; ADV_ID=$(json_field id) ;;
  *)   fail "POST /v1/advertisers → HTTP $CODE: ${BODY:0:200}"; ADV_ID="" ;;
esac
expect2xx "GET /v1/advertisers" GET /v1/advertisers

if [ -n "$ADV_ID" ]; then
  expect2xx "POST /v1/campaigns" POST /v1/campaigns \
    "{\"name\":\"Smoke campaign $TS\",\"advertiserId\":\"$ADV_ID\",\"budget\":50000,\"startDate\":\"2026-06-01T00:00:00Z\",\"status\":\"ACTIVE\"}"
else
  fail "POST /v1/campaigns skipped — no 'id' field in the advertiser response"
fi

# CQRS (write → Postgres + Elasticsearch projection, read → Elasticsearch)
expect2xx "POST /v1/cqrs/advertisers" POST /v1/cqrs/advertisers \
  "{\"name\":\"Smoke CQRS $TS\",\"email\":\"smoke-cqrs+$TS@example.com\",\"tier\":\"STANDARD\"}"
expect2xx "GET /v1/cqrs/advertisers" GET /v1/cqrs/advertisers
expect2xx "GET /v1/cqrs/advertisers/stats" GET /v1/cqrs/advertisers/stats

# GraphQL
http POST /graphql '{"query":"{ advertisers { id name email tier campaigns { id name status } } }"}'
if [ "$CODE" = "200" ] && ! printf '%s' "$BODY" | grep -q '"errors"'; then
  pass "POST /graphql (200, no errors)"
else
  fail "POST /graphql → HTTP $CODE: ${BODY:0:200}"
fi

# Analytics (returns an empty list until events have been produced and aggregated)
expect2xx "GET /v1/metrics/trending" GET "/v1/metrics/trending?limit=5"

# Kong is optional (gateway profile)
kong=$(curl -s -m 3 -o /dev/null -w '%{http_code}' http://localhost:8000/health || true)
if [ "$kong" = "200" ]; then
  pass "Kong proxies /health on :8000"
else
  echo -e "  ${YELLOW}-${NC} Kong not running (gateway profile) — skipped"
fi

echo ""
if [ "$failures" -eq 0 ]; then
  echo -e "${GREEN}All checks passed.${NC}"
else
  echo -e "${RED}${failures} check(s) failed.${NC}"
fi
exit "$failures"
