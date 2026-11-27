# Performance Evidence

`make benchmark` performs 30 read-only HTTP trials per live endpoint after five warm-up requests, takes
one project-container resource snapshot, and combines those observations with the immutable acceptance,
incident, and DBMS-lab artifacts. It writes timestamped JSON, a flat CSV, and an SVG chart under
`artifacts/benchmarks`, plus `latest.json`.

The report has an explicit status and limitation for benchmarks A–K. It does not fill missing cells with
estimates. The current acceptance evidence supports a real online cutover, 13,696 migrated rows, separate
100,000-row indexing, balanced/write-heavy workloads, full validation, index/cache/distributed-query
comparisons, destination recovery, cutover availability, and point-in-time resources.

The following remain deliberately `PARTIAL`: a destructive offline-migration baseline, a controlled
10k/100k/1m migration sweep, repeated read-heavy/write-heavy/balanced trials across rate levels, and
sampled validation. Single lab and reliability observations are labeled as such; they are not capacity,
availability, or production-readiness claims.

Run the snapshot only while the core stack is healthy:

```sh
make health
make benchmark
```

The harness retains every trial and reports mean, median, p95, p99, min, max, and sample standard
deviation for the repeated live reads. Raw per-request durations remain in JSON.
