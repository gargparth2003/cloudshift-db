import { lazy, Suspense, useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, Navigate, Route, Routes } from 'react-router-dom'
import ReactFlow, { Background, Controls, Edge, Handle, MarkerType, MiniMap, Node, Position } from 'reactflow'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from './api'
import type { Connection, Resource, WorkloadStatus } from './types'

const CloudPlatform = lazy(() => import('./cloud/CloudPlatform'))

const positions: Record<string, { x: number; y: number }> = {
  commerce: { x: 20, y: 170 },
  router: { x: 235, y: 170 },
  source: { x: 455, y: 55 },
  replication: { x: 680, y: 55 },
  target: { x: 900, y: 170 },
  validation: { x: 680, y: 285 },
  control: { x: 455, y: 285 },
}

function statusClass(value: string) {
  if (['AVAILABLE', 'COMPLETED', 'MATCHED', 'TARGET'].includes(value)) return 'status good'
  if (['WARNING', 'DEGRADED', 'PAUSED'].includes(value)) return 'status warn'
  if (['FAILED', 'UNREACHABLE', 'MISMATCHED'].includes(value)) return 'status bad'
  return 'status neutral'
}

function formatBytes(value?: number) {
  if (value === undefined) return 'Unavailable'
  const units = ['B', 'KiB', 'MiB', 'GiB']
  let amount = value
  let unit = 0
  while (amount >= 1024 && unit < units.length - 1) { amount /= 1024; unit += 1 }
  return `${amount.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`
}

function formatTime(value?: string) {
  return value ? new Date(value).toLocaleString() : 'Unavailable'
}

function Landing() {
  return (
    <main className="landing">
      <div className="landing-inner">
        <p className="eyebrow">DATABASE RELIABILITY ENGINEERING</p>
        <h1>CloudShift DB</h1>
        <p className="lede">A PostgreSQL migration and reliability platform that combines native logical replication, deterministic validation, measured recovery, and controlled application cutover.</p>
        <div className="evidence-row">
          <div><strong>13</strong><span>tables synchronized</span></div>
          <div><strong>13,563</strong><span>rows final-validated</span></div>
          <div><strong>0</strong><span>final mismatches</span></div>
        </div>
        <p className="evidence-note">Verified locally on 27 November 2026. Results are specific to the recorded development run.</p>
        <div className="landing-actions"><Link className="primary-action" to="/platform">Open Cloud Migration Studio</Link><Link className="secondary-action" to="/replay">Launch Interactive Migration Demo</Link><a className="secondary-action" href="#engineering-outcomes">Review engineering outcomes</a><Link className="secondary-action" to="/database-engineering-lab">Database Engineering Lab</Link></div>
        <section id="engineering-outcomes" className="landing-details">
          <div><span>DATA PLANE</span><h2>Native PostgreSQL replication</h2><p>Initial table synchronization transitions into WAL-backed continuous change replication while transaction boundaries remain PostgreSQL-managed.</p></div>
          <div><span>CONTROL PLANE</span><h2>Validated, staged cutover</h2><p>Assessment, mismatch blocking, write fencing, drain, final validation, sequence synchronization, route switching, and source protection are persisted as evidence.</p></div>
          <div><span>RELIABILITY</span><h2>Measured—not marketed</h2><p>The recorded run distinguishes a 424 ms control fence, a 264 ms observed request-failure window, and a 1,089 ms probe write transition.</p></div>
        </section>
        <p className="attribution">Designed and developed by Parth Garg · M.E. Cloud Computing</p>
      </div>
    </main>
  )
}

