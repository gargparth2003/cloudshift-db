#!/usr/bin/env python3
"""Execute bounded MongoDB document-query practical with synthetic diagnostics."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def env_value(name: str) -> str:
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{name}="):
            return line.split("=", 1)[1]
    raise RuntimeError(f"missing {name}")


def main() -> int:
    javascript = r'''
const lab = db.getSiblingDB("cloudshift_lab");
lab.diagnostics.deleteMany({lab_run:"practical7"});
lab.diagnostics.insertMany([
  {lab_run:"practical7", kind:"replication", severity:"WARNING", migration:"parth-commerce-migration-001", evidence:{component:"replication", wal_bytes:42488, worker:"PAUSED"}, recovery:{result:"RECOVERED", duration_ms:1241}},
  {lab_run:"practical7", kind:"validation", severity:"BLOCKING", migration:"parth-commerce-migration-001", evidence:{component:"validation", mismatches:1, table:"products"}, recovery:{result:"RESTORED", duration_ms:165}},
  {lab_run:"practical7", kind:"cutover", severity:"INFORMATIONAL", migration:"parth-commerce-migration-001", evidence:{component:"cutover", stages:11, fence_ms:424}, recovery:{result:"COMPLETED", duration_ms:470}}
]);
const filtered=lab.diagnostics.find({lab_run:"practical7", "evidence.component":{$in:["replication","validation"]}}, {_id:0}).sort({severity:1}).toArray();
const grouped=lab.diagnostics.aggregate([
  {$match:{lab_run:"practical7"}},
  {$group:{_id:"$severity", documents:{$sum:1}, average_recovery_ms:{$avg:"$recovery.duration_ms"}}},
  {$sort:{_id:1}}
]).toArray();
const nested=lab.diagnostics.findOne({lab_run:"practical7", "evidence.wal_bytes":{$gte:40000}}, {_id:0});
print(EJSON.stringify({inserted:lab.diagnostics.countDocuments({lab_run:"practical7"}), filtered, grouped, nested}));
'''
    result = subprocess.run(
        ["docker", "compose", "--project-name", "cloudshift-parth", "--profile", "academic-mongo",
         "exec", "-T", "mongo-lab", "mongosh", "--quiet", "--username", "cloudshift_admin",
         "--password", env_value("MONGO_ROOT_PASSWORD"), "--authenticationDatabase", "admin", "--eval", javascript],
        cwd=ROOT, check=True, capture_output=True, text=True, timeout=30,
    )
    observed = json.loads(result.stdout.strip().splitlines()[-1])
    if observed["inserted"] != 3 or len(observed["filtered"]) != 2:
        raise RuntimeError(observed)
    report = {
        "schema_version": 1, "observed_at": datetime.now(UTC).isoformat(), "practical": 7,
        "database": "cloudshift_lab", "collection": "diagnostics", "result": observed,
        "features": ["document insertion", "filtering", "grouping", "aggregation", "nested fields"],
        "limitations": "Synthetic diagnostics in a single optional MongoDB instance; durable migration truth remains PostgreSQL.",
    }
    output = ROOT / "artifacts" / "labs" / "mongodb-practical-7.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"inserted={observed['inserted']} filtered={len(observed['filtered'])} groups={len(observed['grouped'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
