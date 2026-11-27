import { useEffect, useMemo, useReducer, useState } from 'react'
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom'
import ReactFlow, { Background, Controls, Edge, MarkerType, MiniMap, Node } from 'reactflow'
import {
  applyScenario, assessMigration, createSimulation, defaultConfig, downloadText, estimateCost, formatDuration,
  generateKubernetes, generateTerraform, providerRegions, providerResources, scenarios, simulationReducer,
  theoreticalTransferSeconds, walGenerationMBps,
} from './domain'
import type { AssessmentCheck, CloudProvider, MigrationConfig, OperatingMode, UnitRates } from './domain'

const configKey = 'cloudshift-v1.1-migration-plan'
const modeKey = 'cloudshift-v1.1-operating-mode'

function loadConfig(): MigrationConfig {
  try { return { ...defaultConfig, ...JSON.parse(localStorage.getItem(configKey) ?? '{}') as Partial<MigrationConfig> } } catch { return defaultConfig }
}

function usePersistentConfig() {
  const [config, setConfigState] = useState<MigrationConfig>(loadConfig)
  const setConfig = (next: MigrationConfig | ((current: MigrationConfig) => MigrationConfig)) => setConfigState(current => {
    const value = typeof next === 'function' ? next(current) : next
    localStorage.setItem(configKey, JSON.stringify(value))
    return value
  })
  return [config, setConfig] as const
}

const routeForMode: Record<OperatingMode, string> = { SANDBOX: '/migration-studio/sandbox', REPLAY: '/replay', LIVE: '/console/migration-command-center' }

function normalizedPath(pathname: string) {
  return pathname.length > 1 ? pathname.replace(/\/+$/, '') : pathname
}

function ModeSelector() {
  const navigate = useNavigate()
  const location = useLocation()
  const path = normalizedPath(location.pathname)
  const inferred: OperatingMode = path === '/replay' ? 'REPLAY' : path.startsWith('/console/') ? 'LIVE' : 'SANDBOX'
  const [mode, setMode] = useState<OperatingMode>(() => (localStorage.getItem(modeKey) as OperatingMode | null) ?? inferred)
  const select = (next: OperatingMode) => { setMode(next); localStorage.setItem(modeKey, next); navigate(routeForMode[next]) }
  return <div className="mode-selector" aria-label="Operating mode">
    <button className={mode === 'SANDBOX' ? 'active' : ''} onClick={() => select('SANDBOX')}><span>Mode A</span>Interactive sandbox</button>
    <button className={mode === 'REPLAY' ? 'active' : ''} onClick={() => select('REPLAY')}><span>Mode B</span>Verified replay</button>
    <button className={mode === 'LIVE' ? 'active' : ''} onClick={() => select('LIVE')}><span>Mode C</span>Live local</button>
  </div>
}

const navGroups = [
  ['OVERVIEW', [['Platform overview', '/platform']]],
  ['MIGRATION STUDIO', [['Migration planner', '/migration-studio/planner'], ['Cloud sandbox', '/migration-studio/sandbox'], ['Migration command center', '/migration-studio/command-center'], ['Verified replay', '/replay'], ['Validation and cutover', '/optimization/feasibility']]],
  ['INFRASTRUCTURE', [['Cloud architecture builder', '/infrastructure/builder'], ['Network and security', '/infrastructure/network'], ['Terraform generator', '/infrastructure/terraform'], ['Kubernetes explorer', '/infrastructure/kubernetes']]],
  ['OPERATIONS', [['Observability and SRE', '/operations/reliability'], ['Disaster recovery', '/operations/disaster-recovery'], ['Incident scenarios', '/operations/incidents']]],
  ['OPTIMIZATION', [['Cost estimator', '/optimization/cost'], ['Migration comparison', '/optimization/comparison'], ['Feasibility assessment', '/optimization/feasibility']]],
  ['DATABASE ENGINEERING', [['Ten DBMS practicals', '/database-engineering-lab']]],
  ['DOCUMENTATION', [['Architecture', '/documentation/architecture'], ['Engineering evidence', 'https://github.com/gargparth2003/cloudshift-db/blob/main/docs/verification-matrix.md'], ['GitHub repository', 'https://github.com/gargparth2003/cloudshift-db']]],
] as const

function EnterpriseShell({ children, label = 'SIMULATED' }: { children: React.ReactNode; label?: 'SIMULATED' | 'ESTIMATED' | 'RECORDED' | 'MEASURED LIVE' }) {
  return <div className="enterprise-shell">
    <header className="enterprise-header"><Link to="/platform" className="enterprise-brand"><b>CS</b><span>CloudShift DB<small>Migration & Operations Platform</small></span></Link><ModeSelector/><span className={`truth-label ${label.toLowerCase().replace(' ', '-')}`}>{label}</span></header>
    <aside className="enterprise-sidebar">{navGroups.map(([group, links]) => <div key={group}><p>{group}</p>{links.map(([name, href]) => href.startsWith('http') ? <a key={href} href={href} target="_blank" rel="noreferrer">{name}</a> : <NavLink key={href} to={href} className={({ isActive }) => isActive ? 'active' : ''}>{name}</NavLink>)}</div>)}</aside>
    <main className="enterprise-workspace">{children}</main>
  </div>
}

function PageHeader({ eyebrow, title, description, actions }: { eyebrow: string; title: string; description: string; actions?: React.ReactNode }) {
  return <header className="cloud-page-header"><div><p>{eyebrow}</p><h1>{title}</h1><span>{description}</span></div>{actions}</header>
}

function TruthNotice({ children }: { children: React.ReactNode }) { return <div className="truth-notice"><strong>SIMULATION BOUNDARY</strong><span>{children}</span></div> }

function update<K extends keyof MigrationConfig>(setConfig: (next: (current: MigrationConfig) => MigrationConfig) => void, key: K, value: MigrationConfig[K]) {
  setConfig(current => ({ ...current, [key]: value }))
}

function NumberInput({ label, value, onChange, min = 0, step = 1 }: { label: string; value: number; onChange: (value: number) => void; min?: number; step?: number }) {
  return <label className="field"><span>{label}</span><input type="number" min={min} step={step} value={value} onChange={event => onChange(Number(event.target.value))}/></label>
}

function SelectInput({ label, value, options, onChange }: { label: string; value: string; options: Array<[string, string]>; onChange: (value: string) => void }) {
  return <label className="field"><span>{label}</span><select value={value} onChange={event => onChange(event.target.value)}>{options.map(([key, text]) => <option key={key} value={key}>{text}</option>)}</select></label>
}

function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (checked: boolean) => void }) {
  return <label className="toggle"><input type="checkbox" checked={checked} onChange={event => onChange(event.target.checked)}/><span>{label}</span></label>
}

