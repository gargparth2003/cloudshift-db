export type Resource = {
  id: string
  name: string
  type: string
  health: string
  state?: string
  version?: string
  last_observed?: string
}

export type Connection = {
  id: string
  source: string
  target: string
  category: 'APPLICATION' | 'REPLICATION' | 'VALIDATION'
  active: boolean
}

export type ReplicationMetrics = {
  state: string
  ready_tables: number
  total_tables: number
  table_states: Record<string, number>
  subscription: { worker_active: boolean; received_lsn?: string; latest_end_lsn?: string } | null
  slot: { active: boolean; confirmed_flush_lsn: string; wal_byte_lag: number } | null
  observed_at: string
}

export type Topology = {
  task_key: string
  state: string
  route: { active_endpoint: string; writes_enabled: boolean; version: number; updated_at: string }
  resources: Resource[]
  connections: Connection[]
  replication: ReplicationMetrics
  observed_at: string
}

export type TableObservation = {
  schema: string
  table: string
  source_row_estimate?: number
  target_row_estimate?: number
  source_bytes?: number
  target_bytes?: number
  subscription_state?: string
  validation?: {
    status: string
    missing_rows: number
    extra_rows: number
    mismatched_rows: number
    completed_at: string
  }
}

export type MigrationEvent = {
  event_id: number
  event_type: string
  component: string
  severity: string
  message: string
  evidence: Record<string, unknown>
  occurred_at: string
}

export type ValidationRun = {
  validation_run_id: string
  scope: string
  status: string
  rows_checked: number
  mismatches: number
  started_at: string
  completed_at?: string
}

export type WorkloadStatus = {
  state: 'RUNNING' | 'PAUSED' | 'STOPPED'
  profile: string
  configured_rate: number
  workload_run_id?: string
  active_database?: string
  operations_per_second: number
  transactions_per_second: number
  reads_per_second: number
  writes_per_second: number
  successful_operations: number
  failed_operations: number
  committed_transactions: number
  rolled_back_or_rejected: number
  p50_latency_ms?: number
  p95_latency_ms?: number
  p99_latency_ms?: number
  observed_at: string
}

export type WorkloadOperation = {
  operation_id: number
  workload_run_id: string
  operation_type: string
  operation_class: 'READ' | 'WRITE'
  success: boolean
  committed: boolean
  latency_ms: number
  active_endpoint?: string
  transaction_ref?: string
  error_class?: string
  observed_at: string
}

export type ProbeSummary = {
  state: string
  probe_run_id?: string
  observations: number
  successful?: number
  failed?: number
  successful_reads?: number
  successful_writes?: number
  sample_interval_ms?: number
  last_source_write?: string
  first_write_failure?: string
  first_target_write?: string
  observed_write_unavailability_ms?: number
  observed_request_failure_window_ms?: number
  method?: string
  precision_limit_ms?: number
}

export type PrometheusPoint = { timestamp: number; value: number }

export type CutoverStage = {
  stage_name: string
  stage_order: number
  status: string
  started_at?: string
  completed_at?: string
  evidence: Record<string, unknown>
  error_message?: string
}

export type ReplayBundle = {
  schema_version: number
  kind: string
  captured_at: string
  claim_boundary: string
  migration: { task_key: string; state: string; version: number }
  route: { active_endpoint: string; writes_enabled: boolean; version: number }
  topology: Topology
  tables: TableObservation[]
  validations: ValidationRun[]
  cutover: {
    cutover_id: string
    outcome: string
    write_unavailability_ms: number
    requested_at: string
    completed_at: string
    stages: CutoverStage[]
  }
  probe: ProbeSummary
  workload: WorkloadStatus
  workload_operations: WorkloadOperation[]
  commerce: {
    health: { state: string; active_database: string; writes_enabled: boolean }
    orders: Array<{ order_id: number; order_ref: string; total: number; created_at: string }>
    activity: Array<{ event_id: number; transaction_ref: string; event_type: string; committed_at: string }>
  }
  backups: Array<{ backup_id: string; storage_reference: string; size_bytes: number; verification_status: string; verified_at: string }>
  incidents: Array<{
    incident_id: string
    severity: string
    affected_resources: string[]
    symptoms: string
    recovery_result?: string
    recovery_duration_ms?: number
    remaining_risk?: string
    detected_at: string
    resolved_at?: string
  }>
  experiments: Array<{ experiment_id: string; experiment_type: string; status: string; result: Record<string, unknown> }>
  events: MigrationEvent[]
  benchmark?: {
    observed_at: string
    method: { read_warmup: number; read_trials: number; selection: string }
    live_read_trials: Record<string, { median_ms: number; p95_ms: number; p99_ms: number; stdev_ms: number; trials: number }>
    benchmarks: Record<string, { status: string; measurements: Record<string, string | number | boolean | null>; limitation: string }>
  }
}
