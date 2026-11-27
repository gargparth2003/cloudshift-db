# ADR-006: Controlled application cutover

Status: Accepted and locally verified on 2026-11-27

## Context

Starting target writes while source writes or forward replication remain active can create divergence, key collisions, and an unsafe rollback boundary. PostgreSQL logical replication also does not synchronize sequence state.

## Decision

CloudShift DB uses a durable application route and an explicit two-step cutover:

1. Fence commerce writes in control metadata.
2. Drain any transaction that passed the route check by acquiring the same PostgreSQL advisory lock used by commerce writes.
3. Wait for observed zero WAL byte lag and all 13 relation states to be ready.
4. Run bounded-memory final validation while the source route is quiesced.
5. Require explicit confirmation matching the migration task identifier.
6. Synchronize target sequences from source observations.
7. Disable the target subscription before independent target writes.
8. Revoke source application-role DML and sequence privileges.
9. Smoke-test the target and atomically publish the target route with writes enabled.

## Alternatives

- DNS-only switching cannot provide a transaction drain or write fence.
- Leaving forward replication enabled after target writes risks conflicts and is rejected.
- Automatic reverse replication was excluded because loop prevention and reverse-cutover correctness have not been implemented.

## Consequences and limitations

The source remains retained but application-write protected. Post-cutover rollback to source is unsafe after target-only commits; forward recovery is required. The disabled logical slot currently remains allocated, so WAL-retention monitoring and an explicit retirement policy are required. The observed 17,725 ms value is the duration of the controlled metadata fence, including operator delay between prepare and execute, not an independent application-probe measurement.
