#!/usr/bin/env python3
"""Run bounded, project-scoped reliability experiments with durable incident evidence."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ["docker", "compose", "--project-name", "cloudshift-parth", "--profile", "core"]
REPORT_DIR = ROOT / "artifacts" / "incidents"
TASK_KEY = "parth-commerce-migration-001"


def run(command: list[str], *, input_bytes: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        command, cwd=ROOT, input=input_bytes, capture_output=True, check=True, timeout=90,
    )


def compose(*args: str) -> bytes:
    return run([*COMPOSE, *args]).stdout


def psql(script: str, variables: dict[str, str] | None = None) -> str:
    command = [*COMPOSE, "exec", "-T", "control-db", "psql", "-U", "cloudshift_admin", "-d", "cloudshift_control", "-At", "-v", "ON_ERROR_STOP=1"]
    for key, value in (variables or {}).items():
        command.extend(["-v", f"{key}={value}"])
    return run(command, input_bytes=script.encode()).stdout.decode().strip()


def fetch(url: str) -> tuple[bool, dict[str, Any] | str]:
    try:
        with urlopen(Request(url, headers={"accept": "application/json"}), timeout=2) as response:
            return True, json.load(response)
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def wait_for(predicate, timeout_seconds: float = 45.0) -> tuple[float, Any]:
    started = time.monotonic()
    latest: Any = None
    while time.monotonic() - started < timeout_seconds:
        latest = predicate()
        if latest:
            return (time.monotonic() - started) * 1000, latest
        time.sleep(0.25)
    raise TimeoutError(f"condition not reached in {timeout_seconds}s; latest={latest}")


def target_interruption() -> Path:
    experiment_id = str(uuid4())
    incident_id = str(uuid4())
    started_at = datetime.now(UTC)
    commerce_url = "http://127.0.0.1:18001/api/v1/commerce/health"
    control_url = "http://127.0.0.1:18000/api/v1/health"
    baseline_ok, baseline = fetch(commerce_url)
    if not baseline_ok or baseline.get("state") != "AVAILABLE" or baseline.get("active_database") != "TARGET":
        raise RuntimeError(f"target interruption requires an available TARGET baseline: {baseline}")

    psql(
        """
        INSERT INTO control.experiment_runs (experiment_id, experiment_type, status, configuration)
        VALUES (:'experiment_id'::uuid, 'DESTINATION_DATABASE_INTERRUPTION', 'RUNNING',
                jsonb_build_object('service','target-db','timeout_seconds',45,'scope','cloudshift-parth'));
        """,
        {"experiment_id": experiment_id},
    )
    stopped = False
    report: dict[str, Any] = {
        "schema_version": 1, "experiment_id": experiment_id, "incident_id": incident_id,
        "scenario": "DESTINATION_DATABASE_INTERRUPTION", "started_at": started_at.isoformat(),
        "baseline": baseline, "timeout_seconds": 45,
    }
    interruption_started = time.monotonic()
    def unavailable_observation():
        ok, payload = fetch(commerce_url)
        if not ok or not isinstance(payload, dict) or payload.get("state") != "AVAILABLE":
            return {"transport_ok": ok, "payload": payload}
        return None

    def recovered_observation():
        ok, payload = fetch(commerce_url)
        if ok and isinstance(payload, dict) and payload.get("state") == "AVAILABLE" and payload.get("active_database") == "TARGET":
            return payload
        return None

    try:
        compose("stop", "target-db")
        stopped = True
        detection_ms, detected = wait_for(unavailable_observation)
        report["detected"] = detected
        report["detection_duration_ms"] = round(detection_ms)
        psql(
            """
            INSERT INTO control.migration_incidents
              (incident_id, migration_id, severity, affected_resources, symptoms,
               suspected_cause, verified_cause, supporting_evidence, detection_duration_ms)
            SELECT :'incident_id'::uuid, migration_id, 'CRITICAL', ARRAY['pg-target-parth'],
                   'Target-routed commerce health became unavailable.',
                   'Controlled destination database interruption.',
                   'The project-owned target-db service was stopped by a bounded experiment.',
                   jsonb_build_object('experiment_id', :'experiment_id', 'observation', :'observation'),
                   :detection_ms
            FROM control.migration_tasks WHERE task_key=:'task_key';
            """,
            {
                "incident_id": incident_id, "experiment_id": experiment_id,
                "observation": str(detected), "detection_ms": str(round(detection_ms)), "task_key": TASK_KEY,
            },
        )
        compose("start", "target-db")
        stopped = False
        recovery_ms, recovered = wait_for(recovered_observation)
        total_recovery_ms = round((time.monotonic() - interruption_started) * 1000)
        control_ok, control_health = fetch(control_url)
        invariant = compose(
            "exec", "-T", "target-db", "psql", "-U", "cloudshift_admin", "-d", "parth_commerce_target",
            "-At", "-v", "ON_ERROR_STOP=1", "-c",
            "SELECT count(*) FROM commerce.orders WHERE order_ref='ORD-LIVE-F89F046F7A2A4EE4';",
        ).decode().strip()
        report.update({
            "recovered": recovered, "service_recovery_poll_ms": round(recovery_ms),
            "recovery_duration_ms": total_recovery_ms, "control_health_available": control_ok,
            "control_health": control_health, "post_cutover_order_count": int(invariant),
            "consistency_check": "TARGET_LOCAL_INVARIANT_ONLY_SOURCE_IS_STALE_AFTER_CUTOVER",
            "result": "RECOVERED" if invariant == "1" else "FAILED",
            "completed_at": datetime.now(UTC).isoformat(),
            "remaining_risk": "Single local experiment; no failover replica is configured.",
        })
        if invariant != "1":
            raise RuntimeError("target invariant failed after recovery")
        psql(
            """
            UPDATE control.migration_incidents
            SET recovery_action='Restarted target-db and waited for PostgreSQL and commerce health.',
                recovery_result='RECOVERED; target-only post-cutover order remained present.',
                recovery_timestamp=now(), recovery_duration_ms=:recovery_ms,
                remaining_risk='Single local experiment; no failover replica is configured.', resolved_at=now()
            WHERE incident_id=:'incident_id'::uuid;
            UPDATE control.experiment_runs
            SET status='COMPLETED', completed_at=now(), result=:'result'::jsonb
            WHERE experiment_id=:'experiment_id'::uuid;
            """,
            {
                "incident_id": incident_id, "experiment_id": experiment_id,
                "recovery_ms": str(total_recovery_ms), "result": json.dumps(report, separators=(",", ":")),
            },
        )
    except Exception as exc:
        report.update({"result": "FAILED", "error": f"{type(exc).__name__}: {exc}", "completed_at": datetime.now(UTC).isoformat()})
        try:
            psql(
                "UPDATE control.experiment_runs SET status='FAILED', completed_at=now(), result=:'result'::jsonb WHERE experiment_id=:'experiment_id'::uuid;",
                {"experiment_id": experiment_id, "result": json.dumps(report, separators=(",", ":"))},
            )
        except Exception:
            pass
        raise
    finally:
        if stopped:
            compose("start", "target-db")

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / f"{experiment_id}.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return report_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", choices=["target-interruption"])
    args = parser.parse_args()
    if args.scenario == "target-interruption":
        target_interruption()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print(exc.stderr.decode(errors="replace"), file=sys.stderr)
        raise SystemExit(exc.returncode or 1)
