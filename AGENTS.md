# CloudShift DB Engineering Context

## Purpose

CloudShift DB is a local-first PostgreSQL migration and reliability platform. Correctness, transactional consistency, real replication evidence, safe cutover, and honest verification take priority over interface breadth.

## Architecture

- Presentation plane: React/TypeScript console (Phase 4).
- Control plane: FastAPI modular monolith in `services/control-plane`.
- Data plane: independent source and target PostgreSQL instances.
- Metadata plane: durable PostgreSQL control database; Redis is optional and never authoritative.
- Infrastructure plane: Docker Compose first, with optional Kubernetes and Terraform later.

The core replication design uses PostgreSQL native logical replication with coordinated initial table synchronization. The commerce application remains routed to the source until final validation and controlled cutover succeed.

## Non-negotiable rules

- Never fabricate metrics, migration progress, logs, benchmark results, health, or deployment state.
- Never compare independently changing databases and call the difference corruption.
- Never claim exactly-once delivery, zero downtime, zero data loss, or production readiness without evidence.
- Keep source, target, and control data separate.
- Preserve transaction boundaries and use explicit consistency checkpoints for final validation.
- Block cutover on critical assessment or validation failures.
- Never reverse-cut over to a stale source after target-only writes.
- Do not expose arbitrary endpoint registration, SQL, shell access, Docker sockets, or secrets.
- Do not alter or remove resources owned by other Docker projects.
- Do not run global Docker prune commands.
- Do not create paid cloud resources, publish externally, or push Git without explicit authorization.

## Conventions

- Python 3.12 in containers; typed FastAPI/Pydantic interfaces.
- PostgreSQL 16.6 for the verified local baseline.
- UTC timestamps internally; timezone-aware values only.
- Parameterized SQL; dynamic identifiers must come from strict allowlists or safe identifier composition.
- API routes are versioned under `/api/v1` and return correlation identifiers.
- Tests must assert observed database state rather than implementation mocks for migration correctness.
- Keep default core memory under the Docker allocation; expensive engines belong to optional profiles.

## Commands

```sh
make up
make health
make seed
make test
make test-integration
make benchmark
make test-browser
make build-public
make down
```

`make down` preserves named volumes. Destructive reset functionality must be explicit and project-scoped.

## Important files

- `docker-compose.yml`: isolated local topology and resource bounds.
- `database/source/init/010_commerce_schema.sql`: canonical commerce schema.
- `database/source/init/020_starter_seed.sql`: deterministic starter dataset.
- `database/control/init/010_control_schema.sql`: durable platform metadata.
- `services/control-plane/app`: API and endpoint discovery.
- `PROJECT_STATUS.md`: verified state, failures, and exact continuation steps.
- `docs/verification-matrix.md`: evidence ledger.

## Definition of done

A feature is complete only when its implementation, verification command, observed result, and limitations are recorded. Core completion additionally requires the mandatory real end-to-end migration, validation mismatch, recovery, cutover, application-route, and replay checks in the master specification.
