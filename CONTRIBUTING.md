# Contributing

CloudShift DB prioritizes database correctness over feature breadth.

Before proposing a change:

1. Read `AGENTS.md`, `PROJECT_STATUS.md`, and the relevant ADR.
2. Keep all Docker resources inside the `cloudshift-parth` project boundary.
3. Add an evidence-backed test for migration, validation, routing, or lifecycle behavior.
4. Do not replace real database integration checks with mocks.
5. Do not include secrets, real customer data, fabricated metrics, or unsupported production claims.

Run the applicable checks:

```sh
make config
make test
make test-integration
```

Pre-cutover replication and mismatch tests require a fresh disposable migration run; see `docs/runbooks/local-migration.md`.
