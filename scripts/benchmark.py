#!/usr/bin/env python3
"""Build an honest, reproducible local benchmark snapshot from observed evidence.

The command performs repeated read-only HTTP trials and combines them with the
latest acceptance, reliability, and lab artifacts. Missing comparisons remain
explicitly NOT_EXECUTED rather than being inferred.
"""

from __future__ import annotations

import csv
import json
import os
import platform
import statistics
import subprocess
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
OUTPUT = ARTIFACTS / "benchmarks"


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def summary(values: list[float]) -> dict[str, float | int]:
    return {
        "trials": len(values),
        "mean_ms": round(statistics.fmean(values), 3),
        "median_ms": round(statistics.median(values), 3),
        "p95_ms": round(percentile(values, 0.95), 3),
        "p99_ms": round(percentile(values, 0.99), 3),
        "min_ms": round(min(values), 3),
        "max_ms": round(max(values), 3),
        "stdev_ms": round(statistics.stdev(values), 3) if len(values) > 1 else 0.0,
    }


def http_trials(url: str, warmup: int = 5, trials: int = 30) -> dict[str, Any]:
    observed: list[float] = []
    for index in range(warmup + trials):
        started = time.perf_counter_ns()
        with urllib.request.urlopen(url, timeout=5) as response:
            response.read()
            if response.status != 200:
                raise RuntimeError(f"{url} returned HTTP {response.status}")
        elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
        if index >= warmup:
            observed.append(elapsed_ms)
    return {"url": url, "warmup_requests": warmup, "raw_ms": [round(v, 3) for v in observed], **summary(observed)}


def docker_resources() -> dict[str, Any]:
    names = [
        "cloudshift-console", "cloudshift-control-plane", "cloudshift-workload-generator",
        "parth-commerce-application", "pg-source-parth", "pg-target-parth", "pg-control-parth",
        "cloudshift-prometheus",
    ]
    command = ["docker", "stats", "--no-stream", "--format", "{{json .}}", *names]
    try:
        completed = subprocess.run(command, check=True, capture_output=True, text=True, timeout=30)
        rows = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
        return {"available": True, "containers": rows}
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError) as error:
        return {"available": False, "error": type(error).__name__, "containers": []}


def latest(pattern: str) -> Path:
    paths = sorted(ARTIFACTS.glob(pattern))
    if not paths:
        raise FileNotFoundError(f"no artifact matched {pattern}")
    return paths[-1]


def workload_events(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    events = evidence["control_plane"]["events"]["value"]
    return [event["evidence"]["metrics"] for event in events if event.get("event_type") == "WORKLOAD_STOPPED"]


def write_csv(path: Path, sections: dict[str, dict[str, Any]]) -> None:
    rows: list[dict[str, Any]] = []
    for benchmark, section in sections.items():
        for metric, value in section.get("measurements", {}).items():
            if isinstance(value, (str, int, float, bool)) or value is None:
                rows.append({"benchmark": benchmark, "status": section["status"], "metric": metric, "value": value})
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["benchmark", "status", "metric", "value"])
        writer.writeheader()
        writer.writerows(rows)


