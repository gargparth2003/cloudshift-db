export type CloudProvider = 'AWS' | 'AZURE' | 'GCP'
export type OperatingMode = 'SANDBOX' | 'REPLAY' | 'LIVE'
export type CheckStatus = 'PASS' | 'WARNING' | 'FAIL' | 'UNKNOWN'
export type MigrationPhase = 'ASSESSMENT' | 'INITIAL_SYNC' | 'CATCH_UP' | 'VALIDATION' | 'READY_FOR_CUTOVER' | 'WRITE_FENCE' | 'ROUTE_SWITCH' | 'COMPLETED' | 'CANCELLED'

export type MigrationConfig = {
  name: string
  source: 'LOCAL_POSTGRESQL' | 'ON_PREMISES_POSTGRESQL' | 'EC2_POSTGRESQL' | 'RDS_POSTGRESQL' | 'AZURE_POSTGRESQL' | 'CLOUD_SQL_POSTGRESQL'
  provider: CloudProvider
  region: string
  postgresVersion: string
  databaseSizeGB: number
  tableCount: number
  estimatedRows: number
  workload: 'READ_HEAVY' | 'BALANCED' | 'WRITE_HEAVY'
  transactionsPerSecond: number
  averageTransactionKB: number
  concurrentConnections: number
  annualGrowthPercent: number
  bandwidthMbps: number
  effectiveBandwidthPercent: number
  latencyMs: number
  connectivity: 'PRIVATE' | 'VPN' | 'PEERING' | 'PUBLIC_TLS'
  strategy: 'OFFLINE' | 'ONLINE_CDC' | 'HOMOGENEOUS'
  availability: 'SINGLE_ZONE' | 'MULTI_ZONE'
  backupRetentionDays: number
  rtoMinutes: number
  rpoMinutes: number
  acceptableInterruptionSeconds: number
  encryptionAtRest: boolean
  tls: boolean
  privateSubnets: boolean
  restrictedDatabaseAccess: boolean
  secretsManagement: boolean
  leastPrivilege: boolean
  vpcCidr: string
  publicSubnetCidr: string
  privateSubnetCidrA: string
  privateSubnetCidrB: string
  databasePubliclyAccessible: boolean
  targetApplyMBps: number
  workerConcurrency: number
  storageCapacityGB: number
  primaryKeyCoveragePercent: number
  replicaIdentityReady: boolean
  requiredExtensions: string[]
  backupAvailable: boolean
}

export type AssessmentCheck = {
  id: string
  title: string
  status: CheckStatus
  component: string
  reason: string
  consequence: string
  remediation: string
}

export type UnitRates = {
  databaseHourly: number
  applicationHourly: number
  workerHourly: number
  storageGBMonth: number
  backupGBMonth: number
  transferGB: number
  monitoringMonth: number
}

export type SimulationEvent = { id: number; elapsedSeconds: number; type: string; message: string }
export type SimulationState = {
  phase: MigrationPhase
  status: 'IDLE' | 'RUNNING' | 'PAUSED' | 'COMPLETED' | 'CANCELLED'
  seed: number
  elapsedSeconds: number
  snapshotRemainingMB: number
  backlogMB: number
  transferredMB: number
  networkAvailable: boolean
  workloadMultiplier: number
  bandwidthMultiplier: number
  applyMultiplier: number
  mismatch: boolean
  validationComplete: boolean
  applicationRoute: 'SOURCE' | 'TARGET'
  events: SimulationEvent[]
}

