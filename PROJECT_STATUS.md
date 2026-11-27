# CloudShift DB Project Status

Last updated: 2026-11-27 (Asia/Kolkata)

## Current phase

Phase 8 — v1.1.0 cloud migration and operations release candidate. The v1.0.0 local acceptance and sanitized
recorded evidence remain intact. The feature branch adds a browser-local planner, deterministic simulator,
architecture/network/FinOps/SRE/DR workspaces, configuration generators, and direct static routes. A clean
DRAFT-to-COMPLETED run verified the migration core, workload, independent availability measurement,
interruption recovery, mismatch guard, staged automated cutover, telemetry, replay, backup/restore,
DBMS practicals, and the expanded command center. All six jobs in GitHub Actions run
[`46024930887`](https://github.com/gargparth2003/cloudshift-db/actions/runs/46024930887) passed.

The v1.1 cloud features are explicitly modeled/configuration-only. No provider credential was used and no
AWS, Azure, Google Cloud, or Kubernetes resource was created. Publication and v1.1 remote CI evidence are
recorded only after the feature branch completes its release gates.

## Phase 0 findings

- Repository began empty on branch `main`, with no commits.
- Host: macOS 26.5.2 on Apple Silicon ARM64.
- Docker: 29.8.0, Compose 5.5.1, aarch64, 10 CPUs, 7.748 GiB allocated memory.
- Existing Docker inventory at inspection: 11 containers (3 running), 73 images.
- DDoS Radar Lite owns `127.0.0.1:8080`; its resources and all InfraForge resources are out of scope and untouched.
- Selected free localhost ports: console 18080, API 18000, commerce 18001, workload/probe 18002,
  Prometheus 19090, source 15432, target 15433, control 15434.
- Host runtimes are intentionally unused for application compatibility: containers pin Python 3.12.8 and PostgreSQL 16.6.

## Implemented

- Project-scoped Compose topology, network, volumes, health checks, resource limits, and localhost-only published ports.
- Independent source, target, and durable control PostgreSQL services.
- Source logical-replication configuration (`wal_level=logical`, bounded slots/senders).
- Normalized 13-table commerce schema with keys, constraints, indexes, view, and analytical materialized view.
- Deterministic starter dataset designed for exactly 13,034 base-table rows.
- Durable control schema covering the required metadata entities.
- Least-purpose application, migration, and observation database roles.
- FastAPI liveness, aggregate health, predefined endpoint inventory, connection testing, and schema discovery.
- Durable migration lifecycle state machine and operator-token mutation guard.
- Native PostgreSQL publication, replication slot, and subscription management.
- Bounded-memory canonical row validation with SHA-256 table checksums and mismatch capture.
- Durable source/target application route and transactional synthetic order creation.
- Controlled write fence, advisory-lock drain, final validation, sequence synchronization, subscription shutdown, target route switch, and source application-role fencing.
- React/TypeScript command center with live topology, resource inspector, summary metrics, table tracker, event timeline, and structured event log.
- Configurable bounded workload generator with read-heavy, write-heavy, balanced, burst, and idle profiles;
  pause/resume/stop controls; durable per-operation evidence; and measured latency/throughput statistics.
- Independent read/write availability probe with durable observations, 250 ms minimum sampling,
  source/failure/target transition timestamps, and explicitly bounded measurement precision.
- Replication pause/resume lifecycle operations and staged automated cutover metadata.
- Prometheus instrumentation for the control plane, commerce service, workload generator, database
  availability, migration state, validation, cutover, and retained-WAL lag. Prometheus is isolated in
  the optional `observability`/`full` profiles with a six-hour retention period.
- Command-center workload/probe controls, measured historical charts, and an application-instrumented
  transaction inspector. Operator credentials are entered at runtime and are not bundled.
- Unit, foundation, replication, and intentional-mismatch integration checks.
- Three-mode cloud operations shell, persistent ten-step planner, nine scenario templates, deterministic
  simulation/backlog state machine, architecture builder, network/security checks, cost formulas, SRE/DR,
  comparison, AWS Terraform generator, Kubernetes explorer, and route-specific static build artifacts.

## Verified

- Phase 0 environment and port inspection.
- Compose configuration: verified locally with `make config`.
- Clean container bootstrap after removing only project-owned disposable volumes.
- Source starter baseline of 13,034 rows, 13 target tables, 22 durable control tables, and logical WAL configuration.
- Native initial synchronization: all 13 relations reached PostgreSQL subscription state `r`.
- Committed INSERT, UPDATE, DELETE, two-row transaction, and rollback exclusion.
- Live commerce source transaction replicated to the target.
- Preliminary full validation: 13,041 rows, zero mismatches, 179.73 ms.
- Intentional target mismatch detected, final validation without a fence blocked, and restored data revalidated.
- Final quiesced validation: 13,046 rows, zero mismatches, 165.79 ms.
- Controlled cutover: 12 sequences synchronized; subscription disabled; source application DML revoked; route changed to target.
- Control write-fence duration: 17,725 ms. This is not an independent availability-probe result.
- First post-cutover target order committed as order 1002, remained absent from source, and source application-role write attempt failed.
- Command-center production build: 106 modules; 368.83 kB JavaScript (119.09 kB gzip).
- Command-center API checks: 7 resources, 7 edges, 13 tracked tables, and 12 durable events.
- Backend tests: 4 passed with one dependency deprecation warning.
- Sampled six-service memory: approximately 204 MiB total; this is a point-in-time observation, not a capacity benchmark.
- Backend tests after workload/probe and telemetry implementation: 6 passed.
- Short balanced workload run at configured 5 ops/s: 35 durable operations, 34 successes, one genuine
  rejected write, 18 committed transactions, measured 3.27 ops/s overall. A running sample observed
  4.145 ops/s, 2.368 committed tx/s, and p50/p95/p99 of 27.621/36.788/41.966 ms.
- Independent target-routed probe run: 23/23 successful observations (18 reads, 5 writes), 250 ms
  sampling precision, and no observed unavailability in that steady-state run.
- Prometheus 3.1.0 started on ARM64; all three application scrape targets reported `up`; source,
  target, and control database availability reported 1; the durable migration state reported COMPLETED.
- Expanded command-center image built with Node 22.14.0 and Recharts 3.11.2 (708 transformed modules).
  The recreated console is healthy and its topology, workload, probe, and Prometheus same-origin routes
  each returned HTTP 200.
- Explicit project reset removed only the `cloudshift-parth` containers, network, and four named volumes;
  images and unrelated Docker projects were preserved. Clean initialization then verified 13,034 source
  rows, 13 target tables, 27 control tables, logical WAL, and DRAFT state.
- Fresh API assessment produced five PASS findings. API migration start created the publication,
  replication slot, and subscription; all 13 relations reached ready state.
- Fresh committed CDC verification passed INSERT, UPDATE, DELETE, two-row atomic commit, and rollback
  exclusion.
- During an approved six-second replication pause under write-heavy workload, the inactive slot retained
  42,488 WAL bytes and transaction-event counts diverged 1,148 source vs 1,106 target. Resume reactivated
  the worker and drained measured lag to zero under continuing workload.
- The recovery workload recorded 382 operations (378 successful, four rejected) and 274 committed
  transactions. Its final measured window was 7.541 ops/s and 5.409 tx/s with p50/p95/p99 latency of
  21.631/32.308/37.870 ms. These are one-run local observations, not capacity claims.
- A 229-observation pre-cutover probe remained fully successful during the pause/resume experiment.
- The fresh mismatch experiment detected the changed target product, blocked unfenced final validation,
  restored the row, and completed a zero-mismatch full validation.
- Automated cutover completed in 470 ms. All 11 durable stages are COMPLETED; 12 sequences were
  synchronized; the subscription was disabled; source application DML was revoked; and the route moved
  to TARGET. The controlled write-fence duration was 424 ms.
- The independent cutover probe recorded 107 observations: 106 successes, one failure, 85 reads, and
  21 committed writes. It measured a 264 ms request-failure window and 1,089 ms from last successful
  source write to first successful target write, with a 250 ms sampling precision limit.
- Post-cutover order `ORD-LIVE-F89F046F7A2A4EE4` committed on TARGET as order 1059, was absent from
  SOURCE, and a direct source application-role INSERT was denied.
- Sanitized replay bundles were captured before reset and after the fresh acceptance run. The original
  bundle is 61,230 bytes and contains no matched credential/token/connection-string patterns.
- A subscription-free PostgreSQL custom backup of the completed target is 238,246 bytes with SHA-256
  `56696f44a6185bfed9af4d73020e22eb50d4ffb72d9f626db0e61f0162d69028`. `pg_restore --list`
  passed, and an isolated restore reproduced all 13 exact table counts and 13,696 total rows with zero
  restored subscriptions. The disposable database was dropped afterward. This is a logical backup,
  not point-in-time recovery.
- The first backup hardening attempt revealed that PostgreSQL dumps subscriptions by default. Its
  disabled restored subscription never activated and the source slot stayed inactive. Creation now uses
  `--no-subscriptions`; the four flawed generated files were securely removed and their durable record
  was marked `REVOKED_EMBEDDED_SUBSCRIPTION` rather than hidden.
- A bounded destination-database interruption was executed against only `target-db`. Commerce moved
  from AVAILABLE/TARGET to UNREACHABLE in 524 ms, then recovered to AVAILABLE/TARGET after restart;
  total measured recovery duration was 1,241 ms. The target-only post-cutover order invariant remained
  present, all three control-plane database health checks recovered, and the incident/experiment plus a
  JSON report were persisted. This single local run is not an availability or MTTR claim.
- The static recorded replay is a 49,220-byte read-only artifact derived from sanitized evidence. Its
  production page exposes event stepping, 11 cutover stages, probe/fence measurements, target orders,
  and backup status without live API dependencies.
- Two actual 1600×1200 Chrome screenshots were visually inspected. An initial invalid capture revealed
  an Nginx physical-directory redirect to internal port 8080; replay data was moved under `/data`, the
  `/replay` route now returns 200 directly, and only corrected CloudShift screenshots were retained.
- Playwright 1.65.1 verified replay event interaction and completed command-center topology inspection
  plus reduced-motion behavior in installed headless Chrome (2 passed). After upgrading Vite to 6.4.6
  and React Router to 7.18.7, `npm audit` reports zero vulnerabilities.
- Advanced DBMS practicals 1–3 executed on an isolated target `lab` schema: normalized/materialized plans,
  ACID and isolation behavior, one serializable failure/one commit, 512.65 ms lock contention, and a
  100,000-row indexing experiment whose equality path changed from Seq Scan to Index Scan.
- Three optional independent PostgreSQL shards each stored 1,000 region-localized rows. Sequential and
  parallel partial aggregation produced identical 3,000-row results; one warm local trial measured
  175.241 ms sequential vs 67.808 ms parallel.
- Optional authenticated Redis verified SET/GET/update/TTL/delete and a legitimate PostgreSQL-backed
  route cache miss/populate/hit/invalidate flow. Optional MongoDB verified three synthetic diagnostic
  inserts, nested filters, grouping, and aggregation. Prometheus verified six instant query families and
  one range series. Optional Neo4j verified a 9-node/12-relationship dependency graph, traversal, impact
  analysis, and the source-to-target path. Optional services were stopped after use; volumes remain.
- Terraform 1.17.2 initialized pinned AWS provider 6.74.0 and validated the no-apply reference architecture.
  Kubernetes Kustomize rendering succeeded; cluster-aware dry-run did not because no reachable cluster is
  configured, so Kubernetes is manifest-prepared but not deployment-verified.
- Final local Gitleaks 8.30.1 scanning covered approximately 4.60 MB and found no leaks. GitHub Actions
  independently passed the frontend/public-offline suite, all 43 backend tests, fresh Compose foundation
  and in-container tests, infrastructure validation, secret scan, and fresh-stack recorded-replay browser
  test in run `46024930887`.
- The public repository is `https://github.com/gargparth2003/cloudshift-db`. GitHub Pages successfully
  deployed the read-only demonstration at `https://gargparth2003.github.io/cloudshift-db/`; its direct
  replay and database-engineering-lab routes passed four Playwright tests against the deployed HTTPS site.
- The release evidence now includes eleven purpose-specific screenshots and an actual WebM migration replay.
  The public bundle is schema v2 with 13 table records and 200 transaction-operation records.
- The v1.1 browser planning domain passes five deterministic tests. Both production builds transform 719
  modules; the lazy cloud-platform chunk is 69.69 kB (20.79 kB gzip). Ten backend-independent Playwright
  journeys pass, including planner export, modeled interruption/recovery/mismatch/cutover, CIDR overlap,
  cost/Terraform behavior, mobile layout, and successful direct refresh of representative static routes.
- The hardened AWS reference passes Terraform 1.17.2/provider 6.74.0 schema validation without plan/apply.
  The unchanged local backend passes 43 tests, its foundation reports 13,563 source rows, 13 target tables,
  27 control tables, and logical WAL, and both live-local browser regressions pass.
- Seven actual 1600-pixel v1.1 screenshots were generated and visually inspected. An actual 1440×900 WebM
  records scenario selection, modeled network failure and blocked cutover, recovery, architecture, and FinOps.
  Gitleaks scanned approximately 7.46 MB with no findings; npm reports zero known vulnerabilities.
- The reproducible benchmark snapshot retained 30 timed reads after five warm-ups for each of three live
  endpoints. Median control/commerce/workload latencies were 0.909/7.738/0.715 ms in that run, with raw
  values, summary statistics, CSV, and an SVG chart saved. Benchmark cells A–E remain explicitly partial;
  F–J are single-trial observations; K combines repeated reads with one eight-container resource snapshot.

## Known limitations

- The original proof used direct publication/subscription setup; the subsequent clean acceptance run verified the fresh-DRAFT API assessment and migration-start path end to end.
- The first historical 17,725 ms write-fence measurement includes operator delay and remains excluded
  from availability claims. The fresh independent measurement is a single local synthetic run and is
  not evidence of production availability or statistically meaningful reliability.
- Destination interruption/recovery and pause-induced retained-WAL growth are verified once. Worker and
  control-plane restarts, source interruption, and bounded connection saturation remain unexecuted.
- Authentication is a local static operator token, not a production identity or authorization system.
- SQL control migrations exist, but Alembic orchestration is not yet configured.
- Browser automation verifies replay interaction, completed topology, and reduced-motion behavior; it
  does not automate every destructive live-local pre-cutover lifecycle control. v1.1 adds browser coverage
  for modeled planner, failure/recovery, validation/cutover, network, cost, Terraform, routes, and mobile use.
- The public site is a static, sanitized replay, not a hosted control plane or a claim that live databases
  are publicly reachable. Its controls cannot mutate local or cloud infrastructure.
- Kubernetes and AWS resources are configuration-only and not deployed. Backup/restore is verified for
  logical dumps, but WAL archiving/PITR is not implemented. No statistically controlled benchmark matrix
  across 100k/1M datasets exists yet.
- The disabled subscription retains its slot; post-cutover WAL retention and explicit slot retirement policy remain to be implemented.
- Development credentials in `.env` are disposable local values; deployment secret management is not implemented.
- Materialized views are not refreshed during cutover. Sequence synchronization is implemented, but concurrent DDL and schema evolution remain unsupported.

## Exact next steps

1. Complete the benchmark cells still labeled `PARTIAL`: offline baseline, controlled migration-size sweep,
   repeated profile/rate matrix, and sampled-validation comparison.
2. Add bounded worker, control-plane, and source interruption plus connection-saturation experiments using
   the existing incident evidence model.
3. Expand browser coverage across safe pre-cutover lifecycle controls; the current video is a recorded
   release artifact rather than an exhaustive lifecycle test.
4. Decide and implement a post-cutover replication-slot retirement policy and WAL-archiving/PITR design.
5. Add production-grade identity, secret management, HA, and statistically controlled performance testing
   before considering any non-demo deployment.
6. Keep AWS and Kubernetes deployment configuration-only until separately authorized; no AWS resource has
   been created by this release.