function RecordedTopology({ topology, state, route }: { topology: import('./types').Topology; state: string; route: string }) {
  const [selected, setSelected] = useState<Resource | null>(null)
  const replicationActive = ['INITIAL_SYNC', 'CONTINUOUS_REPLICATION', 'VALIDATING', 'READY_FOR_CUTOVER'].includes(state)
  const validationActive = state === 'VALIDATING'
  const resources = topology.resources.map(resource => resource.id === 'router' ? { ...resource, state: route } : resource.id === 'replication' ? { ...resource, state: replicationActive ? 'ACTIVE' : 'STOPPED' } : resource)
  const connections = topology.connections.map(connection => ({
    ...connection,
    active: connection.id === 'commerce-router'
      || (connection.id === 'router-source' && route === 'SOURCE')
      || (connection.id === 'router-target' && route === 'TARGET')
      || (connection.category === 'REPLICATION' && replicationActive)
      || (connection.category === 'VALIDATION' && validationActive),
  }))
  const nodes = resources.map(resource => ({ id: resource.id, type: 'resource', data: resource, position: positions[resource.id] ?? { x: 455, y: 420 }, sourcePosition: Position.Right, targetPosition: Position.Left }))
  const edges = connections.map(connection => graphEdge(connection, false))
  return <section className="replay-topology-grid">
    <div className="panel topology-panel">
      <div className="panel-header"><div><h2>Recorded infrastructure topology</h2><p>Connections follow the selected event · application route {route}</p></div><span className={statusClass(state)}>{state.replaceAll('_', ' ')}</span></div>
      <div className="topology-canvas replay-topology"><ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} fitView minZoom={0.45} maxZoom={1.8} onNodeClick={(_, node) => setSelected(node.data as Resource)}><Background color="#d8dee8" gap={20}/><Controls/></ReactFlow></div>
      <div className="legend"><span className="app-line">Application route</span><span className="rep-line">Initial sync / CDC</span><span className="val-line">Validation</span><span className="inactive-line">Inactive at this event</span></div>
    </div>
    <aside className="panel replay-inspector"><div className="panel-header"><div><h2>Recorded resource inspection</h2><p>Select a topology node</p></div></div>{selected ? <dl><dt>Resource</dt><dd>{selected.name}</dd><dt>Type</dt><dd>{selected.type}</dd><dt>Health at capture</dt><dd>{selected.health}</dd><dt>State at this event</dt><dd>{selected.state ?? 'AVAILABLE'}</dd><dt>Version</dt><dd>{selected.version ?? 'Not applicable'}</dd></dl> : <p>Select an application, database, replication, or validation resource to inspect its captured state.</p>}</aside>
  </section>
}

