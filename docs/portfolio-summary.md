# CloudShift DB Portfolio Summary

## Project in one sentence

CloudShift DB is a local-first PostgreSQL migration and reliability platform that performs native logical
replication, deterministic data validation, staged cutover, workload/probe measurement, backup verification,
and incident replay through an interactive command center.

## Verified resume bullets

- Engineered a PostgreSQL 16 migration control plane using native logical replication across 13 commerce
  tables, verified committed INSERT/UPDATE/DELETE and multi-row CDC, blocked cutover on an intentional
  mismatch, and final-validated 13,563 rows with zero mismatches.
- Implemented an 11-stage automated cutover with source write protection and route switching; one local
  synthetic run measured a 424 ms control write fence, a 264 ms independently observed request-failure
  window, and a 1,089 ms source-write-to-target-write transition at 250 ms probe precision.
- Built an observable recovery and evidence system with Prometheus, durable incidents, a subscription-free
  logical backup that restored 13/13 tables and 13,696 rows, a 1,241 ms single-run destination recovery,
  43 backend tests, 2 live browser tests, and 4 backend-independent public-demo tests.

## Architecture

- Data plane: independent PostgreSQL 16.6 source and target databases.
- Control plane: Python 3.12.8 FastAPI service with durable PostgreSQL metadata.
- Application plane: transactional synthetic commerce API and independent workload/probe service.
- Presentation plane: React/TypeScript live console and sanitized static replay.
- Observability: Prometheus metrics for services, databases, validation, replication, workload, and cutover.
- Optional lab plane: Redis, MongoDB, Neo4j, and three PostgreSQL shards in isolated Compose profiles.
- Infrastructure preparation: validated Terraform AWS configuration and rendered Kubernetes manifests;
  neither is deployed.

## Evidence boundary

All timing figures are observations from a local Apple Silicon synthetic run on 27 November 2026. They
are not an SLA, production benchmark, zero-downtime guarantee, or evidence of production readiness.
The 424 ms fence, 264 ms request-failure window, and 1,089 ms probe write transition measure different
boundaries and must not be combined or relabeled as total migration time.

## Production improvements

Replace the static operator token with an identity-aware authorization layer; add TLS and managed secret
rotation; implement schema evolution, WAL archiving/PITR, replication-slot retirement, HA/failover,
multi-run benchmark matrices, alert routing, policy-controlled rollback/fail-forward, and a full disaster-
recovery exercise. Cloud deployment should occur only with an approved cost and security model.