export const providerRegions: Record<CloudProvider, Array<{ code: string; name: string; zones: number }>> = {
  AWS: [
    { code: 'ap-south-1', name: 'Asia Pacific (Mumbai)', zones: 3 },
    { code: 'ap-south-2', name: 'Asia Pacific (Hyderabad)', zones: 3 },
    { code: 'ap-southeast-1', name: 'Asia Pacific (Singapore)', zones: 3 },
    { code: 'eu-west-1', name: 'Europe (Ireland)', zones: 3 },
    { code: 'us-east-1', name: 'US East (N. Virginia)', zones: 6 },
  ],
  AZURE: [
    { code: 'centralindia', name: 'Central India (Pune)', zones: 3 },
    { code: 'indiasouthcentral', name: 'India South Central (Hyderabad)', zones: 3 },
    { code: 'southeastasia', name: 'Southeast Asia (Singapore)', zones: 3 },
    { code: 'northeurope', name: 'North Europe (Ireland)', zones: 3 },
    { code: 'eastus', name: 'East US', zones: 3 },
  ],
  GCP: [
    { code: 'asia-south1', name: 'Mumbai, India', zones: 3 },
    { code: 'asia-south2', name: 'Delhi, India', zones: 3 },
    { code: 'asia-southeast1', name: 'Singapore', zones: 3 },
    { code: 'europe-west1', name: 'Belgium', zones: 3 },
    { code: 'us-central1', name: 'Iowa, USA', zones: 4 },
  ],
}

export const providerResources: Record<CloudProvider, Record<string, string>> = {
  AWS: { network: 'Amazon VPC', compute: 'Amazon EC2', database: 'Amazon RDS PostgreSQL', migration: 'AWS DMS (comparison)', storage: 'Amazon S3', monitoring: 'Amazon CloudWatch', identity: 'AWS IAM', secrets: 'AWS Secrets Manager', kubernetes: 'Amazon EKS' },
  AZURE: { network: 'Azure Virtual Network', compute: 'Azure Virtual Machines', database: 'Azure Database for PostgreSQL', migration: 'Azure Database Migration Service (comparison)', storage: 'Azure Blob Storage', monitoring: 'Azure Monitor', identity: 'Managed identities', secrets: 'Azure Key Vault', kubernetes: 'AKS' },
  GCP: { network: 'Google Cloud VPC', compute: 'Compute Engine', database: 'Cloud SQL PostgreSQL', migration: 'Database Migration Service (comparison)', storage: 'Cloud Storage', monitoring: 'Cloud Monitoring', identity: 'Cloud IAM', secrets: 'Secret Manager', kubernetes: 'GKE' },
}

export const defaultConfig: MigrationConfig = {
  name: 'onprem-to-rds-mumbai', source: 'ON_PREMISES_POSTGRESQL', provider: 'AWS', region: 'ap-south-1', postgresVersion: '16',
  databaseSizeGB: 100, tableCount: 48, estimatedRows: 25_000_000, workload: 'BALANCED', transactionsPerSecond: 120, averageTransactionKB: 8,
  concurrentConnections: 180, annualGrowthPercent: 30, bandwidthMbps: 500, effectiveBandwidthPercent: 70, latencyMs: 35, connectivity: 'VPN',
  strategy: 'ONLINE_CDC', availability: 'MULTI_ZONE', backupRetentionDays: 14, rtoMinutes: 30, rpoMinutes: 5, acceptableInterruptionSeconds: 5,
  encryptionAtRest: true, tls: true, privateSubnets: true, restrictedDatabaseAccess: true, secretsManagement: true, leastPrivilege: true,
  vpcCidr: '10.42.0.0/16', publicSubnetCidr: '10.42.10.0/24', privateSubnetCidrA: '10.42.20.0/24', privateSubnetCidrB: '10.42.21.0/24',
  databasePubliclyAccessible: false, targetApplyMBps: 4, workerConcurrency: 4, storageCapacityGB: 250, primaryKeyCoveragePercent: 100,
  replicaIdentityReady: true, requiredExtensions: [], backupAvailable: true,
}

