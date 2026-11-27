"""Executable PostgreSQL experiments for Advanced DBMS practicals 1–3."""

from __future__ import annotations

import json
import sys
import threading
from datetime import UTC, datetime
from time import perf_counter, sleep
from typing import Any

import psycopg
from psycopg import errors
from psycopg.rows import dict_row

from .config import get_settings


settings = get_settings()


def connection(**kwargs):
    return psycopg.connect(settings.target_database_url, row_factory=dict_row, **kwargs)


def plan(conn, query: str) -> dict[str, Any]:
    row = conn.execute(f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {query}").fetchone()
    document = row["QUERY PLAN"][0]
    node = document["Plan"]
    return {
        "node_type": node["Node Type"],
        "index_name": node.get("Index Name"),
        "actual_rows": node["Actual Rows"],
        "planning_time_ms": document["Planning Time"],
        "execution_time_ms": document["Execution Time"],
        "shared_hit_blocks": node.get("Shared Hit Blocks", 0),
        "shared_read_blocks": node.get("Shared Read Blocks", 0),
    }


def normalization() -> dict[str, Any]:
    with connection() as conn:
        relations = conn.execute(
            """
            SELECT class.relname AS relation, class.relkind,
                   pg_total_relation_size(class.oid) AS total_bytes
            FROM pg_class class JOIN pg_namespace namespace ON namespace.oid=class.relnamespace
            WHERE namespace.nspname='commerce' AND class.relkind IN ('r','m')
            ORDER BY class.relkind, class.relname
            """
        ).fetchall()
        normalized = plan(
            conn,
            """SELECT products.product_id, products.name,
                      COALESCE(sum(items.quantity),0) AS units
               FROM commerce.products products
               LEFT JOIN commerce.order_items items USING (product_id)
               GROUP BY products.product_id, products.name ORDER BY products.product_id""",
        )
        conn.execute("REFRESH MATERIALIZED VIEW commerce.product_sales_summary")
        conn.commit()
        denormalized = plan(
            conn,
            "SELECT product_id, units_ordered FROM commerce.product_sales_summary ORDER BY product_id",
        )
        constraints = conn.execute(
            """
            SELECT count(*) FILTER (WHERE contype='p') AS primary_keys,
                   count(*) FILTER (WHERE contype='f') AS foreign_keys,
                   count(*) FILTER (WHERE contype='u') AS unique_constraints
            FROM pg_constraint constraint_record
            JOIN pg_namespace namespace ON namespace.oid=constraint_record.connamespace
            WHERE namespace.nspname='commerce'
            """
        ).fetchone()
    return {
        "practical": 1,
        "objective": "Compare normalized commerce relationships with a denormalized analytical representation.",
        "normal_forms": {
            "1NF": "Scalar columns and primary keys; repeating order items are separate rows.",
            "2NF": "Non-key order-item facts depend on the complete order_item_id key.",
            "3NF": "Customer, product, supplier, payment, shipment, and warehouse attributes are separated.",
            "BCNF": "Determinants represented by declared candidate keys; business dependencies outside constraints remain an application responsibility.",
        },
        "constraints": constraints,
        "relation_storage": relations,
        "normalized_aggregate_plan": normalized,
        "materialized_summary_plan": denormalized,
        "limitations": "One local dataset and warm-cache plans; materialized data trades freshness and refresh cost for read speed.",
    }


def acid_and_isolation() -> dict[str, Any]:
    with connection() as conn:
        conn.execute("CREATE SCHEMA IF NOT EXISTS lab")
        conn.execute("DROP TABLE IF EXISTS lab.accounts")
        conn.execute("CREATE TABLE lab.accounts (account_id integer PRIMARY KEY, balance integer NOT NULL CHECK (balance >= 0))")
        conn.execute("INSERT INTO lab.accounts VALUES (1,1000),(2,1000)")
        conn.commit()

    with connection() as conn:
        before = conn.execute("SELECT sum(balance) AS total FROM lab.accounts").fetchone()["total"]
        conn.execute("UPDATE lab.accounts SET balance=balance-100 WHERE account_id=1")
        conn.rollback()
    with connection() as conn:
        after_rollback = conn.execute("SELECT sum(balance) AS total FROM lab.accounts").fetchone()["total"]
        consistency_rejected = False
        try:
            conn.execute("UPDATE lab.accounts SET balance=-1 WHERE account_id=1")
        except errors.CheckViolation:
            consistency_rejected = True
            conn.rollback()
        conn.execute("UPDATE lab.accounts SET balance=balance+25 WHERE account_id=2")
        conn.commit()
    with connection() as conn:
        durable_balance = conn.execute("SELECT balance FROM lab.accounts WHERE account_id=2").fetchone()["balance"]

    def isolation_observation(level: str) -> tuple[int, int]:
        with connection() as reset:
            reset.execute("UPDATE lab.accounts SET balance=1000 WHERE account_id=1")
            reset.commit()
        with connection() as reader, connection() as writer:
            reader.execute(f"SET TRANSACTION ISOLATION LEVEL {level}")
            first = reader.execute("SELECT balance FROM lab.accounts WHERE account_id=1").fetchone()["balance"]
            writer.execute("UPDATE lab.accounts SET balance=balance+10 WHERE account_id=1")
            writer.commit()
            second = reader.execute("SELECT balance FROM lab.accounts WHERE account_id=1").fetchone()["balance"]
            reader.rollback()
        return first, second

    read_committed = isolation_observation("READ COMMITTED")
    repeatable_read = isolation_observation("REPEATABLE READ")

    with connection() as setup:
        setup.execute("DROP TABLE IF EXISTS lab.doctors")
        setup.execute("CREATE TABLE lab.doctors (doctor_id integer PRIMARY KEY, on_call boolean NOT NULL)")
        setup.execute("INSERT INTO lab.doctors VALUES (1,true),(2,true)")
        setup.commit()
    barrier = threading.Barrier(2)
    serializable_results: list[str] = []

    def doctor_transaction(doctor_id: int) -> None:
        try:
            with connection() as conn:
                conn.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
                count = conn.execute("SELECT count(*) AS count FROM lab.doctors WHERE on_call").fetchone()["count"]
                barrier.wait(timeout=5)
                if count > 1:
                    conn.execute("UPDATE lab.doctors SET on_call=false WHERE doctor_id=%s", (doctor_id,))
                conn.commit()
                serializable_results.append("COMMITTED")
        except errors.SerializationFailure:
            serializable_results.append("SERIALIZATION_FAILURE")

    threads = [threading.Thread(target=doctor_transaction, args=(item,)) for item in (1, 2)]
    for item in threads: item.start()
    for item in threads: item.join()

    lock_result: dict[str, Any] = {}
    holder = connection()
    holder.execute("UPDATE lab.accounts SET balance=balance+1 WHERE account_id=1")

    def blocked_update() -> None:
        started = perf_counter()
        with connection() as conn:
            conn.execute("SET lock_timeout='5s'")
            conn.execute("UPDATE lab.accounts SET balance=balance+1 WHERE account_id=1")
            conn.commit()
        lock_result["blocked_ms"] = round((perf_counter() - started) * 1000, 2)

    waiter = threading.Thread(target=blocked_update)
    waiter.start()
    sleep(0.5)
    holder.commit()
    holder.close()
    waiter.join()

    return {
        "practical": 2,
        "atomicity": {"before": before, "after_rollback": after_rollback, "preserved": before == after_rollback},
        "consistency": {"negative_balance_rejected": consistency_rejected},
        "durability": {"committed_balance_from_new_session": durable_balance},
        "read_committed": {"first_read": read_committed[0], "second_read": read_committed[1]},
        "repeatable_read": {"first_read": repeatable_read[0], "second_read": repeatable_read[1]},
        "serializable": {"outcomes": sorted(serializable_results)},
        "lock_contention": lock_result,
        "limitations": "PostgreSQL maps READ UNCOMMITTED to READ COMMITTED; anomaly outcomes are PostgreSQL-specific.",
    }


def indexing() -> dict[str, Any]:
    with connection() as conn:
        conn.execute("CREATE SCHEMA IF NOT EXISTS lab")
        conn.execute("DROP TABLE IF EXISTS lab.index_probe")
        conn.execute("CREATE TABLE lab.index_probe (probe_id bigint PRIMARY KEY, lookup_key text NOT NULL, bucket integer NOT NULL, payload text NOT NULL)")
        conn.execute("INSERT INTO lab.index_probe SELECT series, md5(series::text), series % 100, repeat('x',80) FROM generate_series(1,100000) series")
        conn.execute("ANALYZE lab.index_probe")
        conn.commit()
        query = "SELECT * FROM lab.index_probe WHERE lookup_key=md5('50000')"
        unindexed = plan(conn, query)
        conn.execute("CREATE INDEX index_probe_lookup_btree ON lab.index_probe USING btree(lookup_key)")
        conn.commit()
        btree = plan(conn, query)
        conn.execute("DROP INDEX lab.index_probe_lookup_btree")
        conn.execute("CREATE INDEX index_probe_lookup_hash ON lab.index_probe USING hash(lookup_key)")
        conn.execute("CREATE INDEX index_probe_bucket_id ON lab.index_probe(bucket, probe_id)")
        conn.commit()
        hash_plan = plan(conn, query)
        composite = plan(conn, "SELECT * FROM lab.index_probe WHERE bucket=42 ORDER BY probe_id LIMIT 100")
        sizes = conn.execute(
            "SELECT indexrelid::regclass::text AS index_name, pg_relation_size(indexrelid) AS bytes FROM pg_index WHERE indrelid='lab.index_probe'::regclass ORDER BY 1"
        ).fetchall()
    return {
        "practical": 3, "rows": 100000,
        "unindexed": unindexed, "btree": btree, "hash": hash_plan, "composite": composite,
        "index_sizes": sizes,
        "explanation": "B-tree supports equality, ordering, and ranges; hash targets equality. PostgreSQL bitmap scans are runtime access paths, not a separately stored bitmap index type.",
        "limitations": "Single local warm-cache observation; use repeated trials before drawing performance conclusions.",
    }


def reset() -> None:
    with connection() as conn:
        conn.execute("DROP SCHEMA IF EXISTS lab CASCADE")
        conn.commit()


def main() -> int:
    command = sys.argv[1] if len(sys.argv) > 1 else "run"
    if command == "reset":
        reset()
        print(json.dumps({"reset": True}))
        return 0
    result = {
        "schema_version": 1,
        "observed_at": datetime.now(UTC).isoformat(),
        "database": "parth_commerce_target",
        "practicals": [normalization(), acid_and_isolation(), indexing()],
    }
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