function Replay() {
  const replay = useQuery({ queryKey: ['static-replay'], queryFn: api.replay })
  const [step, setStep] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(1)
  const [tableSearch, setTableSearch] = useState('')
  const [transactionSearch, setTransactionSearch] = useState('')
  const eventCount = replay.data?.events.length ?? 0
  useEffect(() => {
    if (!playing || eventCount < 2) return
    const timer = window.setInterval(() => setStep(current => {
      if (current >= eventCount - 1) { setPlaying(false); return current }
      return current + 1
    }), 1200 / speed)
    return () => window.clearInterval(timer)
  }, [playing, speed, eventCount])
  if (replay.isError) return <main className="replay-shell"><div className="error-state">Recorded replay unavailable: {(replay.error as Error).message}</div></main>
  if (!replay.data) return <main className="replay-shell"><div className="loading">Loading recorded migration evidence…</div></main>
  const data = replay.data
  const events = data.events
  const boundedStep = Math.min(step, Math.max(events.length - 1, 0))
  const event = events[boundedStep]
  const finalValidation = data.validations.find(item => item.scope === 'FINAL_QUIESCED')
  const latestIncident = data.incidents[0]
  const currentState = String(event?.evidence.current_state ?? (boundedStep === 0 ? 'DRAFT' : boundedStep >= events.length - 3 ? 'COMPLETED' : 'CONTINUOUS_REPLICATION'))
  const replayRoute = currentState === 'COMPLETED' ? 'TARGET' : 'SOURCE'
  const tables = data.tables.filter(table => !tableSearch || table.table.toLowerCase().includes(tableSearch.toLowerCase()))
  const transactions = data.workload_operations.filter(item => !transactionSearch || `${item.operation_type} ${item.transaction_ref ?? ''} ${item.active_endpoint ?? ''}`.toLowerCase().includes(transactionSearch.toLowerCase()))
  const workloadRuns = events.filter(item => item.event_type === 'WORKLOAD_STOPPED').map(item => item.evidence.metrics as WorkloadStatus)
  return <main className="replay-shell">
    <header className="replay-header"><div><p className="eyebrow">RECORDED VERIFIED DEMONSTRATION</p><h1>CloudShift DB migration replay</h1><p>{data.migration.task_key} · captured {formatTime(data.captured_at)}</p></div><div className="recorded-badge">RECORDED · READ ONLY</div></header>
    <nav className="replay-nav" aria-label="Replay sections"><a href="#playback">Playback</a><a href="#topology">Topology</a><a href="#tables">Tables</a><a href="#transactions">Transactions</a><a href="#performance">Performance</a><a href="#report">Final report</a></nav>
    <div className="replay-boundary">{data.claim_boundary}</div>
    <section className="metric-grid replay-metrics">
      <article><span>Final lifecycle</span><strong>{data.migration.state}</strong><small>Durable state, version {data.migration.version}</small></article>
      <article><span>Final validation</span><strong>{finalValidation?.status ?? 'Unavailable'}</strong><small>{finalValidation?.rows_checked.toLocaleString() ?? '—'} rows checked</small></article>
      <article><span>Cutover stages</span><strong>{data.cutover.stages.filter(stage => stage.status === 'COMPLETED').length} / {data.cutover.stages.length}</strong><small>Persisted stage evidence</small></article>
      <article><span>Control write fence</span><strong>{data.cutover.write_unavailability_ms} ms</strong><small>Not the independent probe window</small></article>
      <article><span>Probe failure window</span><strong>{data.probe.observed_request_failure_window_ms ?? '—'} ms</strong><small>{data.probe.precision_limit_ms ?? '—'} ms sampling precision</small></article>
      <article><span>Final application route</span><strong>{data.route.active_endpoint}</strong><small>Writes {data.route.writes_enabled ? 'enabled' : 'fenced'}</small></article>
    </section>
    <section className="panel replay-player" id="playback">
      <div className="panel-header"><div><h2>Migration event playback</h2><p>Step through durable control-plane events captured during the local run.</p></div><span>{events.length ? `${boundedStep + 1} / ${events.length}` : 'No events'}</span></div>
      <div className="player-controls"><button onClick={() => setPlaying(value => !value)}>{playing ? 'Pause' : 'Play'}</button><button onClick={() => { setPlaying(false); setStep(0) }}>Restart</button><button onClick={() => setStep(Math.max(0, boundedStep - 1))} disabled={boundedStep === 0}>Previous</button><input aria-label="Replay event" type="range" min="0" max={Math.max(events.length - 1, 0)} value={boundedStep} onChange={item => { setPlaying(false); setStep(Number(item.target.value)) }}/><button onClick={() => setStep(Math.min(events.length - 1, boundedStep + 1))} disabled={boundedStep >= events.length - 1}>Next</button><label>Speed<select aria-label="Playback speed" value={speed} onChange={item => setSpeed(Number(item.target.value))}><option value={0.5}>0.5×</option><option value={1}>1×</option><option value={2}>2×</option></select></label></div>
      {event && <div className="replay-event"><time>{formatTime(event.occurred_at)}</time><span className={`severity ${event.severity.toLowerCase()}`}>{event.severity}</span><div><strong>{event.event_type.replaceAll('_', ' ')}</strong><p>{event.message}</p><small>{event.component}</small></div></div>}
    </section>
    <div id="topology"><RecordedTopology topology={data.topology} state={currentState} route={replayRoute}/></div>
    <section className="replay-grid">
      <div className="panel"><div className="panel-header"><div><h2>Automated cutover center</h2><p>Actual persisted stages from the completed workflow.</p></div><span className={statusClass(data.cutover.outcome)}>{data.cutover.outcome}</span></div><ol className="stage-list">{data.cutover.stages.map(stage => <li key={stage.stage_name}><span>{stage.stage_order}</span><div><strong>{stage.stage_name.replaceAll('_',' ')}</strong><small>{formatTime(stage.completed_at)}</small></div><span className={statusClass(stage.status)}>{stage.status}</span></li>)}</ol></div>
      <div className="panel"><div className="panel-header"><div><h2>Recorded destination writes</h2><p>Orders observed through the target-routed commerce API.</p></div><span>{data.commerce.orders.length} shown</span></div><div className="table-scroll"><table><thead><tr><th>Order</th><th>Reference</th><th>Total</th><th>Created</th></tr></thead><tbody>{data.commerce.orders.map(order => <tr key={order.order_id}><td>{order.order_id}</td><td className="mono">{order.order_ref}</td><td>{order.total}</td><td>{formatTime(order.created_at)}</td></tr>)}</tbody></table></div></div>
    </section>
    <section className="panel replay-data-panel recorded-tables" id="tables"><div className="panel-header"><div><h2>Table migration tracker</h2><p>Captured estimates plus exact final validation results</p></div><input aria-label="Filter recorded tables" value={tableSearch} onChange={item => setTableSearch(item.target.value)} placeholder="Filter tables"/></div><div className="table-scroll"><table><thead><tr><th>Table</th><th>Source estimate</th><th>Target estimate</th><th>Sync</th><th>Validation</th><th>Mismatches</th></tr></thead><tbody>{tables.map(table => <tr key={table.table}><td><strong>{table.table}</strong></td><td>{table.source_row_estimate?.toLocaleString() ?? '—'}</td><td>{table.target_row_estimate?.toLocaleString() ?? '—'}</td><td>{table.subscription_state === 'r' ? 'Ready' : table.subscription_state}</td><td><span className={statusClass(table.validation?.status ?? '')}>{table.validation?.status ?? '—'}</span></td><td>{table.validation ? table.validation.missing_rows + table.validation.extra_rows + table.validation.mismatched_rows : '—'}</td></tr>)}</tbody></table></div></section>
    <section className="panel replay-data-panel recorded-transactions" id="transactions"><div className="panel-header"><div><h2>Recorded transaction inspector</h2><p>Application-instrumented operations from the verified workload</p></div><input aria-label="Filter recorded transactions" value={transactionSearch} onChange={item => setTransactionSearch(item.target.value)} placeholder="Filter transactions"/></div><div className="table-scroll"><table><thead><tr><th>Observed</th><th>Operation</th><th>Class</th><th>Result</th><th>Route</th><th>Latency</th><th>Transaction</th></tr></thead><tbody>{transactions.slice(0,100).map(item => <tr key={item.operation_id}><td>{formatTime(item.observed_at)}</td><td>{item.operation_type}</td><td>{item.operation_class}</td><td>{item.committed ? 'Committed' : item.success ? 'Read' : 'Rejected'}</td><td>{item.active_endpoint}</td><td>{item.latency_ms.toFixed(2)} ms</td><td className="mono">{item.transaction_ref ?? '—'}</td></tr>)}</tbody></table></div></section>
    <section className="panel replay-data-panel" id="performance"><div className="panel-header"><div><h2>Recorded performance observations</h2><p>Actual workload completion summaries; single local runs</p></div><span>MEASURED</span></div><div className="performance-grid">{workloadRuns.map((run,index) => <article key={`${run.profile}-${index}`}><span>{run.profile.replaceAll('_',' ')}</span><strong>{run.operations_per_second.toFixed(3)} ops/s</strong><div className="latency-bars"><i style={{width:`${Math.min(100,(run.p50_latency_ms ?? 0)*2)}%`}}/><i style={{width:`${Math.min(100,(run.p95_latency_ms ?? 0)*2)}%`}}/><i style={{width:`${Math.min(100,(run.p99_latency_ms ?? 0)*2)}%`}}/></div><small>P50/P95/P99 {run.p50_latency_ms}/{run.p95_latency_ms}/{run.p99_latency_ms} ms · {run.committed_transactions} commits</small></article>)}</div></section>
    <section className="replay-grid" id="report"><div className="panel"><div className="panel-header"><div><h2>Validation report</h2><p>Full and final-quiesced comparisons</p></div></div><div className="report-list">{data.validations.map(item => <div key={item.validation_run_id}><span>{item.scope.replaceAll('_',' ')}</span><strong className={statusClass(item.status)}>{item.status}</strong><small>{item.rows_checked.toLocaleString()} rows · {item.mismatches} mismatches</small></div>)}</div></div><div className="panel"><div className="panel-header"><div><h2>Failure and recovery</h2><p>Bounded target interruption experiment</p></div></div>{latestIncident ? <div className="incident-card"><strong>{latestIncident.severity} · {latestIncident.affected_resources.join(', ')}</strong><p>{latestIncident.symptoms}</p><dl><dt>Recovery</dt><dd>{latestIncident.recovery_duration_ms} ms</dd><dt>Result</dt><dd>{latestIncident.recovery_result}</dd><dt>Remaining risk</dt><dd>{latestIncident.remaining_risk}</dd></dl></div> : <p className="empty-inspector">No recorded incident.</p>}</div></section>
    <section className="panel replay-footer"><div><strong>Final migration report</strong><p>{finalValidation?.rows_checked.toLocaleString()} rows final-validated · {data.cutover.stages.length} cutover stages · route {data.route.active_endpoint}</p></div><div><strong>Backup evidence</strong><p>{data.backups.filter(item => item.verification_status === 'VERIFIED').length} verified logical archive · subscription-free restore verification</p></div><Link to="/">Return to CloudShift DB</Link></section>
  </main>
}

