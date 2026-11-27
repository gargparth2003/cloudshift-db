#!/usr/bin/env python3
"""Execute PromQL instant/range/rate practicals against measured CloudShift telemetry."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:19090/api/v1"


def query(path: str, parameters: dict) -> dict:
    with urlopen(f"{BASE}/{path}?{urlencode(parameters)}", timeout=10) as response:
        document = json.load(response)
    if document["status"] != "success":
        raise RuntimeError(document)
    return document["data"]


def main() -> int:
    end = datetime.now(UTC)
    start = end - timedelta(hours=1)
    expressions = {
        "instant_target_health": "up",
        "database_availability_gauge": "cloudshift_database_available",
        "workload_counter": "cloudshift_workload_operations_total",
        "workload_rate": "sum(rate(cloudshift_workload_operations_total[5m]))",
        "wal_lag_gauge": "cloudshift_replication_wal_byte_lag",
        "validation_duration": "cloudshift_validation_duration_ms",
    }
    instant = {name: query("query", {"query": expression}) for name, expression in expressions.items()}
    range_data = query(
        "query_range",
        {
            "query": "cloudshift_replication_wal_byte_lag",
            "start": start.timestamp(), "end": end.timestamp(), "step": "30s",
        },
    )
    report = {
        "schema_version": 1,
        "observed_at": end.isoformat(),
        "practical": 9,
        "queries": expressions,
        "instant_results": instant,
        "range_query": {"window": "1h", "step": "30s", "result": range_data},
        "explanation": "Counters represent cumulative operations and require rate/increase functions; gauges represent current availability, state, connections, or lag and can move both directions.",
        "limitations": "Prometheus retention is six hours and the local process restart/reset history is intentionally bounded.",
    }
    output = ROOT / "artifacts" / "labs" / "prometheus-practical-9.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"instant_queries={len(instant)} range_series={len(range_data['result'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