export const scenarios: Record<string, { title: string; description: string; config: Partial<MigrationConfig>; incident?: string }> = {
  onprem_rds: { title: 'On-premises PostgreSQL to Amazon RDS', description: 'Private online migration into Multi-AZ RDS in Mumbai.', config: {} },
  ec2_private: { title: 'EC2 PostgreSQL to private managed PostgreSQL', description: 'Same-cloud homogeneous migration with VPC-private routing.', config: { source: 'EC2_POSTGRESQL', connectivity: 'PRIVATE', databaseSizeGB: 250 } },
  ha_multi_zone: { title: 'High-availability multi-zone migration', description: 'Stricter recovery objectives and zonal placement.', config: { availability: 'MULTI_ZONE', rtoMinutes: 10, rpoMinutes: 1, backupRetentionDays: 30 } },
  constrained: { title: 'Bandwidth-constrained migration', description: 'Large source over a constrained VPN path.', config: { databaseSizeGB: 800, bandwidthMbps: 80, latencyMs: 85 } },
  overload: { title: 'Replication overload at peak traffic', description: 'Incoming WAL exceeds target apply capacity until tuned.', config: { transactionsPerSecond: 900, averageTransactionKB: 16, targetApplyMBps: 4 }, incident: 'WORKLOAD_SPIKE' },
  partition: { title: 'Network interruption and recovery', description: 'A deterministic partition builds backlog before recovery.', config: { databaseSizeGB: 120 }, incident: 'NETWORK_PARTITION' },
  mismatch: { title: 'Validation mismatch blocks cutover', description: 'Integrity failure requires repair and revalidation.', config: {}, incident: 'VALIDATION_MISMATCH' },
  cost: { title: 'Cost-optimized cloud architecture', description: 'Single-zone planning baseline with explicit availability trade-off.', config: { availability: 'SINGLE_ZONE', databaseSizeGB: 50, storageCapacityGB: 100, backupRetentionDays: 7 } },
  disaster_recovery: { title: 'Backup restoration planning', description: 'Cross-region encrypted backup and restoration runbook.', config: { backupRetentionDays: 35, rtoMinutes: 60, rpoMinutes: 15 }, incident: 'DESTINATION_UNAVAILABLE' },
}

export function applyScenario(key: string): MigrationConfig {
  return { ...defaultConfig, ...(scenarios[key]?.config ?? {}), name: key.replaceAll('_', '-') }
}

function ipToInt(ip: string): number | null {
  const parts = ip.split('.')
  if (parts.length !== 4 || parts.some(part => !/^\d{1,3}$/.test(part) || Number(part) > 255)) return null
  return parts.reduce((value, part) => ((value << 8) | Number(part)) >>> 0, 0)
}

export function parseCidr(cidr: string): { start: number; end: number; prefix: number } | null {
  const [ip, rawPrefix, ...extra] = cidr.split('/')
  if (extra.length || rawPrefix === undefined || !/^\d{1,2}$/.test(rawPrefix)) return null
  const address = ipToInt(ip)
  const prefix = Number(rawPrefix)
  if (address === null || prefix < 0 || prefix > 32) return null
  const mask = prefix === 0 ? 0 : (0xffffffff << (32 - prefix)) >>> 0
  const start = (address & mask) >>> 0
  const size = 2 ** (32 - prefix)
  return { start, end: start + size - 1, prefix }
}

export function cidrContains(parent: string, child: string): boolean {
  const a = parseCidr(parent); const b = parseCidr(child)
  return Boolean(a && b && a.start <= b.start && a.end >= b.end)
}

export function cidrsOverlap(first: string, second: string): boolean {
  const a = parseCidr(first); const b = parseCidr(second)
  return Boolean(a && b && a.start <= b.end && b.start <= a.end)
}

