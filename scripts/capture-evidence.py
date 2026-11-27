#!/usr/bin/env python3
"""Capture a sanitized, read-only replay evidence bundle from the local stack."""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


TASK_KEY = "parth-commerce-migration-001"
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def fetch_json(base_url: str, path: str) -> Any:
    request = Request(f"{base_url}{path}", headers={"accept": "application/json"})
    with urlopen(request, timeout=15) as response:
        return json.load(response)


def safe_fetch(base_url: str, path: str) -> dict[str, Any]:
    try:
        return {"available": True, "value": fetch_json(base_url, path)}
    except Exception as exc:  # evidence capture must preserve partial results
        return {"available": False, "error": f"{type(exc).__name__}: {exc}"}


def compose_inventory() -> dict[str, Any]:
    command = [
        "docker", "compose", "--project-name", "cloudshift-parth",
        "--profile", "core", "--profile", "observability", "ps", "--format", "json",
    ]
    try:
        result = subprocess.run(
            command, cwd=PROJECT_ROOT, check=True, capture_output=True, text=True, timeout=30,
        )
        records = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
        allowed = {"Name", "Service", "State", "Health", "Image", "Publishers"}
        return {"available": True, "value": [{key: row.get(key) for key in allowed} for row in records]}
    except Exception as exc:
        return {"available": False, "error": f"{type(exc).__name__}: {exc}"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="JSON output path")
    args = parser.parse_args()

    captured_at = datetime.now(UTC)
    api_port = os.environ.get("CLOUDSHIFT_API_PORT", "18000")
    workload_port = os.environ.get("CLOUDSHIFT_WORKLOAD_PORT", "18002")
    commerce_port = os.environ.get("CLOUDSHIFT_COMMERCE_PORT", "18001")
    prometheus_port = os.environ.get("CLOUDSHIFT_PROMETHEUS_PORT", "19090")
    api = f"http://127.0.0.1:{api_port}"
    workload = f"http://127.0.0.1:{workload_port}"
    commerce = f"http://127.0.0.1:{commerce_port}"
    prometheus = f"http://127.0.0.1:{prometheus_port}"

    api_paths = {
        "health": "/api/v1/health",
        "migration": f"/api/v1/migrations/{TASK_KEY}",
        "route": "/api/v1/application-route",
        "replication": f"/api/v1/migrations/{TASK_KEY}/metrics",
        "topology": f"/api/v1/migrations/{TASK_KEY}/topology",
        "tables": f"/api/v1/migrations/{TASK_KEY}/tables",
        "validations": f"/api/v1/migrations/{TASK_KEY}/validations?limit=100",
        "cutovers": f"/api/v1/migrations/{TASK_KEY}/cutovers?limit=100",
        "events": f"/api/v1/migrations/{TASK_KEY}/events?limit=500",
        "backups": "/api/v1/backups?limit=100",
        "incidents": "/api/v1/incidents?limit=100",
        "experiments": "/api/v1/experiments?limit=100",
    }
    workload_paths = {
        "workload": "/api/v1/workload",
        "workload_operations": "/api/v1/workload/operations?limit=500",
        "probe": "/api/v1/probe",
        "probe_observations": "/api/v1/probe/observations?limit=1000",
    }
    commerce_paths = {
        "health": "/api/v1/commerce/health",
        "orders": "/api/v1/commerce/orders?limit=100",
        "activity": "/api/v1/commerce/activity?limit=200",
    }
    prometheus_queries = {
        "scrape_up": "up",
        "database_available": "cloudshift_database_available",
        "migration_state": "cloudshift_migration_state",
        "retained_wal_bytes": "cloudshift_replication_wal_byte_lag",
    }

    evidence = {
        "schema_version": 1,
        "kind": "cloudshift-local-replay-evidence",
        "captured_at": captured_at.isoformat(),
        "claim_boundary": (
            "Sanitized observations from one local development run; not a production, cloud, "
            "zero-downtime, or capacity claim."
        ),
        "host": {"system": platform.system(), "machine": platform.machine()},
        "compose": compose_inventory(),
        "control_plane": {name: safe_fetch(api, path) for name, path in api_paths.items()},
        "workload_and_probe": {
            name: safe_fetch(workload, path) for name, path in workload_paths.items()
        },
        "commerce_application": {
            name: safe_fetch(commerce, path) for name, path in commerce_paths.items()
        },
        "prometheus": {
            name: safe_fetch(prometheus, f"/api/v1/query?{urlencode({'query': query})}")
            for name, query in prometheus_queries.items()
        },
    }

    output = args.output or (
        PROJECT_ROOT / "artifacts" / f"replay-evidence-{captured_at.strftime('%Y%m%dT%H%M%SZ')}.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(f"{output.suffix}.tmp")
    temporary.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(output)
    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
