#!/usr/bin/env python3
"""Create, verify, restore, and clean up project-scoped PostgreSQL backups."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKUP_DIR = ROOT / "backups"
COMPOSE = ["docker", "compose", "--project-name", "cloudshift-parth"]
ENDPOINTS = {
    "source": ("source-db", "parth_commerce_source"),
    "target": ("target-db", "parth_commerce_target"),
}
RESTORE_DATABASE = "cloudshift_restore_verify"


def run(command: list[str], *, input_bytes: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        command, cwd=ROOT, input=input_bytes, capture_output=True, check=True, timeout=180,
    )


def compose_exec(service: str, *command: str, input_bytes: bytes | None = None) -> bytes:
    return run([*COMPOSE, "exec", "-T", service, *command], input_bytes=input_bytes).stdout


def exact_counts(service: str, database: str) -> dict[str, int]:
    query = """
    SELECT table_name || '=' ||
           (xpath('/row/count/text()', query_to_xml(
             format('SELECT count(*) AS count FROM commerce.%I', table_name), false, true, '')))[1]::text
    FROM information_schema.tables
    WHERE table_schema='commerce' AND table_type='BASE TABLE'
    ORDER BY table_name;
    """
    output = compose_exec(
        service, "psql", "-U", "cloudshift_admin", "-d", database, "-At", "-v", "ON_ERROR_STOP=1", "-c", query,
    ).decode()
    return {name: int(value) for name, value in (line.split("=", 1) for line in output.splitlines() if line)}


def create(endpoint: str) -> Path:
    service, database = ENDPOINTS[endpoint]
    captured_at = datetime.now(UTC)
    stem = f"{endpoint}-{captured_at.strftime('%Y%m%dT%H%M%SZ')}"
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    archive = BACKUP_DIR / f"{stem}.dump"
    temporary = archive.with_suffix(".dump.tmp")

    dump = compose_exec(
        service, "pg_dump", "-U", "cloudshift_admin", "-d", database,
        "--format=custom", "--compress=6", "--no-owner", "--no-acl", "--no-subscriptions",
    )
    temporary.write_bytes(dump)
    temporary.replace(archive)
    checksum = hashlib.sha256(dump).hexdigest()
    listing = compose_exec(service, "pg_restore", "--list", input_bytes=dump).decode()
    if "TABLE DATA commerce" not in listing:
        raise RuntimeError("pg_restore archive listing did not contain commerce table data")
    counts = exact_counts(service, database)

    relative = archive.relative_to(ROOT).as_posix()
    sql = """
    INSERT INTO control.backup_records
      (endpoint_id, storage_reference, size_bytes, checksum, verification_status, verified_at)
    SELECT endpoint_id, :'storage_reference', :size_bytes, :'checksum', 'VERIFIED', now()
    FROM control.database_endpoints WHERE endpoint_key=:'endpoint_key';
    """
    compose_exec(
        "control-db", "psql", "-U", "cloudshift_admin", "-d", "cloudshift_control",
        "-v", "ON_ERROR_STOP=1", "-v", f"endpoint_key={endpoint}",
        "-v", f"storage_reference={relative}", "-v", f"size_bytes={archive.stat().st_size}",
        "-v", f"checksum={checksum}", input_bytes=sql.encode(),
    )
    manifest = {
        "schema_version": 1,
        "endpoint": endpoint,
        "database": database,
        "created_at": captured_at.isoformat(),
        "archive": relative,
        "size_bytes": archive.stat().st_size,
        "sha256": checksum,
        "verification": "pg_restore --list passed",
        "table_counts": counts,
        "total_rows": sum(counts.values()),
        "claim_boundary": "Logical pg_dump backup; not point-in-time recovery.",
    }
    archive.with_suffix(".manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return archive


def resolve_archive(value: str) -> Path:
    archive = (ROOT / value).resolve() if not Path(value).is_absolute() else Path(value).resolve()
    if archive.parent != BACKUP_DIR.resolve() or archive.suffix != ".dump":
        raise ValueError("backup archive must be a .dump file directly inside the project backups directory")
    if not archive.is_file():
        raise FileNotFoundError(archive)
    return archive


def restore(value: str) -> Path:
    archive = resolve_archive(value)
    manifest_path = archive.with_suffix(".manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual_checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    if actual_checksum != manifest["sha256"]:
        raise RuntimeError("backup checksum does not match its manifest")

    run([*COMPOSE, "--profile", "backup", "up", "-d", "--wait", "restore-db"])
    compose_exec(
        "restore-db", "psql", "-U", "cloudshift_admin", "-d", "postgres", "-v", "ON_ERROR_STOP=1",
        "-c", f'DROP DATABASE IF EXISTS {RESTORE_DATABASE} WITH (FORCE);',
    )
    compose_exec(
        "restore-db", "psql", "-U", "cloudshift_admin", "-d", "postgres", "-v", "ON_ERROR_STOP=1",
        "-c", f"CREATE DATABASE {RESTORE_DATABASE};",
    )
    compose_exec(
        "restore-db", "pg_restore", "-U", "cloudshift_admin", "-d", RESTORE_DATABASE,
        "--exit-on-error", "--no-owner", "--no-acl", f"/backups/{archive.name}",
    )
    observed = exact_counts("restore-db", RESTORE_DATABASE)
    restored_subscriptions = int(compose_exec(
        "restore-db", "psql", "-U", "cloudshift_admin", "-d", RESTORE_DATABASE,
        "-At", "-v", "ON_ERROR_STOP=1", "-c", "SELECT count(*) FROM pg_subscription;",
    ).decode().strip())
    matched = observed == manifest["table_counts"]
    report = {
        "schema_version": 1,
        "archive": archive.relative_to(ROOT).as_posix(),
        "restored_database": RESTORE_DATABASE,
        "restored_on": "isolated optional restore-db service",
        "verified_at": datetime.now(UTC).isoformat(),
        "checksum_verified": True,
        "table_counts_match": matched,
        "expected_table_counts": manifest["table_counts"],
        "observed_table_counts": observed,
        "expected_total_rows": manifest["total_rows"],
        "observed_total_rows": sum(observed.values()),
        "restored_subscriptions": restored_subscriptions,
        "active_endpoints_modified": False,
        "point_in_time_recovery_claimed": False,
    }
    report_path = archive.with_suffix(".restore.json")
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    if not matched or restored_subscriptions != 0:
        raise RuntimeError("restore verification failed: table counts differ or a subscription was restored")
    return report_path


def cleanup() -> None:
    subscription_count = int(compose_exec(
        "restore-db", "psql", "-U", "cloudshift_admin", "-d", RESTORE_DATABASE,
        "-At", "-v", "ON_ERROR_STOP=1", "-c",
        "SELECT count(*) FROM pg_subscription WHERE subname='parth_cloudshift_subscription';",
    ).decode().strip())
    if subscription_count:
        compose_exec(
            "restore-db", "psql", "-U", "cloudshift_admin", "-d", RESTORE_DATABASE,
            "-v", "ON_ERROR_STOP=1", "-c",
            "ALTER SUBSCRIPTION parth_cloudshift_subscription SET (slot_name = NONE); "
            "DROP SUBSCRIPTION parth_cloudshift_subscription;",
        )
    compose_exec(
        "restore-db", "psql", "-U", "cloudshift_admin", "-d", "postgres", "-v", "ON_ERROR_STOP=1",
        "-c", f'DROP DATABASE IF EXISTS {RESTORE_DATABASE} WITH (FORCE);',
    )
    print(f"dropped disposable database {RESTORE_DATABASE}; restore service and volume were preserved")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    create_parser = subparsers.add_parser("create")
    create_parser.add_argument("endpoint", choices=sorted(ENDPOINTS))
    restore_parser = subparsers.add_parser("restore")
    restore_parser.add_argument("archive")
    subparsers.add_parser("cleanup")
    args = parser.parse_args()
    if args.command == "create":
        create(args.endpoint)
    elif args.command == "restore":
        restore(args.archive)
    else:
        cleanup()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as exc:
        message = exc.stderr.decode(errors="replace").strip()
        print(f"command failed: {message}", file=sys.stderr)
        sys.exit(exc.returncode or 1)