function ScenarioPicker({ config, setConfig, onLoaded }: { config: MigrationConfig; setConfig: (value: MigrationConfig | ((current: MigrationConfig) => MigrationConfig)) => void; onLoaded?: (key: string) => void }) {
  return <div className="scenario-strip">{Object.entries(scenarios).map(([key, scenario]) => <button key={key} onClick={() => { setConfig(applyScenario(key)); onLoaded?.(key) }} className={config.name === key.replaceAll('_', '-') ? 'selected' : ''}><strong>{scenario.title}</strong><span>{scenario.description}</span></button>)}</div>
}

function Overview({ config, setConfig }: PlatformProps) {
  const checks = assessMigration(config)
  const failures = checks.filter(item => item.status === 'FAIL').length
  return <EnterpriseShell><PageHeader eyebrow="CLOUDSHIFT DB v1.1.0" title="Plan, simulate, and inspect a cloud database migration" description="A browser-local engineering workspace plus preserved recorded PostgreSQL evidence and an isolated live-local mode." actions={<Link className="cloud-primary" to="/migration-studio/planner">Start guided plan</Link>}/>
    <TruthNotice>No credentials are collected. Sandbox values are modeled locally; replay values are recorded evidence; live values come only from locally deployed services.</TruthNotice>
    <section className="operating-mode-grid"><article><span>MODE A · SIMULATED</span><h2>Interactive cloud sandbox</h2><p>Configure network, capacity, security, cost inputs, and deterministic failure scenarios.</p><Link to="/migration-studio/sandbox">Open sandbox</Link></article><article><span>MODE B · RECORDED</span><h2>Verified migration replay</h2><p>Inspect the preserved 13-table local PostgreSQL migration and its measured evidence.</p><Link to="/replay">Open replay</Link></article><article><span>MODE C · MEASURED LIVE</span><h2>Live local infrastructure</h2><p>Connect to the Docker-isolated control plane; privileged controls never appear on the public build.</p><Link to="/console/migration-command-center">Open local console</Link></article></section>
    <section className="overview-grid"><div className="workspace-panel"><div className="section-heading"><div><p>ACTIVE PLAN</p><h2>{config.name}</h2></div><span className={failures ? 'pill fail' : 'pill pass'}>{failures ? `${failures} blockers` : 'preflight clear'}</span></div><dl className="summary-list"><dt>Route</dt><dd>{config.source.replaceAll('_', ' ')} → {providerResources[config.provider].database}</dd><dt>Region</dt><dd>{config.region}</dd><dt>Data</dt><dd>{config.databaseSizeGB} GB · {config.tableCount} tables · {config.estimatedRows.toLocaleString()} rows</dd><dt>Strategy</dt><dd>{config.strategy.replaceAll('_', ' ')}</dd><dt>Theoretical transfer</dt><dd>{formatDuration(theoreticalTransferSeconds(config))}</dd></dl></div><div className="workspace-panel recruiter-path"><div className="section-heading"><div><p>THREE-MINUTE RECRUITER PATH</p><h2>See the engineering decisions respond</h2></div></div><ol><li>Load a constrained or overloaded scenario.</li><li>Run the migration and interrupt its network.</li><li>Inspect the blocker, restore capacity, validate, and cut over.</li><li>Export the plan and secure AWS Terraform files.</li></ol></div></section>
    <h2 className="section-title">Scenario templates</h2><ScenarioPicker config={config} setConfig={setConfig}/>
  </EnterpriseShell>
}

const wizardSteps = ['Source environment', 'Destination cloud', 'Destination region', 'Database configuration', 'Network configuration', 'Migration strategy', 'Availability requirements', 'Security configuration', 'Preflight assessment', 'Review and generate plan']