export function assessMigration(config: MigrationConfig): AssessmentCheck[] {
  const checks: AssessmentCheck[] = []
  const add = (id: string, title: string, status: CheckStatus, component: string, reason: string, consequence: string, remediation: string) => checks.push({ id, title, status, component, reason, consequence, remediation })
  add('engine', 'PostgreSQL compatibility', Number(config.postgresVersion) >= 10 ? 'PASS' : 'FAIL', 'Database engine', `PostgreSQL ${config.postgresVersion} selected.`, 'Native logical replication requires PostgreSQL 10 or newer.', 'Upgrade the source or choose offline dump/restore.')
  add('keys', 'Primary-key coverage', config.primaryKeyCoveragePercent === 100 ? 'PASS' : config.primaryKeyCoveragePercent >= 90 ? 'WARNING' : 'FAIL', 'Source schema', `${config.primaryKeyCoveragePercent}% of replicated tables have primary keys.`, 'UPDATE and DELETE replication requires suitable replica identity.', 'Add primary keys or explicitly configure REPLICA IDENTITY FULL after impact testing.')
  add('identity', 'Replica identity', config.replicaIdentityReady ? 'PASS' : 'FAIL', 'Source schema', config.replicaIdentityReady ? 'Replica identity is declared ready.' : 'Replica identity is not ready.', 'Changed rows may not be identifiable to the subscriber.', 'Configure and verify replica identity for every published table.')
  const transferSeconds = theoreticalTransferSeconds(config)
  add('bandwidth', 'Initial transfer duration', Number.isFinite(transferSeconds) && transferSeconds < 7 * 86400 ? 'PASS' : 'WARNING', 'Network', `${formatDuration(transferSeconds)} theoretical minimum at effective bandwidth.`, 'A long snapshot extends dual-running time and accumulated change volume.', 'Increase bandwidth, compress transfer, stage closer to the source, or split the migration.')
  const incoming = walGenerationMBps(config)
  add('convergence', 'CDC convergence', config.targetApplyMBps > incoming ? 'PASS' : 'FAIL', 'Replication worker', `${incoming.toFixed(2)} MB/s modeled WAL versus ${config.targetApplyMBps.toFixed(2)} MB/s target apply capacity.`, 'Backlog cannot converge when incoming change volume meets or exceeds apply capacity.', 'Increase target/worker capacity or reduce write traffic before cutover.')
  add('network', 'Private connectivity', config.connectivity !== 'PUBLIC_TLS' ? 'PASS' : 'WARNING', 'Network', `${config.connectivity.replaceAll('_', ' ')} selected.`, 'Public paths increase exposure and require strict allowlists and TLS.', 'Prefer VPN, peering, or provider-private connectivity.')
  add('cidr', 'Subnet containment', [config.publicSubnetCidr, config.privateSubnetCidrA, config.privateSubnetCidrB].every(cidr => cidrContains(config.vpcCidr, cidr)) ? 'PASS' : 'FAIL', 'VPC', 'Subnets must be contained by the parent VPC.', 'Invalid routing and deployment failure.', 'Select non-overlapping subnets inside the VPC CIDR.')
  add('overlap', 'Subnet overlap', !cidrsOverlap(config.publicSubnetCidr, config.privateSubnetCidrA) && !cidrsOverlap(config.publicSubnetCidr, config.privateSubnetCidrB) && !cidrsOverlap(config.privateSubnetCidrA, config.privateSubnetCidrB) ? 'PASS' : 'FAIL', 'VPC', 'Subnet address ranges were compared deterministically.', 'Overlapping CIDRs cannot form a valid subnet plan.', 'Assign distinct subnet ranges.')
  add('exposure', 'Database exposure', !config.databasePubliclyAccessible && config.privateSubnets ? 'PASS' : 'FAIL', 'Target database', config.databasePubliclyAccessible ? 'Public database access is enabled.' : 'Target is private.', 'Public exposure expands the attack surface.', 'Disable public accessibility and place the database in private DB subnets.')
  add('encryption', 'Encryption controls', config.encryptionAtRest && config.tls ? 'PASS' : 'FAIL', 'Security', `At-rest encryption ${config.encryptionAtRest ? 'on' : 'off'}; TLS ${config.tls ? 'on' : 'off'}.`, 'Data can be exposed at rest or in transit.', 'Enable provider-managed at-rest encryption and require TLS.')
  add('access', 'Identity and secrets', config.restrictedDatabaseAccess && config.secretsManagement && config.leastPrivilege ? 'PASS' : 'FAIL', 'Security', 'Restricted access, secrets management, and least privilege are assessed together.', 'Broad/static credentials increase compromise impact.', 'Use a secrets manager, scoped roles, rotation, and security-group references.')
  add('storage', 'Destination capacity', config.storageCapacityGB >= config.databaseSizeGB * 1.2 ? 'PASS' : 'FAIL', 'Target storage', `${config.storageCapacityGB} GB provisioned for ${config.databaseSizeGB} GB plus growth/headroom.`, 'Copy or WAL retention can exhaust storage.', 'Provision at least 20% headroom plus expected growth and retained WAL.')
  add('backup', 'Verified backup available', config.backupAvailable ? 'PASS' : 'FAIL', 'Recovery', config.backupAvailable ? 'A backup is declared available.' : 'No usable backup is declared.', 'Migration failure may lack a safe restoration path.', 'Create and test a restoration before migration.')
  add('availability', 'Availability-zone design', config.availability === 'MULTI_ZONE' ? 'PASS' : 'WARNING', 'Target architecture', `${config.availability.replaceAll('_', ' ')} selected.`, 'Single-zone designs have a zonal failure dependency.', 'Use at least two DB subnets and a supported multi-zone database configuration.')
  add('extensions', 'Extension compatibility', config.requiredExtensions.length ? 'UNKNOWN' : 'PASS', 'Database extensions', config.requiredExtensions.length ? `${config.requiredExtensions.join(', ')} require provider-specific confirmation.` : 'No required extensions entered.', 'Unsupported extensions can block migration or alter behavior.', 'Compare every extension/version with the destination provider support matrix.')
  return checks
}