const practicals = [
  ['01', 'Normalization and denormalization', '13-table commerce schema', '1NF–BCNF reasoning plus normalized and materialized aggregate plans.'],
  ['02', 'ACID and isolation', '512.65 ms lock wait', 'Rollback, constraints, durability, snapshots, serialization failure, and row locking.'],
  ['03', 'Query optimization', '100,000-row probe', 'Sequential scan compared with B-tree, hash, and composite index paths.'],
  ['04', 'Distributed sharding', '3 physical PostgreSQL shards', 'NORTH, SOUTH, and WEST partitions with enforced region placement.'],
  ['05', 'Distributed query processing', '3,000 rows merged', 'Identical partial aggregates; 175.241 ms sequential and 67.808 ms parallel in one trial.'],
  ['06', 'Redis key-value operations', 'CRUD and TTL verified', 'Authenticated SET, GET, update, expiry inspection, and deletion.'],
  ['07', 'MongoDB document queries', '3 diagnostic documents', 'Nested filters, severity grouping, and recovery-time aggregation.'],
  ['08', 'Authoritative caching', 'Miss → fill → hit → invalidate', 'PostgreSQL remains authoritative while a bounded Redis route cache is exercised.'],
  ['09', 'Time-series analysis', '6 instant queries + 1 range', 'Prometheus counters, gauges, rates, health, WAL lag, and validation duration.'],
  ['10', 'Graph dependency analysis', '9 nodes · 12 relationships', 'Neo4j traversal, impact analysis, and the source-to-target migration path.'],
]

