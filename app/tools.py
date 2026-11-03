"""Two read-only tools backed by synthetic JSON fixtures."""
import json
import os
from pathlib import Path

from pydantic import ValidationError

from app.schemas import DeploymentPolicy, ServiceState, ToolArgs


class ToolError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code  # "not_found" | "invalid_data" | "unauthorized_tool" | "invalid_arguments"


def _fixture_dir() -> Path:
    return Path(os.environ.get("FIXTURE_DIR", Path(__file__).resolve().parent.parent / "fixtures"))


def _load(name: str) -> dict:
    try:
        return json.loads((_fixture_dir() / name).read_text())
    except (OSError, json.JSONDecodeError):
        raise ToolError("invalid_data")


def get_service_state(service_id: str, environment: str) -> dict:
    row = _load("services.json").get(f"{service_id}:{environment}")
    if row is None:
        raise ToolError("not_found")
    try:
        state = ServiceState(**row)
    except (ValidationError, TypeError):
        raise ToolError("invalid_data")
    p = f"state:{service_id}:{environment}"
    return {
        "data": state.model_dump(),
        "evidence_refs": [f"{p}:replicas", f"{p}:error_rate", f"{p}:health", f"{p}:owner"],
    }


def get_deployment_policy(service_id: str, environment: str) -> dict:
    row = _load("policies.json").get(f"{service_id}:{environment}")
    if row is None:
        raise ToolError("not_found")
    try:
        policy = DeploymentPolicy(**row)
    except (ValidationError, TypeError):
        raise ToolError("invalid_data")
    p = f"policy:{service_id}:{environment}"
    return {"data": policy.model_dump(), "evidence_refs": [f"{p}:range", f"{p}:approval"]}


# The allowlist. The model can only ever reach these two read-only functions.
TOOLS = {
    "get_service_state": get_service_state,
    "get_deployment_policy": get_deployment_policy,
}

_ARG_SCHEMA = {
    "type": "object",
    "properties": {
        "service_id": {"type": "string"},
        "environment": {"type": "string", "enum": ["development", "production"]},
    },
    "required": ["service_id", "environment"],
    "additionalProperties": False,
}

TOOL_SPECS = [
    {"type": "function", "function": {
        "name": "get_service_state",
        "description": "Read-only. Current replicas, owner, and recent health/error evidence.",
        "parameters": _ARG_SCHEMA}},
    {"type": "function", "function": {
        "name": "get_deployment_policy",
        "description": "Read-only. Permitted replica range, approval requirements, constraints.",
        "parameters": _ARG_SCHEMA}},
]


def run_tool(name: str, raw_args: dict, expected: ToolArgs) -> dict:
    """Validate and execute one model-requested tool call."""
    if name not in TOOLS:
        raise ToolError("unauthorized_tool")
    try:
        args = ToolArgs(**raw_args)
    except (ValidationError, TypeError):
        raise ToolError("invalid_arguments")
    if args != expected:  # model may not inspect other services/environments
        raise ToolError("invalid_arguments")
    return TOOLS[name](args.service_id, args.environment)