export function walGenerationMBps(config: MigrationConfig): number {
  return Math.max(0, config.transactionsPerSecond * config.averageTransactionKB / 1024 * (config.workload === 'WRITE_HEAVY' ? 1 : config.workload === 'BALANCED' ? 0.55 : 0.2))
}

export function effectiveTransferMBps(config: MigrationConfig): number {
  return Math.max(0, config.bandwidthMbps / 8 * Math.min(100, Math.max(0, config.effectiveBandwidthPercent)) / 100)
}

export function theoreticalTransferSeconds(config: MigrationConfig): number {
  const rate = effectiveTransferMBps(config)
  return rate > 0 ? config.databaseSizeGB * 1024 / rate : Number.POSITIVE_INFINITY
}

export function formatDuration(seconds: number): string {
  if (!Number.isFinite(seconds)) return 'unbounded'
  if (seconds < 60) return `${Math.ceil(seconds)} seconds`
  if (seconds < 3600) return `${(seconds / 60).toFixed(1)} minutes`
  if (seconds < 86400) return `${(seconds / 3600).toFixed(1)} hours`
  return `${(seconds / 86400).toFixed(1)} days`
}

export function estimateCost(config: MigrationConfig, rates: UnitRates) {
  const ha = config.availability === 'MULTI_ZONE' ? 2 : 1
  const database = Math.max(0, rates.databaseHourly) * 730 * ha
  const application = Math.max(0, rates.applicationHourly) * 730
  const storage = Math.max(0, rates.storageGBMonth) * config.storageCapacityGB * ha
  const backup = Math.max(0, rates.backupGBMonth) * config.databaseSizeGB * Math.max(1, config.backupRetentionDays / 30)
  const monitoring = Math.max(0, rates.monitoringMonth)
  const monthly = database + application + storage + backup + monitoring
  const migrationHours = theoreticalTransferSeconds(config) / 3600
  const migrationWorker = Number.isFinite(migrationHours) ? Math.max(0, rates.workerHourly) * migrationHours : 0
  const transfer = Math.max(0, rates.transferGB) * config.databaseSizeGB
  return { database, application, storage, backup, monitoring, monthly, migrationWorker, transfer, oneTime: migrationWorker + transfer, highAvailabilityImpact: ha === 2 ? database / 2 + storage / 2 : 0 }
}

function event(state: SimulationState, type: string, message: string): SimulationState {
  const next = [...state.events, { id: (state.events.at(-1)?.id ?? 0) + 1, elapsedSeconds: state.elapsedSeconds, type, message }].slice(-120)
  return { ...state, events: next }
}

export function createSimulation(config: MigrationConfig, seed = 110): SimulationState {
  return { phase: 'ASSESSMENT', status: 'IDLE', seed, elapsedSeconds: 0, snapshotRemainingMB: config.databaseSizeGB * 1024, backlogMB: 0, transferredMB: 0, networkAvailable: true, workloadMultiplier: 1, bandwidthMultiplier: 1, applyMultiplier: 1, mismatch: false, validationComplete: false, applicationRoute: 'SOURCE', events: [] }
}

