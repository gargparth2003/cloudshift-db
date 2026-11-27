# Local migration runbook

## Start and inspect

```sh
cp .env.example .env
make up
make health
make test-integration
```

Open <http://127.0.0.1:18080/console/migration-command-center> and <http://127.0.0.1:18000/api/docs>.

## Safety boundaries

- Use only the `cloudshift-parth` Compose project.
- Never run a global Docker prune.
- `make down` preserves database volumes.
- Do not use the post-cutover source as a rollback target after target-only writes.
- Do not drop the retained replication slot until WAL retention and recovery requirements have been reviewed.

## Verified test ordering on a fresh disposable run

1. `make test-integration`
2. Run assessment and start migration through the operator APIs.
3. `make test-replication`
4. `make test-validation`
5. Create a source-routed commerce order.
6. Prepare cutover, inspect the final validation, and execute only with exact task confirmation.
7. Create a target-routed order and verify the source application role cannot write.

The replication and mismatch scripts are pre-cutover tests. They are not expected to succeed after the subscription is disabled and source application writes are fenced.

## Current recovery position

Pre-cutover errors preserve the source as authoritative and should restore the source route with writes enabled after diagnosis. After target-only commits, do not route writes back to source. Reverse replication is not implemented; use forward recovery and retain both databases for investigation.
