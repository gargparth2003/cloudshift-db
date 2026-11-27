#!/usr/bin/env python3
"""Execute bounded Neo4j dependency graph and impact-analysis practical."""

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


def cypher(query: str) -> str:
    result = subprocess.run(
        ["docker", "compose", "--project-name", "cloudshift-parth", "--profile", "academic-graph",
         "exec", "-T", "neo4j-lab", "cypher-shell", "-u", "neo4j", "-p", env_value("NEO4J_PASSWORD"),
         "--format", "plain", query],
        cwd=ROOT, check=True, capture_output=True, text=True, timeout=30,
    )
    return result.stdout.strip()


def main() -> int:
    cypher("MATCH (node {labRun:'practical10'}) DETACH DELETE node")
    cypher("""
    CREATE (app:Application {name:'parth-commerce-application',labRun:'practical10'}),
           (source:Database {name:'pg-source-parth',role:'SOURCE',labRun:'practical10'}),
           (target:Database {name:'pg-target-parth',role:'TARGET',labRun:'practical10'}),
           (control:Database {name:'pg-control-parth',role:'CONTROL',labRun:'practical10'}),
           (schema:Schema {name:'commerce',labRun:'practical10'}),
           (customers:Table {name:'customers',labRun:'practical10'}),
           (orders:Table {name:'orders',labRun:'practical10'}),
           (items:Table {name:'order_items',labRun:'practical10'}),
           (products:Table {name:'products',labRun:'practical10'}),
           (app)-[:ROUTES_TO]->(target),
           (source)-[:MIGRATES_TO]->(target),
           (control)-[:ORCHESTRATES]->(source),
           (control)-[:ORCHESTRATES]->(target),
           (target)-[:HOSTS]->(schema),
           (schema)-[:CONTAINS]->(customers),
           (schema)-[:CONTAINS]->(orders),
           (schema)-[:CONTAINS]->(items),
           (schema)-[:CONTAINS]->(products),
           (orders)-[:REFERENCES]->(customers),
           (items)-[:REFERENCES]->(orders),
           (items)-[:REFERENCES]->(products)
    """)
    counts = cypher("MATCH (node {labRun:'practical10'}) OPTIONAL MATCH (node)-[relationship]->() RETURN count(DISTINCT node) AS nodes,count(relationship) AS relationships")
    traversal = cypher("MATCH path=(app:Application {labRun:'practical10'})-[:ROUTES_TO|HOSTS|CONTAINS*1..4]->(table:Table) RETURN table.name AS reachable_table,length(path) AS hops ORDER BY reachable_table")
    impact = cypher("MATCH path=(table:Table {name:'customers',labRun:'practical10'})<-[:REFERENCES*1..3]-(dependent:Table) RETURN dependent.name AS impacted_table,length(path) AS hops ORDER BY hops")
    migration_path = cypher("MATCH path=(source:Database {role:'SOURCE',labRun:'practical10'})-[:MIGRATES_TO]->(target:Database) RETURN source.name AS source,target.name AS target,length(path) AS hops")
    report = {
        "schema_version": 1, "observed_at": datetime.now(UTC).isoformat(), "practical": 10,
        "graph_counts": counts, "dependency_traversal": traversal,
        "impact_analysis": impact, "migration_path": migration_path,
        "explanation": "Typed relationships support dependency traversal and migration impact analysis without recursive join construction.",
        "limitations": "Single-node optional Neo4j lab with a curated subset of the schema; not a production graph catalog.",
    }
    output = ROOT / "artifacts" / "labs" / "neo4j-practical-10.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(counts)
    print(migration_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