export type SimulationAction =
  | { type: 'START' } | { type: 'PAUSE' } | { type: 'RESUME' } | { type: 'CANCEL' } | { type: 'RESTART'; config: MigrationConfig }
  | { type: 'TICK'; config: MigrationConfig; seconds: number } | { type: 'NETWORK'; available: boolean }
  | { type: 'WORKLOAD'; multiplier: number } | { type: 'BANDWIDTH'; multiplier: number } | { type: 'APPLY'; multiplier: number }
  | { type: 'MISMATCH'; enabled: boolean } | { type: 'VALIDATE' } | { type: 'CUTOVER' }

export function simulationReducer(state: SimulationState, action: SimulationAction): SimulationState {
  if (action.type === 'START' && state.status === 'IDLE') return event({ ...state, status: 'RUNNING', phase: 'INITIAL_SYNC' }, 'SIMULATION_STARTED', 'Assessment passed; initial synchronization started.')
  if (action.type === 'PAUSE' && state.status === 'RUNNING') return event({ ...state, status: 'PAUSED' }, 'SIMULATION_PAUSED', 'Modeled processing paused; source workload continues only when explicitly ticked.')
  if (action.type === 'RESUME' && state.status === 'PAUSED') return event({ ...state, status: 'RUNNING' }, 'SIMULATION_RESUMED', 'Modeled processing resumed.')
  if (action.type === 'CANCEL' && ['RUNNING', 'PAUSED'].includes(state.status)) return event({ ...state, status: 'CANCELLED', phase: 'CANCELLED' }, 'SIMULATION_CANCELLED', 'Scenario cancelled without changing any real resource.')
  if (action.type === 'RESTART') return createSimulation(action.config, state.seed)
  if (action.type === 'NETWORK') return event({ ...state, networkAvailable: action.available }, action.available ? 'NETWORK_RESTORED' : 'NETWORK_INTERRUPTED', action.available ? 'Modeled connectivity restored.' : 'Modeled replication path interrupted; backlog will grow.')
  if (action.type === 'WORKLOAD') return event({ ...state, workloadMultiplier: Math.max(0.1, action.multiplier) }, 'WORKLOAD_CHANGED', `Workload multiplier set to ${action.multiplier.toFixed(1)}×.`)
  if (action.type === 'BANDWIDTH') return event({ ...state, bandwidthMultiplier: Math.max(0.1, action.multiplier) }, 'BANDWIDTH_CHANGED', `Bandwidth multiplier set to ${action.multiplier.toFixed(1)}×.`)
  if (action.type === 'APPLY') return event({ ...state, applyMultiplier: Math.max(0.1, action.multiplier) }, 'APPLY_CAPACITY_CHANGED', `Target apply multiplier set to ${action.multiplier.toFixed(1)}×.`)
  if (action.type === 'MISMATCH') return event({ ...state, mismatch: action.enabled, validationComplete: action.enabled ? false : state.validationComplete }, action.enabled ? 'VALIDATION_MISMATCH_INJECTED' : 'VALIDATION_MISMATCH_REPAIRED', action.enabled ? 'A deterministic integrity mismatch now blocks cutover.' : 'The modeled mismatch was repaired; revalidation is required.')
  if (action.type === 'VALIDATE') {
    if (state.snapshotRemainingMB > 0.01 || state.backlogMB > 0.01) return event(state, 'VALIDATION_BLOCKED', 'Required synchronization or backlog remains.')
    if (state.mismatch) return event({ ...state, phase: 'VALIDATION', validationComplete: false }, 'VALIDATION_FAILED', 'Integrity mismatch detected; cutover remains blocked.')
    return event({ ...state, phase: 'READY_FOR_CUTOVER', validationComplete: true }, 'VALIDATION_PASSED', 'Modeled validation passed with no unresolved mismatch.')
  }
  if (action.type === 'CUTOVER') {
    if (!state.validationComplete || state.mismatch || state.backlogMB > 0.01 || state.snapshotRemainingMB > 0.01) return event(state, 'CUTOVER_BLOCKED', 'Cutover requires completed synchronization, zero backlog, and a clean validation.')
    return event({ ...state, phase: 'COMPLETED', status: 'COMPLETED', applicationRoute: 'TARGET' }, 'CUTOVER_COMPLETED', 'Modeled write fence and route switch completed; application now targets the destination.')
  }
  if (action.type === 'TICK' && state.status === 'RUNNING') {
    const seconds = Math.max(0, Math.min(60, action.seconds))
    const incoming = walGenerationMBps(action.config) * state.workloadMultiplier * seconds
    const networkFactor = state.networkAvailable ? 1 : 0
    const copyCapacity = effectiveTransferMBps(action.config) * state.bandwidthMultiplier * networkFactor * seconds
    const applyCapacity = action.config.targetApplyMBps * state.applyMultiplier * networkFactor * seconds
    let snapshot = state.snapshotRemainingMB
    let backlog = state.backlogMB + incoming
    let transferred = state.transferredMB
    let phase = state.phase
    if (snapshot > 0) {
      const copied = Math.min(snapshot, copyCapacity)
      snapshot = Math.max(0, snapshot - copied)
      transferred += copied
      if (snapshot === 0) phase = 'CATCH_UP'
    } else {
      backlog = Math.max(0, backlog - applyCapacity)
      phase = backlog <= 0.01 ? 'VALIDATION' : 'CATCH_UP'
    }
    return { ...state, elapsedSeconds: state.elapsedSeconds + seconds, snapshotRemainingMB: snapshot, backlogMB: backlog, transferredMB: transferred, phase }
  }
  return state
}

