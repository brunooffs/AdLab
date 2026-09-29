#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  e2e.sh — end-to-end regression check of the whole pipeline
#
#      producer → Kafka → Spark Structured Streaming → Elasticsearch → API
#
#  Proves that every click the producer emitted is counted exactly once in all four
#  aggregate indices, and that the API reports the same numbers. Run it after every
#  upgrade or configuration change.
#
#  Isolation: it uses a throw-away Kafka topic, so events from earlier runs cannot
#  pollute the counts. It DOES reset the AdLab aggregate indices and Spark
#  checkpoints (exactly like ./spark.sh) and stops any Spark job you have running.
#
#  Needs:  ./start.sh streaming
#  Usage:  bin/e2e.sh
#  Env:    EVENTS=300  RATE=50  TIMEOUT=240 (seconds to wait for aggregates)  POLL=5
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail
cd "$(dirname "$0")/.."

EVENTS=${EVENTS:-300}
RATE=${RATE:-50}
TIMEOUT=${TIMEOUT:-240}
POLL=${POLL:-5}
API=${API:-http://localhost:3000}
ES=${ES:-http://localhost:9200}
TOPIC="e2e-$(date +%s)"
STOP_FILE=/tmp/adlab-spark-stop
WORK=$(mktemp -d "${TMPDIR:-/tmp}/adlab-e2e.XXXXXX")
SPARK_PID=""
failures=0

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
step() { echo -e "\n${CYAN}▸ $1${NC}"; }
pass() { echo -e "  ${GREEN}✓${NC} $1"; }
fail() { echo -e "  ${RED}✗${NC} $1"; failures=$((failures + 1)); }
die()  { echo -e "  ${RED}✗${NC} $1"; exit 1; }
kx()   { docker exec kafka /opt/kafka/bin/"$@"; }
show_log_problems() {   # show_log_problems FILE — first errors (the root cause) + the tail
  echo "  --- first errors in $(basename "$1") ---"
  grep -nE "ERROR|Exception|Caused by|Traceback" "$1" 2>/dev/null | head -12 | cut -c1-220 | sed 's/^/      /'
  echo "  --- last 6 lines ---"
  tail -6 "$1" 2>/dev/null | cut -c1-220 | sed 's/^/      /'
}
save_logs() {           # keep everything needed to debug a failed run
  local dir=".e2e-logs/$TOPIC" c
  mkdir -p "$dir" && printf '*\n' > .e2e-logs/.gitignore      # the directory ignores itself
  cp "$WORK"/*.log "$dir"/ 2>/dev/null || true
  for c in kafka spark-master spark-worker elasticsearch api; do
    docker logs --tail 300 "$c" > "$dir/container-$c.log" 2>&1 || true
  done
  echo -e "\n${YELLOW}Logs saved in $dir/${NC}"
}
# No `docker ps | grep -q`: under pipefail, grep exiting early can make the pipeline "fail".
running() { local names; names=$(docker ps --format '{{.Names}}' 2>/dev/null) || return 1; grep -qx "$1" <<< "$names"; }

cleanup() {
  local rc=$?
  docker exec spark-master touch "$STOP_FILE" >/dev/null 2>&1 || true
  if [ -n "$SPARK_PID" ]; then
    for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
      kill -0 "$SPARK_PID" 2>/dev/null || break
      sleep 2
    done
    kill "$SPARK_PID" 2>/dev/null || true
  fi
  kx kafka-topics.sh --bootstrap-server localhost:9092 --delete --topic "$TOPIC" >/dev/null 2>&1 || true
  [ "$rc" -eq 0 ] || save_logs
  rm -rf "$WORK"
}
trap cleanup EXIT
trap 'exit 130' INT TERM

es_sum() {   # es_sum INDEX  →  integer total of click_count, or empty if unavailable
  curl -s -X POST "$ES/$1/_refresh" >/dev/null 2>&1
  curl -s "$ES/$1/_search?size=0" -H 'Content-Type: application/json' \
    -d '{"aggs":{"t":{"sum":{"field":"click_count"}}}}' 2>/dev/null | python3 -c '
import sys, json
try:
    print(int(round(json.load(sys.stdin)["aggregations"]["t"]["value"] or 0)))
except Exception:
    print("")'
}

echo -e "${CYAN}=== AdLab end-to-end regression ===${NC}"
echo "  topic $TOPIC | $EVENTS events at $RATE/s | timeout ${TIMEOUT}s"
echo -e "  ${YELLOW}Note: resets the aggregate indices and Spark checkpoints, like ./spark.sh${NC}"

# ── Prerequisites ────────────────────────────────────────────────────────────
step "Prerequisites"
command -v python3 >/dev/null 2>&1 || die "python3 is required"
for c in api elasticsearch kafka spark-master spark-worker; do
  running "$c" || die "container '$c' is not running — start the stack with:  ./start.sh streaming"
done
curl -sf "$API/health" >/dev/null 2>&1 || die "API not healthy at $API"
pass "streaming stack is up"

# ── API sanity ───────────────────────────────────────────────────────────────
step "API sanity"
if bash bin/smoke.sh >"$WORK/smoke.log" 2>&1; then
  pass "bin/smoke.sh passed"
else
  fail "bin/smoke.sh failed:"; sed 's/^/      /' "$WORK/smoke.log" | tail -12
fi
metrics=$(curl -sf "$API/metrics" 2>/dev/null || true)
if grep -q '^http_request_duration_seconds_bucket' <<< "$metrics"; then
  pass "API exposes Prometheus histogram metrics"
else
  fail "API /metrics has no http_request_duration_seconds_bucket series"
fi

# ── Topic + Spark ────────────────────────────────────────────────────────────
step "Kafka topic and Spark job"
kx kafka-topics.sh --bootstrap-server localhost:9092 --create --topic "$TOPIC" \
  --partitions 3 --replication-factor 1 >/dev/null 2>&1 \
  || die "could not create topic $TOPIC"
pass "created topic $TOPIC (3 partitions)"

docker exec spark-master rm -f "$STOP_FILE" >/dev/null 2>&1 || true
SPARK_APP=adclick_runner.py RUN_SECONDS=$((TIMEOUT + 240)) STOP_FILE="$STOP_FILE" KAFKA_TOPIC="$TOPIC" \
  ./spark.sh >"$WORK/spark.log" 2>&1 &
SPARK_PID=$!

ready=0
for _ in $(seq 1 75); do
  if grep -q "streaming queries running" "$WORK/spark.log" 2>/dev/null; then ready=1; break; fi
  kill -0 "$SPARK_PID" 2>/dev/null || break
  sleep 2
done
if [ "$ready" -ne 1 ]; then
  show_log_problems "$WORK/spark.log"
  die "Spark job did not start (waited 150s)"
fi
pass "Spark job running (4 streaming queries)"

# ── Produce ──────────────────────────────────────────────────────────────────
step "Producing $EVENTS events"
docker compose --profile streaming --profile tools run --rm -e KAFKA_TOPIC="$TOPIC" producer \
  python producer.py --events "$EVENTS" --rate "$RATE" >"$WORK/producer.log" 2>&1
prod_rc=$?
sent=$(sed -n 's/.*Done\. Sent \([0-9][0-9]*\) events.*/\1/p' "$WORK/producer.log" | tail -1)
if [ "$prod_rc" -eq 0 ] && [ "${sent:-0}" = "$EVENTS" ]; then
  pass "producer sent $sent events"
else
  echo "  --- producer output (last 15 lines) ---"; tail -15 "$WORK/producer.log" | sed 's/^/      /'
  die "producer failed (exit $prod_rc, sent=${sent:-?})"
fi

# ── Ground truth from Kafka itself ───────────────────────────────────────────
step "Counting events in Kafka (ground truth)"
truth=$(kx kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic "$TOPIC" \
  --from-beginning --timeout-ms 15000 2>/dev/null | python3 -c '
import sys, json
total = clicks = 0
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        e = json.loads(line)
    except ValueError:
        continue
    total += 1
    clicks += 1 if e.get("action") == "click" else 0
print(total, clicks)')
read -r kafka_total clicks <<< "${truth:-0 0}"
if [ "$kafka_total" = "$EVENTS" ]; then
  pass "Kafka holds $kafka_total events, of which $clicks are clicks"
else
  fail "Kafka holds $kafka_total events, expected $EVENTS"
fi
[ "${clicks:-0}" -gt 0 ] || die "no click events were generated; rerun with a larger EVENTS"

# ── Aggregates in Elasticsearch ──────────────────────────────────────────────
step "Waiting for Spark to aggregate into Elasticsearch (up to ${TIMEOUT}s)"
deadline=$(( $(date +%s) + TIMEOUT )); got=""; spark_dead=0
while [ "$(date +%s)" -lt "$deadline" ]; do
  got=$(es_sum item-click-counts)
  [ "$got" = "$clicks" ] && break
  if [ -n "$got" ] && [ "$got" -gt "$clicks" ]; then break; fi        # double counting
  kill -0 "$SPARK_PID" 2>/dev/null || { spark_dead=1; break; }
  sleep "$POLL"
done
if [ "$spark_dead" -eq 1 ] && [ "$got" != "$clicks" ]; then
  fail "the Spark job exited before the aggregates arrived"
  show_log_problems "$WORK/spark.log"
  exit 1          # everything after this would only be a consequence of the crash
fi
if [ "$got" = "$clicks" ]; then
  pass "item-click-counts: $got clicks (matches Kafka)"
else
  fail "item-click-counts: got '${got:-none}', expected $clicks"
  show_log_problems "$WORK/spark.log"
fi
for idx in clicks-per-market clicks-per-adtype clicks-per-campaign; do
  v=""
  for _ in 1 2 3 4 5 6 7 8 9 10 11 12; do
    v=$(es_sum "$idx"); [ "$v" = "$clicks" ] && break; sleep "$POLL"
  done
  if [ "$v" = "$clicks" ]; then pass "$idx: $v clicks"; else fail "$idx: got '${v:-none}', expected $clicks"; fi
done

# ── API reads the same numbers ───────────────────────────────────────────────
step "API agrees with Elasticsearch"
trend=$(curl -s "$API/v1/metrics/trending?limit=100")
read -r api_total top_ad top_clicks <<< "$(printf '%s' "$trend" | python3 -c '
import sys, json
try:
    ads = json.load(sys.stdin)["ads"]
    top = max(ads, key=lambda a: a["clicks"]) if ads else {"ad_id": "-", "clicks": 0}
    print(sum(a["clicks"] for a in ads), top["ad_id"], top["clicks"])
except Exception:
    print("-1 - 0")')"
if [ "$api_total" = "$clicks" ]; then
  pass "/v1/metrics/trending sums to $api_total clicks"
else
  fail "/v1/metrics/trending sums to '$api_total', expected $clicks"
fi
now=$(date +%s)
one=$(curl -s "$API/v1/metrics/clicks?ad_id=$top_ad&from=$((now - 3600))&to=$((now + 120))" | python3 -c '
import sys, json
try:
    print(json.load(sys.stdin)["clicks"])
except Exception:
    print("")')
if [ "$one" = "$top_clicks" ]; then
  pass "/v1/metrics/clicks for $top_ad = $one (matches trending)"
else
  fail "/v1/metrics/clicks for $top_ad = '${one:-none}', trending says $top_clicks"
fi

# ── Stop cleanly ─────────────────────────────────────────────────────────────
step "Stopping the Spark job"
docker exec spark-master touch "$STOP_FILE" >/dev/null 2>&1 || true
for _ in $(seq 1 30); do kill -0 "$SPARK_PID" 2>/dev/null || break; sleep 2; done
if kill -0 "$SPARK_PID" 2>/dev/null; then
  fail "Spark job did not stop within 60s"
elif grep -q "Streaming queries stopped" "$WORK/spark.log"; then
  pass "Spark job stopped cleanly"
else
  fail "Spark job ended without the clean-stop message"
fi
SPARK_PID=""

echo ""
if [ "$failures" -eq 0 ]; then
  echo -e "${GREEN}E2E PASSED${NC} — $EVENTS events → $clicks clicks, counted exactly once end to end (${SECONDS}s)"
else
  echo -e "${RED}E2E FAILED${NC} — $failures check(s) failed (${SECONDS}s)"
fi
exit "$failures"