function DatabaseLab() {
  return <main className="lab-shell"><header><div><p className="eyebrow">ADVANCED DATABASE MANAGEMENT SYSTEMS</p><h1>Database Engineering Lab</h1><p>Ten executable, evidence-backed experiments kept separate from the production migration workflow.</p></div><Link to="/">CloudShift DB</Link></header><div className="lab-boundary">LOCAL SYNTHETIC OBSERVATIONS · NOT PRODUCTION BENCHMARKS</div><section className="lab-grid">{practicals.map(([number,title,result,description]) => <article key={number}><span>{number}</span><div><h2>{title}</h2><strong>{result}</strong><p>{description}</p></div></article>)}</section><section className="panel lab-footer"><div><strong>Reproducible evidence</strong><p>Commands, theory, SQL/query detail, observed output, limitations, and reset behavior are documented in <code>docs/dbms-lab.md</code>.</p></div><Link to="/replay">Launch migration replay</Link></section></main>
}

function Layout({ children }: { children: React.ReactNode }) {
  return (
    <div className="shell">
      <header className="global-header">
        <div className="brand-mark">CS</div>
        <strong>CloudShift DB</strong>
        <span className="header-divider" />
        <span>Parth Garg — Cloud Engineering Lab</span>
        <span className="header-spacer" />
        <span className="mode">LIVE LOCAL ENVIRONMENT</span>
      </header>
      <aside className="sidebar">
        <p className="nav-label">OPERATIONS</p>
        <Link to="/console/migration-command-center" className="nav-active">Migration Command Center</Link>
        <a href="/api/docs" target="_blank" rel="noreferrer">API documentation</a>
        <p className="nav-label">ENVIRONMENT</p>
        <span>Source database</span><span>Target database</span><span>Control database</span>
      </aside>
      <div className="content">{children}</div>
    </div>
  )
}

function ResourceNode({ data }: { data: Resource }) {
  return (
    <div className={`resource-node ${data.health === 'AVAILABLE' ? 'healthy' : ''}`}>
      <Handle type="target" position={Position.Left}/>
      <button type="button" aria-label={`Inspect ${data.name}`} className="resource-node-content">
        <span className="node-type">{data.type.replace('_', ' ')}</span>
        <strong>{data.name}</strong>
        <span>{data.state ?? data.health}</span>
      </button>
      <Handle type="source" position={Position.Right}/>
    </div>
  )
}

function WorkloadPanel() {
  const queryClient = useQueryClient()
  const workload = useQuery({ queryKey: ['workload'], queryFn: api.workload })
  const probe = useQuery({ queryKey: ['probe'], queryFn: api.probe })
  const [token, setToken] = useState('')
  const [profile, setProfile] = useState('BALANCED')
  const [rate, setRate] = useState(5)
  const mutation = useMutation<unknown, Error, { kind: 'workload' | 'probe'; action: string; body?: unknown }>({
    mutationFn: ({ kind, action, body }: { kind: 'workload' | 'probe'; action: string; body?: unknown }) =>
      kind === 'workload' ? api.workloadAction(action, token, body) : api.probeAction(action, token, body),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['workload'] }); queryClient.invalidateQueries({ queryKey: ['probe'] }) },
  })
  const state = workload.data?.state ?? 'STOPPED'
  return <section className="panel workload-panel">
    <div className="panel-header"><div><h2>Workload and availability controls</h2><p>Actual commerce requests; configured rate is distinct from measured throughput.</p></div><span className={statusClass(state === 'RUNNING' ? 'AVAILABLE' : state)}>{state}</span></div>
    <div className="control-row">
      <label>Profile<select value={profile} onChange={event => setProfile(event.target.value)}>{['READ_HEAVY','WRITE_HEAVY','BALANCED','BURST','IDLE'].map(value => <option key={value}>{value}</option>)}</select></label>
      <label>Operations/s<select value={rate} onChange={event => setRate(Number(event.target.value))}>{[5,10,25,50].map(value => <option key={value}>{value}</option>)}</select></label>
      <label className="token-field">Local operator token<input type="password" value={token} onChange={event => setToken(event.target.value)} placeholder="Not stored in the build"/></label>
      <button disabled={!token || state !== 'STOPPED' || mutation.isPending} onClick={() => mutation.mutate({ kind:'workload', action:'start', body:{ profile, rate } })}>Start</button>
      <button disabled={!token || state !== 'RUNNING' || mutation.isPending} onClick={() => mutation.mutate({ kind:'workload', action:'pause' })}>Pause</button>
      <button disabled={!token || state !== 'PAUSED' || mutation.isPending} onClick={() => mutation.mutate({ kind:'workload', action:'resume' })}>Resume</button>
      <button disabled={!token || !['RUNNING','PAUSED'].includes(state) || mutation.isPending} onClick={() => mutation.mutate({ kind:'workload', action:'stop' })}>Stop</button>
      <button disabled={!token || probe.data?.state === 'RUNNING' || mutation.isPending} onClick={() => mutation.mutate({ kind:'probe', action:'start', body:{sample_interval_ms:250,write_interval_ms:1000} })}>Start probe</button>
      <button disabled={!token || probe.data?.state !== 'RUNNING' || mutation.isPending} onClick={() => mutation.mutate({ kind:'probe', action:'stop' })}>Stop probe</button>
    </div>
    {mutation.isError && <div className="error-inline">{(mutation.error as Error).message}</div>}
    <div className="workload-metrics">
      <div><span>Measured operations/s</span><strong>{workload.data?.operations_per_second?.toFixed(2) ?? 'Unavailable'}</strong></div>
      <div><span>Committed tx/s</span><strong>{workload.data?.transactions_per_second?.toFixed(2) ?? 'Unavailable'}</strong></div>
      <div><span>P50 / P95 / P99</span><strong>{workload.data?.p50_latency_ms?.toFixed(1) ?? '—'} / {workload.data?.p95_latency_ms?.toFixed(1) ?? '—'} / {workload.data?.p99_latency_ms?.toFixed(1) ?? '—'} ms</strong></div>
      <div><span>Success / failure</span><strong>{workload.data?.successful_operations ?? 0} / {workload.data?.failed_operations ?? 0}</strong></div>
      <div><span>Active route</span><strong>{workload.data?.active_database ?? 'Unavailable'}</strong></div>
      <div><span>Probe observations</span><strong>{probe.data?.observations ?? 0}</strong><small>{probe.data?.sample_interval_ms ? `${probe.data.sample_interval_ms} ms precision` : 'Not running'}</small></div>
    </div>
  </section>
}

