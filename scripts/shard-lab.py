#!/usr/bin/env python3
"""Execute region sharding and sequential/parallel distributed query practicals."""

from __future__ import annotations

import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter


ROOT = Path(__file__).resolve().parents[1]
SERVICES = ("shard-north", "shard-south", "shard-west")
COMPOSE = ["docker", "compose", "--project-name", "cloudshift-parth", "--profile", "distributed"]


def query(service: str) -> dict:
    started = perf_counter()
    result = subprocess.run(
        [*COMPOSE, "exec", "-T", service, "psql", "-U", "cloudshift_admin", "-d", "cloudshift_shard",
         "-At", "-F", "|", "-v", "ON_ERROR_STOP=1", "-c",
         "SELECT region_code,count(*),sum(annual_value) FROM shard.customers GROUP BY region_code;"],
        cwd=ROOT, check=True, capture_output=True, text=True, timeout=30,
    )
    region, count, value = result.stdout.strip().split("|")
    return {
        "service": service, "region": region, "rows": int(count),
        "annual_value": float(value), "duration_ms": round((perf_counter() - started) * 1000, 3),
    }


def main() -> int:
    sequential_started = perf_counter()
    sequential = [query(service) for service in SERVICES]
    sequential_ms = round((perf_counter() - sequential_started) * 1000, 3)
    parallel_started = perf_counter()
    with ThreadPoolExecutor(max_workers=3) as executor:
        parallel = list(executor.map(query, SERVICES))
    parallel_ms = round((perf_counter() - parallel_started) * 1000, 3)
    sequential_total = sum(item["rows"] for item in sequential)
    parallel_total = sum(item["rows"] for item in parallel)
    if sequential_total != 3000 or parallel_total != sequential_total:
        raise RuntimeError("distributed result merge failed")
    report = {
        "schema_version": 1,
        "observed_at": datetime.now(UTC).isoformat(),
        "practical_4": {
            "shard_key": "region_code",
            "independent_services": list(SERVICES),
            "distribution": sequential,
            "total_rows": sequential_total,
            "cross_shard_transaction_limit": "No atomic transaction coordinator is implemented across shards.",
        },
        "practical_5": {
            "query": "count and sum annual_value grouped locally by region",
            "decomposition": "one partial aggregate per physical PostgreSQL shard",
            "sequential_duration_ms": sequential_ms,
            "parallel_duration_ms": parallel_ms,
            "parallel_responses": parallel,
            "merged_rows": parallel_total,
            "results_identical": [item["rows"] for item in sequential] == [item["rows"] for item in parallel],
            "limitations": "One warm local trial; process and Docker overhead dominate this small dataset.",
        },
    }
    output = ROOT / "artifacts" / "labs" / "distributed-practicals-4-5.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
