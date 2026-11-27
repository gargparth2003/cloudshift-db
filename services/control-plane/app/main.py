from datetime import UTC, datetime
from secrets import compare_digest
from time import perf_counter
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from psycopg import Error as PsycopgError

from .config import get_settings
from .database import check_health, discover_schema, endpoints
from .cutover import application_route, automated_cutover, execute_cutover, prepare_cutover
from .migration import (
    list_migrations,
    migration_record,
    pause_replication,
    replication_metrics,
    resume_replication,
    run_assessment,
    start_migration,
)
from .models import EndpointSummary, HealthState, ServiceHealth
from .metrics import observe_request, register_collector
from .observations import (
    backup_inventory, cutover_history, experiment_history, incident_history,
    migration_events, table_observations, topology, validation_history,
)
from .validation import run_validation

settings = get_settings()
register_collector(settings)
app = FastAPI(
    title="CloudShift DB Control Plane",
    version="0.1.0",
    description="Local-first PostgreSQL migration control plane.",
    docs_url="/api/docs",
    redoc_url=None,
)


@app.middleware("http")
async def correlation_id(request: Request, call_next):
    started = perf_counter()
    request_id = request.headers.get("x-correlation-id", str(uuid4()))[:128]
    request.state.correlation_id = request_id
    response = await call_next(request)
    response.headers["x-correlation-id"] = request_id
    route = request.scope.get("route")
    route_path = getattr(route, "path", "unmatched")
    observe_request(request.method, route_path, response.status_code, started)
    return response


@app.exception_handler(PsycopgError)
async def database_error(request: Request, exc: PsycopgError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "code": "DATABASE_UNAVAILABLE",
            "message": exc.__class__.__name__,
            "correlation_id": request.state.correlation_id,
        },
    )


@app.get("/api/v1/health/live")
def liveness() -> dict[str, str]:
    return {"status": "alive"}


@app.get("/metrics", include_in_schema=False, response_class=PlainTextResponse)
def prometheus_metrics():
    return PlainTextResponse(generate_latest().decode("utf-8"), media_type=CONTENT_TYPE_LATEST)


@app.get("/api/v1/health", response_model=ServiceHealth)
def health() -> ServiceHealth:
    observations = [check_health(endpoint) for endpoint in endpoints(settings).values()]
    state = (
        HealthState.AVAILABLE
        if all(item.state == HealthState.AVAILABLE for item in observations)
        else HealthState.DEGRADED
    )
    return ServiceHealth(
        service=settings.service_name,
        deployment_mode=settings.deployment_mode,
        state=state,
        observed_at=datetime.now(UTC),
        databases=observations,
    )


@app.get("/api/v1/endpoints", response_model=list[EndpointSummary])
def list_endpoints() -> list[EndpointSummary]:
    return [
        EndpointSummary(
            id=item.id, resource_name=item.resource_name, environment=item.environment,
            role=item.role, database_name=item.database_name,
        )
        for item in endpoints(settings).values()
    ]


def endpoint_or_404(endpoint_id: str):
    endpoint = endpoints(settings).get(endpoint_id)
    if endpoint is None:
        raise HTTPException(status_code=404, detail="Endpoint not found")
    return endpoint


def require_operator(
    x_cloudshift_token: Annotated[str | None, Header()] = None,
) -> None:
    if x_cloudshift_token is None or not compare_digest(
        x_cloudshift_token, settings.control_api_token
    ):
        raise HTTPException(status_code=401, detail="Valid operator token required")


@app.post("/api/v1/endpoints/{endpoint_id}/test")
def test_endpoint(endpoint_id: str):
    return check_health(endpoint_or_404(endpoint_id))


@app.get("/api/v1/endpoints/{endpoint_id}/schema")
def endpoint_schema(endpoint_id: str):
    return discover_schema(endpoint_or_404(endpoint_id))


@app.get("/api/v1/migrations")
def migrations():
    return list_migrations(settings)


@app.get("/api/v1/migrations/{task_key}")
def migration_detail(task_key: str):
    record = migration_record(settings, task_key)
    if record is None:
        raise HTTPException(status_code=404, detail="Migration not found")
    return record


