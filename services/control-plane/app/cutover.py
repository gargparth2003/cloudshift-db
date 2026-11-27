from datetime import UTC, datetime
import json
from time import monotonic, sleep
from typing import Any
from uuid import UUID

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from .config import Settings
from .database import check_health, connect, endpoints
from .migration import migration_record, replication_metrics, transition
from .models import HealthState
from .state_machine import MigrationState
from .validation import run_validation

ADVISORY_LOCK_ID = 20261127
STAGES = {
    "DESTINATION_READINESS": 1,
    "SOURCE_WRITE_FENCE": 2,
    "IN_FLIGHT_DRAIN": 3,
    "FINAL_SYNCHRONIZATION": 4,
    "FINAL_VALIDATION": 5,
    "SEQUENCE_SYNCHRONIZATION": 6,
    "SOURCE_WRITE_PROTECTION": 7,
    "REPLICATION_TRANSITION": 8,
    "APPLICATION_ROUTE_SWITCH": 9,
    "DESTINATION_SMOKE_TEST": 10,
    "APPLICATION_TRAFFIC_RESTORED": 11,
}


def application_route(settings: Settings) -> dict[str, Any]:
    with connect(endpoints(settings)["control"]) as connection:
        route = connection.execute(
            """
            SELECT route_key, active_endpoint::text, writes_enabled, version, updated_at
            FROM control.application_routes WHERE route_key = 'parth-commerce-application'
            """
        ).fetchone()
    if route is None:
        raise RuntimeError("application route is not configured")
    return route


def _set_route(settings: Settings, endpoint: str, writes_enabled: bool) -> dict[str, Any]:
    with connect(endpoints(settings)["control"]) as connection:
        route = connection.execute(
            """
            UPDATE control.application_routes
            SET active_endpoint = %s, writes_enabled = %s,
                version = version + 1, updated_at = now()
            WHERE route_key = 'parth-commerce-application'
            RETURNING route_key, active_endpoint::text, writes_enabled, version, updated_at
            """,
            (endpoint, writes_enabled),
        ).fetchone()
    assert route is not None
    return route


def _create_cutover(settings: Settings, task_key: str) -> UUID:
    with connect(endpoints(settings)["control"]) as connection:
        migration = connection.execute(
            "SELECT migration_id FROM control.migration_tasks WHERE task_key=%s", (task_key,)
        ).fetchone()
        row = connection.execute(
            """
            INSERT INTO control.cutover_history (migration_id, outcome)
            VALUES (%s, 'IN_PROGRESS') RETURNING cutover_id
            """,
            (migration["migration_id"],),
        ).fetchone()
        for stage_name, stage_order in STAGES.items():
            connection.execute(
                """
                INSERT INTO control.cutover_stages (cutover_id, stage_name, stage_order, status)
                VALUES (%s, %s, %s, 'PENDING')
                """,
                (row["cutover_id"], stage_name, stage_order),
            )
    return row["cutover_id"]


def _active_cutover(settings: Settings, task_key: str) -> UUID | None:
    with connect(endpoints(settings)["control"]) as connection:
        row = connection.execute(
            """
            SELECT history.cutover_id FROM control.cutover_history history
            JOIN control.migration_tasks task ON task.migration_id=history.migration_id
            WHERE task.task_key=%s AND history.outcome='IN_PROGRESS'
            ORDER BY history.requested_at DESC LIMIT 1
            """,
            (task_key,),
        ).fetchone()
    return row["cutover_id"] if row else None


def _stage(
    settings: Settings, cutover_id: UUID, stage_name: str, status: str,
    evidence: dict[str, Any] | None = None, error: str | None = None,
) -> None:
    with connect(endpoints(settings)["control"]) as connection:
        connection.execute(
            """
            UPDATE control.cutover_stages
            SET status=%s,
                started_at=CASE WHEN %s='RUNNING' AND started_at IS NULL THEN now() ELSE started_at END,
                completed_at=CASE WHEN %s IN ('COMPLETED','FAILED','BLOCKED') THEN now() ELSE completed_at END,
                evidence=%s::jsonb, error_message=%s
            WHERE cutover_id=%s AND stage_name=%s
            """,
            (status, status, status, json.dumps(evidence or {}, default=str), error, cutover_id, stage_name),
        )


def _wait_for_zero_lag(settings: Settings, task_key: str, timeout_seconds: float = 20.0) -> dict[str, Any]:
    deadline = monotonic() + timeout_seconds
    latest: dict[str, Any] | None = None
    while monotonic() < deadline:
        latest = replication_metrics(settings, task_key)
        slot = latest["slot"]
        if slot and slot["active"] and slot["wal_byte_lag"] == 0 and latest["ready_tables"] == 13:
            return latest
        sleep(0.1)
    raise RuntimeError(f"replication did not reach zero measured WAL lag: {latest}")


