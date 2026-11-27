import hashlib
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, Iterator
from uuid import UUID

from psycopg import Connection, sql
from psycopg.rows import DictRow

from .config import Settings
from .database import connect, endpoints
from .state_machine import MigrationState
from .migration import migration_record, replication_metrics, transition

MAX_CAPTURED_MISMATCHES = 100


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        normalized = value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
        return normalized.isoformat(timespec="microseconds")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, UUID):
        return str(value)
    raise TypeError(f"unsupported canonical value: {type(value).__name__}")


def canonical_row(row: dict[str, Any]) -> bytes:
    return json.dumps(
        row, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        default=_json_default,
    ).encode("utf-8")


def _table_primary_keys(connection: Connection[DictRow]) -> list[tuple[str, list[str]]]:
    rows = connection.execute(
        """
        SELECT table_class.relname AS table_name,
               array_agg(attribute.attname ORDER BY key_column.ordinality) AS primary_key
        FROM pg_constraint constraint_record
        JOIN pg_class table_class ON table_class.oid = constraint_record.conrelid
        JOIN pg_namespace namespace ON namespace.oid = table_class.relnamespace
        JOIN unnest(constraint_record.conkey) WITH ORDINALITY key_column(attnum, ordinality) ON true
        JOIN pg_attribute attribute
          ON attribute.attrelid = table_class.oid AND attribute.attnum = key_column.attnum
        WHERE constraint_record.contype = 'p' AND namespace.nspname = 'commerce'
        GROUP BY table_class.relname
        ORDER BY table_class.relname
        """
    ).fetchall()
    return [(row["table_name"], row["primary_key"]) for row in rows]


def _stream_rows(
    connection: Connection[DictRow], table: str, primary_key: list[str], cursor_name: str
) -> Iterator[dict[str, Any]]:
    query = sql.SQL("SELECT * FROM {}.{} ORDER BY {}").format(
        sql.Identifier("commerce"),
        sql.Identifier(table),
        sql.SQL(", ").join(sql.Identifier(column) for column in primary_key),
    )
    with connection.cursor(name=cursor_name) as cursor:
        cursor.itersize = 500
        cursor.execute(query)
        while batch := cursor.fetchmany(500):
            yield from batch


def _key(row: dict[str, Any], columns: list[str]) -> tuple[Any, ...]:
    return tuple(row[column] for column in columns)