function safeName(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9-]/g, '-').replace(/-+/g, '-').replace(/^-|-$/g, '') || 'cloudshift'
}

export function generateTerraform(config: MigrationConfig): Record<string, string> {
  if (config.provider !== 'AWS') return { 'UNSUPPORTED.txt': `${config.provider} is an architecture-planning model in CloudShift DB v1.1.0. Provider-specific Terraform is not generated.` }
  const prefix = safeName(config.name)
  const main = `resource "aws_vpc" "migration" {\n  cidr_block = var.vpc_cidr\n  enable_dns_support = true\n  enable_dns_hostnames = true\n  tags = merge(var.tags, { Name = "${prefix}-vpc" })\n}\n\nresource "aws_subnet" "database" {\n  count = 2\n  vpc_id = aws_vpc.migration.id\n  cidr_block = [var.database_subnet_cidrs[0], var.database_subnet_cidrs[1]][count.index]\n  availability_zone = data.aws_availability_zones.available.names[count.index]\n  tags = merge(var.tags, { Name = "${prefix}-db-\${count.index + 1}" })\n}\n\ndata "aws_availability_zones" "available" { state = "available" }\n\nresource "aws_db_subnet_group" "target" {\n  name = "${prefix}"\n  subnet_ids = aws_subnet.database[*].id\n}\n\nresource "aws_security_group" "target" {\n  name = "${prefix}-database"\n  vpc_id = aws_vpc.migration.id\n  ingress { from_port = 5432; to_port = 5432; protocol = "tcp"; security_groups = [aws_security_group.migration_worker.id] }\n}\n\nresource "aws_security_group" "migration_worker" { name = "${prefix}-worker"; vpc_id = aws_vpc.migration.id }\n\nresource "aws_db_instance" "target" {\n  identifier = "${prefix}-target"\n  engine = "postgres"\n  engine_version = var.postgres_version\n  instance_class = var.database_instance_class\n  allocated_storage = var.database_storage_gb\n  max_allocated_storage = var.database_max_storage_gb\n  storage_type = "gp3"\n  storage_encrypted = true\n  multi_az = var.multi_az\n  publicly_accessible = false\n  db_subnet_group_name = aws_db_subnet_group.target.name\n  vpc_security_group_ids = [aws_security_group.target.id]\n  username = var.database_username\n  password = var.database_password\n  backup_retention_period = var.backup_retention_days\n  deletion_protection = var.deletion_protection\n  skip_final_snapshot = false\n  final_snapshot_identifier = "${prefix}-final"\n  tags = var.tags\n}\n`
  const variables = `variable "aws_region" { type = string; default = "${config.region}" }\nvariable "vpc_cidr" { type = string; default = "${config.vpcCidr}" }\nvariable "database_subnet_cidrs" { type = list(string); default = ["${config.privateSubnetCidrA}", "${config.privateSubnetCidrB}"]; validation { condition = length(var.database_subnet_cidrs) >= 2; error_message = "At least two database subnets are required." } }\nvariable "postgres_version" { type = string; default = "${config.postgresVersion}" }\nvariable "database_instance_class" { type = string; default = "db.t4g.small" }\nvariable "database_storage_gb" { type = number; default = ${Math.ceil(config.storageCapacityGB)} }\nvariable "database_max_storage_gb" { type = number; default = ${Math.ceil(config.storageCapacityGB * 2)} }\nvariable "database_username" { type = string; default = "cloudshift_admin" }\nvariable "database_password" { type = string; sensitive = true; nullable = false }\nvariable "multi_az" { type = bool; default = ${config.availability === 'MULTI_ZONE'} }\nvariable "backup_retention_days" { type = number; default = ${config.backupRetentionDays} }\nvariable "deletion_protection" { type = bool; default = true }\nvariable "tags" { type = map(string); default = { Project = "cloudshift-db"; ManagedBy = "terraform" } }\n`
  return {
    'versions.tf': `terraform { required_version = ">= 1.7, < 2.0"; required_providers { aws = { source = "hashicorp/aws"; version = "~> 6.0" } } }\nprovider "aws" { region = var.aws_region }\n`,
    'main.tf': main,
    'variables.tf': variables,
    'outputs.tf': `output "database_endpoint" { value = aws_db_instance.target.address; sensitive = true }\noutput "vpc_id" { value = aws_vpc.migration.id }\n`,
    'terraform.tfvars.example': `# Copy to terraform.tfvars; never commit real passwords.\naws_region = "${config.region}"\ndatabase_password = "REPLACE_USING_TF_VAR_OR_SECRET_STORE"\n`,
    'README.md': `# Generated CloudShift AWS plan\n\nArchitecture artifact only. Review before use.\n\n1. Set credentials outside Terraform files.\n2. Run \`terraform init\`.\n3. Run \`terraform validate\`.\n4. Run \`terraform plan\` and review every billable resource.\n5. Run \`terraform apply\` only with explicit authorization; apply can create billable AWS resources.\n`,
  }
}