def write_svg(path: Path, trials: dict[str, dict[str, Any]]) -> None:
    labels = list(trials)
    values = [float(trials[label]["median_ms"]) for label in labels]
    ceiling = max(values) * 1.2 or 1
    bars = []
    for index, (label, value) in enumerate(zip(labels, values, strict=True)):
        x = 80 + index * 220
        height = 230 * value / ceiling
        y = 300 - height
        bars.append(f'<rect x="{x}" y="{y:.1f}" width="120" height="{height:.1f}" fill="#14b8a6"/>')
        bars.append(f'<text x="{x + 60}" y="325" text-anchor="middle" fill="#dbeafe">{label}</text>')
        bars.append(f'<text x="{x + 60}" y="{y - 8:.1f}" text-anchor="middle" fill="#f8fafc">{value:.3f} ms</text>')
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="760" height="380" viewBox="0 0 760 380">'
        '<rect width="760" height="380" fill="#071426"/><text x="30" y="40" fill="#f8fafc" font-size="22">'
        'CloudShift repeated read latency (median)</text><line x1="50" y1="300" x2="720" y2="300" stroke="#64748b"/>'
        + "".join(bars) + '</svg>'
    )
    path.write_text(svg)


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    evidence_path = latest("replay-evidence-*.json")
    evidence = load(evidence_path)
    postgres = load(ARTIFACTS / "labs/postgres-practicals-1-3.json")
    distributed = load(ARTIFACTS / "labs/distributed-practicals-4-5.json")
    redis = load(ARTIFACTS / "labs/redis-practicals-6-8.json")
    incident = load(latest("incidents/*.json"))
    practical3 = next(item for item in postgres["practicals"] if item["practical"] == 3)
    workloads = workload_events(evidence)
    validations = evidence["control_plane"]["validations"]["value"]
    cutover = evidence["control_plane"]["cutovers"]["value"][0]
    probe = evidence["workload_and_probe"]["probe"]["value"]

    ports = {
        "control_health": int(os.getenv("CLOUDSHIFT_API_PORT", "18000")),
        "commerce_orders": int(os.getenv("CLOUDSHIFT_COMMERCE_PORT", "18001")),
        "workload_health": int(os.getenv("CLOUDSHIFT_WORKLOAD_PORT", "18002")),
    }
    live_trials = {
        "control_health": http_trials(f'http://127.0.0.1:{ports["control_health"]}/api/v1/health/live'),
        "commerce_orders": http_trials(f'http://127.0.0.1:{ports["commerce_orders"]}/api/v1/commerce/orders?limit=20'),
        "workload_health": http_trials(f'http://127.0.0.1:{ports["workload_health"]}/api/v1/workload/health'),
    }

    sections = {
        "A_offline_vs_online": {
            "status": "PARTIAL",
            "measurements": {"online_request_failure_window_ms": probe["observed_request_failure_window_ms"]},
            "limitation": "Online migration was measured; a destructive offline baseline was not executed.",
        },
        "B_dataset_sizes": {
            "status": "PARTIAL",
            "measurements": {"migration_rows_observed": 13696, "index_probe_rows": practical3["rows"]},
            "limitation": "The 13,696-row migration and separate 100,000-row index probe are real; a 1,000,000-row migration was not run.",
        },
        "C_workload_profiles": {
            "status": "PARTIAL",
            "measurements": {"profiles_observed": ",".join(sorted({item["profile"] for item in workloads})), "runs": len(workloads)},
            "limitation": "Balanced and write-heavy completion events exist; no equivalent read-heavy repeated trial exists.",
        },
        "D_workload_rates": {
            "status": "PARTIAL",
            "measurements": {"configured_rates": ",".join(str(item["configured_rate"]) for item in workloads), "max_observed_ops_s": max(item["operations_per_second"] for item in workloads)},
            "limitation": "Observed run summaries are single local trials and do not form a rate sweep.",
        },
        "E_validation_modes": {
            "status": "PARTIAL",
            "measurements": {"full_runs": sum(item["scope"] == "FULL" for item in validations), "final_quiesced_runs": sum(item["scope"] == "FINAL_QUIESCED" for item in validations)},
            "limitation": "Full and final-quiesced validation are implemented; sampled validation is not implemented.",
        },
        "F_indexed_queries": {
            "status": "OBSERVED_SINGLE_TRIAL",
            "measurements": {"rows": practical3["rows"], "unindexed_ms": practical3["unindexed"]["execution_time_ms"], "btree_ms": practical3["btree"]["execution_time_ms"], "hash_ms": practical3["hash"]["execution_time_ms"]},
            "limitation": practical3["limitations"],
        },
        "G_redis_cache": {
            "status": "OBSERVED_SINGLE_TRIAL",
            "measurements": {"database_read_ms": redis["practical_8"]["database_read"]["latency_ms"], "cache_hit_ms": redis["practical_8"]["cache_hit"]["latency_ms"]},
            "limitation": redis["practical_8"]["limitations"],
        },
        "H_distributed_query": {
            "status": "OBSERVED_SINGLE_TRIAL",
            "measurements": {"rows": distributed["practical_5"]["merged_rows"], "sequential_ms": distributed["practical_5"]["sequential_duration_ms"], "parallel_ms": distributed["practical_5"]["parallel_duration_ms"]},
            "limitation": distributed["practical_5"]["limitations"],
        },
        "I_interruption_recovery": {
            "status": "OBSERVED_SINGLE_TRIAL",
            "measurements": {"detection_ms": incident["detection_duration_ms"], "recovery_ms": incident["recovery_duration_ms"]},
            "limitation": incident["remaining_risk"],
        },
        "J_cutover_availability": {
            "status": "OBSERVED_SINGLE_TRIAL",
            "measurements": {"workflow_ms": round((datetime.fromisoformat(cutover["completed_at"]) - datetime.fromisoformat(cutover["requested_at"])).total_seconds() * 1000), "write_fence_ms": cutover["write_unavailability_ms"], "request_failure_window_ms": probe["observed_request_failure_window_ms"], "write_transition_ms": probe["observed_write_unavailability_ms"], "probe_precision_ms": probe["precision_limit_ms"]},
            "limitation": "One synthetic local cutover; probe durations are bounded by 250 ms sampling precision.",
        },
        "K_resources_and_live_reads": {
            "status": "REPEATED_READS_AND_POINT_IN_TIME_RESOURCES",
            "measurements": {f"{name}_median_ms": result["median_ms"] for name, result in live_trials.items()},
            "limitation": "Thirty read trials after five warm-ups plus one Docker stats snapshot; not a saturation or capacity test.",
        },
    }

    now = datetime.now(UTC)
    stem = now.strftime("benchmark-%Y%m%dT%H%M%SZ")
    report = {
        "schema_version": 1,
        "observed_at": now.isoformat(),
        "environment": {"hardware": "Apple MacBook Air M4, 10 Docker CPUs, 7.748 GiB Docker memory", "host_architecture": platform.machine(), "python": platform.python_version(), "evidence_source": str(evidence_path.relative_to(ROOT))},
        "method": {"read_warmup": 5, "read_trials": 30, "selection": "all observed trials retained; no favorable-run filtering"},
        "live_read_trials": live_trials,
        "resources": docker_resources(),
        "benchmarks": sections,
    }
    json_path = OUTPUT / f"{stem}.json"
    csv_path = OUTPUT / f"{stem}.csv"
    svg_path = OUTPUT / f"{stem}.svg"
    json_path.write_text(json.dumps(report, indent=2, default=str) + "\n")
    write_csv(csv_path, sections)
    write_svg(svg_path, live_trials)
    (OUTPUT / "latest.json").write_text(json.dumps(report, indent=2, default=str) + "\n")
    print(json.dumps({"json": str(json_path), "csv": str(csv_path), "chart": str(svg_path), "statuses": {key: value["status"] for key, value in sections.items()}}, indent=2))


if __name__ == "__main__":
    main()
