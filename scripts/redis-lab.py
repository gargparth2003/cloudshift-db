#!/usr/bin/env python3
"""Execute bounded Redis CRUD, TTL, and legitimate metadata-cache practicals."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ["docker", "compose", "--project-name", "cloudshift-parth"]


def local_env(name: str) -> str:
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{name}="):
            return line.split("=", 1)[1]
    raise RuntimeError(f"missing {name}")


PASSWORD = local_env("REDIS_PASSWORD")


def redis(*args: str) -> tuple[str, float]:
    started = perf_counter()
    result = subprocess.run(
        [*COMPOSE, "--profile", "academic-redis", "exec", "-T", "redis-lab",
         "redis-cli", "--no-auth-warning", "-a", PASSWORD, "--raw", *args],
        cwd=ROOT, check=True, capture_output=True, text=True, timeout=15,
    )
    return result.stdout.strip(), round((perf_counter() - started) * 1000, 3)


def database_snapshot() -> tuple[dict, float]:
    started = perf_counter()
    result = subprocess.run(
        [*COMPOSE, "--profile", "core", "exec", "-T", "control-db", "psql", "-U", "cloudshift_admin",
         "-d", "cloudshift_control", "-At", "-F", "|", "-c",
         "SELECT active_endpoint::text,writes_enabled,version FROM control.application_routes WHERE route_key='parth-commerce-application';"],
        cwd=ROOT, check=True, capture_output=True, text=True, timeout=15,
    )
    endpoint, writes, version = result.stdout.strip().split("|")
    return {"active_endpoint": endpoint, "writes_enabled": writes == "t", "version": int(version)}, round((perf_counter() - started) * 1000, 3)


def main() -> int:
    key = "cloudshift:lab:migration-state"
    redis("DEL", key)
    set_result, set_ms = redis("SET", key, "CONTINUOUS_REPLICATION", "EX", "60")
    get_value, get_ms = redis("GET", key)
    update_result, update_ms = redis("SET", key, "COMPLETED", "KEEPTTL")
    updated_value, updated_get_ms = redis("GET", key)
    ttl, ttl_ms = redis("TTL", key)
    deleted, delete_ms = redis("DEL", key)

    cache_key = "cloudshift:cache:application-route"
    redis("DEL", cache_key)
    miss_value, miss_ms = redis("GET", cache_key)
    snapshot, database_ms = database_snapshot()
    payload = json.dumps(snapshot, separators=(",", ":"))
    redis("SET", cache_key, payload, "EX", "30")
    hit_value, hit_ms = redis("GET", cache_key)
    invalidated, invalidation_ms = redis("DEL", cache_key)
    after_invalidation, after_invalidation_ms = redis("GET", cache_key)

    report = {
        "schema_version": 1,
        "observed_at": datetime.now(UTC).isoformat(),
        "practical_6": {
            "set": {"result": set_result, "latency_ms": set_ms},
            "get": {"value": get_value, "latency_ms": get_ms},
            "update": {"result": update_result, "value": updated_value, "latency_ms": update_ms + updated_get_ms},
            "ttl": {"seconds": int(ttl), "latency_ms": ttl_ms},
            "delete": {"keys_removed": int(deleted), "latency_ms": delete_ms},
        },
        "practical_8": {
            "durable_source": "PostgreSQL control.application_routes",
            "cache_miss": {"value": miss_value or None, "latency_ms": miss_ms},
            "database_read": {"value": snapshot, "latency_ms": database_ms},
            "cache_hit": {"value": json.loads(hit_value), "latency_ms": hit_ms},
            "ttl_seconds": 30,
            "invalidation": {"keys_removed": int(invalidated), "latency_ms": invalidation_ms},
            "after_invalidation": {"value": after_invalidation or None, "latency_ms": after_invalidation_ms},
            "stale_data_prevention": "Route mutations must delete/version this cache key; PostgreSQL remains authoritative.",
            "limitations": "One local subprocess-inclusive sample; not a statistically meaningful latency comparison.",
        },
    }
    output = ROOT / "artifacts" / "labs" / "redis-practicals-6-8.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