def prepare_cutover(settings: Settings, task_key: str) -> dict[str, Any]:
    record = migration_record(settings, task_key)
    if record is None:
        raise LookupError(task_key)
    if record["state"] != MigrationState.CONTINUOUS_REPLICATION:
        raise ValueError(f"cutover preparation requires CONTINUOUS_REPLICATION, observed {record['state']}")
    route = application_route(settings)
    if route["active_endpoint"] != "SOURCE":
        raise ValueError("cutover preparation requires the source application route")

    cutover_id = _create_cutover(settings, task_key)
    _stage(settings, cutover_id, "DESTINATION_READINESS", "RUNNING")
    target_health = check_health(endpoints(settings)["target"])
    if target_health.state != HealthState.AVAILABLE:
        _stage(settings, cutover_id, "DESTINATION_READINESS", "BLOCKED", error="Destination unavailable")
        with connect(endpoints(settings)["control"]) as connection:
            connection.execute(
                "UPDATE control.cutover_history SET outcome='FAILED', completed_at=now() WHERE cutover_id=%s",
                (cutover_id,),
            )
        raise ValueError("destination is unavailable")
    _stage(settings, cutover_id, "DESTINATION_READINESS", "COMPLETED", {"health": target_health.state})

    _stage(settings, cutover_id, "SOURCE_WRITE_FENCE", "RUNNING")
    fenced_at = _set_route(settings, "SOURCE", False)["updated_at"]
    _stage(settings, cutover_id, "SOURCE_WRITE_FENCE", "COMPLETED", {"fenced_at": fenced_at})
    try:
        _stage(settings, cutover_id, "IN_FLIGHT_DRAIN", "RUNNING")
        with connect(endpoints(settings)["source"]) as source_connection:
            source_connection.execute("SELECT pg_advisory_lock(%s)", (ADVISORY_LOCK_ID,))
            source_connection.execute("SELECT pg_advisory_unlock(%s)", (ADVISORY_LOCK_ID,))
        _stage(settings, cutover_id, "IN_FLIGHT_DRAIN", "COMPLETED")
        _stage(settings, cutover_id, "FINAL_SYNCHRONIZATION", "RUNNING")
        lag = _wait_for_zero_lag(settings, task_key)
        _stage(settings, cutover_id, "FINAL_SYNCHRONIZATION", "COMPLETED", {"wal_byte_lag": 0})
        _stage(settings, cutover_id, "FINAL_VALIDATION", "RUNNING")
        validation = run_validation(settings, task_key, "FINAL_QUIESCED")
        if validation["status"] != "MATCHED":
            _stage(settings, cutover_id, "FINAL_VALIDATION", "BLOCKED", {"status": validation["status"]})
            _set_route(settings, "SOURCE", True)
            raise ValueError("final validation mismatch; source writes restored and cutover blocked")
        _stage(
            settings, cutover_id, "FINAL_VALIDATION", "COMPLETED",
            {"validation_run_id": validation["validation_run_id"], "rows_checked": validation["rows_checked"]},
        )
        with connect(endpoints(settings)["control"]) as connection:
            connection.execute(
                "UPDATE control.cutover_history SET final_validation_run_id=%s WHERE cutover_id=%s",
                (validation["validation_run_id"], cutover_id),
            )
        return {
            "cutover_id": cutover_id, "task_key": task_key, "state": MigrationState.READY_FOR_CUTOVER,
            "source_writes_fenced_at": fenced_at, "replication": lag,
            "validation": validation,
        }
    except Exception:
        current = application_route(settings)
        if current["active_endpoint"] == "SOURCE" and not current["writes_enabled"]:
            _set_route(settings, "SOURCE", True)
        with connect(endpoints(settings)["control"]) as connection:
            connection.execute(
                "UPDATE control.cutover_history SET outcome='FAILED', completed_at=now() WHERE cutover_id=%s",
                (cutover_id,),
            )
        raise


def _sync_sequences(settings: Settings) -> list[dict[str, Any]]:
    with connect(endpoints(settings)["source"]) as source_connection:
        sequences = source_connection.execute(
            """
            SELECT sequencename, last_value
            FROM pg_sequences WHERE schemaname = 'commerce'
            ORDER BY sequencename
            """
        ).fetchall()
    with connect(endpoints(settings)["target"]) as target_connection:
        for sequence in sequences:
            target_connection.execute(
                sql.SQL("SELECT setval({}::regclass, %s, true)").format(
                    sql.Literal(f"commerce.{sequence['sequencename']}")
                ),
                (sequence["last_value"],),
            )
    return [{"sequence": row["sequencename"], "value": row["last_value"]} for row in sequences]


