\set ON_ERROR_STOP on

CREATE TABLE IF NOT EXISTS control.workload_runs (
    workload_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    migration_id uuid REFERENCES control.migration_tasks(migration_id),
    profile text NOT NULL CHECK (profile IN ('READ_HEAVY', 'WRITE_HEAVY', 'BALANCED', 'BURST', 'IDLE')),
    configured_rate integer NOT NULL CHECK (configured_rate IN (5, 10, 25, 50)),
    random_seed bigint NOT NULL,
    status text NOT NULL CHECK (status IN ('RUNNING', 'PAUSED', 'STOPPED', 'FAILED')),
    started_at timestamptz NOT NULL DEFAULT now(),
    stopped_at timestamptz
);

CREATE TABLE IF NOT EXISTS control.workload_operations (
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

CREATE TABLE IF NOT EXISTS control.availability_probe_runs (
    probe_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    migration_id uuid REFERENCES control.migration_tasks(migration_id),
    sample_interval_ms integer NOT NULL CHECK (sample_interval_ms BETWEEN 100 AND 5000),
    write_interval_ms integer NOT NULL CHECK (write_interval_ms BETWEEN 250 AND 10000),
    status text NOT NULL CHECK (status IN ('RUNNING', 'STOPPED', 'FAILED')),
    started_at timestamptz NOT NULL DEFAULT now(),
    stopped_at timestamptz
);

CREATE TABLE IF NOT EXISTS control.availability_probe_observations (
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

CREATE INDEX IF NOT EXISTS idx_workload_operations_run_observed
    ON control.workload_operations(workload_run_id, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_probe_observations_run_observed
    ON control.availability_probe_observations(probe_run_id, observed_at DESC);
