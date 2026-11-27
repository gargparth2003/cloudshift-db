import asyncio
import random
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from secrets import compare_digest
from time import monotonic_ns
from typing import Annotated, Any, Literal
from uuid import UUID

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from pydantic import BaseModel, Field

from .config import get_settings
from .database import connect, endpoints

settings = get_settings()
TASK_KEY = "parth-commerce-migration-001"
ALLOWED_RATES = {5, 10, 25, 50}

WORKLOAD_OPERATIONS = Counter(
    "cloudshift_workload_operations_total", "Observed workload operations", ["class", "result"]
)
WORKLOAD_COMMITS = Counter("cloudshift_workload_commits_total", "Committed workload transactions")
WORKLOAD_LATENCY = Histogram(
    "cloudshift_workload_operation_duration_seconds",
    "Workload operation duration",
    ["class"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5),
)
WORKLOAD_RUNNING = Gauge("cloudshift_workload_running", "Whether the workload is running")
PROBE_REQUESTS = Counter(
    "cloudshift_workload_probe_requests_total", "Availability probe requests", ["type", "result"]
)
PROBE_LATENCY = Histogram(
    "cloudshift_workload_probe_duration_seconds",
    "Availability probe request duration",
    ["type"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5),
)


class WorkloadConfig(BaseModel):
    profile: Literal["READ_HEAVY", "WRITE_HEAVY", "BALANCED", "BURST", "IDLE"] = "BALANCED"
    rate: int = Field(default=5)

    def model_post_init(self, __context: Any) -> None:
        if self.rate not in ALLOWED_RATES:
            raise ValueError("rate must be one of 5, 10, 25, or 50 operations per second")


class ProbeConfig(BaseModel):
    sample_interval_ms: int = Field(default=250, ge=100, le=5000)
    write_interval_ms: int = Field(default=1000, ge=250, le=10000)


@dataclass
class WorkloadRuntime:
    state: str = "STOPPED"
    profile: str = "BALANCED"
    rate: int = 5
    run_id: UUID | None = None
    seed: int | None = None
    task: asyncio.Task[None] | None = None
    stop_requested: bool = False
    started_at: datetime | None = None
    observations: deque[tuple[float, float, str, bool, bool]] = field(
        default_factory=lambda: deque(maxlen=10000)
    )


@dataclass
class ProbeRuntime:
    state: str = "STOPPED"
    run_id: UUID | None = None
    sample_interval_ms: int = 250
    write_interval_ms: int = 1000
    task: asyncio.Task[None] | None = None
    stop_requested: bool = False


workload = WorkloadRuntime()
probe = ProbeRuntime()


def require_operator(x_cloudshift_token: Annotated[str | None, Header()] = None) -> None:
    if x_cloudshift_token is None or not compare_digest(x_cloudshift_token, settings.control_api_token):
        raise HTTPException(status_code=401, detail="Valid operator token required")


def _migration_id(connection) -> UUID:
    row = connection.execute(
        "SELECT migration_id FROM control.migration_tasks WHERE task_key = %s", (TASK_KEY,)
    ).fetchone()
    if row is None:
        raise RuntimeError("migration task is not configured")
    return row["migration_id"]


def _record_event(event_type: str, message: str, evidence: dict[str, Any]) -> None:
    import json

    with connect(endpoints(settings)["control"]) as connection:
        connection.execute(
            """
            INSERT INTO control.migration_events
                (migration_id, event_type, component, message, evidence)
            VALUES (%s, %s, 'cloudshift-workload-generator', %s, %s::jsonb)
            """,
            (_migration_id(connection), event_type, message, json.dumps(evidence, default=str)),
        )


