import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.models.fake import FakeModel

H = {"X-API-Token": "test-token"}
MALICIOUS = json.loads((Path(__file__).parent.parent / "fixtures" / "malicious_request.json").read_text())


@pytest.fixture(autouse=True)
def _token(monkeypatch):
    monkeypatch.setenv("PLAN_API_TOKEN", "test-token")


def call(body, script="good", headers=H):
    return TestClient(create_app(FakeModel(script)), raise_server_exceptions=False).post(
        "/plan", json=body, headers=headers)


def req(svc, env, n, reason="capacity"):
    return {"service_id": svc, "environment": env, "desired_replicas": n, "reason": reason}


def test_dev_allowed_vs_prod_requires_approval():
    dev = call(req("dev-healthy", "development", 3)).json()
    assert dev["decision"] == "allowed"
    assert dev["change_artifact"] == {"service": "dev-healthy", "environment": "development",
                                      "previous_replicas": 2, "proposed_replicas": 3}
    prod = call(req("prod-healthy", "production", 4)).json()
    assert prod["decision"] == "requires_approval"
    assert set(prod["change_artifact"]) == {"service", "environment", "previous_replicas", "proposed_replicas"}
    assert prod["applied"] is False


@pytest.mark.parametrize("body,status,decision", [
    (req("dev-healthy", "development", 6), 200, "blocked"),       # above dev max 5
    (req("dev-healthy", "development", 0), 200, "blocked"),
    (req("prod-healthy", "production", 1), 200, "blocked"),       # below prod min 2
    (req("prod-healthy", "production", 11), 200, "blocked"),
    (req("dev-healthy", "development", "3"), 422, None),          # non-int
    (req("dev-healthy", "development", 2.5), 422, None),
    (req("dev-healthy", "development", True), 422, None),
    ({"service_id": "dev-healthy"}, 422, None),                   # malformed
])
def test_invalid_and_out_of_range(body, status, decision):
    r = call(body)
    assert r.status_code == status
    if decision:
        assert r.json()["decision"] == decision and r.json()["change_artifact"] is None


def test_missing_or_wrong_token_rejected():
    assert call(req("dev-healthy", "development", 3), headers={}).status_code == 401
    assert call(req("dev-healthy", "development", 3), headers={"X-API-Token": "nope"}).status_code == 401


def test_no_change_and_unhealthy_scaleup():
    nc = call(req("dev-healthy", "development", 2)).json()
    assert nc["decision"] == "no_change" and nc["change_artifact"] is None
    up = call(req("dev-unhealthy", "development", 4)).json()
    assert up["decision"] == "blocked" and up["change_artifact"] is None
    down = call(req("dev-unhealthy", "development", 1)).json()   # scale-down is not blocked by error rate
    assert down["decision"] == "allowed"


def test_malicious_reason_cannot_bypass_policy():
    d = call(MALICIOUS).json()
    assert d["decision"] == "requires_approval"          # prod still needs a human
    assert d["change_artifact"]["proposed_replicas"] == 8
    assert {t["tool"] for t in d["tool_trace"]} <= {"get_service_state", "get_deployment_policy"}


def test_missing_policy_or_service_fails_safe():
    d = call(req("no-policy", "development", 3)).json()
    assert d["decision"] == "blocked" and d["change_artifact"] is None
    assert call(req("ghost", "development", 3)).status_code == 404


@pytest.mark.parametrize("script", ["unauthorized_tool", "bad_args", "other_service", "fake_evidence",
                                    "invalid_json", "no_tools", "never_finishes"])
def test_bad_model_output_is_rejected(script):
    r = call(req("dev-healthy", "development", 3), script=script)
    assert r.status_code == 502 and "change_artifact" not in r.json()


def test_provider_failure_is_controlled_and_leaks_nothing():
    r = call(req("dev-healthy", "development", 3), script="provider_error")
    assert r.status_code == 502 and r.json() == {"error": "model_provider_unavailable"}
    assert "Traceback" not in r.text and "test-token" not in r.text


def test_invalid_fixture_data_fails_safe(tmp_path, monkeypatch):
    # corrupt state (negative replicas) must never produce an approval
    (tmp_path / "services.json").write_text(json.dumps({"dev-healthy:development": {
        "service_id": "dev-healthy", "environment": "development", "replicas": -1, "owner": "x",
        "error_rate": 0.0, "health": "healthy", "window": "last 30m"}}))
    (tmp_path / "policies.json").write_text(json.dumps({"dev-healthy:development": {
        "min_replicas": 1, "max_replicas": 5, "requires_approval": False, "constraints": []}}))
    monkeypatch.setenv("FIXTURE_DIR", str(tmp_path))
    d = call(req("dev-healthy", "development", 3)).json()
    assert d["decision"] == "blocked" and d["change_artifact"] is None


def test_logs_never_contain_token_or_reason(caplog):
    caplog.set_level("INFO")
    call(MALICIOUS)
    call(req("dev-healthy", "development", 3), script="provider_error")
    assert "test-token" not in caplog.text and "Ignore approvals" not in caplog.text
