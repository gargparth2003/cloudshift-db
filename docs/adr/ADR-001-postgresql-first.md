# ADR-001: PostgreSQL-first core

Status: Accepted

## Context

The core must prove a real online relational migration on a memory-constrained ARM64 development environment. Optional database engines must not weaken that proof.

## Decision

Use independent PostgreSQL 16.6 source, target, and control clusters. Use native logical replication for the Phase 2 vertical slice and PostgreSQL for durable lifecycle metadata.

## Alternatives

- A custom WAL decoder would expose richer row events but adds correctness and recovery risk.
- Kafka/Debezium adds operational weight not required for the initial proof.
- A single cluster with multiple databases would not demonstrate independent cluster behavior.

## Consequences and limitations

PostgreSQL handles the coordinated initial table synchronization and committed change application. DDL and sequence values are not replicated automatically, large-object support is limited, and schema evolution requires explicit coordination. Direct per-row CDC payloads are not available to the control plane; application transaction identifiers will be correlated with target observations instead.