def _create_workload_run(config: WorkloadConfig, seed: int) -> UUID:
    with connect(endpoints(settings)["control"]) as connection:
        row = connection.execute(
            """
            INSERT INTO control.workload_runs
                (migration_id, profile, configured_rate, random_seed, status)
            VALUES (%s, %s, %s, %s, 'RUNNING') RETURNING workload_run_id
            """,
            (_migration_id(connection), config.profile, config.rate, seed),
        ).fetchone()
    return row["workload_run_id"]


def _update_workload_run(run_id: UUID, status: str) -> None:
    with connect(endpoints(settings)["control"]) as connection:
        connection.execute(
            """
            UPDATE control.workload_runs SET status = %s,
                stopped_at = CASE WHEN %s = 'STOPPED' THEN now() ELSE stopped_at END
            WHERE workload_run_id = %s
            """,
            (status, status, run_id),
        )


def _update_workload_config(run_id: UUID, profile: str, rate: int) -> None:
    with connect(endpoints(settings)["control"]) as connection:
        connection.execute(
            "UPDATE control.workload_runs SET profile=%s, configured_rate=%s WHERE workload_run_id=%s",
            (profile, rate, run_id),
        )


def _active_route() -> str | None:
    with connect(endpoints(settings)["control"]) as connection:
        row = connection.execute(
            "SELECT active_endpoint::text FROM control.application_routes WHERE route_key='parth-commerce-application'"
        ).fetchone()
    return row["active_endpoint"] if row else None


