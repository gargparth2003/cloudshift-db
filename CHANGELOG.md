# Changelog

## 1.0.0 — 2026-11-27

### Added

- Isolated PostgreSQL source, target, and control clusters.
- Deterministic normalized commerce dataset and durable migration metadata.
- FastAPI discovery, lifecycle, replication metrics, validation, and cutover APIs.
- Native PostgreSQL initial synchronization and logical replication vertical slice.
- Transactional synthetic commerce service with durable source/target routing.
- Bounded-memory deterministic validation and mismatch evidence.
- Controlled cutover with sequence synchronization and source application fencing.
- React/TypeScript live migration command center backed by observed state.
- Backend-independent public replay with event playback, topology, table/transaction inspection,
  performance observations, failure recovery, final report, and Database Engineering Lab.
- Subscription-free backup/restore, bounded destination interruption evidence, Prometheus telemetry,
  ten executable DBMS practicals, benchmark artifacts, and infrastructure preparation.

### Verified locally

- Final quiesced validation of 13,563 rows with zero mismatches.
- Post-cutover target write and source application-role protection.
- 43 backend, 2 live browser, and 4 backend-independent public tests plus both production builds.

See `PROJECT_STATUS.md` for exact evidence and limitations.
