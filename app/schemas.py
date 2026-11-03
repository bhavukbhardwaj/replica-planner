"""Pydantic models: HTTP contract, tool arguments/outputs, model output."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

Environment = Literal["development", "production"]
Decision = Literal["allowed", "requires_approval", "blocked", "no_change"]
SERVICE_ID_PATTERN = r"^[a-z0-9][a-z0-9-]{0,62}$"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------- HTTP request ----------
class PlanRequest(Strict):
    service_id: str = Field(pattern=SERVICE_ID_PATTERN)
    environment: Environment
    desired_replicas: StrictInt  # rejects "3", 3.0, true; range is judged by policy code
    reason: str = Field(max_length=500)


# ---------- tool args / outputs ----------
class ToolArgs(Strict):
    service_id: str = Field(pattern=SERVICE_ID_PATTERN)
    environment: Environment


class ServiceState(Strict):
    service_id: str
    environment: Environment
    replicas: int = Field(ge=0)
    owner: str
    error_rate: float = Field(ge=0, le=1)
    health: str
    window: str


class DeploymentPolicy(Strict):
    min_replicas: int = Field(ge=0)
    max_replicas: int = Field(ge=0)
    requires_approval: bool
    constraints: list[str]

    @field_validator("max_replicas")
    @classmethod
    def _ordered(cls, v, info):
        if "min_replicas" in info.data and v < info.data["min_replicas"]:
            raise ValueError("max_replicas < min_replicas")
        return v


# ---------- model final answer (untrusted) ----------
class ModelAnswer(Strict):
    explanation: str = Field(min_length=1, max_length=1500)
    evidence_refs: list[str] = Field(min_length=1, max_length=20)


# ---------- HTTP response ----------
class Artifact(Strict):
    service: str
    environment: Environment
    previous_replicas: int
    proposed_replicas: int


class StateView(Strict):
    replicas: int | None
    error_rate: float | None = None
    owner: str | None = None


class ToolCallTrace(Strict):
    tool: str
    arguments: dict
    ok: bool


class PlanResponse(Strict):
    decision: Decision
    current_state: StateView
    requested_state: StateView
    decision_basis: str          # produced by code
    explanation: str             # produced by model, display only
    evidence_refs: list[str]
    verification_steps: list[str]
    rollback: list[str]
    change_artifact: Artifact | None
    applied: Literal[False] = False
    tool_trace: list[ToolCallTrace]
