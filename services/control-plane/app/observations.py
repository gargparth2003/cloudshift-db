from datetime import UTC, datetime
from typing import Any

from psycopg import sql

from .config import Settings
from .cutover import application_route
from .database import check_health, connect, endpoints
from .migration import migration_record, replication_metrics


def migration_events(settings: Settings, task_key: str, limit: int = 100) -> list[dict[str, Any]]:
    with connect(endpoints(settings)["control"]) as connection:
        rows = connection.execute(
            """
            SELECT event.event_id, event.event_type, event.component,
                   event.severity::text, event.message, event.evidence, event.occurred_at
            FROM control.migration_events event
            JOIN control.migration_tasks task ON task.migration_id = event.migration_id
            WHERE task.task_key = %s
            ORDER BY event.occurred_at DESC LIMIT %s
            """,
            (task_key, limit),
        ).fetchall()
    return rows


def validation_history(settings: Settings, task_key: str, limit: int = 20) -> list[dict[str, Any]]:
    with connect(endpoints(settings)["control"]) as connection:
        rows = connection.execute(
            """
            SELECT run.validation_run_id, run.scope, run.status, run.started_at, run.completed_at,
                   COALESCE(sum(result.rows_checked), 0)::bigint AS rows_checked,
                   COALESCE(sum(result.missing_rows + result.extra_rows + result.mismatched_rows), 0)::bigint AS mismatches
            FROM control.validation_runs run
            JOIN control.migration_tasks task ON task.migration_id = run.migration_id
            LEFT JOIN control.validation_results result ON result.validation_run_id = run.validation_run_id
            WHERE task.task_key = %s
            GROUP BY run.validation_run_id
            ORDER BY run.started_at DESC LIMIT %s
            """,
            (task_key, limit),
        ).fetchall()
    return rows


def cutover_history(settings: Settings, task_key: str, limit: int = 20) -> list[dict[str, Any]]:
    with connect(endpoints(settings)["control"]) as connection:
        histories = connection.execute(
            """
            SELECT history.cutover_id, history.requested_at, history.completed_at,
                   history.outcome, history.write_unavailability_ms,
                   history.final_validation_run_id, history.evidence
            FROM control.cutover_history history
            JOIN control.migration_tasks task ON task.migration_id = history.migration_id
            WHERE task.task_key = %s
            ORDER BY history.requested_at DESC LIMIT %s
            """,
            (task_key, limit),
        ).fetchall()
        for history in histories:
            history["stages"] = connection.execute(
                """
                SELECT stage_name, stage_order, status, started_at, completed_at,
                       evidence, error_message
                FROM control.cutover_stages
                WHERE cutover_id = %s ORDER BY stage_order
                """,
                (history["cutover_id"],),
            ).fetchall()
    return histories


def backup_inventory(settings: Settings, limit: int = 100) -> list[dict[str, Any]]:
    with connect(endpoints(settings)["control"]) as connection:
        return connection.execute(
            """
            SELECT backup.backup_id, endpoint.endpoint_key, endpoint.resource_name,
                   backup.storage_reference, backup.size_bytes, backup.checksum,
                   backup.verification_status, backup.created_at, backup.verified_at
            FROM control.backup_records backup
            JOIN control.database_endpoints endpoint ON endpoint.endpoint_id=backup.endpoint_id
            ORDER BY backup.created_at DESC LIMIT %s
            """,
            (limit,),
        ).fetchall()


def incident_history(settings: Settings, limit: int = 100) -> list[dict[str, Any]]:
    with connect(endpoints(settings)["control"]) as connection:
        return connection.execute(
            """
            SELECT incident.incident_id, task.task_key, incident.severity::text,
                   incident.affected_resources, incident.symptoms, incident.suspected_cause,
                   incident.verified_cause, incident.supporting_evidence,
                   incident.detection_duration_ms, incident.recovery_action,
                   incident.recovery_result, incident.recovery_timestamp,
                   incident.recovery_duration_ms, incident.remaining_risk,
                   incident.detected_at, incident.resolved_at
            FROM control.migration_incidents incident
            LEFT JOIN control.migration_tasks task ON task.migration_id=incident.migration_id
            ORDER BY incident.detected_at DESC LIMIT %s
            """,
            (limit,),
        ).fetchall()


def experiment_history(settings: Settings, limit: int = 100) -> list[dict[str, Any]]:
    with connect(endpoints(settings)["control"]) as connection:
        return connection.execute(
            """
            SELECT experiment_id, experiment_type, status, configuration, result,
                   started_at, completed_at
            FROM control.experiment_runs ORDER BY started_at DESC LIMIT %s
            """,
            (limit,),
        ).fetchall()


