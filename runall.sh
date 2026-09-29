#!/usr/bin/env bash
echo "== Prometheus targets"; curl -s localhost:9090/api/v1/targets | python3 -c 'import sys,json
for t in json.load(sys.stdin)["data"]["activeTargets"]: print(" ", t["labels"]["job"], t["health"], (t.get("lastError") or "")[:90])'

echo "== API metrics reached Prometheus"; curl -s -G localhost:9090/api/v1/query --data-urlencode 'query=sum(http_requests_total)' | python3 -c 'import sys,json; r=json.load(sys.stdin)["data"]["result"]; print("  series found:", len(r))'

echo "== Grafana datasources + dashboards"; curl -s -u admin:admin localhost:3001/api/datasources | python3 -c 'import sys,json
for d in json.load(sys.stdin): print(" ", d["name"], d["type"], "(default)" if d["isDefault"] else "")'
curl -s -u admin:admin 'localhost:3001/api/search?type=dash-db' | python3 -c 'import sys,json
for d in json.load(sys.stdin): print("  dashboard:", d["title"])'

echo "== Tempo has traces from the API"; curl -s -G localhost:3200/api/search --data-urlencode 'tags=service.name=adlab-api' --data-urlencode limit=3 | python3 -c 'import sys,json; print("  traces found:", len(json.load(sys.stdin).get("traces",[])))'

echo "== Kafka UI sees the cluster"; curl -s localhost:8080/api/clusters | python3 -c 'import sys,json
for c in json.load(sys.stdin): print(" ", c["name"], c["status"])'

echo "== Kibana dashboard + Keycloak"; curl -s 'localhost:5601/api/saved_objects/_find?type=dashboard' | python3 -c 'import sys,json
for o in json.load(sys.stdin)["saved_objects"]: print("  dashboard:", o["attributes"]["title"])'
curl -s -o /dev/null -w '  keycloak master realm: HTTP %{http_code}\n' localhost:8180/realms/master