function HistoricalCharts() {
  const operations = useQuery({ queryKey: ['chart','operations'], queryFn: () => api.prometheusRange('sum(rate(cloudshift_workload_operations_total[1m]))'), refetchInterval: 15000 })
  const lag = useQuery({ queryKey: ['chart','lag'], queryFn: () => api.prometheusRange('cloudshift_replication_wal_byte_lag'), refetchInterval: 15000 })
  const render = (points: {timestamp:number;value:number}[] | undefined, unit: string) => points?.length ? <ResponsiveContainer width="100%" height={190}><LineChart data={points}><CartesianGrid strokeDasharray="3 3"/><XAxis dataKey="timestamp" tickFormatter={value => new Date(value*1000).toLocaleTimeString()} minTickGap={30}/><YAxis/><Tooltip labelFormatter={value => new Date(Number(value)*1000).toLocaleString()} formatter={value => [`${Number(value).toFixed(2)} ${unit}`]}/><Line type="monotone" dataKey="value" stroke="#1f5f9f" dot={false} isAnimationActive={false}/></LineChart></ResponsiveContainer> : <div className="chart-empty">No historical series is available. Start the observability profile and workload to collect samples.</div>
  return <section className="panel charts-panel"><div className="panel-header"><div><h2>Historical performance</h2><p>Actual Prometheus samples · last 15 minutes · 15-second step</p></div><span>{operations.isError || lag.isError ? 'Prometheus unavailable' : 'MEASURED'}</span></div><div className="chart-grid"><div><h3>Workload operation rate</h3>{render(operations.data,'ops/s')}</div><div><h3>Retained WAL byte lag</h3>{render(lag.data,'bytes')}</div></div></section>
}

function TransactionInspector() {
  const operations = useQuery({ queryKey: ['workload-operations'], queryFn: api.workloadOperations })
  const [search, setSearch] = useState('')
  const rows = (operations.data ?? []).filter(row => !search || `${row.operation_type} ${row.transaction_ref ?? ''} ${row.active_endpoint ?? ''}`.toLowerCase().includes(search.toLowerCase()))
  return <section className="panel transaction-panel"><div className="panel-header"><div><h2>Transaction inspector</h2><p>Application-instrumented workload operations; not direct WAL row decoding.</p></div><input aria-label="Filter transactions" value={search} onChange={event => setSearch(event.target.value)} placeholder="Filter operation or transaction"/></div><div className="table-scroll"><table><thead><tr><th>Observed</th><th>Operation</th><th>Class</th><th>Commit</th><th>Route</th><th>Latency</th><th>Transaction</th><th>Error</th></tr></thead><tbody>{rows.map(row => <tr key={row.operation_id}><td>{formatTime(row.observed_at)}</td><td>{row.operation_type}</td><td>{row.operation_class}</td><td><span className={statusClass(row.success ? 'AVAILABLE' : 'FAILED')}>{row.committed ? 'Committed' : row.success ? 'Read' : 'Failed'}</span></td><td>{row.active_endpoint ?? 'Unavailable'}</td><td>{Number(row.latency_ms).toFixed(2)} ms</td><td className="mono">{row.transaction_ref ?? '—'}</td><td>{row.error_class ?? '—'}</td></tr>)}</tbody></table></div></section>
}

