from datetime import UTC, datetime
from typing import Any

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from .config import Settings
from .database import Endpoint, connect, endpoints
from .state_machine import MigrationState, validate_transition

PUBLICATION_NAME = "parth_cloudshift_publication"
SUBSCRIPTION_NAME = "parth_cloudshift_subscription"
SLOT_NAME = "parth_cloudshift_slot"


def migration_record(settings: Settings, task_key: str) -> dict[str, Any] | None:
    control = endpoints(settings)["control"]
    with connect(control) as connection:
        return connection.execute(
            """
            SELECT task_key, state::text, version, created_at, updated_at
            FROM control.migration_tasks WHERE task_key = %s
            """,
            (task_key,),
        ).fetchone()


def list_migrations(settings: Settings) -> list[dict[str, Any]]:
    with connect(endpoints(settings)["control"]) as connection:
        return connection.execute(
            """
            SELECT task_key, state::text, version, created_at, updated_at
            FROM control.migration_tasks ORDER BY created_at
            """
        ).fetchall()


def transition(settings: Settings, task_key: str, requested: MigrationState, trigger: str) -> dict[str, Any]:
    control = endpoints(settings)["control"]
    with connect(control) as connection:
        row = connection.execute(
            "SELECT migration_id, state::text, version FROM control.migration_tasks WHERE task_key = %s FOR UPDATE",
            (task_key,),
        ).fetchone()
        if row is None:
            raise LookupError(task_key)
        current = MigrationState(row["state"])
        validate_transition(current, requested)
        updated = connection.execute(
            """
            UPDATE control.migration_tasks
            SET state = %s, version = version + 1, updated_at = now()
            WHERE migration_id = %s AND version = %s
            RETURNING task_key, state::text, version, created_at, updated_at
            """,
            (requested.value, row["migration_id"], row["version"]),
        ).fetchone()
        connection.execute(
            """
            INSERT INTO control.migration_events
                (migration_id, event_type, component, message, evidence)
            VALUES (%s, 'STATE_TRANSITION', 'cloudshift-control-plane', %s,
                    jsonb_build_object(
                        'previous_state', %s::text,
                        'current_state', %s::text,
                        'trigger', %s::text
                    ))
            """,
            (
                row["migration_id"], f"Migration transitioned from {current} to {requested}.",
                current.value, requested.value, trigger,
            ),
        )
        assert updated is not None
        return updated


def run_assessment(settings: Settings, task_key: str) -> dict[str, Any]:
    record = migration_record(settings, task_key)
    if record is None:
        raise LookupError(task_key)
    transition(settings, task_key, MigrationState.ASSESSING, "API_ASSESSMENT_REQUEST")
    source = endpoints(settings)["source"]
    target = endpoints(settings)["target"]
    findings: list[dict[str, Any]] = []

    def finding(identifier: str, severity: str, observed: Any, description: str, action: str) -> None:
        findings.append({
            "id": identifier, "severity": severity, "observed_evidence": observed,
            "description": description, "recommended_action": action,
        })

    with connect(source) as connection:
        wal_level = connection.execute("SHOW wal_level").fetchone()["wal_level"]
        finding("SOURCE_WAL_LEVEL", "PASS" if wal_level == "logical" else "BLOCKING", wal_level,
                "Source WAL level must support logical decoding.", "Set wal_level=logical and restart PostgreSQL.")
        missing_keys = connection.execute(
            """
            SELECT count(*) AS count FROM pg_class table_class
            JOIN pg_namespace namespace ON namespace.oid = table_class.relnamespace
            WHERE namespace.nspname = 'commerce' AND table_class.relkind = 'r'
              AND NOT EXISTS (
                SELECT 1 FROM pg_constraint constraint_record
                WHERE constraint_record.conrelid = table_class.oid AND constraint_record.contype = 'p'
              )
            """
        ).fetchone()["count"]
        finding("PRIMARY_KEYS", "PASS" if missing_keys == 0 else "BLOCKING", {"tables_without_primary_key": missing_keys},
                "Published tables require stable replica identity.", "Add primary keys or explicitly configure replica identity.")
        role = connection.execute(
            "SELECT rolreplication FROM pg_roles WHERE rolname = 'cloudshift_migrator'"
        ).fetchone()
        replication_role = bool(role and role["rolreplication"])
        finding("REPLICATION_ROLE", "PASS" if replication_role else "BLOCKING", replication_role,
                "Migration role requires PostgreSQL replication permission.", "Grant only the required replication and table privileges.")

    with connect(target) as connection:
        target_tables = connection.execute(
            "SELECT count(*) AS count FROM information_schema.tables WHERE table_schema = 'commerce' AND table_type = 'BASE TABLE'"
        ).fetchone()["count"]
        finding("TARGET_SCHEMA", "PASS" if target_tables == 13 else "BLOCKING", {"tables": target_tables},
                "Target commerce schema must match the supported schema.", "Apply the reviewed target schema before migration.")
        target_rows = connection.execute(
            "SELECT count(*) AS count FROM commerce.transaction_events"
        ).fetchone()["count"]
        finding("TARGET_EXISTING_ROWS", "PASS" if target_rows == 0 else "WARNING", {"transaction_events": target_rows},
                "Existing target records can conflict with initial synchronization.", "Use an empty target or verify it belongs to this migration.")

    has_blocker = any(item["severity"] == "BLOCKING" for item in findings)
    final_state = MigrationState.ASSESSMENT_FAILED if has_blocker else MigrationState.READY
    transition(settings, task_key, final_state, "ASSESSMENT_COMPLETED")
    return {
        "task_key": task_key,
        "state": final_state,
        "findings": findings,
        "executed_at": datetime.now(UTC),
    }