function MigrationPlanner({ config, setConfig }: PlatformProps) {
  const [step, setStep] = useState(0)
  const checks = assessMigration(config)
  const fields = (() => {
    if (step === 0) return <SelectInput label="Source environment" value={config.source} onChange={value => update(setConfig, 'source', value as MigrationConfig['source'])} options={[['LOCAL_POSTGRESQL','Local PostgreSQL'],['ON_PREMISES_POSTGRESQL','On-premises PostgreSQL'],['EC2_POSTGRESQL','Self-managed PostgreSQL on EC2'],['RDS_POSTGRESQL','Amazon RDS PostgreSQL'],['AZURE_POSTGRESQL','Azure PostgreSQL'],['CLOUD_SQL_POSTGRESQL','Google Cloud SQL PostgreSQL']]}/>
    if (step === 1) return <SelectInput label="Destination provider" value={config.provider} onChange={value => { const provider = value as CloudProvider; setConfig(current => ({ ...current, provider, region: providerRegions[provider][0].code })) }} options={[['AWS','Amazon Web Services'],['AZURE','Microsoft Azure'],['GCP','Google Cloud Platform']]}/>
    if (step === 2) return <SelectInput label="Destination region" value={config.region} onChange={value => update(setConfig, 'region', value)} options={providerRegions[config.provider].map(region => [region.code, `${region.name} · ${region.zones} zones`])}/>
    if (step === 3) return <div className="form-grid"><SelectInput label="PostgreSQL version" value={config.postgresVersion} onChange={value => update(setConfig, 'postgresVersion', value)} options={['13','14','15','16','17'].map(value => [value, `PostgreSQL ${value}`])}/><NumberInput label="Database size (GB)" value={config.databaseSizeGB} onChange={value => update(setConfig, 'databaseSizeGB', value)}/><NumberInput label="Tables" value={config.tableCount} onChange={value => update(setConfig, 'tableCount', value)}/><NumberInput label="Estimated rows" value={config.estimatedRows} onChange={value => update(setConfig, 'estimatedRows', value)}/><NumberInput label="Transactions/second" value={config.transactionsPerSecond} onChange={value => update(setConfig, 'transactionsPerSecond', value)}/><NumberInput label="Average transaction (KB)" value={config.averageTransactionKB} onChange={value => update(setConfig, 'averageTransactionKB', value)} step={0.5}/><NumberInput label="Concurrent connections" value={config.concurrentConnections} onChange={value => update(setConfig, 'concurrentConnections', value)}/><NumberInput label="Annual growth (%)" value={config.annualGrowthPercent} onChange={value => update(setConfig, 'annualGrowthPercent', value)}/></div>
    if (step === 4) return <div className="form-grid"><NumberInput label="Available bandwidth (Mbps)" value={config.bandwidthMbps} onChange={value => update(setConfig, 'bandwidthMbps', value)}/><NumberInput label="Effective utilization (%)" value={config.effectiveBandwidthPercent} onChange={value => update(setConfig, 'effectiveBandwidthPercent', Math.min(100, value))}/><NumberInput label="Estimated latency (ms)" value={config.latencyMs} onChange={value => update(setConfig, 'latencyMs', value)}/><SelectInput label="Connectivity" value={config.connectivity} onChange={value => update(setConfig, 'connectivity', value as MigrationConfig['connectivity'])} options={[['PRIVATE','Provider private connectivity'],['VPN','Site-to-site VPN'],['PEERING','VPC/VNet peering'],['PUBLIC_TLS','Public internet with TLS']]}/></div>
    if (step === 5) return <SelectInput label="Migration strategy" value={config.strategy} onChange={value => update(setConfig, 'strategy', value as MigrationConfig['strategy'])} options={[['OFFLINE','Offline dump and restore'],['ONLINE_CDC','Online initial copy with CDC'],['HOMOGENEOUS','Homogeneous PostgreSQL migration']]}/>
    if (step === 6) return <div className="form-grid"><SelectInput label="Availability" value={config.availability} onChange={value => update(setConfig, 'availability', value as MigrationConfig['availability'])} options={[['SINGLE_ZONE','Single-zone'],['MULTI_ZONE','Multi-zone design']]}/><NumberInput label="Backup retention (days)" value={config.backupRetentionDays} onChange={value => update(setConfig, 'backupRetentionDays', Math.min(35, value))}/><NumberInput label="RTO (minutes)" value={config.rtoMinutes} onChange={value => update(setConfig, 'rtoMinutes', value)}/><NumberInput label="RPO (minutes)" value={config.rpoMinutes} onChange={value => update(setConfig, 'rpoMinutes', value)}/><NumberInput label="Acceptable interruption (seconds)" value={config.acceptableInterruptionSeconds} onChange={value => update(setConfig, 'acceptableInterruptionSeconds', value)}/></div>
    if (step === 7) return <div className="toggle-grid"><Toggle label="Encryption at rest" checked={config.encryptionAtRest} onChange={value => update(setConfig, 'encryptionAtRest', value)}/><Toggle label="Require TLS" checked={config.tls} onChange={value => update(setConfig, 'tls', value)}/><Toggle label="Private database subnets" checked={config.privateSubnets} onChange={value => update(setConfig, 'privateSubnets', value)}/><Toggle label="Restricted database access" checked={config.restrictedDatabaseAccess} onChange={value => update(setConfig, 'restrictedDatabaseAccess', value)}/><Toggle label="Secrets manager design" checked={config.secretsManagement} onChange={value => update(setConfig, 'secretsManagement', value)}/><Toggle label="Least-privilege roles" checked={config.leastPrivilege} onChange={value => update(setConfig, 'leastPrivilege', value)}/></div>
    if (step === 8) return <AssessmentTable checks={checks}/>
    return <div className="review-plan"><pre>{JSON.stringify({ schemaVersion: 1, kind: 'cloudshift-migration-plan', generatedAt: new Date().toISOString(), classification: 'SIMULATED_ARCHITECTURE_PLAN', config, assessment: checks }, null, 2)}</pre><button className="cloud-primary" onClick={() => downloadText(`${config.name}.json`, JSON.stringify({ schemaVersion: 1, kind: 'cloudshift-migration-plan', config, assessment: checks }, null, 2), 'application/json')}>Download migration plan JSON</button></div>
  })()
  return <EnterpriseShell><PageHeader eyebrow="MIGRATION STUDIO" title="Cloud migration configuration wizard" description="Ten engineering steps produce a persistent, downloadable architecture plan—never cloud credentials."/>
    <div className="wizard-layout"><ol className="wizard-steps">{wizardSteps.map((name, index) => <li key={name} className={index === step ? 'active' : index < step ? 'complete' : ''}><button onClick={() => setStep(index)}><span>{index + 1}</span>{name}</button></li>)}</ol><section className="workspace-panel wizard-content"><div className="section-heading"><div><p>STEP {step + 1} OF 10</p><h2>{wizardSteps[step]}</h2></div><span className="truth-label estimated">PLANNING INPUT</span></div><div className="wizard-fields">{fields}</div><footer><button disabled={step === 0} onClick={() => setStep(current => current - 1)}>Previous</button><button className="cloud-primary" disabled={step === 9} onClick={() => setStep(current => current + 1)}>Continue</button></footer></section></div>
  </EnterpriseShell>
}

function AssessmentTable({ checks }: { checks: AssessmentCheck[] }) {
  return <div className="assessment-table"><div className="assessment-summary">{(['PASS','WARNING','FAIL','UNKNOWN'] as const).map(status => <span key={status} className={`pill ${status.toLowerCase()}`}>{checks.filter(item => item.status === status).length} {status}</span>)}</div>{checks.map(check => <details key={check.id} open={check.status === 'FAIL'}><summary><span className={`pill ${check.status.toLowerCase()}`}>{check.status}</span><strong>{check.title}</strong><small>{check.component}</small></summary><div><p><b>Finding:</b> {check.reason}</p><p><b>Consequence:</b> {check.consequence}</p><p><b>Remediation:</b> {check.remediation}</p></div></details>)}</div>
}

type PlatformProps = { config: MigrationConfig; setConfig: (value: MigrationConfig | ((current: MigrationConfig) => MigrationConfig)) => void }