const nodeTypes = { resource: ResourceNode }

function graphEdge(connection: Connection, reducedMotion: boolean): Edge {
  const colors = { APPLICATION: '#1d4ed8', REPLICATION: '#0f766e', VALIDATION: '#7c3aed' }
  return {
    id: connection.id, source: connection.source, target: connection.target,
    type: 'smoothstep', animated: connection.active && !reducedMotion,
    markerEnd: { type: MarkerType.ArrowClosed, color: colors[connection.category] },
    style: {
      stroke: connection.active ? colors[connection.category] : '#a8b2c1',
      strokeWidth: connection.active ? 2.5 : 1.2,
      strokeDasharray: connection.active ? undefined : '5 5',
      opacity: connection.active ? 1 : 0.55,
    },
    label: connection.active ? connection.category.toLowerCase() : undefined,
  }
}

function CommandCenter() {
  const [selected, setSelected] = useState<Resource | null>(null)
  const [reducedMotion, setReducedMotion] = useState(false)
  const topology = useQuery({ queryKey: ['topology'], queryFn: api.topology })
  const tables = useQuery({ queryKey: ['tables'], queryFn: api.tables })
  const events = useQuery({ queryKey: ['events'], queryFn: api.events })
  const validations = useQuery({ queryKey: ['validations'], queryFn: api.validations })

  const nodes = useMemo<Node[]>(() => (topology.data?.resources ?? []).map((resource) => ({
    id: resource.id, type: 'resource', data: resource,
    position: positions[resource.id] ?? { x: 455, y: 420 },
    sourcePosition: Position.Right, targetPosition: Position.Left,
  })), [topology.data])
  const edges = useMemo(() => (topology.data?.connections ?? []).map((edge) => graphEdge(edge, reducedMotion)), [topology.data, reducedMotion])

  if (topology.isError) return <Layout><div className="error-state">Control plane unavailable: {(topology.error as Error).message}</div></Layout>
  if (!topology.data) return <Layout><div className="loading">Loading observed infrastructure…</div></Layout>
  const data = topology.data
  const latestValidation = validations.data?.[0]
  const lag = data.replication.slot?.wal_byte_lag

  return (
    <Layout>
      <section className="page-header">
        <div><p className="breadcrumb">Migration tasks / {data.task_key}</p><h1>Live Migration Command Center</h1></div>
        <div className="observed">Last observed<br/><strong>{formatTime(data.observed_at)}</strong></div>
      </section>
      <section className="task-strip">
        <span className={statusClass(data.state)}>{data.state.replaceAll('_', ' ')}</span>
        <span>parth-source-dc01 → parth-cloud-region01</span>
        <span>Route: <strong>{data.route.active_endpoint}</strong></span>
        <span>Writes: <strong>{data.route.writes_enabled ? 'enabled' : 'fenced'}</strong></span>
      </section>
      <section className="toolbar" aria-label="Migration operations">
        {['Assess', 'Start', 'Pause', 'Resume', 'Validate', 'Prepare cutover', 'Execute cutover'].map(action => (
          <button key={action} disabled title="Migration is completed; lifecycle prevents this operation.">{action}</button>
        ))}
        <span className="toolbar-note">Controls are disabled by the completed lifecycle state.</span>
      </section>
      <section className="metric-grid">
        <article><span>Migration state</span><strong>{data.state.replaceAll('_', ' ')}</strong><small>Durable control metadata</small></article>
        <article><span>Table synchronization</span><strong>{data.replication.ready_tables} / {data.replication.total_tables}</strong><small>Observed PostgreSQL relation states</small></article>
        <article><span>Replication worker</span><strong>{data.replication.subscription?.worker_active ? 'Active' : 'Stopped'}</strong><small>Stopped after verified cutover</small></article>
        <article><span>WAL byte lag</span><strong>{lag === undefined ? 'Unavailable' : formatBytes(lag)}</strong><small>Measured; slot retained after shutdown</small></article>
        <article><span>Final validation</span><strong>{latestValidation?.status ?? 'Unavailable'}</strong><small>{latestValidation ? `${latestValidation.rows_checked.toLocaleString()} rows checked` : 'No observation'}</small></article>
        <article><span>Active database</span><strong>{data.route.active_endpoint}</strong><small>Route version {data.route.version}</small></article>
      </section>
      <WorkloadPanel/>
      <section className="workspace-grid">
        <div className="panel topology-panel">
          <div className="panel-header"><div><h2>Migration topology</h2><p>Observed activity, not packet-level inspection</p></div><label><input type="checkbox" checked={reducedMotion} onChange={event => setReducedMotion(event.target.checked)} /> Reduced motion</label></div>
          <div className="topology-canvas">
            <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} fitView minZoom={0.5} maxZoom={1.8} onNodeClick={(_, node) => setSelected(node.data as Resource)}>
              <Background color="#d8dee8" gap={20}/><MiniMap pannable zoomable/><Controls/>
            </ReactFlow>
          </div>
          <div className="legend"><span className="app-line">Application route</span><span className="rep-line">Logical replication</span><span className="val-line">Validation path</span><span className="inactive-line">Inactive</span></div>
        </div>
        <aside className="panel inspector">
          <div className="panel-header"><div><h2>Resource inspector</h2><p>Select a topology node</p></div></div>
          {selected ? <dl>
            <dt>Resource</dt><dd>{selected.name}</dd><dt>Type</dt><dd>{selected.type}</dd>
            <dt>Health</dt><dd><span className={statusClass(selected.health)}>{selected.health}</span></dd>
            <dt>Operational state</dt><dd>{selected.state ?? 'Observed available'}</dd>
            <dt>Version</dt><dd>{selected.version ?? 'Not applicable'}</dd>
            <dt>Last observation</dt><dd>{formatTime(selected.last_observed ?? data.observed_at)}</dd>
          </dl> : <div className="empty-inspector">Choose a database, worker, application, or control-plane resource to inspect current state.</div>}
        </aside>
      </section>
      <section className="panel table-panel">
        <div className="panel-header"><div><h2>Table migration tracker</h2><p>PostgreSQL estimates are labeled; validation results are exact.</p></div><span>{tables.data?.length ?? 0} tables</span></div>
        {tables.isError ? <div className="error-inline">Table observations unavailable.</div> : <div className="table-scroll"><table><thead><tr><th>Table</th><th>Source estimate</th><th>Target estimate</th><th>Source size</th><th>Sync state</th><th>Validation</th><th>Mismatches</th></tr></thead><tbody>
          {(tables.data ?? []).map(table => <tr key={table.table}><td><strong>{table.table}</strong><small>{table.schema}</small></td><td>{table.source_row_estimate?.toLocaleString() ?? 'Unavailable'}<small>estimated</small></td><td>{table.target_row_estimate?.toLocaleString() ?? 'Unavailable'}<small>estimated</small></td><td>{formatBytes(table.source_bytes)}</td><td>{table.subscription_state === 'r' ? 'Ready' : table.subscription_state ?? 'Unavailable'}</td><td><span className={statusClass(table.validation?.status ?? '')}>{table.validation?.status ?? 'Unavailable'}</span></td><td>{table.validation ? table.validation.missing_rows + table.validation.extra_rows + table.validation.mismatched_rows : '—'}</td></tr>)}
        </tbody></table></div>}
      </section>
      <TransactionInspector/>
      <HistoricalCharts/>
      <section className="lower-grid">
        <div className="panel timeline"><div className="panel-header"><div><h2>Migration event timeline</h2><p>Durable events emitted by completed operations</p></div></div>
          <ol>{(events.data ?? []).map(event => <li key={event.event_id}><time>{formatTime(event.occurred_at)}</time><div><strong>{event.event_type.replaceAll('_', ' ')}</strong><p>{event.message}</p><small>{event.component} · {event.severity}</small></div></li>)}</ol>
        </div>
        <div className="panel terminal"><div className="panel-header"><div><h2>Operational event log</h2><p>Structured control-plane events; no shell access</p></div></div>
          <div className="log-view">{(events.data ?? []).slice(0, 30).map(event => <div key={event.event_id}><time>{new Date(event.occurred_at).toISOString()}</time><span className={`severity ${event.severity.toLowerCase()}`}>{event.severity}</span><span>{event.component}</span><p>{event.message}</p></div>)}</div>
        </div>
      </section>
    </Layout>
  )
}

export default function App() {
  const platform = <Suspense fallback={<main className="cloud-loading">Loading CloudShift operations workspace…</main>}><CloudPlatform/></Suspense>
  return <Routes><Route path="/" element={<Landing/>}/><Route path="/replay" element={<Replay/>}/><Route path="/database-engineering-lab" element={<DatabaseLab/>}/><Route path="/console/migration-command-center" element={<CommandCenter/>}/><Route path="/platform" element={platform}/><Route path="/migration-studio/*" element={platform}/><Route path="/infrastructure/*" element={platform}/><Route path="/operations/*" element={platform}/><Route path="/optimization/*" element={platform}/><Route path="/documentation/*" element={platform}/><Route path="*" element={<Navigate to="/" replace/>}/></Routes>
}