def _record_workload_operation(
    run_id: UUID, operation: str, operation_class: str, success: bool,
    committed: bool, latency_ms: float, endpoint: str | None,
    transaction_ref: str | None, error_class: str | None,
) -> None:
    with connect(endpoints(settings)["control"]) as connection:
        connection.execute(
            """
            INSERT INTO control.workload_operations
                (workload_run_id, operation_type, operation_class, success, committed,
                 latency_ms, active_endpoint, transaction_ref, error_class)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                run_id, operation, operation_class, success, committed, latency_ms,
                endpoint, transaction_ref, error_class,
            ),
        )


def _operation_choice(rng: random.Random, profile: str) -> tuple[str, str, str, dict[str, Any] | None]:
    read_probability = {"READ_HEAVY": 0.8, "WRITE_HEAVY": 0.25, "BALANCED": 0.5, "BURST": 0.5}[profile]
    if rng.random() < read_probability:
        operation = rng.choice(["products", "inventory", "customers", "orders", "activity"])
        return operation, "READ", f"/api/v1/commerce/{operation}?limit=20", None
    operation = rng.choice(
        ["order", "customer", "product_update", "payment_update", "shipment_update", "delete_customer"]
    )
    if operation == "order":
        return operation, "WRITE", "/api/v1/commerce/orders", {
            "customer_id": 1, "product_id": rng.randint(1, 1000), "quantity": rng.randint(1, 2),
        }
    return operation, "WRITE", f"/api/v1/commerce/synthetic/{operation}", {
        "product_id": rng.randint(1, 1000)
    }


async def _execute_operation(client: httpx.AsyncClient, rng: random.Random) -> None:
    if workload.run_id is None:
        return
    operation, operation_class, path, payload = _operation_choice(rng, workload.profile)
    started = monotonic_ns()
    success = committed = False
    endpoint = transaction_ref = error_class = None
    try:
        if operation_class == "READ":
            response = await client.get(path)
        else:
            response = await client.post(
                path, json=payload, headers={"x-cloudshift-token": settings.control_api_token}
            )
        response.raise_for_status()
        body = response.json()
        success = True
        committed = bool(body.get("committed", False))
        endpoint = body.get("active_database")
        transaction_ref = body.get("transaction_ref")
    except httpx.HTTPStatusError as exc:
        error_class = f"HTTP_{exc.response.status_code}"
    except httpx.HTTPError as exc:
        error_class = exc.__class__.__name__
    latency_ms = (monotonic_ns() - started) / 1_000_000
    now_seconds = datetime.now(UTC).timestamp()
    workload.observations.append((now_seconds, latency_ms, operation_class, success, committed))
    WORKLOAD_OPERATIONS.labels(operation_class, "success" if success else "failure").inc()
    WORKLOAD_LATENCY.labels(operation_class).observe(latency_ms / 1000)
    if committed:
        WORKLOAD_COMMITS.inc()
    await asyncio.to_thread(
        _record_workload_operation, workload.run_id, operation, operation_class, success,
        committed, latency_ms, endpoint, transaction_ref, error_class,
    )


async def _workload_loop(seed: int) -> None:
    rng = random.Random(seed)
    async with httpx.AsyncClient(base_url=settings.commerce_base_url, timeout=5) as client:
        while not workload.stop_requested:
            if workload.state == "PAUSED" or workload.profile == "IDLE":
                await asyncio.sleep(0.1)
                continue
            effective_rate = workload.rate
            if workload.profile == "BURST" and int(datetime.now(UTC).timestamp()) % 4 >= 2:
                effective_rate = max(1, workload.rate // 5)
            await _execute_operation(client, rng)
            await asyncio.sleep(1 / effective_rate)


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return round(ordered[index], 3)


def workload_status() -> dict[str, Any]:
    cutoff = datetime.now(UTC).timestamp() - 60
    recent = [item for item in workload.observations if item[0] >= cutoff]
    latencies = [item[1] for item in recent]
    reads = sum(item[2] == "READ" for item in recent)
    writes = sum(item[2] == "WRITE" for item in recent)
    successes = sum(item[3] for item in recent)
    commits = sum(item[4] for item in recent)
    window = min(60.0, max(1.0, datetime.now(UTC).timestamp() - (workload.started_at.timestamp() if workload.started_at else cutoff)))
    return {
        "state": workload.state, "profile": workload.profile, "configured_rate": workload.rate,
        "workload_run_id": workload.run_id, "active_window_seconds": round(window, 3),
        "active_database": _active_route(),
        "operations_per_second": round(len(recent) / window, 3),
        "transactions_per_second": round(commits / window, 3),
        "reads_per_second": round(reads / window, 3), "writes_per_second": round(writes / window, 3),
        "successful_operations": successes, "failed_operations": len(recent) - successes,
        "committed_transactions": commits, "rolled_back_or_rejected": writes - commits,
        "p50_latency_ms": _percentile(latencies, 0.50),
        "p95_latency_ms": _percentile(latencies, 0.95),
        "p99_latency_ms": _percentile(latencies, 0.99),
        "measurement_window": "LAST_60_SECONDS_IN_PROCESS",
        "observed_at": datetime.now(UTC),
    }


def _create_probe_run(config: ProbeConfig) -> UUID:
    with connect(endpoints(settings)["control"]) as connection:
        row = connection.execute(
            """
            INSERT INTO control.availability_probe_runs
                (migration_id, sample_interval_ms, write_interval_ms, status)
            VALUES (%s, %s, %s, 'RUNNING') RETURNING probe_run_id
            """,
            (_migration_id(connection), config.sample_interval_ms, config.write_interval_ms),
        ).fetchone()
    return row["probe_run_id"]


def _record_probe(
    run_id: UUID, request_type: str, success: bool, latency_ms: float,
    endpoint: str | None, transaction_ref: str | None, error_class: str | None,
) -> None:
    with connect(endpoints(settings)["control"]) as connection:
        connection.execute(
            """
            INSERT INTO control.availability_probe_observations
                (probe_run_id, request_type, success, latency_ms, active_endpoint,
                 transaction_ref, error_class)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (run_id, request_type, success, latency_ms, endpoint, transaction_ref, error_class),
        )


