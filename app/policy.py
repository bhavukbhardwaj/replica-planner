"""Deterministic decision engine. Never sees model output."""
from dataclasses import dataclass

from app.schemas import DeploymentPolicy, ServiceState

# Hard limits from the exercise (AC2). Intersected with the fixture policy range.
ENV_LIMITS = {"development": (1, 5), "production": (2, 10)}
# Exercise policy only (AC3) - not a universal scaling recommendation.
ERROR_RATE_THRESHOLD = 0.05


@dataclass(frozen=True)
class Outcome:
    decision: str
    basis: str


def decide(environment: str, desired: int, state: ServiceState | None,
           policy: DeploymentPolicy | None) -> Outcome:
    # 1. Missing/invalid state or policy fails safely (never approves).
    if state is None or policy is None:
        return Outcome("blocked", "State or deployment policy unavailable; failing safe.")
    lo = max(ENV_LIMITS[environment][0], policy.min_replicas)
    hi = min(ENV_LIMITS[environment][1], policy.max_replicas)
    # 2. Out of range.
    if not (lo <= desired <= hi):
        return Outcome("blocked", f"Requested {desired} replicas is outside the permitted range {lo}-{hi}.")
    # 3. Already matching.
    if desired == state.replicas:
        return Outcome("no_change", f"Service already runs {desired} replicas; nothing to change.")
    # 4. Unhealthy scale-up.
    if desired > state.replicas and state.error_rate > ERROR_RATE_THRESHOLD:
        return Outcome("blocked", f"Scale-up blocked: error rate {state.error_rate:.1%} exceeds "
                                  f"{ERROR_RATE_THRESHOLD:.0%}; investigate first.")
    # 5. Production (or policy) requires human approval.
    if environment == "production" or policy.requires_approval:
        return Outcome("requires_approval", "Production changes require human approval; this is a proposal only.")
    # 6. Allowed.
    return Outcome("allowed", "Within policy range and service is healthy.")