function SimulationWorkspace({ config, initialScenario }: { config: MigrationConfig; initialScenario?: string }) {
  const [state, dispatch] = useReducer(simulationReducer, config, value => createSimulation(value))
  const [speed, setSpeed] = useState(1)
  useEffect(() => {
    if (state.status !== 'RUNNING') return
    const timer = window.setInterval(() => dispatch({ type: 'TICK', config, seconds: 10 * speed }), 500)
    return () => window.clearInterval(timer)
  }, [state.status, config, speed])
  useEffect(() => {
    const incident = initialScenario ? scenarios[initialScenario]?.incident : undefined
    if (incident === 'NETWORK_PARTITION') dispatch({ type: 'NETWORK', available: false })
    if (incident === 'VALIDATION_MISMATCH') dispatch({ type: 'MISMATCH', enabled: true })
    if (incident === 'WORKLOAD_SPIKE') dispatch({ type: 'WORKLOAD', multiplier: 2 })
  }, [initialScenario])
  const incoming = walGenerationMBps(config) * state.workloadMultiplier
  const cutoverReady = state.validationComplete && !state.mismatch && state.backlogMB <= .01 && state.snapshotRemainingMB <= .01
  return <div className="simulation-workspace">
    <div className="simulation-toolbar"><button disabled={state.status !== 'IDLE'} onClick={() => dispatch({ type: 'START' })}>Start</button><button disabled={state.status !== 'RUNNING'} onClick={() => dispatch({ type: 'PAUSE' })}>Pause</button><button disabled={state.status !== 'PAUSED'} onClick={() => dispatch({ type: 'RESUME' })}>Resume</button><button disabled={!['RUNNING','PAUSED'].includes(state.status)} onClick={() => dispatch({ type: 'CANCEL' })}>Cancel</button><button onClick={() => dispatch({ type: 'RESTART', config })}>Restart</button><label>Speed<select aria-label="Simulation speed" value={speed} onChange={event => setSpeed(Number(event.target.value))}><option value={0.5}>0.5×</option><option value={1}>1×</option><option value={4}>4×</option><option value={10}>10×</option></select></label><span className={`pill ${state.networkAvailable ? 'pass' : 'fail'}`}>{state.networkAvailable ? 'NETWORK AVAILABLE' : 'NETWORK PARTITION'}</span></div>
    <div className="simulation-metrics"><article><span>Phase</span><strong>{state.phase.replaceAll('_',' ')}</strong><small>{state.status}</small></article><article><span>Snapshot remaining</span><strong>{(state.snapshotRemainingMB / 1024).toFixed(2)} GB</strong><small>{(state.transferredMB / 1024).toFixed(2)} GB copied</small></article><article><span>CDC backlog</span><strong>{state.backlogMB.toFixed(2)} MB</strong><small>{incoming.toFixed(2)} MB/s incoming</small></article><article><span>Application route</span><strong>{state.applicationRoute}</strong><small>{cutoverReady ? 'ready for route switch' : 'cutover guarded'}</small></article><article><span>Integrity</span><strong>{state.mismatch ? 'MISMATCH' : state.validationComplete ? 'VALIDATED' : 'PENDING'}</strong><small>modeled validation state</small></article></div>
    <MigrationFlow state={state}/>
    <div className="scenario-controls"><div><h3>Traffic and capacity</h3><label>Workload <input aria-label="Workload multiplier" type="range" min="0.2" max="3" step="0.1" value={state.workloadMultiplier} onChange={event => dispatch({ type: 'WORKLOAD', multiplier: Number(event.target.value) })}/><b>{state.workloadMultiplier.toFixed(1)}×</b></label><label>Bandwidth <input aria-label="Bandwidth multiplier" type="range" min="0.1" max="2" step="0.1" value={state.bandwidthMultiplier} onChange={event => dispatch({ type: 'BANDWIDTH', multiplier: Number(event.target.value) })}/><b>{state.bandwidthMultiplier.toFixed(1)}×</b></label><label>Target apply <input aria-label="Apply capacity multiplier" type="range" min="0.2" max="3" step="0.1" value={state.applyMultiplier} onChange={event => dispatch({ type: 'APPLY', multiplier: Number(event.target.value) })}/><b>{state.applyMultiplier.toFixed(1)}×</b></label></div><div><h3>Controlled scenarios</h3><button onClick={() => dispatch({ type: 'NETWORK', available: false })}>Interrupt network</button><button onClick={() => dispatch({ type: 'NETWORK', available: true })}>Restore network</button><button onClick={() => dispatch({ type: 'MISMATCH', enabled: true })}>Inject validation mismatch</button><button onClick={() => dispatch({ type: 'MISMATCH', enabled: false })}>Repair mismatch</button><button onClick={() => dispatch({ type: 'VALIDATE' })}>Run validation</button><button className="cloud-primary" onClick={() => dispatch({ type: 'CUTOVER' })}>Execute modeled cutover</button></div></div>
    <section className="workspace-panel event-console"><div className="section-heading"><div><p>BOUNDED EVENT HISTORY</p><h2>Simulation decisions</h2></div><span>{state.events.length} / 120 retained</span></div>{state.events.length ? state.events.slice().reverse().map(item => <div key={item.id}><time>T+{item.elapsedSeconds}s</time><strong>{item.type.replaceAll('_',' ')}</strong><span>{item.message}</span></div>) : <p className="empty-copy">Start the scenario to generate deterministic events.</p>}</section>
  </div>
}

function MigrationFlow({ state }: { state: ReturnType<typeof createSimulation> }) {
  const nodes: Node[] = [
    { id:'app', position:{x:0,y:130}, data:{label:`Application\nroute: ${state.applicationRoute}`}},
    { id:'source', position:{x:220,y:40}, data:{label:'PostgreSQL source'}},
    { id:'worker', position:{x:450,y:130}, data:{label:`Migration worker\n${state.phase.replaceAll('_',' ')}`}},
    { id:'target', position:{x:690,y:40}, data:{label:'PostgreSQL target'}},
    { id:'validation', position:{x:690,y:220}, data:{label:`Validation\n${state.mismatch ? 'MISMATCH' : state.validationComplete ? 'PASS' : 'PENDING'}`}},
    { id:'backup', position:{x:920,y:130}, data:{label:'Encrypted backup'}},
  ]
  const active = state.status === 'RUNNING'
  const edges: Edge[] = [
    { id:'app-source',source:'app',target:'source',animated:active && state.applicationRoute==='SOURCE',label:'application traffic',style:{stroke:state.applicationRoute==='SOURCE'?'#38bdf8':'#64748b'}},
    { id:'source-worker',source:'source',target:'worker',animated:active&&state.networkAvailable,label:'snapshot + WAL',style:{stroke:state.networkAvailable?'#2dd4bf':'#dc2626',strokeDasharray:state.networkAvailable?undefined:'6 5'}},
    { id:'worker-target',source:'worker',target:'target',animated:active&&state.networkAvailable,label:'apply',style:{stroke:state.networkAvailable?'#2dd4bf':'#dc2626'}},
    { id:'target-validation',source:'target',target:'validation',animated:state.phase==='VALIDATION',label:'checksums',style:{stroke:'#a78bfa'}},
    { id:'app-target',source:'target',target:'app',animated:state.applicationRoute==='TARGET',label:'route switch',style:{stroke:state.applicationRoute==='TARGET'?'#38bdf8':'#64748b'}},
    { id:'target-backup',source:'target',target:'backup',animated:active,label:'backup',style:{stroke:'#f59e0b'}},
  ].map(edge => ({ ...edge, markerEnd:{type:MarkerType.ArrowClosed} }))
  return <section className="workspace-panel simulation-flow"><div className="section-heading"><div><p>LOGICAL MIGRATION TOPOLOGY</p><h2>Paths respond to modeled state</h2></div><div className="topology-legend"><span className="cyan">traffic</span><span className="teal">replication</span><span className="purple">validation</span><span className="red">interrupted</span></div></div><div><ReactFlow nodes={nodes} edges={edges} fitView nodesDraggable={false} nodesConnectable={false} minZoom={0.6} maxZoom={1.5}><Background gap={18}/><Controls/></ReactFlow></div></section>
}

function Sandbox({ config, setConfig }: PlatformProps) {
  const [scenario, setScenario] = useState<string>()
  return <EnterpriseShell><PageHeader eyebrow="MIGRATION STUDIO · MODE A" title="Interactive Cloud Migration Command Center" description="A deterministic browser engine—not a prerecorded animation and not a PostgreSQL benchmark." actions={<Link className="cloud-secondary" to="/migration-studio/planner">Edit plan</Link>}/><TruthNotice>All values on this page are SIMULATED from visible assumptions. No real cloud or database operation is performed.</TruthNotice><ScenarioPicker config={config} setConfig={setConfig} onLoaded={setScenario}/><SimulationWorkspace config={config} initialScenario={scenario}/></EnterpriseShell>
}

