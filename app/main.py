import logging

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app import policy
from app.agent import AgentError, run_agent
from app.auth import require_token
from app.config import build_model
from app.models.base import ProviderError
from app.schemas import (Artifact, DeploymentPolicy, PlanRequest, PlanResponse,
                         ServiceState, StateView)

log = logging.getLogger("planner")
logging.basicConfig(level=logging.INFO)  # we never log tokens, keys, or the free-text reason


def _steps(decision: str, req: PlanRequest, prev: int | None) -> tuple[list[str], list[str]]:
    if decision in ("allowed", "requires_approval"):
        verify = [f"After a human applies the change, confirm {req.service_id} runs {req.desired_replicas} ready replicas in {req.environment}.",
                  "Watch error rate and latency for 15 minutes; it should not rise above the pre-change level.",
                  "Confirm no pending/crash-looping pods."]
        rollback = [f"Scale {req.service_id} back to {prev} replicas (manual; this service does not execute it).",
                    "Limitation: rollback does not undo effects of load shifted or requests failed during the change."]
    elif decision == "no_change":
        verify = ["Nothing to verify; no change was proposed."]
        rollback = ["Not applicable; no artifact was produced."]
    else:
        verify = ["Resolve the blocking condition, then submit a new request."]
        rollback = ["Not applicable; nothing was proposed or applied."]
    return verify, rollback


def create_app(model=None) -> FastAPI:
    app = FastAPI(title="Replica Planner")

    @app.exception_handler(RequestValidationError)
    async def _bad_input(_: Request, exc: RequestValidationError):
        errs = [{"field": ".".join(str(x) for x in e["loc"][1:]), "msg": e["msg"]} for e in exc.errors()]
        return JSONResponse({"error": "invalid_request", "details": errs}, status_code=422)

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, exc: Exception):
        log.error("unhandled %s", type(exc).__name__)  # class only: no traces or payloads
        return JSONResponse({"error": "internal_error"}, status_code=500)

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    @app.post("/plan", response_model=PlanResponse, dependencies=[Depends(require_token)])
    def plan(req: PlanRequest):
        try:
            client = model or build_model()
            res = run_agent(req, client)
        except ProviderError as e:
            log.warning("provider failure: %s", e)
            return JSONResponse({"error": "model_provider_unavailable"}, status_code=502)
        except AgentError as e:
            log.warning("model output rejected: %s", e)
            return JSONResponse({"error": "model_output_rejected", "detail": str(e)}, status_code=502)

        if res.state_err == "not_found":
            return JSONResponse({"error": "unknown_service_or_environment"}, status_code=404)

        state = ServiceState(**res.state) if res.state else None
        pol = DeploymentPolicy(**res.policy) if res.policy else None
        out = policy.decide(req.environment, req.desired_replicas, state, pol)
        prev = state.replicas if state else None
        verify, rollback = _steps(out.decision, req, prev)
        artifact = None
        if out.decision in ("allowed", "requires_approval"):
            artifact = Artifact(service=req.service_id, environment=req.environment,
                                previous_replicas=prev, proposed_replicas=req.desired_replicas)
        log.info("plan service=%s env=%s decision=%s", req.service_id, req.environment, out.decision)
        return PlanResponse(
            decision=out.decision,
            current_state=StateView(replicas=prev, error_rate=state.error_rate if state else None,
                                    owner=state.owner if state else None),
            requested_state=StateView(replicas=req.desired_replicas),
            decision_basis=out.basis,
            explanation=res.answer.explanation if res.answer else "Evidence unavailable; no explanation generated.",
            evidence_refs=res.answer.evidence_refs if res.answer else [],
            verification_steps=verify, rollback=rollback,
            change_artifact=artifact, tool_trace=res.trace)

    return app


app = create_app()