def table_observations(settings: Settings, task_key: str) -> list[dict[str, Any]]:
    if migration_record(settings, task_key) is None:
        raise LookupError(task_key)
    result: dict[str, dict[str, Any]] = {}
    for endpoint_id in ("source", "target"):
        with connect(endpoints(settings)[endpoint_id]) as connection:
            rows = connection.execute(
                """
                SELECT table_name, estimated_rows, total_bytes
                FROM (
                    SELECT class.relname AS table_name,
                           GREATEST(class.reltuples::bigint, 0) AS estimated_rows,
                           pg_total_relation_size(class.oid) AS total_bytes
                    FROM pg_class class
                    JOIN pg_namespace namespace ON namespace.oid = class.relnamespace
                    WHERE namespace.nspname = 'commerce' AND class.relkind = 'r'
                ) tables ORDER BY table_name
                """
            ).fetchall()
            for row in rows:
                entry = result.setdefault(row["table_name"], {"schema": "commerce", "table": row["table_name"]})
                entry[f"{endpoint_id}_row_estimate"] = row["estimated_rows"]
                entry[f"{endpoint_id}_bytes"] = row["total_bytes"]

    with connect(endpoints(settings)["target"]) as connection:
        states = connection.execute(
            """
            SELECT class.relname AS table_name, relation.srsubstate AS state
            FROM pg_subscription_rel relation
            JOIN pg_class class ON class.oid = relation.srrelid
            """
        ).fetchall()
    for row in states:
        if row["table_name"] in result:
            result[row["table_name"]]["subscription_state"] = row["state"]

    with connect(endpoints(settings)["control"]) as connection:
        validations = connection.execute(
            """
            SELECT DISTINCT ON (result.table_name) result.table_name,
                   result.missing_rows, result.extra_rows, result.mismatched_rows,
                   run.status, run.completed_at
            FROM control.validation_results result
            JOIN control.validation_runs run ON run.validation_run_id = result.validation_run_id
            JOIN control.migration_tasks task ON task.migration_id = run.migration_id
            WHERE task.task_key = %s
            ORDER BY result.table_name, run.completed_at DESC NULLS LAST
            """,
            (task_key,),
        ).fetchall()
    for row in validations:
        if row["table_name"] in result:
            result[row["table_name"]]["validation"] = row
    return list(result.values())


def topology(settings: Settings, task_key: str) -> dict[str, Any]:
    record = migration_record(settings, task_key)
    if record is None:
        raise LookupError(task_key)
    health = {key: check_health(value) for key, value in endpoints(settings).items()}
    route = application_route(settings)
    metrics = replication_metrics(settings, task_key)
    return {
        "task_key": task_key,
        "state": record["state"],
        "route": route,
        "resources": [
            {"id": "commerce", "name": "parth-commerce-application", "type": "APPLICATION", "health": "AVAILABLE"},
            {"id": "router", "name": "parth-application-router", "type": "ROUTER", "health": "AVAILABLE", "state": route["active_endpoint"]},
            *[
                {
                    "id": key, "name": value.resource_name, "type": "POSTGRESQL",
                    "health": value.state, "version": value.postgres_version,
                    "last_observed": value.observed_at,
                }
                for key, value in health.items()
            ],
            {"id": "replication", "name": "PostgreSQL logical replication", "type": "INTERNAL_WORKER", "health": "AVAILABLE" if metrics["subscription"] else "UNAVAILABLE", "state": "ACTIVE" if metrics["subscription"] and metrics["subscription"]["worker_active"] else "STOPPED"},
            {"id": "validation", "name": "cloudshift-validation-engine", "type": "CONTROL_PLANE", "health": "AVAILABLE"},
        ],
        "connections": [
            {"id": "commerce-router", "source": "commerce", "target": "router", "category": "APPLICATION", "active": True},
            {"id": "router-source", "source": "router", "target": "source", "category": "APPLICATION", "active": route["active_endpoint"] == "SOURCE"},
            {"id": "router-target", "source": "router", "target": "target", "category": "APPLICATION", "active": route["active_endpoint"] == "TARGET"},
            {"id": "source-replication", "source": "source", "target": "replication", "category": "REPLICATION", "active": bool(metrics["subscription"] and metrics["subscription"]["worker_active"])},
            {"id": "replication-target", "source": "replication", "target": "target", "category": "REPLICATION", "active": bool(metrics["subscription"] and metrics["subscription"]["worker_active"])},
            {"id": "source-validation", "source": "source", "target": "validation", "category": "VALIDATION", "active": record["state"] == "VALIDATING"},
            {"id": "target-validation", "source": "target", "target": "validation", "category": "VALIDATION", "active": record["state"] == "VALIDATING"},
        ],
        "replication": metrics,
        "observed_at": datetime.now(UTC),
    }