def _subscription_connection(settings: Settings) -> str:
    password = settings.migration_db_password.replace("'", "''").replace("\\", "\\\\")
    return (
        "host=source-db port=5432 dbname=parth_commerce_source "
        f"user=cloudshift_migrator password={password} application_name=cloudshift-cdc-worker"
    )


def start_migration(settings: Settings, task_key: str) -> dict[str, Any]:
    record = migration_record(settings, task_key)
    if record is None:
        raise LookupError(task_key)
    if record["state"] in {MigrationState.INITIAL_SYNC, MigrationState.CONTINUOUS_REPLICATION}:
        return replication_metrics(settings, task_key)
    transition(settings, task_key, MigrationState.INITIAL_SYNC, "API_START_REQUEST")
    try:
        source = endpoints(settings)["source"]
        with connect(source) as connection:
            exists = connection.execute(
                "SELECT 1 FROM pg_publication WHERE pubname = %s", (PUBLICATION_NAME,)
            ).fetchone()
            if not exists:
                connection.execute(
                    "CREATE PUBLICATION parth_cloudshift_publication FOR TABLES IN SCHEMA commerce"
                )

        target = endpoints(settings)["target"]
        with psycopg.connect(target.dsn, autocommit=True, row_factory=dict_row) as connection:
            exists = connection.execute(
                "SELECT 1 FROM pg_subscription WHERE subname = %s", (SUBSCRIPTION_NAME,)
            ).fetchone()
            if not exists:
                connection.execute(
                    sql.SQL(
                        "CREATE SUBSCRIPTION parth_cloudshift_subscription "
                        "CONNECTION {} PUBLICATION parth_cloudshift_publication "
                        "WITH (copy_data=true, create_slot=true, enabled=true, "
                        "slot_name='parth_cloudshift_slot')"
                    ).format(sql.Literal(_subscription_connection(settings)))
                )
        return replication_metrics(settings, task_key)
    except Exception:
        transition(settings, task_key, MigrationState.FAILED, "MIGRATION_START_FAILED")
        raise


def replication_metrics(settings: Settings, task_key: str) -> dict[str, Any]:
    record = migration_record(settings, task_key)
    if record is None:
        raise LookupError(task_key)
    with connect(endpoints(settings)["target"]) as connection:
        states = connection.execute(
            "SELECT srsubstate AS state, count(*) AS count FROM pg_subscription_rel GROUP BY srsubstate"
        ).fetchall()
        subscription = connection.execute(
            """
            SELECT sub.subname, stat.pid IS NOT NULL AS worker_active,
                   stat.received_lsn, stat.latest_end_lsn, stat.latest_end_time
            FROM pg_subscription sub
            LEFT JOIN pg_stat_subscription stat ON stat.subid = sub.oid
            WHERE sub.subname = %s
            """,
            (SUBSCRIPTION_NAME,),
        ).fetchone()
    with connect(endpoints(settings)["source"]) as connection:
        slot = connection.execute(
            """
            SELECT active, confirmed_flush_lsn::text,
                   pg_wal_lsn_diff(pg_current_wal_lsn(), confirmed_flush_lsn)::bigint AS wal_byte_lag
            FROM pg_replication_slots WHERE slot_name = %s
            """,
            (SLOT_NAME,),
        ).fetchone()
    ready_tables = sum(row["count"] for row in states if row["state"] == "r")
    if record["state"] == MigrationState.INITIAL_SYNC and ready_tables == 13 and slot and slot["active"]:
        record = transition(settings, task_key, MigrationState.CONTINUOUS_REPLICATION, "REPLICATION_READY_OBSERVED")
    return {
        "task_key": task_key,
        "state": record["state"],
        "table_states": {row["state"]: row["count"] for row in states},
        "ready_tables": ready_tables,
        "total_tables": 13,
        "subscription": subscription,
        "slot": slot,
        "measurement": {"wal_byte_lag": "MEASURED", "table_progress": "OBSERVED_STATE"},
        "observed_at": datetime.now(UTC),
    }


def pause_replication(settings: Settings, task_key: str) -> dict[str, Any]:
    record = migration_record(settings, task_key)
    if record is None:
        raise LookupError(task_key)
    if record["state"] != MigrationState.CONTINUOUS_REPLICATION:
        raise ValueError(f"replication pause requires CONTINUOUS_REPLICATION, observed {record['state']}")
    target = endpoints(settings)["target"]
    with psycopg.connect(target.dsn, autocommit=True) as connection:
        connection.execute("ALTER SUBSCRIPTION parth_cloudshift_subscription DISABLE")
    transition(settings, task_key, MigrationState.PAUSED, "REPLICATION_PAUSE_REQUEST")
    metrics = replication_metrics(settings, task_key)
    metrics["warning"] = "The inactive replication slot retains WAL until replication resumes or the slot is explicitly retired."
    return metrics


def resume_replication(settings: Settings, task_key: str) -> dict[str, Any]:
    record = migration_record(settings, task_key)
    if record is None:
        raise LookupError(task_key)
    if record["state"] != MigrationState.PAUSED:
        raise ValueError(f"replication resume requires PAUSED, observed {record['state']}")
    target = endpoints(settings)["target"]
    with psycopg.connect(target.dsn, autocommit=True) as connection:
        connection.execute("ALTER SUBSCRIPTION parth_cloudshift_subscription ENABLE")
    transition(settings, task_key, MigrationState.CONTINUOUS_REPLICATION, "REPLICATION_RESUME_REQUEST")
    return replication_metrics(settings, task_key)
