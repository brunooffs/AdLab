#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  preflight.sh — sanity-check the machine before starting AdLab.
#  Usage: bin/preflight.sh [profile ...]   (called by ./start.sh)
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'; NC='\033[0m'
fail=0
ok()   { echo -e "  ${GREEN}✓${NC} $1"; }
warn() { echo -e "  ${YELLOW}!${NC} $1"; }
bad()  { echo -e "  ${RED}✗${NC} $1"; fail=1; }

echo "Preflight checks:"

if ! command -v docker >/dev/null 2>&1; then
  bad "docker not found — install Docker Desktop or Docker Engine"; exit 1
fi
if ! docker info >/dev/null 2>&1; then
  bad "Docker daemon is not running"; exit 1
fi
ok "Docker daemon reachable"

if docker compose version >/dev/null 2>&1; then
  ok "Compose v2 ($(docker compose version --short 2>/dev/null))"
else
  bad "Docker Compose v2 plugin missing (the 'docker compose' command)"
fi

# spark/Dockerfile uses `ADD --chmod`, a BuildKit-only feature. Without the
# buildx CLI plugin, `docker compose build` silently falls back to the legacy
# builder and fails ~50s into the build with a cryptic "--chmod option
# requires BuildKit" error — only checked when the streaming profile (which
# builds spark/Dockerfile) is actually requested.
for profile in "$@"; do
  if [ "$profile" = "streaming" ]; then
    if docker buildx version >/dev/null 2>&1; then
      ok "buildx ($(docker buildx version 2>/dev/null | awk '{print $2; exit}'))"
    else
      bad "docker buildx plugin missing — required to build the Spark image. See CONTRIBUTING.md#troubleshooting"
    fi
    break
  fi
done

# Memory available to Docker (on macOS/Windows this is the VM's allocation).
mem_bytes=$(docker info --format '{{.MemTotal}}' 2>/dev/null || echo 0)
mem_gb=$(( ${mem_bytes:-0} / 1073741824 ))
if   [ "$mem_gb" -ge 14 ]; then ok "Docker has ${mem_gb} GB of memory — enough for every profile"
elif [ "$mem_gb" -ge 8 ];  then warn "Docker has ${mem_gb} GB — fine for core; streaming + analytics together may be tight"
else warn "Docker has only ${mem_gb} GB — raise it in Docker Desktop → Settings → Resources"
fi

# Elasticsearch refuses to boot on a native Linux host with a low vm.max_map_count.
if [ "$(uname -s)" = "Linux" ] && [ -r /proc/sys/vm/max_map_count ]; then
  mmc=$(cat /proc/sys/vm/max_map_count)
  if [ "$mmc" -ge 262144 ]; then
    ok "vm.max_map_count = $mmc"
  else
    bad "vm.max_map_count = $mmc (Elasticsearch needs >= 262144). Fix: sudo sysctl -w vm.max_map_count=262144"
  fi
fi

# True if something already listens on 127.0.0.1:PORT (where compose will bind).
# Pure bash — needs neither lsof nor ss.
port_in_use() { (exec 3<>"/dev/tcp/127.0.0.1/$1") >/dev/null 2>&1; }

# Is a container running? (No `docker ps | grep -q`: under pipefail it can report failure.)
running() { local names; names=$(docker ps --format '{{.Names}}' 2>/dev/null) || return 1; grep -qx "$1" <<< "$names"; }

# Ports each profile publishes on the host (core is always started).
ports_for() {
  case "$1" in
    core)          echo "3000 5432 6379 9200 27017" ;;
    gateway)       echo "8000 8001" ;;
    streaming)     echo "9092 9094 8080 8081 8082 7077" ;;
    analytics)     echo "5601" ;;
    observability) echo "9090 3001 3200 4317 4318" ;;
    extras)        echo "9042 8180" ;;
  esac
}

# Only check ports if AdLab is not already running (otherwise we'd flag ourselves).
if ! running api; then
  busy=""
  for profile in core "$@"; do
    for port in $(ports_for "$profile"); do
      port_in_use "$port" && busy="$busy $port"
    done
  done
  if [ -n "$busy" ]; then
    bad "ports already in use:$busy — stop whatever holds them (an older stack? a local Postgres/Redis?)"
  else
    ok "required ports are free"
  fi
fi

exit $fail
