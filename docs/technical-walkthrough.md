# Technical walkthrough

## One request, end to end
Request: `prod-healthy`, `production`, 3 → 5 replicas, reason `"launch"`.

```
client ──X-API-Token──▶ FastAPI POST /plan                               app/main.py
  1 auth: constant-time compare with env PLAN_API_TOKEN            → 401    app/auth.py
  2 schema: strict int, env enum, id regex, reason ≤500 chars      → 422    app/schemas.py
  3 agent loop (≤4 model turns, provider timeout)                         app/agent.py
      system prompt + request as JSON data (reason is quoted, never instructions)
      model ─tool_calls─▶ allowlist? args valid? same service/env as request?  else 502
      tool  ─validated fixture data + evidence refs─▶ model                 app/tools.py
      model ─final JSON {explanation, evidence_refs}
  4 accept only if both tools ran and every ref came from a tool result → else 502
  5 policy.decide(env, desired, state, policy)  ← tool data only, no model text   app/policy.py
  6 code builds artifact, verification and rollback → PlanResponse (applied=false)
```
For this request the model calls `get_service_state` (3 replicas, 0.5% errors) and `get_deployment_policy` (2–10, approval required).
It answers with refs like `policy:prod-healthy:production:approval`. Code checks each ref against the set the tools returned.
`decide` walks the precedence and stops at "production → `requires_approval`". The artifact holds exactly `{service, environment, previous_replicas: 3, proposed_replicas: 5}`.

## Decision precedence (`app/policy.py`)
1. State or policy missing/invalid → `blocked` (fail safe)
2. Outside env limits ∩ fixture range (dev 1–5, prod 2–10) → `blocked`
3. Equal to current → `no_change` (a repeated request never invents a deployment)
4. Increase while error rate > 5% → `blocked`
5. Production → `requires_approval`
6. Otherwise → `allowed`

Only `allowed`/`requires_approval` carry an artifact.

## Trust boundaries
- **Untrusted:** the `reason` text and everything the model emits (tool names, arguments, prose, refs). Code never parses `reason`.
- **Trusted after validation:** the request's identifiers and numeric target, fixture data (schema-checked inside the tools), `policy.py`.
- **Model influence is limited to** which allowed tool it calls first and the display-only `explanation`. It cannot change the target, decision, artifact, verification or rollback.
  The real run shows why this matters: in case 3 of `docs/sample-real-model-run.txt`, gpt-oss:20b wrote "no approval required" for a request that code correctly `blocked`.

## Tradeoffs
- **Code decides, model gathers and explains.** This makes the agent narrower, but correctness never depends on model quality, and every rule can be unit-tested.
- **Reject, don't repair.** Bad model output returns 502 instead of being patched. Failures stay visible, at the cost of occasional rejections with weak models.
- **Tool args pinned to the request.** This stops the model from reading other services. Fine for a one-service planner.
- **No agent framework.** Plain `httpx` against an OpenAI-compatible API works with local Ollama or a hosted provider, and the loop stays easy to audit (~100 lines).

## Failure behavior
| Condition | Result |
|---|---|
| missing/wrong token | 401 |
| malformed body, non-integer replicas | 422 with field list |
| unknown service/environment | 404 |
| missing or invalid policy/state | 200 `blocked`, no artifact |
| provider timeout/HTTP error | 502 `model_provider_unavailable` |
| unauthorized tool, bad args, other service, fake refs, bad JSON, step cap hit | 502 `model_output_rejected` |
| anything unexpected | 500 `internal_error` (class name logged, no trace returned) |

Logs record service, environment and decision only. Never tokens, keys or the reason text, and a test asserts this.

## Tests
`uv run pytest -q` runs 23 offline tests. `FakeModel` is a scriptable double, and the tests assert status, decision and artifact, never prose. Coverage:
- dev allowed vs prod approval
- out-of-range, non-integer and malformed input
- missing/wrong token
- no-change, unhealthy scale-up (scale-down still allowed)
- malicious reason
- missing policy, unknown service, corrupt fixture
- seven misbehaving-model scripts and provider failure
- log hygiene

## Reproduce (offline, about 1 minute)
```bash
uv sync
PLAN_API_TOKEN=demo-token MODEL_PROVIDER=fake uv run uvicorn app.main:app --port 8000 &

# normal: allowed dev plan with artifact
curl -s -X POST localhost:8000/plan -H 'X-API-Token: demo-token' -H 'Content-Type: application/json' \
  -d '{"service_id":"dev-healthy","environment":"development","desired_replicas":3,"reason":"traffic"}'

# cannot proceed: unhealthy scale-up → "blocked", change_artifact null
curl -s -X POST localhost:8000/plan -H 'X-API-Token: demo-token' -H 'Content-Type: application/json' \
  -d '{"service_id":"dev-unhealthy","environment":"development","desired_replicas":4,"reason":"capacity"}'

# rejected: wrong token → 401
curl -s -o /dev/null -w '%{http_code}\n' -X POST localhost:8000/plan -H 'X-API-Token: wrong' -d '{}'
```
For the real model, use `MODEL_PROVIDER=ollama` (needs `ollama pull gpt-oss:20b`). `./scripts/demo.sh` runs all seven cases.

## Production gaps
- Real inventory, metrics and policy sources (still read-only)
- SSO and per-user authorization in place of the shared token
- Persistent audit log of every plan
- Integration with the change-approval workflow
- Rate limiting and an overall request deadline
- A secret manager in place of env vars
- A model evaluation suite and monitoring of the rejection rate
- CI with dependency and supply-chain scanning
