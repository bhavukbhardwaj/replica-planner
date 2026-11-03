# Technical walkthrough

## One request, end to end
```
client ──X-API-Token──▶ FastAPI /plan
  1 auth (constant-time compare vs PLAN_API_TOKEN)           → 401
  2 pydantic validation (strict int, enum env, id pattern)    → 422
  3 agent loop (≤4 model turns, provider timeout)
      model ──tool call──▶ allowlist + strict args + must equal request's service/env
      tool  ──fixture JSON (validated) + evidence refs──▶ model
      model ──{explanation, evidence_refs}
  4 reject unless both tools were used and every ref was returned by a tool   → 502
  5 policy.decide(request, tool-fetched state, tool-fetched policy)   [no model input]
  6 code builds artifact, verification and rollback text → PlanResponse
```
Files: `app/main.py` (flow), `app/agent.py` (loop/validation), `app/tools.py` (allowlist, fixtures), `app/policy.py` (decision), `app/models/*` (fake and OpenAI-compatible/Ollama clients).

## Trust boundaries
- **Untrusted:** the `reason` text and everything the model emits. `reason` is sent to the model only as a JSON field, and code never parses it.
- **Trusted:** the request's numeric target and identifiers (after validation), fixtures (read by code), and `policy.py`.
- The model cannot influence decision, target, artifact, verification or rollback. Its only effect is the `explanation` string, which is display-only, plus which allowed tool it calls first.

## Decision precedence (`policy.py`)
Missing/invalid state or policy → `blocked` (fail safe) → out of range (env limits ∩ fixture policy) `blocked` → equal `no_change` → increase with error rate >5% `blocked` → production `requires_approval` → `allowed`. Artifacts (service, environment, previous, proposed replicas only) exist only for `allowed`/`requires_approval`; responses always say `applied: false`.

## Tradeoffs
- Code-owned decisions make the "agent" mostly a context gatherer and explainer. This is intentional: the model adds value (tool selection, readable rationale), and correctness never depends on it.
- Invalid model output is **rejected** (502) rather than patched, so errors are visible; the cost is occasional failures with weak models.
- Model-visible tool arguments must match the request, which prevents the model from reading other services.
- Plain `httpx` against an OpenAI-compatible API avoids an agent framework and works with Ollama or hosted providers.

## Failure behavior
Bad token 401; malformed input 422; unknown service/env 404; missing policy → `blocked` with no artifact; provider timeout/error 502 `model_provider_unavailable`; rejected model output 502. Unexpected errors return a generic 500. Logs hold decisions and error class names only: never tokens, keys, the reason text, or stack traces in responses.

## Tests (`uv run pytest -q`, offline)
`FakeModel` is a scriptable double. Tests assert decisions and artifacts, not prose: dev allowed vs prod approval; out-of-range, non-integer and missing/wrong token; no-change, unhealthy scale-up (and scale-down allowed); malicious reason, missing policy, unknown service; and seven bad-model behaviors (unauthorized tool, bad args, other service, fabricated evidence, invalid JSON, no tools, never finishing) plus provider failure.

## Reproduce
```bash
PLAN_API_TOKEN=demo-token MODEL_PROVIDER=ollama uv run uvicorn app.main:app &
PLAN_API_TOKEN=demo-token ./scripts/demo.sh        # normal: case 1; blocked: case 3; rejected: case 7 (401)
```
A genuine gpt-oss:20b run of all cases is in `docs/sample-real-model-run.txt`.

## Production gaps
Real inventory/metrics and policy sources; SSO and per-user authorization; audit log; rate limiting; secret management beyond env vars; prompt/model evaluation suite; approval-workflow integration; stricter handling of retries and concurrent requests; supply-chain scanning.
