"""Deterministic model double for offline runs and tests."""
import json

from app.models.base import ModelTurn, ProviderError


class FakeModel:
    """script: good | unauthorized_tool | bad_args | other_service | fake_evidence |
    invalid_json | no_tools | provider_error | never_finishes"""

    def __init__(self, script: str = "good"):
        self.script = script

    def _args(self, messages):
        req = json.loads(messages[1]["content"])
        return {"service_id": req["service_id"], "environment": req["environment"]}

    def chat(self, messages, tools):
        s = self.script
        if s == "provider_error":
            raise ProviderError("simulated provider failure")
        tool_msgs = [m for m in messages if m["role"] == "tool"]
        if s == "unauthorized_tool":
            return ModelTurn(tool_calls=[{"id": "1", "name": "apply_change", "arguments": self._args(messages)}])
        if s == "bad_args":
            return ModelTurn(tool_calls=[{"id": "1", "name": "get_service_state", "arguments": {"service_id": "x", "extra": 1}}])
        if s == "other_service":
            a = self._args(messages) | {"service_id": "prod-healthy"}
            return ModelTurn(tool_calls=[{"id": "1", "name": "get_service_state",
                                          "arguments": a | {"environment": "production"}}])
        if s == "never_finishes":
            return ModelTurn(tool_calls=[{"id": str(len(tool_msgs)), "name": "get_service_state",
                                          "arguments": self._args(messages)}])
        if not tool_msgs and s != "no_tools":
            a = self._args(messages)
            return ModelTurn(tool_calls=[{"id": "1", "name": "get_service_state", "arguments": a},
                                         {"id": "2", "name": "get_deployment_policy", "arguments": a}])
        if s == "invalid_json":
            return ModelTurn(content="sure, scaling now!")
        refs = []
        for m in tool_msgs:
            refs += json.loads(m["content"]).get("evidence_refs", [])
        if s == "fake_evidence":
            refs = ["state:made-up:production:replicas"]
        return ModelTurn(content=json.dumps({
            "explanation": "Reviewed current state and deployment policy; see decision basis.",
            "evidence_refs": refs[:3] or ["none"],
        }))