async def _probe_request(client: httpx.AsyncClient, request_type: str) -> None:
    if probe.run_id is None:
        return
    started = monotonic_ns()
    success = False
    endpoint = transaction_ref = error_class = None
    try:
        if request_type == "READ":
            response = await client.get("/api/v1/commerce/probe")
        else:
            response = await client.post(
                "/api/v1/commerce/probe", headers={"x-cloudshift-token": settings.control_api_token}
            )
        response.raise_for_status()
        body = response.json()
        success = True
        endpoint = body.get("active_database")
        transaction_ref = body.get("transaction_ref")
    except httpx.HTTPStatusError as exc:
        error_class = f"HTTP_{exc.response.status_code}"
    except httpx.HTTPError as exc:
        error_class = exc.__class__.__name__
    latency_ms = (monotonic_ns() - started) / 1_000_000
    PROBE_REQUESTS.labels(request_type, "success" if success else "failure").inc()
    PROBE_LATENCY.labels(request_type).observe(latency_ms / 1000)
    await asyncio.to_thread(
        _record_probe, probe.run_id, request_type, success, latency_ms,
        endpoint, transaction_ref, error_class,
    )


async def _probe_loop() -> None:
    next_write = 0.0
    loop = asyncio.get_running_loop()
    async with httpx.AsyncClient(base_url=settings.commerce_base_url, timeout=5) as client:
        while not probe.stop_requested:
            await _probe_request(client, "READ")
            if loop.time() >= next_write:
                await _probe_request(client, "WRITE")
                next_write = loop.time() + probe.write_interval_ms / 1000
            await asyncio.sleep(probe.sample_interval_ms / 1000)


def _stop_probe_run(run_id: UUID, status: str = "STOPPED") -> None:
    with connect(endpoints(settings)["control"]) as connection:
        connection.execute(
            "UPDATE control.availability_probe_runs SET status=%s, stopped_at=now() WHERE probe_run_id=%s",
            (status, run_id),
        )


def _reconcile_orphan_runs() -> None:
    with connect(endpoints(settings)["control"]) as connection:
        connection.execute(
            "UPDATE control.workload_runs SET status='FAILED', stopped_at=now() WHERE status IN ('RUNNING','PAUSED')"
        )
        connection.execute(
            "UPDATE control.availability_probe_runs SET status='FAILED', stopped_at=now() WHERE status='RUNNING'"
        )