def execute_cutover(settings: Settings, task_key: str, confirmation: str) -> dict[str, Any]:
    if confirmation != task_key:
        raise ValueError("cutover confirmation must exactly match the migration task key")
    record = migration_record(settings, task_key)
    if record is None:
        raise LookupError(task_key)
    if record["state"] != MigrationState.READY_FOR_CUTOVER:
        raise ValueError(f"cutover requires READY_FOR_CUTOVER, observed {record['state']}")
    route = application_route(settings)
    if route["active_endpoint"] != "SOURCE" or route["writes_enabled"]:
        raise ValueError("cutover requires a fenced source application route")
    fenced_at = route["updated_at"]
    cutover_id = _active_cutover(settings, task_key)
    if cutover_id is None:
        raise ValueError("no prepared cutover workflow was found")
    transition(settings, task_key, MigrationState.CUTOVER_IN_PROGRESS, "CUTOVER_CONFIRMED")

    try:
        _wait_for_zero_lag(settings, task_key)
        _stage(settings, cutover_id, "SEQUENCE_SYNCHRONIZATION", "RUNNING")
        sequences = _sync_sequences(settings)
        _stage(settings, cutover_id, "SEQUENCE_SYNCHRONIZATION", "COMPLETED", {"sequence_count": len(sequences)})
        _stage(settings, cutover_id, "REPLICATION_TRANSITION", "RUNNING")
        with psycopg.connect(
            endpoints(settings)["target"].dsn, autocommit=True, row_factory=dict_row
        ) as target_connection:
            target_connection.execute("ALTER SUBSCRIPTION parth_cloudshift_subscription DISABLE")
        _stage(settings, cutover_id, "REPLICATION_TRANSITION", "COMPLETED", {"subscription_enabled": False})
        _stage(settings, cutover_id, "SOURCE_WRITE_PROTECTION", "RUNNING")
        with connect(endpoints(settings)["source"]) as source_connection:
            source_connection.execute(
                "REVOKE INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA commerce FROM parth_commerce_app"
            )
            source_connection.execute(
                "REVOKE USAGE ON ALL SEQUENCES IN SCHEMA commerce FROM parth_commerce_app"
            )
        _stage(settings, cutover_id, "SOURCE_WRITE_PROTECTION", "COMPLETED")

        _stage(settings, cutover_id, "DESTINATION_SMOKE_TEST", "RUNNING")
        with psycopg.connect(settings.app_target_database_url, row_factory=dict_row) as target_app:
            target_app.execute("SELECT count(*) AS products FROM commerce.products").fetchone()
            target_app.execute("SELECT 1")
        _stage(settings, cutover_id, "DESTINATION_SMOKE_TEST", "COMPLETED")

        _stage(settings, cutover_id, "APPLICATION_ROUTE_SWITCH", "RUNNING")
        enabled_route = _set_route(settings, "TARGET", True)
        _stage(settings, cutover_id, "APPLICATION_ROUTE_SWITCH", "COMPLETED", {"active_endpoint": "TARGET"})
        _stage(settings, cutover_id, "APPLICATION_TRAFFIC_RESTORED", "COMPLETED", {"writes_enabled": True})
        downtime_ms = round((enabled_route["updated_at"] - fenced_at).total_seconds() * 1000)
        final_record = transition(settings, task_key, MigrationState.COMPLETED, "TARGET_SMOKE_TEST_PASSED")
        with connect(endpoints(settings)["control"]) as control_connection:
            migration = control_connection.execute(
                "SELECT migration_id FROM control.migration_tasks WHERE task_key = %s", (task_key,)
            ).fetchone()
            final_validation = control_connection.execute(
                """
                SELECT validation_run_id FROM control.validation_runs
                WHERE migration_id = %s AND scope = 'FINAL_QUIESCED' AND status = 'MATCHED'
                ORDER BY completed_at DESC LIMIT 1
                """,
                (migration["migration_id"],),
            ).fetchone()
            control_connection.execute(
                """
                UPDATE control.cutover_history
                SET completed_at=now(), outcome='COMPLETED', write_unavailability_ms=%s,
                    final_validation_run_id=%s,
                    evidence=jsonb_build_object('measurement', 'CONTROLLED_WRITE_FENCE_DURATION',
                                                'target_smoke_test', true,
                                                'sequence_count', %s::integer)
                WHERE cutover_id=%s
                """,
                (
                    downtime_ms, final_validation["validation_run_id"], len(sequences), cutover_id,
                ),
            )
        return {
            "cutover_id": cutover_id, "task_key": task_key, "state": final_record["state"],
            "active_database": "TARGET", "writes_enabled": True,
            "write_fence_duration_ms": downtime_ms,
            "downtime_measurement": "CONTROLLED_WRITE_FENCE_DURATION",
            "sequences_synchronized": sequences,
            "subscription_enabled": False, "source_application_writes_revoked": True,
            "completed_at": datetime.now(UTC),
        }
    except Exception:
        with connect(endpoints(settings)["control"]) as connection:
            connection.execute(
                "UPDATE control.cutover_history SET outcome='FAILED', completed_at=now() WHERE cutover_id=%s",
                (cutover_id,),
            )
        try:
            transition(settings, task_key, MigrationState.RECOVERY_REQUIRED, "CUTOVER_FAILED")
        except Exception:
            pass
        raise


def automated_cutover(settings: Settings, task_key: str, confirmation: str) -> dict[str, Any]:
    started = datetime.now(UTC)
    preparation = prepare_cutover(settings, task_key)
    execution = execute_cutover(settings, task_key, confirmation)
    execution["workflow_duration_ms"] = round((datetime.now(UTC) - started).total_seconds() * 1000)
    execution["preparation_validation_run_id"] = preparation["validation"]["validation_run_id"]
    return execution
