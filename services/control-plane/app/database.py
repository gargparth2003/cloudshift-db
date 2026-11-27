from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row

from .config import Settings
from .models import ColumnInfo, DatabaseHealth, HealthState, SchemaDiscovery, TableInfo


@dataclass(frozen=True)
class Endpoint:
    id: str
    resource_name: str
    environment: str
    role: str
    database_name: str
    dsn: str


def endpoints(settings: Settings) -> dict[str, Endpoint]:
    return {
        "source": Endpoint(
            "source", "pg-source-parth", "parth-source-dc01", "SOURCE",
            "parth_commerce_source", settings.source_database_url,
        ),
        "target": Endpoint(
            "target", "pg-target-parth", "parth-cloud-region01", "TARGET",
            "parth_commerce_target", settings.target_database_url,
        ),
        "control": Endpoint(
            "control", "pg-control-parth", "cloudshift-local-control", "CONTROL",
            "cloudshift_control", settings.control_database_url,
        ),
    }


@contextmanager
def connect(endpoint: Endpoint) -> Iterator[Connection[dict[str, Any]]]:
    with psycopg.connect(endpoint.dsn, connect_timeout=3, row_factory=dict_row) as connection:
        connection.execute("SET statement_timeout = '5s'")
        yield connection


def check_health(endpoint: Endpoint) -> DatabaseHealth:
    started = perf_counter()
    try:
        with connect(endpoint) as connection:
            row = connection.execute(
                "SELECT current_database() AS database_name, version() AS postgres_version"
            ).fetchone()
        assert row is not None
        return DatabaseHealth(
            endpoint_id=endpoint.id,
            resource_name=endpoint.resource_name,
            database_name=row["database_name"],
            postgres_version=row["postgres_version"],
            state=HealthState.AVAILABLE,
            latency_ms=round((perf_counter() - started) * 1000, 2),
            observed_at=datetime.now(UTC),
        )
    except psycopg.Error as exc:
        return DatabaseHealth(
            endpoint_id=endpoint.id,
            resource_name=endpoint.resource_name,
            state=HealthState.UNREACHABLE,
            latency_ms=round((perf_counter() - started) * 1000, 2),
            observed_at=datetime.now(UTC),
            error=exc.__class__.__name__,
        )


def discover_schema(endpoint: Endpoint) -> SchemaDiscovery:
    with connect(endpoint) as connection:
        table_rows = connection.execute(
            """
            SELECT n.nspname AS schema_name, c.relname AS table_name,
                   GREATEST(c.reltuples::bigint, 0) AS estimated_rows,
                   pg_total_relation_size(c.oid) AS total_bytes
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relkind IN ('r', 'p')
              AND n.nspname NOT IN ('pg_catalog', 'information_schema')
            ORDER BY n.nspname, c.relname
            """
        ).fetchall()
        column_rows = connection.execute(
            """
            SELECT table_schema AS schema_name, table_name, column_name,
                   data_type, is_nullable = 'YES' AS nullable, column_default
            FROM information_schema.columns
            WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
            ORDER BY table_schema, table_name, ordinal_position
            """
        ).fetchall()
        setting_rows = connection.execute(
            "SELECT name, setting FROM pg_settings WHERE name IN "
            "('wal_level', 'max_replication_slots', 'max_wal_senders') ORDER BY name"
        ).fetchall()

    columns: dict[tuple[str, str], list[ColumnInfo]] = {}
    for row in column_rows:
        key = (row["schema_name"], row["table_name"])
        columns.setdefault(key, []).append(
            ColumnInfo(
                name=row["column_name"], data_type=row["data_type"],
                nullable=row["nullable"], default=row["column_default"],
            )
        )
    tables = [
        TableInfo(
            schema_name=row["schema_name"], table_name=row["table_name"],
            estimated_rows=row["estimated_rows"], total_bytes=row["total_bytes"],
            columns=columns.get((row["schema_name"], row["table_name"]), []),
        )
        for row in table_rows
    ]
    return SchemaDiscovery(
        endpoint_id=endpoint.id,
        observed_at=datetime.now(UTC),
        tables=tables,
        settings={row["name"]: row["setting"] for row in setting_rows},
    )