type ArchitectureNode = Node<{ label: string; type: string; provider: string; status: string; security: string; capacity: string; subnet: string; dependencies: string }>
function architectureFor(config: MigrationConfig): { nodes: ArchitectureNode[]; edges: Edge[] } {
  const r = providerResources[config.provider]
  const node = (id:string,x:number,y:number,label:string,type:string,subnet:string,dependencies:string):ArchitectureNode => ({ id,position:{x,y},data:{label,type,provider:config.provider,status:'PLANNED',security:type.includes('Database')?'private · TLS · encrypted':'least privilege',capacity:type.includes('Database')?`${config.storageCapacityGB} GB`:'modeled',subnet,dependencies},style:{borderLeft:`4px solid ${type.includes('Database')?'#14b8a6':'#3b82f6'}`}})
  const nodes = [node('vpc',20,30,r.network,'Network boundary',config.vpcCidr,'none'),node('app',250,30,r.compute,'Application compute',config.publicSubnetCidr,'load balancer, target'),node('worker',250,210,'Migration worker','Migration compute',config.privateSubnetCidrA,'source, target'),node('target',520,30,r.database,'Database target',config.privateSubnetCidrB,'worker, secrets'),node('storage',790,30,r.storage,'Backup storage','provider service','target'),node('monitor',520,210,r.monitoring,'Monitoring','provider service','application, worker, target'),node('secrets',790,210,r.secrets,'Secrets manager','provider service','application, worker')]
  const edges = [['vpc','app','contains'],['vpc','worker','contains'],['vpc','target','contains'],['app','target','5432 / TLS'],['worker','target','snapshot + CDC'],['target','storage','encrypted backup'],['monitor','target','metrics'],['secrets','worker','runtime secret']].map(([source,target,label],index) => ({id:`a${index}`,source,target,label,markerEnd:{type:MarkerType.ArrowClosed},style:{stroke:'#64748b'}}))
  return { nodes, edges }
}

function ArchitectureBuilder({ config, setConfig }: PlatformProps) {
  const initial = useMemo(() => architectureFor(config), [config])
  const [nodes, setNodes] = useState(initial.nodes)
  const [edges] = useState(initial.edges)
  const [selected, setSelected] = useState<ArchitectureNode['data'] | null>(null)
  const [view, setView] = useState('PHYSICAL')
  useEffect(() => { const next = architectureFor(config); setNodes(next.nodes); setSelected(null) }, [config])
  const addMonitoring = () => setNodes(current => current.some(item => item.id.startsWith('custom')) ? current : [...current, { id:'custom-monitor',position:{x:900,y:350},data:{label:'Additional monitoring collector',type:'Monitoring service',provider:config.provider,status:'PLANNED',security:'egress-only metrics',capacity:'user configured',subnet:'provider service',dependencies:'target'},style:{borderLeft:'4px solid #a78bfa'} }])
  const checks = assessMigration(config).filter(item => ['cidr','overlap','exposure','network','availability'].includes(item.id))
  return <EnterpriseShell><PageHeader eyebrow="INFRASTRUCTURE" title="Interactive cloud architecture builder" description="Provider-aware resources, selectable dependencies, draggable placement, deterministic architecture checks, and JSON export." actions={<div className="provider-tabs">{(['AWS','AZURE','GCP'] as const).map(provider => <button className={config.provider===provider?'active':''} onClick={() => setConfig(current => ({...current,provider,region:providerRegions[provider][0].code}))} key={provider}>{provider}</button>)}</div>}/><TruthNotice>AWS has a Terraform implementation. Azure and GCP are terminology-correct architecture planning models only.</TruthNotice>
    <div className="builder-toolbar"><label>Topology view<select value={view} onChange={event => setView(event.target.value)}><option>PHYSICAL</option><option>LOGICAL MIGRATION</option><option>NETWORK</option><option>SECURITY BOUNDARY</option></select></label><button onClick={addMonitoring}>Add monitoring resource</button><button onClick={() => setNodes(current => current.filter(item => item.id !== 'custom-monitor'))}>Remove custom resource</button><button onClick={() => downloadText(`${config.name}-architecture.json`, JSON.stringify({ provider:config.provider, view, nodes:nodes.map(({id,position,data})=>({id,position,data})), edges }, null, 2), 'application/json')}>Export architecture JSON</button></div>
    <div className="builder-grid"><section className="workspace-panel architecture-canvas"><ReactFlow nodes={nodes} edges={edges} onNodesChange={changes => setNodes(current => changes.reduce((all, change) => change.type==='position' && change.position ? all.map(node => node.id===change.id?{...node,position:change.position!}:node) : all, current))} onNodeClick={(_,node)=>setSelected(node.data as ArchitectureNode['data'])} fitView minZoom={0.4} maxZoom={1.8}><Background/><MiniMap/><Controls/></ReactFlow></section><aside className="workspace-panel resource-inspector"><div className="section-heading"><div><p>RESOURCE INSPECTOR</p><h2>{selected?.label ?? 'Select a resource'}</h2></div></div>{selected ? <dl>{Object.entries(selected).map(([key,value]) => <div key={key}><dt>{key}</dt><dd>{value}</dd></div>)}</dl> : <p>Choose a node to inspect provider, subnet, security, capacity, connections, and dependencies.</p>}</aside></div>
    <section className="workspace-panel constraint-report"><div className="section-heading"><div><p>ARCHITECTURE VALIDATION</p><h2>Specific remediation, not a readiness score</h2></div></div><AssessmentTable checks={checks}/></section>
  </EnterpriseShell>
}

