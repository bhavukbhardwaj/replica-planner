#!/usr/bin/env bash
# Usage: PLAN_API_TOKEN=demo-token ./scripts/demo.sh [base_url]   (server must already be running)
BASE=${1:-http://localhost:8000}
H=(-H "X-API-Token: ${PLAN_API_TOKEN:-demo-token}" -H "Content-Type: application/json")
run() { echo "### $1"; shift; curl -s -X POST "$BASE/plan" "${H[@]}" -d "$1" | python3 -m json.tool; echo; }
run "1. allowed dev plan"            '{"service_id":"dev-healthy","environment":"development","desired_replicas":3,"reason":"traffic spike"}'
run "2. prod -> requires_approval"   '{"service_id":"prod-healthy","environment":"production","desired_replicas":5,"reason":"launch"}'
run "3. unhealthy scale-up -> blocked" '{"service_id":"dev-unhealthy","environment":"development","desired_replicas":4,"reason":"more capacity"}'
run "4. malicious reason"            "$(cat "$(dirname "$0")/../fixtures/malicious_request.json")"
run "5. no_change"                   '{"service_id":"dev-healthy","environment":"development","desired_replicas":2,"reason":"noop"}'
run "6. out of range -> blocked"     '{"service_id":"dev-healthy","environment":"development","desired_replicas":9,"reason":"too many"}'
echo "### 7. missing token -> 401"; curl -s -o /dev/null -w "%{http_code}\n" -X POST "$BASE/plan" -H "Content-Type: application/json" -d '{}'