def _json_safe(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return json.loads(canonical_row(row))


def _compare_table(
    source_connection: Connection[DictRow],
    target_connection: Connection[DictRow],
    table: str,
    primary_key: list[str],
) -> dict[str, Any]:
    source_iterator = iter(_stream_rows(source_connection, table, primary_key, f"source_{table}"))
    target_iterator = iter(_stream_rows(target_connection, table, primary_key, f"target_{table}"))
    source_row = next(source_iterator, None)
    target_row = next(target_iterator, None)
    source_hash = hashlib.sha256()
    target_hash = hashlib.sha256()
    checked = matched = missing = extra = mismatched = 0
    captured: list[dict[str, Any]] = []

    while source_row is not None or target_row is not None:
        source_key = _key(source_row, primary_key) if source_row is not None else None
        target_key = _key(target_row, primary_key) if target_row is not None else None
        if target_row is None or (source_row is not None and source_key < target_key):
            source_bytes = canonical_row(source_row)
            source_hash.update(source_bytes)
            missing += 1
            checked += 1
            if len(captured) < MAX_CAPTURED_MISMATCHES:
                captured.append({"primary_key": source_key, "source": _json_safe(source_row), "target": None})
            source_row = next(source_iterator, None)
            continue
        if source_row is None or target_key < source_key:
            target_bytes = canonical_row(target_row)
            target_hash.update(target_bytes)
            extra += 1
            checked += 1
            if len(captured) < MAX_CAPTURED_MISMATCHES:
                captured.append({"primary_key": target_key, "source": None, "target": _json_safe(target_row)})
            target_row = next(target_iterator, None)
            continue

        source_bytes = canonical_row(source_row)
        target_bytes = canonical_row(target_row)
        source_hash.update(source_bytes)
        target_hash.update(target_bytes)
        checked += 1
        if source_bytes == target_bytes:
            matched += 1
        else:
            mismatched += 1
            if len(captured) < MAX_CAPTURED_MISMATCHES:
                captured.append({"primary_key": source_key, "source": _json_safe(source_row), "target": _json_safe(target_row)})
        source_row = next(source_iterator, None)
        target_row = next(target_iterator, None)

    return {
        "schema_name": "commerce", "table_name": table,
        "rows_checked": checked, "rows_matched": matched,
        "missing_rows": missing, "extra_rows": extra, "mismatched_rows": mismatched,
        "source_checksum": source_hash.hexdigest(), "target_checksum": target_hash.hexdigest(),
        "checksum_method": "SHA-256 over canonical JSON rows ordered by primary key",
        "captured_mismatches": captured,
    }


def run_validation(settings: Settings, task_key: str, scope: str) -> dict[str, Any]:
    if scope not in {"FULL", "FINAL_QUIESCED"}:
        raise ValueError("validation scope must be FULL or FINAL_QUIESCED")
    record = migration_record(settings, task_key)
    if record is None:
        raise LookupError(task_key)
    metrics = replication_metrics(settings, task_key)
    if not metrics["slot"] or not metrics["slot"]["active"] or metrics["ready_tables"] != 13:
        raise ValueError("replication is not ready for validation")
    if scope == "FINAL_QUIESCED":
        with connect(endpoints(settings)["control"]) as connection:
            route = connection.execute(
                """
                SELECT active_endpoint::text, writes_enabled
                FROM control.application_routes WHERE route_key = 'parth-commerce-application'
                """
            ).fetchone()
        if route is None or route["active_endpoint"] != "SOURCE" or route["writes_enabled"]:
            raise ValueError("final quiesced validation requires a fenced source application route")

    transition(settings, task_key, MigrationState.VALIDATING, "VALIDATION_REQUEST")
    control = endpoints(settings)["control"]
    with connect(control) as connection:
        migration = connection.execute(
            "SELECT migration_id FROM control.migration_tasks WHERE task_key = %s", (task_key,)
        ).fetchone()
        validation = connection.execute(
            """
            INSERT INTO control.validation_runs (migration_id, scope, status)
            VALUES (%s, %s, 'RUNNING') RETURNING validation_run_id
            """,
            (migration["migration_id"], scope),
        ).fetchone()
        validation_run_id = validation["validation_run_id"]

    started = datetime.now(UTC)
    results: list[dict[str, Any]] = []
    try:
        with connect(endpoints(settings)["source"]) as source_connection, connect(
            endpoints(settings)["target"]
        ) as target_connection:
            source_connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            target_connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            for table, primary_key in _table_primary_keys(source_connection):
                results.append(_compare_table(source_connection, target_connection, table, primary_key))

        mismatch_count = sum(
            item["missing_rows"] + item["extra_rows"] + item["mismatched_rows"] for item in results
        )
        status = "MATCHED" if mismatch_count == 0 else "MISMATCHED"
        with connect(control) as connection:
            for result in results:
                result_row = connection.execute(
                    """
                    INSERT INTO control.validation_results
                        (validation_run_id, schema_name, table_name, rows_checked, rows_matched,
                         missing_rows, extra_rows, mismatched_rows, checksum_method)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING result_id
                    """,
                    (
                        validation_run_id, result["schema_name"], result["table_name"],
                        result["rows_checked"], result["rows_matched"], result["missing_rows"],
                        result["extra_rows"], result["mismatched_rows"], result["checksum_method"],
                    ),
                ).fetchone()
                for mismatch in result["captured_mismatches"]:
                    connection.execute(
                        """
                        INSERT INTO control.validation_mismatches
                            (result_id, primary_key, source_value, target_value)
                        VALUES (%s, %s::jsonb, %s::jsonb, %s::jsonb)
                        """,
                        (
                            result_row["result_id"], json.dumps(mismatch["primary_key"], default=_json_default),
                            json.dumps(mismatch["source"], default=_json_default) if mismatch["source"] else None,
                            json.dumps(mismatch["target"], default=_json_default) if mismatch["target"] else None,
                        ),
                    )
            connection.execute(
                "UPDATE control.validation_runs SET status = %s, completed_at = now() WHERE validation_run_id = %s",
                (status, validation_run_id),
            )
        next_state = (
            MigrationState.READY_FOR_CUTOVER
            if scope == "FINAL_QUIESCED" and mismatch_count == 0
            else MigrationState.CONTINUOUS_REPLICATION
        )
        transition(settings, task_key, next_state, "VALIDATION_COMPLETED")
        return {
            "validation_run_id": validation_run_id, "task_key": task_key, "scope": scope,
            "consistency_boundary": (
                "FINAL_QUIESCED" if scope == "FINAL_QUIESCED"
                else "PRELIMINARY_STABLE_OBSERVATION"
            ),
            "cutover_safe": scope == "FINAL_QUIESCED" and mismatch_count == 0,
            "status": status, "mismatch_count": mismatch_count,
            "rows_checked": sum(item["rows_checked"] for item in results),
            "duration_ms": round((datetime.now(UTC) - started).total_seconds() * 1000, 2),
            "tables": results,
        }
    except Exception:
        with connect(control) as connection:
            connection.execute(
                "UPDATE control.validation_runs SET status = 'FAILED', completed_at = now() WHERE validation_run_id = %s",
                (validation_run_id,),
            )
        transition(settings, task_key, MigrationState.CONTINUOUS_REPLICATION, "VALIDATION_FAILED")
        raise