function NetworkSecurity({ config, setConfig }: PlatformProps) {
  const checks = assessMigration(config).filter(item => ['cidr','overlap','network','exposure','encryption','access'].includes(item.id))
  const paths = [
    ['Application → database', config.restrictedDatabaseAccess && !config.databasePubliclyAccessible, 'Security-group reference on TCP 5432'],
    ['Migration worker → source', config.connectivity !== 'PUBLIC_TLS' || config.tls, `${config.connectivity.replaceAll('_',' ')} path with TLS`],
    ['Migration worker → target', config.privateSubnets && config.restrictedDatabaseAccess, 'Private subnet plus scoped database ingress'],
    ['Monitoring → application', true, 'Metrics-only application endpoint'],
    ['Application → object storage', config.leastPrivilege, 'Identity policy scoped to backup objects'],
  ] as const
  return <EnterpriseShell><PageHeader eyebrow="INFRASTRUCTURE" title="Network and security playground" description="IPv4 CIDR, routing assumption, exposure, encryption, and modeled connectivity decisions."/><TruthNotice>This is deterministic architecture reasoning, not packet-level emulation or a reachability analyzer connected to a cloud account.</TruthNotice>
    <div className="network-grid"><section className="workspace-panel"><div className="section-heading"><div><p>ADDRESS PLAN</p><h2>VPC and subnets</h2></div></div><div className="form-grid network-form">{([['vpcCidr','VPC CIDR'],['publicSubnetCidr','Public subnet'],['privateSubnetCidrA','Private database subnet A'],['privateSubnetCidrB','Private database subnet B']] as const).map(([key,label]) => <label className="field" key={key}><span>{label}</span><input value={config[key]} onChange={event => update(setConfig,key,event.target.value)}/></label>)}<SelectInput label="Connectivity" value={config.connectivity} onChange={value => update(setConfig,'connectivity',value as MigrationConfig['connectivity'])} options={[['PRIVATE','Private connectivity'],['VPN','Site-to-site VPN'],['PEERING','VPC peering'],['PUBLIC_TLS','Public with TLS']]}/><Toggle label="Database publicly accessible" checked={config.databasePubliclyAccessible} onChange={value=>update(setConfig,'databasePubliclyAccessible',value)}/><Toggle label="TLS required" checked={config.tls} onChange={value=>update(setConfig,'tls',value)}/><Toggle label="Restricted database ingress" checked={config.restrictedDatabaseAccess} onChange={value=>update(setConfig,'restrictedDatabaseAccess',value)}/></div></section><section className="workspace-panel"><div className="section-heading"><div><p>CONNECTIVITY TESTS</p><h2>Modeled decisions</h2></div></div><div className="connectivity-tests">{paths.map(([path,allowed,reason])=><div key={path}><span className={`pill ${allowed?'pass':'fail'}`}>{allowed?'ALLOW':'DENY'}</span><strong>{path}</strong><p>{reason}</p></div>)}</div></section></div><section className="workspace-panel"><div className="section-heading"><div><p>SECURITY ASSESSMENT</p><h2>Findings and remediations</h2></div><button onClick={()=>downloadText(`${config.name}-security-assessment.json`,JSON.stringify({classification:'SIMULATED',config:{provider:config.provider,region:config.region,network:{vpc:config.vpcCidr,subnets:[config.publicSubnetCidr,config.privateSubnetCidrA,config.privateSubnetCidrB],connectivity:config.connectivity}},checks},null,2),'application/json')}>Download report</button></div><AssessmentTable checks={checks}/></section>
  </EnterpriseShell>
}

function CostEstimator({ config }: PlatformProps) {
  const [rates,setRates]=useState<UnitRates>({databaseHourly:0,applicationHourly:0,workerHourly:0,storageGBMonth:0,backupGBMonth:0,transferGB:0,monitoringMonth:0})
  const cost=estimateCost(config,rates)
  const rows: Array<[keyof UnitRates,string]>=[['databaseHourly','Database instance / hour'],['applicationHourly','Application hosting / hour'],['workerHourly','Migration worker / hour'],['storageGBMonth','Database storage / GB-month'],['backupGBMonth','Backup storage / GB-month'],['transferGB','Network transfer / GB'],['monitoringMonth','Monitoring / month']]
  const exportData={classification:'ESTIMATED_FROM_USER_SUPPLIED_RATES',provider:config.provider,region:config.region,observationDate:'2026-11-27',assumptions:{rates,availability:config.availability,databaseSizeGB:config.databaseSizeGB,storageCapacityGB:config.storageCapacityGB},estimate:cost,exclusions:['taxes','support','discounts','reserved commitments','request charges','cross-region services not explicitly entered']}
  return <EnterpriseShell label="ESTIMATED"><PageHeader eyebrow="OPTIMIZATION · FINOPS" title="Transparent cloud cost estimator" description="Editable unit rates and visible formulas avoid pretending a static website is a provider quote."/><TruthNotice>All rates default to zero. Enter dated values from an official calculator or price sheet; CloudShift never creates a billable resource.</TruthNotice><div className="cost-layout"><section className="workspace-panel"><div className="section-heading"><div><p>USER-SUPPLIED UNIT RATES · USD</p><h2>Pricing assumptions</h2></div><span>Observed 27 Nov 2026</span></div><div className="form-grid">{rows.map(([key,label])=><NumberInput key={key} label={label} value={rates[key]} step={0.001} onChange={value=>setRates(current=>({...current,[key]:value}))}/>)}</div><div className="pricing-sources"><a href="https://aws.amazon.com/rds/postgresql/pricing/" target="_blank" rel="noreferrer">AWS RDS official pricing</a><a href="https://azure.microsoft.com/pricing/calculator/" target="_blank" rel="noreferrer">Azure official calculator</a><a href="https://cloud.google.com/products/calculator" target="_blank" rel="noreferrer">Google Cloud official calculator</a></div></section><section className="workspace-panel cost-result"><div className="section-heading"><div><p>FORMULA OUTPUT</p><h2>Architecture estimate</h2></div></div><strong>${cost.monthly.toFixed(2)}<small>/ modeled month</small></strong><dl><dt>Database compute</dt><dd>${cost.database.toFixed(2)}</dd><dt>Application hosting</dt><dd>${cost.application.toFixed(2)}</dd><dt>Database storage</dt><dd>${cost.storage.toFixed(2)}</dd><dt>Backup storage</dt><dd>${cost.backup.toFixed(2)}</dd><dt>Monitoring</dt><dd>${cost.monitoring.toFixed(2)}</dd><dt>HA monthly impact</dt><dd>${cost.highAvailabilityImpact.toFixed(2)}</dd><dt>One-time migration</dt><dd>${cost.oneTime.toFixed(2)}</dd></dl><p>Monthly = 730 hours × compute rates × availability multiplier + storage + backup + monitoring. One-time = theoretical transfer hours × worker rate + transfer GB × unit rate.</p><div className="export-row"><button onClick={()=>downloadText(`${config.name}-cost.json`,JSON.stringify(exportData,null,2),'application/json')}>Export JSON</button><button onClick={()=>downloadText(`${config.name}-cost.csv`,`category,usd\nmonthly,${cost.monthly.toFixed(2)}\none_time,${cost.oneTime.toFixed(2)}\nha_impact,${cost.highAvailabilityImpact.toFixed(2)}\n`,'text/csv')}>Export CSV</button></div></section></div></EnterpriseShell>
}

function Feasibility({ config }: PlatformProps) {
  const checks=assessMigration(config)
  const failed=checks.filter(item=>item.status==='FAIL')
  return <EnterpriseShell><PageHeader eyebrow="OPTIMIZATION" title="Migration feasibility assessment" description="Individual evidence-based checks replace a misleading readiness percentage." actions={<button onClick={()=>downloadText(`${config.name}-feasibility.json`,JSON.stringify({classification:'SIMULATED_ASSESSMENT',generatedAt:new Date().toISOString(),checks},null,2),'application/json')}>Download assessment</button>}/><div className={`decision-banner ${failed.length?'blocked':'ready'}`}><div><span>{failed.length?'CUTOVER NOT FEASIBLE':'MODELED PREFLIGHT PASSED'}</span><h2>{failed.length?`${failed.length} engineering blocker${failed.length===1?'':'s'} require remediation`:'No deterministic blocker in the current planning inputs'}</h2></div><dl><dt>Theoretical initial transfer</dt><dd>{formatDuration(theoreticalTransferSeconds(config))}</dd><dt>Modeled WAL generation</dt><dd>{walGenerationMBps(config).toFixed(2)} MB/s</dd><dt>Target apply capacity</dt><dd>{config.targetApplyMBps.toFixed(2)} MB/s</dd></dl></div><section className="workspace-panel"><AssessmentTable checks={checks}/></section></EnterpriseShell>
}

