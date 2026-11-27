\set ON_ERROR_STOP on

CREATE EXTENSION IF NOT EXISTS pgcrypto;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
CREATE SCHEMA control;

CREATE TYPE control.endpoint_role AS ENUM ('SOURCE', 'TARGET', 'CONTROL');
CREATE TYPE control.health_state AS ENUM ('UNKNOWN', 'CHECKING', 'AVAILABLE', 'DEGRADED', 'UNREACHABLE', 'MISCONFIGURED');
CREATE TYPE control.migration_state AS ENUM (
    'DRAFT', 'ASSESSING', 'ASSESSMENT_FAILED', 'READY', 'INITIAL_SYNC',
    'CONTINUOUS_REPLICATION', 'VALIDATING', 'READY_FOR_CUTOVER',
    'CUTOVER_IN_PROGRESS', 'COMPLETED', 'PAUSED', 'FAILED',
    'RECOVERY_REQUIRED', 'CANCELLED'
);
CREATE TYPE control.severity AS ENUM ('INFORMATIONAL', 'WARNING', 'BLOCKING', 'CRITICAL');

CREATE TABLE control.workspaces (
    workspace_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE control.environments (
    environment_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL REFERENCES control.workspaces(workspace_id),
    name text NOT NULL,
    deployment_mode text NOT NULL CHECK (deployment_mode IN ('LIVE_LOCAL', 'PUBLIC_REPLAY', 'AWS')),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (workspace_id, name)
);

CREATE TABLE control.database_endpoints (
    endpoint_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    environment_id uuid NOT NULL REFERENCES control.environments(environment_id),
    endpoint_key text NOT NULL UNIQUE,
    resource_name text NOT NULL,
    endpoint_role control.endpoint_role NOT NULL,
    engine text NOT NULL DEFAULT 'postgresql',
    database_name text NOT NULL,
    host_reference text NOT NULL,
    port integer NOT NULL CHECK (port BETWEEN 1 AND 65535),
    credential_reference text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE control.endpoint_health_checks (
    check_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    endpoint_id uuid NOT NULL REFERENCES control.database_endpoints(endpoint_id) ON DELETE CASCADE,
    state control.health_state NOT NULL,
    latency_ms numeric(12,3),
    evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
    observed_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE control.migration_tasks (
    migration_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    task_key text NOT NULL UNIQUE,
    workspace_id uuid NOT NULL REFERENCES control.workspaces(workspace_id),
    source_endpoint_id uuid NOT NULL REFERENCES control.database_endpoints(endpoint_id),
    target_endpoint_id uuid NOT NULL REFERENCES control.database_endpoints(endpoint_id),
    state control.migration_state NOT NULL DEFAULT 'DRAFT',
    version integer NOT NULL DEFAULT 1 CHECK (version > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (source_endpoint_id <> target_endpoint_id)
);

CREATE TABLE control.migration_runs (
    run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    migration_id uuid NOT NULL REFERENCES control.migration_tasks(migration_id),
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    outcome text,
    error_details jsonb
);

CREATE TABLE control.migration_table_mappings (
    mapping_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    migration_id uuid NOT NULL REFERENCES control.migration_tasks(migration_id) ON DELETE CASCADE,
    source_schema text NOT NULL,
    source_table text NOT NULL,
    target_schema text NOT NULL,
    target_table text NOT NULL,
    sync_state text NOT NULL DEFAULT 'PENDING',
    source_row_estimate bigint,
    target_rows_observed bigint,
    last_observed_at timestamptz,
    UNIQUE (migration_id, source_schema, source_table)
);

CREATE TABLE control.migration_checkpoints (
    checkpoint_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    migration_id uuid NOT NULL REFERENCES control.migration_tasks(migration_id),
    checkpoint_type text NOT NULL,
    source_lsn pg_lsn,
    target_lsn pg_lsn,
    context jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE control.replication_observations (
    observation_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    migration_id uuid NOT NULL REFERENCES control.migration_tasks(migration_id),
    slot_name text,
    worker_state text,
    source_current_lsn pg_lsn,
    confirmed_flush_lsn pg_lsn,
    wal_byte_lag bigint CHECK (wal_byte_lag IS NULL OR wal_byte_lag >= 0),
    observed_latency_ms numeric(14,3),
    observed_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE control.migration_events (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    migration_id uuid REFERENCES control.migration_tasks(migration_id),
    event_type text NOT NULL,
    component text NOT NULL,
    severity control.severity NOT NULL DEFAULT 'INFORMATIONAL',
    message text NOT NULL,
    evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
    occurred_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE control.migration_metrics (
    metric_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    migration_id uuid REFERENCES control.migration_tasks(migration_id),
    metric_name text NOT NULL,
    metric_value double precision NOT NULL,
    unit text NOT NULL,
    measurement_kind text NOT NULL CHECK (measurement_kind IN ('MEASURED', 'ESTIMATED')),
    observed_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE control.validation_runs (
    validation_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    migration_id uuid NOT NULL REFERENCES control.migration_tasks(migration_id),
    scope text NOT NULL CHECK (scope IN ('SAMPLED', 'TABLE', 'FULL', 'FINAL_QUIESCED')),
    consistency_checkpoint_id uuid REFERENCES control.migration_checkpoints(checkpoint_id),
    status text NOT NULL,
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz
);

CREATE TABLE control.validation_results (
    result_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    validation_run_id uuid NOT NULL REFERENCES control.validation_runs(validation_run_id) ON DELETE CASCADE,
    schema_name text NOT NULL,
    table_name text NOT NULL,
    rows_checked bigint NOT NULL DEFAULT 0,
    rows_matched bigint NOT NULL DEFAULT 0,
    missing_rows bigint NOT NULL DEFAULT 0,
    extra_rows bigint NOT NULL DEFAULT 0,
    mismatched_rows bigint NOT NULL DEFAULT 0,
    checksum_method text,
    UNIQUE (validation_run_id, schema_name, table_name)
);

CREATE TABLE control.validation_mismatches (
    mismatch_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    result_id uuid NOT NULL REFERENCES control.validation_results(result_id) ON DELETE CASCADE,
    primary_key jsonb NOT NULL,
    source_value jsonb,
    target_value jsonb,
    detected_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE control.migration_incidents (
    incident_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    migration_id uuid REFERENCES control.migration_tasks(migration_id),
    severity control.severity NOT NULL,
    affected_resources text[] NOT NULL DEFAULT '{}'::text[],
    symptoms text NOT NULL,
    suspected_cause text,
    verified_cause text,
    supporting_evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
    detection_duration_ms bigint CHECK (detection_duration_ms IS NULL OR detection_duration_ms >= 0),
    recovery_action text,
    recovery_result text,
    recovery_timestamp timestamptz,
    recovery_duration_ms bigint CHECK (recovery_duration_ms IS NULL OR recovery_duration_ms >= 0),
    remaining_risk text,
    detected_at timestamptz NOT NULL DEFAULT now(),
    resolved_at timestamptz
);

CREATE TABLE control.cutover_history (
    cutover_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    migration_id uuid NOT NULL REFERENCES control.migration_tasks(migration_id),
    requested_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    outcome text NOT NULL,
    write_unavailability_ms bigint,
    final_validation_run_id uuid REFERENCES control.validation_runs(validation_run_id),
    evidence jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE control.cutover_stages (
    cutover_stage_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cutover_id uuid NOT NULL REFERENCES control.cutover_history(cutover_id) ON DELETE CASCADE,
    stage_name text NOT NULL,
    stage_order integer NOT NULL CHECK (stage_order > 0),
    status text NOT NULL CHECK (status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'BLOCKED')),
    started_at timestamptz,
    completed_at timestamptz,
    evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
    error_message text,
    UNIQUE (cutover_id, stage_name)
);

CREATE TABLE control.backup_records (
    backup_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    endpoint_id uuid NOT NULL REFERENCES control.database_endpoints(endpoint_id),
    storage_reference text NOT NULL,
    size_bytes bigint CHECK (size_bytes >= 0),
    checksum text,
    verification_status text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    verified_at timestamptz
);

CREATE TABLE control.user_roles (
    subject_id text NOT NULL,
    role_name text NOT NULL CHECK (role_name IN ('VIEWER', 'OPERATOR', 'ADMIN')),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (subject_id, role_name)
);

CREATE TABLE control.audit_logs (
    audit_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    actor text NOT NULL,
    action text NOT NULL,
    resource_type text NOT NULL,
    resource_id text,
    correlation_id text NOT NULL,
    outcome text NOT NULL,
    details jsonb NOT NULL DEFAULT '{}'::jsonb,
    occurred_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE control.benchmark_runs (
    benchmark_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    benchmark_type text NOT NULL,
    configuration jsonb NOT NULL,
    raw_result_reference text,
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz
);

CREATE TABLE control.experiment_runs (
    experiment_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    experiment_type text NOT NULL,
    status text NOT NULL,
    configuration jsonb NOT NULL,
    result jsonb,
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz
);

CREATE TABLE control.application_routes (
    route_key text PRIMARY KEY,
    active_endpoint control.endpoint_role NOT NULL CHECK (active_endpoint IN ('SOURCE', 'TARGET')),
    writes_enabled boolean NOT NULL DEFAULT true,
    version integer NOT NULL DEFAULT 1 CHECK (version > 0),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE control.workload_runs (
    workload_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    migration_id uuid REFERENCES control.migration_tasks(migration_id),
    profile text NOT NULL CHECK (profile IN ('READ_HEAVY', 'WRITE_HEAVY', 'BALANCED', 'BURST', 'IDLE')),
    configured_rate integer NOT NULL CHECK (configured_rate IN (5, 10, 25, 50)),
    random_seed bigint NOT NULL,
    status text NOT NULL CHECK (status IN ('RUNNING', 'PAUSED', 'STOPPED', 'FAILED')),
    started_at timestamptz NOT NULL DEFAULT now(),
    stopped_at timestamptz
);

CREATE TABLE control.workload_operations (
    operation_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    workload_run_id uuid NOT NULL REFERENCES control.workload_runs(workload_run_id) ON DELETE CASCADE,
    operation_type text NOT NULL,
    operation_class text NOT NULL CHECK (operation_class IN ('READ', 'WRITE')),
    success boolean NOT NULL,
    committed boolean NOT NULL,
    latency_ms numeric(14,3) NOT NULL CHECK (latency_ms >= 0),
    active_endpoint control.endpoint_role CHECK (active_endpoint IN ('SOURCE', 'TARGET')),
    transaction_ref text,
    error_class text,
    observed_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE control.availability_probe_runs (
    probe_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    migration_id uuid REFERENCES control.migration_tasks(migration_id),
    sample_interval_ms integer NOT NULL CHECK (sample_interval_ms BETWEEN 100 AND 5000),
    write_interval_ms integer NOT NULL CHECK (write_interval_ms BETWEEN 250 AND 10000),
    status text NOT NULL CHECK (status IN ('RUNNING', 'STOPPED', 'FAILED')),
    started_at timestamptz NOT NULL DEFAULT now(),
    stopped_at timestamptz
);

CREATE TABLE control.availability_probe_observations (
    observation_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    probe_run_id uuid NOT NULL REFERENCES control.availability_probe_runs(probe_run_id) ON DELETE CASCADE,
    request_type text NOT NULL CHECK (request_type IN ('READ', 'WRITE')),
    success boolean NOT NULL,
    latency_ms numeric(14,3) NOT NULL CHECK (latency_ms >= 0),
    active_endpoint control.endpoint_role CHECK (active_endpoint IN ('SOURCE', 'TARGET')),
    transaction_ref text,
    error_class text,
    observed_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_health_endpoint_observed ON control.endpoint_health_checks(endpoint_id, observed_at DESC);
CREATE INDEX idx_events_migration_occurred ON control.migration_events(migration_id, occurred_at DESC);
CREATE INDEX idx_metrics_migration_name_observed ON control.migration_metrics(migration_id, metric_name, observed_at DESC);
CREATE INDEX idx_replication_migration_observed ON control.replication_observations(migration_id, observed_at DESC);
CREATE INDEX idx_audit_occurred ON control.audit_logs(occurred_at DESC);
CREATE INDEX idx_workload_operations_run_observed ON control.workload_operations(workload_run_id, observed_at DESC);
CREATE INDEX idx_probe_observations_run_observed ON control.availability_probe_observations(probe_run_id, observed_at DESC);

WITH workspace AS (
    INSERT INTO control.workspaces (name)
    VALUES ('Parth Garg — Cloud Engineering Lab')
    RETURNING workspace_id
), environments AS (
    INSERT INTO control.environments (workspace_id, name, deployment_mode)
    SELECT workspace_id, name, 'LIVE_LOCAL'
    FROM workspace
    CROSS JOIN (VALUES ('parth-source-dc01'), ('parth-cloud-region01')) names(name)
    RETURNING environment_id, name
)
INSERT INTO control.database_endpoints (
    environment_id, endpoint_key, resource_name, endpoint_role, database_name,
    host_reference, port, credential_reference
)
SELECT environment_id, 'source', 'pg-source-parth', 'SOURCE'::control.endpoint_role, 'parth_commerce_source',
       'source-db', 5432, 'env:SOURCE_DATABASE_URL'
FROM environments WHERE name = 'parth-source-dc01'
UNION ALL
SELECT environment_id, 'target', 'pg-target-parth', 'TARGET'::control.endpoint_role, 'parth_commerce_target',
       'target-db', 5432, 'env:TARGET_DATABASE_URL'
FROM environments WHERE name = 'parth-cloud-region01';

INSERT INTO control.migration_tasks (
    task_key, workspace_id, source_endpoint_id, target_endpoint_id
)
SELECT 'parth-commerce-migration-001', w.workspace_id, source.endpoint_id, target.endpoint_id
FROM control.workspaces w
JOIN control.database_endpoints source ON source.endpoint_key = 'source'
JOIN control.database_endpoints target ON target.endpoint_key = 'target'
WHERE w.name = 'Parth Garg — Cloud Engineering Lab';

INSERT INTO control.migration_events (migration_id, event_type, component, message)
SELECT migration_id, 'MIGRATION_CREATED', 'cloudshift-control-plane',
       'Migration task created in DRAFT state.'
FROM control.migration_tasks WHERE task_key = 'parth-commerce-migration-001';

INSERT INTO control.application_routes (route_key, active_endpoint, writes_enabled)
VALUES ('parth-commerce-application', 'SOURCE', true);
