# CloudShift DB Interview Guide

## 30-second explanation

CloudShift DB demonstrates how to migrate a transactional PostgreSQL application while it continues to
serve traffic. PostgreSQL performs initial synchronization and WAL-based logical replication; a FastAPI
control plane tracks lifecycle, validates source and target content, fences writes, drains transactions,
synchronizes sequences, switches the application route, and protects the source. The React command center
shows real captured state, while the public site replays sanitized evidence without a live database.

## Two-minute explanation

The system separates source, target, and control databases. A deterministic 13-table commerce schema is
seeded at the source and PostgreSQL publication/subscription primitives copy it to the target. The migration
lifecycle prevents unsafe jumps and stores events durably. A workload generator produces actual routed reads
and transactional writes, while a separate 250 ms probe measures availability independently of the cutover
controller. Validation canonicalizes bounded batches and compares row counts and SHA-256 content checksums.

Cutover is an 11-stage workflow: target readiness, source write fence, in-flight drain, zero-lag check,
final validation, sequence synchronization, source protection, replication transition, target smoke test,
route switch, and traffic restoration. In one local run, the controller fence was 424 ms; the independent
probe observed a 264 ms request-failure window and 1,089 ms between its last source write and first target
write. Those are different measurements, not a zero-downtime claim. Backup/restore, destination interruption,
Prometheus telemetry, replay evidence, and ten DBMS practicals complete the engineering narrative.

## Five-minute demonstration

1. Open the cloud migration studio and explain the `SIMULATED`, `RECORDED`, and `MEASURED LIVE` boundaries.
2. Load a constrained scenario, inspect assessment blockers, then interrupt and recover the deterministic
   simulation. Show why mismatch or lag blocks cutover.
3. Inspect the architecture/network design, enter an explicit unit rate in the transparent cost model, and
   export the plan or secure AWS-first Terraform review artifact.
4. Launch the verified migration replay; play from DRAFT through initial sync, continuous replication, validation,
   ready-for-cutover, cutover-in-progress, and COMPLETED.
5. Select source, replication, target, and router nodes. Show that the recorded route moves from SOURCE to
   TARGET and that active connections follow lifecycle state.
6. Filter the 13-table tracker and the recorded transaction inspector. Explain estimates versus exact final
   validation and application instrumentation versus raw WAL decoding.
7. Compare the 424 ms fence, 264 ms request failure, and 1,089 ms write transition. Show all 11 cutover stages.
8. Open failure/recovery, backup evidence, and the final report. Finish with the Database Engineering Lab and
   explain why optional engines remain separate from the core product.

## System design questions

### Why use a durable control database?

Migration state, cutover stages, incidents, validations, routes, and evidence must survive process restarts.
Keeping them separate from both migrated databases avoids contaminating source/target comparisons.

### How is a concurrent lifecycle request controlled?

The transition reads the migration row `FOR UPDATE`, validates the requested edge, and updates using the
observed version. PostgreSQL serializes competing row locks; invalid or duplicate lifecycle transitions are
rejected or return the existing active observation.

### Why is reverse cutover unsafe after target-only writes?

The source is stale once the target accepts unique writes and forward replication is disabled. Returning
traffic would lose or diverge those writes. Recovery must fail forward or use an explicitly designed reverse
replication/reconciliation procedure.

## PostgreSQL replication questions

### What is the difference between initial sync and CDC?

The subscription first copies the existing table snapshot. Once relations reach ready state, logical decoding
streams committed WAL changes from the replication slot. A rollback produces no committed target change.

### Why require primary keys?

Updates and deletes need stable replica identity. The assessment blocks unsupported tables rather than
silently accepting ambiguous change application.

### What happens while a subscription is paused?

The source slot retains WAL. The experiment observed 42,488 retained bytes during a bounded pause; unchecked
retention can exhaust storage, so monitoring and a retirement policy are required.

### How is consistency established at cutover?

Writes are fenced, in-flight application work is drained with an advisory-lock boundary, measured WAL lag
must reach zero, and a final quiesced checksum comparison must match before traffic moves.

## Cloud architecture questions

### Why not deploy the prepared AWS architecture automatically?

The repository contains cost-bearing VPC/RDS/EC2/S3 configuration, but the project explicitly prohibits provisioning.
Terraform validation proves configuration structure, not cloud operability or production readiness.

### Why are estimator prices editable and initially zero?

Provider prices vary by date, region, commitment, usage tier, and tax context. A hard-coded number would look
authoritative after it became stale. The UI links official pricing sources, requires explicit rates, shows the
formula, and labels the result estimated.

### How would this evolve in AWS?

Use Multi-AZ managed PostgreSQL, private subnets, a controlled migration worker, Secrets Manager rotation,
TLS, least-privilege IAM, centralized logs/metrics, protected backup storage, and an approved failover runbook.

## SRE and DevOps questions

### What did the availability probe add?

It measured user-facing reads and committed writes independently of controller timestamps. That prevents an
operator delay or internal fence timer from being mislabeled as application unavailability.

### What was verified during recovery?

Stopping only the target produced detection in 524 ms and total recovery in 1,241 ms in one local trial. The
post-cutover target-only order remained present and all database health checks recovered.

### What is still missing for an SLO?

Repeated failure trials, production-like load and network conditions, statistical confidence, alert delivery,
multi-node failover, error budgets, and sustained observation. A single local recovery is not an MTTR claim.

## Technical limitations

Authentication is a local static token; there is no automatic schema evolution, PITR, production HA,
post-cutover slot retirement, or validated reverse replication. Kubernetes and Terraform are configuration-
only. Benchmarks A–E remain partial and F–J are single-trial observations. The public demo is deliberately
read-only and uses captured synthetic evidence.