function TerraformGenerator({ config }: PlatformProps) {
  const files=generateTerraform(config); const [selected,setSelected]=useState(Object.keys(files)[0])
  useEffect(()=>setSelected(Object.keys(generateTerraform(config))[0]),[config])
  return <EnterpriseShell><PageHeader eyebrow="INFRASTRUCTURE AS CODE" title="Terraform configuration generator" description="Secure AWS-first artifacts derived from the selected plan; Azure and GCP combinations are explicitly unsupported."/><TruthNotice>Generated files are review artifacts. They are never executed here. terraform apply can create billable resources and requires separate authorization.</TruthNotice><div className="code-workspace"><aside>{Object.keys(files).map(file=><button className={selected===file?'active':''} onClick={()=>setSelected(file)} key={file}>{file}</button>)}</aside><section><div className="code-toolbar"><span>{selected}</span><div><button onClick={()=>navigator.clipboard?.writeText(files[selected])}>Copy</button><button onClick={()=>downloadText(selected,files[selected])}>Download file</button></div></div><pre>{files[selected]}</pre></section></div><section className="workspace-panel generated-guide"><h2>Safe workflow</h2><ol><li>Review network ranges, instance class, retention, encryption, and deletion protection.</li><li>Supply sensitive variables through a secure CI secret or <code>TF_VAR_database_password</code>.</li><li>Run <code>terraform init</code> and <code>terraform validate</code>.</li><li>Run <code>terraform plan</code>; inspect every resource and cost.</li><li>Run <code>terraform apply</code> only under an approved cloud change.</li></ol></section></EnterpriseShell>
}

function KubernetesExplorer({ config }: PlatformProps) {
  const [replicas,setReplicas]=useState(2); const [cpu,setCpu]=useState('100m'); const [memory,setMemory]=useState('192Mi'); const [storage,setStorage]=useState('10Gi')
  const yaml=generateKubernetes(config,replicas,cpu,memory,storage)
  const resources=[['Namespace',config.name],['Deployment','cloudshift-control-plane'],['Pods',`${replicas} desired`],['Secret reference','cloudshift-secrets'],['ConfigMap','cloudshift-config'],['PersistentVolumeClaim',storage],['NetworkPolicy','default-deny'],['Readiness / liveness','HTTP health probes']]
  return <EnterpriseShell><PageHeader eyebrow="INFRASTRUCTURE" title="Kubernetes deployment explorer" description="Inspect and generate a bounded manifest overlay without claiming a cluster exists."/><TruthNotice>MANIFEST-PREPARED only. No Kubernetes API is contacted and no workload is deployed.</TruthNotice><div className="kube-grid"><section className="workspace-panel"><div className="section-heading"><div><p>DEPLOYMENT GRAPH</p><h2>Resource relationships</h2></div></div><div className="kube-graph">{resources.map(([kind,name],index)=><div key={kind}><span>{kind}</span><strong>{name}</strong>{index<resources.length-1&&<i/>}</div>)}</div><div className="form-grid"><NumberInput label="Application replicas" value={replicas} min={1} onChange={setReplicas}/><label className="field"><span>CPU request</span><input value={cpu} onChange={e=>setCpu(e.target.value)}/></label><label className="field"><span>Memory request</span><input value={memory} onChange={e=>setMemory(e.target.value)}/></label><label className="field"><span>Storage request</span><input value={storage} onChange={e=>setStorage(e.target.value)}/></label></div></section><section className="workspace-panel yaml-inspector"><div className="section-heading"><div><p>GENERATED YAML</p><h2>Supported overlay</h2></div><button onClick={()=>downloadText(`${config.name}-kubernetes.yaml`,yaml,'application/yaml')}>Download manifest</button></div><pre>{yaml}</pre></section></div></EnterpriseShell>
}

function Reliability({ config, setConfig }: PlatformProps) {
  const [scenario,setScenario]=useState('partition')
  const windowMinutes=60; const allowedDowntime=(1-0.999)*windowMinutes*60
  return <EnterpriseShell><PageHeader eyebrow="OPERATIONS · SRE" title="Reliability and incident simulator" description="Modeled incidents change migration state and expose recovery actions, objectives, and remaining risk."/><div className="sre-strip"><article><span>Observation window</span><strong>{windowMinutes} minutes</strong><small>modeled denominator</small></article><article><span>Objective</span><strong>99.9%</strong><small>{allowedDowntime.toFixed(1)}s error budget</small></article><article><span>Configured RTO</span><strong>{config.rtoMinutes} min</strong><small>planning objective</small></article><article><span>Configured RPO</span><strong>{config.rpoMinutes} min</strong><small>planning objective</small></article></div><div className="incident-picker">{Object.entries(scenarios).filter(([,item])=>item.incident).map(([key,item])=><button key={key} className={scenario===key?'active':''} onClick={()=>{setScenario(key);setConfig(applyScenario(key))}}><span>{item.incident?.replaceAll('_',' ')}</span><strong>{item.title}</strong><small>{item.description}</small></button>)}</div><SimulationWorkspace key={scenario} config={config} initialScenario={scenario}/></EnterpriseShell>
}

function DisasterRecovery({ config, setConfig }: PlatformProps) {
  const [interval,setIntervalHours]=useState(6); const [type,setType]=useState('LOGICAL + SNAPSHOT'); const [crossRegion,setCrossRegion]=useState(true)
  const runbook=`# CloudShift disaster recovery runbook\n\nClassification: MODELED CLOUD PLAN\n\n## Objectives\n- RTO: ${config.rtoMinutes} minutes\n- RPO: ${config.rpoMinutes} minutes\n- Backup interval: ${interval} hours\n- Retention: ${config.backupRetentionDays} days\n- Backup type: ${type}\n- Cross-region copy: ${crossRegion?'designed':'not configured'}\n\n## Recovery procedure\n1. Declare incident and freeze unsafe writes.\n2. Identify the newest verified encrypted recovery point within RPO.\n3. Restore into a disposable isolated destination.\n4. Verify schema, exact table counts, checksums, roles, and absence of unintended subscriptions.\n5. Run application smoke tests and security checks.\n6. Approve route change only after validation.\n7. Monitor recovery and preserve incident evidence.\n8. Document remaining risk and retire temporary resources.\n`
  return <EnterpriseShell><PageHeader eyebrow="OPERATIONS" title="Backup and disaster recovery planner" description="Design backup flow and export a runbook while preserving the separate verified local restore evidence."/><div className="evidence-callout"><span>MEASURED LOCAL EVIDENCE</span><strong>13 / 13 tables · 13,696 rows restored</strong><p>Subscription-free logical restore verified in the v1.0.0 controlled local run. This does not validate a cloud backup service.</p></div><div className="dr-grid"><section className="workspace-panel"><div className="section-heading"><div><p>MODELED BACKUP POLICY</p><h2>Recovery design</h2></div></div><div className="form-grid"><NumberInput label="Backup interval (hours)" value={interval} min={1} onChange={setIntervalHours}/><NumberInput label="Retention (days)" value={config.backupRetentionDays} min={1} onChange={value=>update(setConfig,'backupRetentionDays',Math.min(35,value))}/><SelectInput label="Backup type" value={type} onChange={setType} options={[['LOGICAL + SNAPSHOT','Logical + provider snapshot'],['SNAPSHOT','Provider snapshot'],['LOGICAL','Logical archive']]}/><Toggle label="Encrypted cross-region copy design" checked={crossRegion} onChange={setCrossRegion}/></div><div className="backup-flow">{['Source database','Backup worker','Encrypted object storage','Disposable restore','Checksum verification'].map((name,index)=><div key={name}><strong>{name}</strong>{index<4&&<span>→</span>}</div>)}</div></section><section className="workspace-panel runbook"><div className="section-heading"><div><p>GENERATED ARTIFACT</p><h2>Disaster recovery runbook</h2></div><button onClick={()=>downloadText(`${config.name}-dr-runbook.md`,runbook,'text/markdown')}>Download runbook</button></div><pre>{runbook}</pre></section></div></EnterpriseShell>
}

