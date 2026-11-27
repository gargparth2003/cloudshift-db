import os

os.environ.setdefault("SOURCE_DATABASE_URL", "postgresql://unused")
os.environ.setdefault("TARGET_DATABASE_URL", "postgresql://unused")
os.environ.setdefault("CONTROL_DATABASE_URL", "postgresql://unused")
os.environ.setdefault("CONTROL_API_TOKEN", "test-operator-token")
os.environ.setdefault("MIGRATION_DB_PASSWORD", "test-migration-password")
os.environ.setdefault("APP_SOURCE_DATABASE_URL", "postgresql://unused")
os.environ.setdefault("APP_TARGET_DATABASE_URL", "postgresql://unused")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def test_liveness_and_correlation_id() -> None:
    response = TestClient(app).get(
        "/api/v1/health/live", headers={"x-correlation-id": "test-request"}
    )
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}
    assert response.headers["x-correlation-id"] == "test-request"