def probe_summary(run_id: UUID | None = None) -> dict[str, Any]:
    with connect(endpoints(settings)["control"]) as connection:
        if run_id is None:
            row = connection.execute(
                "SELECT probe_run_id FROM control.availability_probe_runs ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
            if row is None:
                return {"state": probe.state, "observations": 0, "observed_at": datetime.now(UTC)}
            run_id = row["probe_run_id"]
        run = connection.execute(
            "SELECT * FROM control.availability_probe_runs WHERE probe_run_id=%s", (run_id,)
        ).fetchone()
        aggregate = connection.execute(
            """
            SELECT count(*)::bigint AS observations,
                   count(*) FILTER (WHERE success)::bigint AS successful,
                   count(*) FILTER (WHERE NOT success)::bigint AS failed,
                   count(*) FILTER (WHERE request_type='READ' AND success)::bigint AS successful_reads,
                   count(*) FILTER (WHERE request_type='WRITE' AND success)::bigint AS successful_writes,
                   min(observed_at) AS first_observation, max(observed_at) AS last_observation
            FROM control.availability_probe_observations WHERE probe_run_id=%s
            """,
            (run_id,),
        ).fetchone()
        markers = connection.execute(
            """
            SELECT
              max(observed_at) FILTER (WHERE success AND active_endpoint='SOURCE') AS last_source_success,
              max(observed_at) FILTER (WHERE success AND request_type='WRITE' AND active_endpoint='SOURCE') AS last_source_write,
              min(observed_at) FILTER (WHERE NOT success) AS first_failure,
              min(observed_at) FILTER (WHERE NOT success AND request_type='WRITE') AS first_write_failure,
              min(observed_at) FILTER (WHERE success AND active_endpoint='TARGET') AS first_target_success,
              min(observed_at) FILTER (WHERE success AND request_type='WRITE' AND active_endpoint='TARGET') AS first_target_write
            FROM control.availability_probe_observations WHERE probe_run_id=%s
            """,
            (run_id,),
        ).fetchone()
    write_unavailability_ms = None
    if markers["first_write_failure"] and markers["first_target_write"]:
        write_unavailability_ms = round(
            (markers["first_target_write"] - markers["first_write_failure"]).total_seconds() * 1000
        )
    failure_window_ms = None
    if markers["first_failure"] and markers["first_target_success"]:
        failure_window_ms = round(
            (markers["first_target_success"] - markers["first_failure"]).total_seconds() * 1000
        )
    return {
        "state": probe.state if probe.run_id == run_id else run["status"],
        "probe_run_id": run_id, "sample_interval_ms": run["sample_interval_ms"],
        "write_interval_ms": run["write_interval_ms"], **aggregate, **markers,
        "observed_write_unavailability_ms": write_unavailability_ms,
        "observed_request_failure_window_ms": failure_window_ms,
        "method": "HTTP commerce read and committed synthetic write probes",
        "precision_limit_ms": run["sample_interval_ms"],
        "observed_at": datetime.now(UTC),
    }


@asynccontextmanager
async def lifespan(_: FastAPI):
    await asyncio.to_thread(_reconcile_orphan_runs)
    yield
    workload.stop_requested = True
    probe.stop_requested = True
    for task in (workload.task, probe.task):
        if task and not task.done():
            task.cancel()


app = FastAPI(
    title="CloudShift Workload and Availability Service", version="0.1.0",
    docs_url="/api/docs", redoc_url=None, lifespan=lifespan,
)


@app.get("/api/v1/workload/health")
def health():
    return {"status": "alive", "workload_state": workload.state, "probe_state": probe.state}


@app.get("/api/v1/workload")
def get_workload_status():
    return workload_status()


@app.post("/api/v1/workload/start", dependencies=[Depends(require_operator)])
async def start_workload(config: WorkloadConfig):
    if workload.state in {"RUNNING", "PAUSED"}:
        raise HTTPException(status_code=409, detail="Workload is already active")
    seed = monotonic_ns() % 2_147_483_647
    run_id = await asyncio.to_thread(_create_workload_run, config, seed)
    workload.state, workload.profile, workload.rate = "RUNNING", config.profile, config.rate
    workload.run_id, workload.seed = run_id, seed
    workload.stop_requested = False
    workload.started_at = datetime.now(UTC)
    workload.observations.clear()
    WORKLOAD_RUNNING.set(1)
    workload.task = asyncio.create_task(_workload_loop(seed))
    await asyncio.to_thread(
        _record_event, "WORKLOAD_STARTED", "Continuous workload started.",
        {"run_id": str(run_id), "profile": config.profile, "configured_rate": config.rate},
    )
    return workload_status()


@app.post("/api/v1/workload/pause", dependencies=[Depends(require_operator)])
async def pause_workload():
    if workload.state != "RUNNING" or workload.run_id is None:
        raise HTTPException(status_code=409, detail="Only a running workload can be paused")
    workload.state = "PAUSED"
    await asyncio.to_thread(_update_workload_run, workload.run_id, "PAUSED")
    return workload_status()


@app.post("/api/v1/workload/resume", dependencies=[Depends(require_operator)])
async def resume_workload():
    if workload.state != "PAUSED" or workload.run_id is None:
        raise HTTPException(status_code=409, detail="Only a paused workload can be resumed")
    workload.state = "RUNNING"
    await asyncio.to_thread(_update_workload_run, workload.run_id, "RUNNING")
    return workload_status()


@app.post("/api/v1/workload/stop", dependencies=[Depends(require_operator)])
async def stop_workload():
    if workload.state not in {"RUNNING", "PAUSED"} or workload.run_id is None:
        raise HTTPException(status_code=409, detail="Workload is not active")
    workload.stop_requested = True
    if workload.task:
        await workload.task
    workload.state = "STOPPED"
    WORKLOAD_RUNNING.set(0)
    await asyncio.to_thread(_update_workload_run, workload.run_id, "STOPPED")
    await asyncio.to_thread(
        _record_event, "WORKLOAD_STOPPED", "Continuous workload stopped.",
        {"run_id": str(workload.run_id), "metrics": workload_status()},
    )
    return workload_status()


@app.post("/api/v1/workload/configure", dependencies=[Depends(require_operator)])
def configure_workload(config: WorkloadConfig):
    if workload.state not in {"RUNNING", "PAUSED"}:
        raise HTTPException(status_code=409, detail="Workload is not active")
    workload.profile, workload.rate = config.profile, config.rate
    if workload.run_id:
        _update_workload_config(workload.run_id, config.profile, config.rate)
    return workload_status()


@app.get("/api/v1/workload/operations")
def workload_operations(limit: int = 100):
    bounded_limit = min(max(limit, 1), 500)
    with connect(endpoints(settings)["control"]) as connection:
        rows = connection.execute(
            """
            SELECT operation_id, workload_run_id, operation_type, operation_class,
                   success, committed, latency_ms, active_endpoint::text,
                   transaction_ref, error_class, observed_at
            FROM control.workload_operations
            ORDER BY observed_at DESC LIMIT %s
            """,
            (bounded_limit,),
        ).fetchall()
    return rows


@app.get("/api/v1/probe")
def get_probe_status():
    return probe_summary(probe.run_id)


@app.get("/api/v1/probe/observations")
def probe_observations(limit: int = 200):
    bounded_limit = min(max(limit, 1), 1000)
    with connect(endpoints(settings)["control"]) as connection:
        return connection.execute(
            """
            SELECT observation_id, probe_run_id, request_type, success, latency_ms,
                   active_endpoint::text, transaction_ref, error_class, observed_at
            FROM control.availability_probe_observations
            ORDER BY observed_at DESC LIMIT %s
            """,
            (bounded_limit,),
        ).fetchall()


@app.post("/api/v1/probe/start", dependencies=[Depends(require_operator)])
async def start_probe(config: ProbeConfig):
    if probe.state == "RUNNING":
        raise HTTPException(status_code=409, detail="Availability probe is already running")
    run_id = await asyncio.to_thread(_create_probe_run, config)
    probe.state, probe.run_id = "RUNNING", run_id
    probe.sample_interval_ms, probe.write_interval_ms = config.sample_interval_ms, config.write_interval_ms
    probe.stop_requested = False
    probe.task = asyncio.create_task(_probe_loop())
    await asyncio.to_thread(
        _record_event, "AVAILABILITY_PROBE_STARTED", "Independent availability probe started.",
        {"run_id": str(run_id), "sample_interval_ms": config.sample_interval_ms,
         "write_interval_ms": config.write_interval_ms},
    )
    return probe_summary(run_id)


@app.post("/api/v1/probe/stop", dependencies=[Depends(require_operator)])
async def stop_probe():
    if probe.state != "RUNNING" or probe.run_id is None:
        raise HTTPException(status_code=409, detail="Availability probe is not running")
    probe.stop_requested = True
    if probe.task:
        await probe.task
    probe.state = "STOPPED"
    await asyncio.to_thread(_stop_probe_run, probe.run_id)
    summary = probe_summary(probe.run_id)
    await asyncio.to_thread(
        _record_event, "AVAILABILITY_PROBE_STOPPED", "Independent availability probe stopped.",
        {"run_id": str(probe.run_id), "summary": summary},
    )
    return summary


@app.get("/metrics", response_class=PlainTextResponse)
def metrics():
    return PlainTextResponse(generate_latest().decode("utf-8"), media_type=CONTENT_TYPE_LATEST)
