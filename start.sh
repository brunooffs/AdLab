#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  start.sh — Start AdLab. Services are grouped into compose profiles so you
#  bring up only what your machine (and the exercise) needs.
#
#  Usage: ./start.sh [profile ...] [--no-dashboard]
#    ./start.sh                        core: postgres, redis, mongodb, elasticsearch, api
#    ./start.sh streaming              + kafka, kafka-ui, spark
#    ./start.sh streaming analytics    + kibana
#    ./start.sh all                    gateway + streaming + analytics + observability
#  Profiles: gateway streaming analytics observability extras
#  ADLAB_SKIP_PREFLIGHT=1 skips the machine checks in bin/preflight.sh.
#  --no-dashboard skips starting the local control panel (dashboard/server.js) —
#  useful for CI/automation, where an extra background Node process nobody
#  asked for is more surprise than convenience.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail
cd "$(dirname "$0")"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; RED='\033[0;31m'; NC='\033[0m'
VALID="gateway streaming analytics observability extras"

# Strip --no-dashboard out before profile parsing, same way "all" is handled
# below — so it's never mistaken for an unknown profile name.
SKIP_DASHBOARD=0
ARGS=()
for a in "$@"; do
  if [ "$a" = "--no-dashboard" ]; then SKIP_DASHBOARD=1; else ARGS+=("$a"); fi
done
set -- "${ARGS[@]+"${ARGS[@]}"}"

if [ "${1:-}" = "all" ]; then set -- gateway streaming analytics observability; fi

PROFILE_ARGS=()
for p in "$@"; do
  case " $VALID " in
    *" $p "*) PROFILE_ARGS+=(--profile "$p") ;;
    *) echo -e "${RED}Unknown profile: $p${NC}  (valid: $VALID, or 'all')"; exit 1 ;;
  esac
done
REQUESTED=" $* "
has() { case "$REQUESTED" in *" $1 "*) return 0 ;; *) return 1 ;; esac; }

echo -e "${CYAN}=== AdLab — starting core${*:+ + $*} ===${NC}\n"

[ "${ADLAB_SKIP_PREFLIGHT:-0}" = "1" ] || bash bin/preflight.sh "$@"

# Compose orders startup itself: every depends_on has a health condition, and
# the one-shot 'migrate' service must finish before 'api' starts.
echo -e "\n${YELLOW}Building and starting services...${NC}"
docker compose ${PROFILE_ARGS[@]+"${PROFILE_ARGS[@]}"} up -d --build

echo -e "\n${YELLOW}Waiting for the API to become healthy...${NC}"
ready=0
for _ in $(seq 1 60); do
  if curl -sf http://localhost:3000/health >/dev/null 2>&1; then ready=1; break; fi
  printf "."; sleep 3
done
echo
if [ "$ready" -ne 1 ]; then
  echo -e "${RED}API did not become healthy within 3 minutes. Recent logs:${NC}"
  docker compose logs --tail=40 migrate api || true
  exit 1
fi

if has gateway; then
  echo -e "\n${YELLOW}Waiting for Kong...${NC}"
  kong_ready=0
  for _ in $(seq 1 30); do
    if curl -sf http://localhost:8000/health >/dev/null 2>&1; then kong_ready=1; break; fi
    printf "."; sleep 2
  done
  echo
  [ "$kong_ready" -eq 1 ] || echo -e "${YELLOW}Kong did not answer on :8000 within 60s — check: docker logs kong${NC}"
fi

if has analytics; then
  bash bin/setup-kibana.sh || echo -e "${YELLOW}Kibana import skipped — run bin/setup-kibana.sh once Kibana is up.${NC}"
fi

# Local control panel (dashboard/server.js) — a plain host-run Node process,
# not a container, same as it's always been when started manually. Everything
# else in this project deliberately needs no Node/Python on the host; this is
# the one exception, so a missing `node` degrades to a skip, not a failure.
DASHBOARD_URL="http://127.0.0.1:4400"
DASHBOARD_STARTED=0
start_dashboard() {
  if (echo > /dev/tcp/127.0.0.1/4400) 2>/dev/null; then
    echo -e "${YELLOW}Dashboard already running at ${DASHBOARD_URL}${NC}"
    DASHBOARD_STARTED=1
    return
  fi
  if ! command -v node >/dev/null 2>&1; then
    echo -e "${YELLOW}node not found on PATH — skipping dashboard (install Node, or run: node dashboard/server.js)${NC}"
    return
  fi
  nohup node dashboard/server.js > .dashboard.log 2>&1 &
  echo $! > .dashboard.pid
  sleep 1
  if kill -0 "$(cat .dashboard.pid)" 2>/dev/null; then
    echo -e "${GREEN}Dashboard started: ${DASHBOARD_URL}${NC}"
    DASHBOARD_STARTED=1
  else
    echo -e "${YELLOW}Dashboard failed to start — check .dashboard.log${NC}"
    rm -f .dashboard.pid
  fi
}
if [ "$SKIP_DASHBOARD" -ne 1 ]; then
  echo -e "\n${YELLOW}Starting the local dashboard...${NC}"
  start_dashboard
fi

echo -e "\n${YELLOW}Containers:${NC}"
docker compose ${PROFILE_ARGS[@]+"${PROFILE_ARGS[@]}"} ps --format "table {{.Name}}\t{{.Status}}"

echo -e "\n${GREEN}=== AdLab is up ===${NC}\n"
echo -e "${CYAN}URLs:${NC}"
echo "  API docs:      http://localhost:3000/docs"
echo "  Elasticsearch: http://localhost:9200"
has gateway       && echo "  Kong:          http://localhost:8000"
has streaming     && { echo "  Kafka UI:      http://localhost:8080"; echo "  Spark UI:      http://localhost:8081"; }
has analytics     && echo "  Kibana:        http://localhost:5601"
has observability && { echo "  Grafana:       http://localhost:3001  (admin/admin)"; echo "  Prometheus:    http://localhost:9090"; }
[ "$DASHBOARD_STARTED" -eq 1 ] && echo "  Dashboard:     ${DASHBOARD_URL}"
echo ""
echo -e "${CYAN}Next steps:${NC}"
echo "  ./bin/smoke.sh                 # verify the API end to end"
has streaming && echo "  ./produce.sh 500 5             # send events, then ./spark.sh to aggregate them"
has streaming || echo "  ./start.sh streaming           # add Kafka + Spark"
echo "  ./status.sh                    # health of everything"
echo ""
