# Academic Syllabus Mapping

| Topic | CloudShift implementation | Executed evidence |
|---|---|---|
| Relational modeling and normalization | 13-table commerce schema, constraints, keys, materialized summary | Practical 1 |
| Transactions and concurrency control | Atomicity, constraints, durability, isolation, locks, serialization failure | Practical 2 |
| Query processing and optimization | `EXPLAIN ANALYZE`, buffers, B-tree/hash/composite indexes | Practical 3; 100,000 rows |
| Distributed databases and fragmentation | Region-keyed NORTH/SOUTH/WEST PostgreSQL shards | Practical 4; 1,000 rows/shard |
| Distributed query processing | Sequential/parallel partial aggregates and result merge | Practical 5; identical 3,000-row result |
| Key-value databases | Authenticated Redis CRUD and TTL | Practical 6 |
| Document databases | MongoDB nested filters and aggregations | Practical 7 |
| Database caching | PostgreSQL-authoritative Redis miss/fill/hit/invalidate | Practical 8 |
| Time-series databases | Prometheus counters, gauges, rates, instant/range queries | Practical 9 |
| Graph databases | Neo4j migration/dependency traversal and impact analysis | Practical 10; 9 nodes/12 edges |
| Recovery and reliability | Subscription-free backup/restore and target interruption | 13,696 restored rows; 1,241 ms recovery trial |
| Cloud databases and IaC | AWS reference Terraform and Kubernetes preparation | Terraform validated; Kustomize rendered; not deployed |

Each practical's objective, theory, executable command, output, limitations, and reset behavior are detailed
in [`docs/dbms-lab.md`](../dbms-lab.md). Results are local synthetic observations rather than production
benchmarks.