export function generateKubernetes(config: MigrationConfig, replicas: number, cpu: string, memory: string, storage: string): string {
  const name = safeName(config.name)
  return `apiVersion: v1\nkind: Namespace\nmetadata:\n  name: ${name}\n---\napiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: cloudshift-control-plane\n  namespace: ${name}\nspec:\n  replicas: ${Math.max(1, Math.min(20, replicas))}\n  selector:\n    matchLabels: { app: cloudshift-control-plane }\n  template:\n    metadata:\n      labels: { app: cloudshift-control-plane }\n    spec:\n      containers:\n        - name: control-plane\n          image: ghcr.io/gargparth2003/cloudshift-control-plane:1.1.0\n          ports: [{ containerPort: 8000 }]\n          envFrom:\n            - configMapRef: { name: cloudshift-config }\n            - secretRef: { name: cloudshift-secrets }\n          readinessProbe: { httpGet: { path: /api/v1/health/live, port: 8000 }, initialDelaySeconds: 5, periodSeconds: 5 }\n          livenessProbe: { httpGet: { path: /api/v1/health/live, port: 8000 }, initialDelaySeconds: 15, periodSeconds: 10 }\n          resources:\n            requests: { cpu: ${cpu}, memory: ${memory} }\n            limits: { cpu: "1", memory: 512Mi }\n          securityContext: { runAsNonRoot: true, allowPrivilegeEscalation: false, readOnlyRootFilesystem: true }\n---\napiVersion: v1\nkind: PersistentVolumeClaim\nmetadata: { name: migration-evidence, namespace: ${name} }\nspec:\n  accessModes: [ReadWriteOnce]\n  resources: { requests: { storage: ${storage} } }\n---\napiVersion: networking.k8s.io/v1\nkind: NetworkPolicy\nmetadata: { name: default-deny, namespace: ${name} }\nspec: { podSelector: {}, policyTypes: [Ingress, Egress] }\n`
}

export function downloadText(filename: string, content: string, mime = 'text/plain') {
  const blob = new Blob([content], { type: mime })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url; anchor.download = filename; anchor.click()
  URL.revokeObjectURL(url)
}