function StrategyComparison({ config }: PlatformProps) {
  const strategies=[['Offline dump / restore','Unavailable during export, transfer, and restore','Lower','Simple network path','Restore source or discard target','PostgreSQL tools','Lowest worker complexity','Long application interruption'],['Online native logical replication','Writes continue through initial copy and CDC','High','Stable bidirectional reachability','Fence and route decision required','PostgreSQL 10+; schema managed separately','Self-managed workers','WAL retention, replica identity, convergence'],['Cloud-managed migration service','Provider service dependent','Medium','Provider-specific endpoints and roles','Provider-specific task and route rollback','Consult provider matrix','Service + transfer charges','No execution verified in this project']]
  return <EnterpriseShell><PageHeader eyebrow="OPTIMIZATION" title="Migration strategy comparison" description="Measured local evidence is used only for native logical replication; configured estimates remain modeled."/><div className="comparison-table"><table><thead><tr><th>Strategy</th><th>Write availability</th><th>Complexity</th><th>Network</th><th>Cutover / rollback</th><th>Compatibility</th><th>Cost model</th><th>Primary risks</th></tr></thead><tbody>{strategies.map(row=><tr key={row[0]}>{row.map((cell,index)=><td key={cell}>{index===0?<strong>{cell}</strong>:cell}</td>)}</tr>)}</tbody></table></div><div className="evidence-callout"><span>RECORDED NATIVE REPLICATION EVIDENCE</span><strong>13 tables · 13,563 final-validated rows · 0 mismatches</strong><p>424 ms write fence and 264 ms probe failure window were distinct single-run local observations—not estimates for this {config.databaseSizeGB} GB plan.</p></div></EnterpriseShell>
}

const architectureComponents=[
  ['Control plane','FastAPI lifecycle, validation, cutover, workload, and evidence APIs','services/control-plane/app','services/control-plane/tests'],
  ['Data plane','Independent PostgreSQL source and target with native logical replication','database/source/init','tests/integration'],
  ['Metadata plane','Durable migration, event, validation, workload, incident, and backup records','database/control/init/010_control_schema.sql','services/control-plane/tests'],
  ['Presentation plane','Three-mode React console and browser-local planning engines','apps/console/src','apps/console/tests-public'],
  ['Infrastructure plane','Compose baseline plus configuration-only AWS Terraform and Kubernetes','docker-compose.yml','infrastructure'],
]
function ArchitectureDocs() {
  return <EnterpriseShell><PageHeader eyebrow="DOCUMENTATION" title="Interactive architecture map" description="Move from platform responsibility to implementation, dependency, tests, and known boundary."/><div className="architecture-docs">{architectureComponents.map(([name,purpose,source,tests])=><details key={name}><summary><span>{name}</span><strong>{purpose}</strong></summary><div><dl><dt>Implementation</dt><dd><a href={`https://github.com/gargparth2003/cloudshift-db/tree/main/${source}`} target="_blank" rel="noreferrer">{source}</a></dd><dt>Associated tests</dt><dd><a href={`https://github.com/gargparth2003/cloudshift-db/tree/main/${tests}`} target="_blank" rel="noreferrer">{tests}</a></dd><dt>Boundary</dt><dd>{name==='Infrastructure plane'?'Terraform and Kubernetes are validated configuration only; no cloud deployment is claimed.':'Public mode cannot invoke live or privileged operations.'}</dd></dl></div></details>)}</div><section className="workspace-panel state-machine"><h2>Migration state machine</h2><div>{['DRAFT','ASSESSED','INITIAL SYNC','CONTINUOUS REPLICATION','VALIDATING','READY FOR CUTOVER','WRITE FENCE','ROUTE SWITCH','COMPLETED'].map((state,index)=><span key={state}>{state}{index<8&&<i>→</i>}</span>)}</div></section></EnterpriseShell>
}

function CommandCenterAlias({ config, setConfig }: PlatformProps) { return <Sandbox config={config} setConfig={setConfig}/> }

export default function CloudPlatform() {
  const [config,setConfig]=usePersistentConfig()
  const path=normalizedPath(useLocation().pathname)
  if(path==='/platform') return <Overview config={config} setConfig={setConfig}/>
  if(path==='/migration-studio/planner') return <MigrationPlanner config={config} setConfig={setConfig}/>
  if(path==='/migration-studio/sandbox') return <Sandbox config={config} setConfig={setConfig}/>
  if(path==='/migration-studio/command-center') return <CommandCenterAlias config={config} setConfig={setConfig}/>
  if(path==='/infrastructure/builder') return <ArchitectureBuilder config={config} setConfig={setConfig}/>
  if(path==='/infrastructure/network') return <NetworkSecurity config={config} setConfig={setConfig}/>
  if(path==='/infrastructure/terraform') return <TerraformGenerator config={config} setConfig={setConfig}/>
  if(path==='/infrastructure/kubernetes') return <KubernetesExplorer config={config} setConfig={setConfig}/>
  if(path==='/operations/reliability'||path==='/operations/incidents') return <Reliability config={config} setConfig={setConfig}/>
  if(path==='/operations/disaster-recovery') return <DisasterRecovery config={config} setConfig={setConfig}/>
  if(path==='/optimization/cost') return <CostEstimator config={config} setConfig={setConfig}/>
  if(path==='/optimization/comparison') return <StrategyComparison config={config} setConfig={setConfig}/>
  if(path==='/optimization/feasibility') return <Feasibility config={config} setConfig={setConfig}/>
  if(path==='/documentation/architecture') return <ArchitectureDocs/>
  return <Overview config={config} setConfig={setConfig}/>
}
