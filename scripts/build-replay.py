#!/usr/bin/env python3
"""Build a compact static recruiter replay from a sanitized evidence capture."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def value(section: dict, key: str):
    record = section[key]
    if not record.get("available"):
        raise ValueError(f"required evidence section is unavailable: {key}")
    return record["value"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "apps" / "console" / "public" / "data" / "replay-latest.json",
    )
    args = parser.parse_args()
    evidence = json.loads(args.evidence.read_text(encoding="utf-8"))
    control = evidence["control_plane"]
    workload = evidence["workload_and_probe"]
    commerce = evidence["commerce_application"]
    cutovers = value(control, "cutovers")
    if not cutovers:
        raise ValueError("evidence has no completed cutover")
    cutover = cutovers[0]
    if cutover["outcome"] != "COMPLETED":
        raise ValueError("latest cutover is not completed")
    events = list(reversed(value(control, "events")))
    replay = {
        "schema_version": 2,
        "kind": "cloudshift-static-replay",
        "captured_at": evidence["captured_at"],
        "claim_boundary": evidence["claim_boundary"],
        "migration": value(control, "migration"),
        "route": value(control, "route"),
        "topology": value(control, "topology"),
        "validations": value(control, "validations"),
        "tables": value(control, "tables"),
        "cutover": cutover,
        "probe": value(workload, "probe"),
        "workload": value(workload, "workload"),
        "workload_operations": value(workload, "workload_operations")[:200],
        "commerce": {
            "health": value(commerce, "health"),
            "orders": value(commerce, "orders")["items"][:20],
            "activity": value(commerce, "activity")["items"][:50],
        },
        "backups": value(control, "backups"),
        "incidents": value(control, "incidents"),
        "experiments": value(control, "experiments"),
        "events": events,
    }
    benchmark_path = ROOT / "artifacts" / "benchmarks" / "latest.json"
    if benchmark_path.exists():
        benchmark = json.loads(benchmark_path.read_text(encoding="utf-8"))
        replay["benchmark"] = {
            "observed_at": benchmark["observed_at"],
            "method": benchmark["method"],
            "live_read_trials": benchmark["live_read_trials"],
            "benchmarks": benchmark["benchmarks"],
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(replay, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(args.output)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
