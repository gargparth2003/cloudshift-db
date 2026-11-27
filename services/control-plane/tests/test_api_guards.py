from fastapi.testclient import TestClient

import app.main as main


TASK = "parth-commerce-migration-001"
TOKEN = {"x-cloudshift-token": main.settings.control_api_token}
client = TestClient(main.app)


def test_mutating_route_requires_operator_token(monkeypatch) -> None:
    monkeypatch.setattr(main, "start_migration", lambda *_: {"state": "INITIAL_SYNC"})
    response = client.post(f"/api/v1/migrations/{TASK}/start")
    assert response.status_code == 401
    assert response.json()["detail"] == "Valid operator token required"


def test_duplicate_start_returns_existing_observation(monkeypatch) -> None:
    calls = 0

    def existing(*_):
        nonlocal calls
        calls += 1
        return {"task_key": TASK, "state": "CONTINUOUS_REPLICATION", "ready_tables": 13}

    monkeypatch.setattr(main, "start_migration", existing)
    first = client.post(f"/api/v1/migrations/{TASK}/start", headers=TOKEN)
    second = client.post(f"/api/v1/migrations/{TASK}/start", headers=TOKEN)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert calls == 2


def test_validation_failure_is_conflict_not_success(monkeypatch) -> None:
    def mismatch(*_):
        raise ValueError("final validation mismatch")

    monkeypatch.setattr(main, "run_validation", mismatch)
    response = client.post(f"/api/v1/migrations/{TASK}/validate?scope=FINAL_QUIESCED", headers=TOKEN)
    assert response.status_code == 409
    assert "mismatch" in response.json()["detail"]


def test_cutover_confirmation_must_match_task() -> None:
    response = client.post(
        f"/api/v1/migrations/{TASK}/cutover?confirmation=wrong-task",
        headers=TOKEN,
    )
    assert response.status_code == 409
    assert "exactly match" in response.json()["detail"]


def test_unknown_endpoint_is_not_open_proxy() -> None:
    response = client.post("/api/v1/endpoints/arbitrary-external-host/test")
    assert response.status_code == 404
    assert response.json()["detail"] == "Endpoint not found"