@app.post("/api/v1/migrations/{task_key}/assessment", dependencies=[Depends(require_operator)])
def assess_migration(task_key: str):
    try:
        return run_assessment(settings, task_key)
    except LookupError:
        raise HTTPException(status_code=404, detail="Migration not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/v1/migrations/{task_key}/start", dependencies=[Depends(require_operator)])
def start_migration_route(task_key: str):
    try:
        return start_migration(settings, task_key)
    except LookupError:
        raise HTTPException(status_code=404, detail="Migration not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/v1/migrations/{task_key}/pause", dependencies=[Depends(require_operator)])
def pause_migration_route(task_key: str):
    try:
        return pause_replication(settings, task_key)
    except LookupError:
        raise HTTPException(status_code=404, detail="Migration not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/v1/migrations/{task_key}/resume", dependencies=[Depends(require_operator)])
def resume_migration_route(task_key: str):
    try:
        return resume_replication(settings, task_key)
    except LookupError:
        raise HTTPException(status_code=404, detail="Migration not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/v1/migrations/{task_key}/metrics")
def migration_metrics(task_key: str):
    try:
        return replication_metrics(settings, task_key)
    except LookupError:
        raise HTTPException(status_code=404, detail="Migration not found") from None


@app.post("/api/v1/migrations/{task_key}/validate", dependencies=[Depends(require_operator)])
def validate_migration(task_key: str, scope: str = "FULL"):
    try:
        return run_validation(settings, task_key, scope)
    except LookupError:
        raise HTTPException(status_code=404, detail="Migration not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/v1/application-route")
def get_application_route():
    return application_route(settings)


@app.post("/api/v1/migrations/{task_key}/cutover/prepare", dependencies=[Depends(require_operator)])
def prepare_cutover_route(task_key: str):
    try:
        return prepare_cutover(settings, task_key)
    except LookupError:
        raise HTTPException(status_code=404, detail="Migration not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/v1/migrations/{task_key}/cutover", dependencies=[Depends(require_operator)])
def execute_cutover_route(task_key: str, confirmation: str):
    try:
        return execute_cutover(settings, task_key, confirmation)
    except LookupError:
        raise HTTPException(status_code=404, detail="Migration not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/v1/migrations/{task_key}/cutover/automated", dependencies=[Depends(require_operator)])
def automated_cutover_route(task_key: str, confirmation: str):
    try:
        return automated_cutover(settings, task_key, confirmation)
    except LookupError:
        raise HTTPException(status_code=404, detail="Migration not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/v1/migrations/{task_key}/events")
def get_migration_events(task_key: str, limit: int = 100):
    return migration_events(settings, task_key, min(max(limit, 1), 500))


@app.get("/api/v1/migrations/{task_key}/validations")
def get_validation_history(task_key: str, limit: int = 20):
    return validation_history(settings, task_key, min(max(limit, 1), 100))


@app.get("/api/v1/migrations/{task_key}/cutovers")
def get_cutover_history(task_key: str, limit: int = 20):
    return cutover_history(settings, task_key, min(max(limit, 1), 100))


@app.get("/api/v1/backups")
def get_backup_inventory(limit: int = 100):
    return backup_inventory(settings, min(max(limit, 1), 500))


@app.get("/api/v1/incidents")
def get_incident_history(limit: int = 100):
    return incident_history(settings, min(max(limit, 1), 500))


@app.get("/api/v1/experiments")
def get_experiment_history(limit: int = 100):
    return experiment_history(settings, min(max(limit, 1), 500))


@app.get("/api/v1/migrations/{task_key}/tables")
def get_table_observations(task_key: str):
    try:
        return table_observations(settings, task_key)
    except LookupError:
        raise HTTPException(status_code=404, detail="Migration not found") from None


@app.get("/api/v1/migrations/{task_key}/topology")
def get_topology(task_key: str):
    try:
        return topology(settings, task_key)
    except LookupError:
        raise HTTPException(status_code=404, detail="Migration not found") from None
