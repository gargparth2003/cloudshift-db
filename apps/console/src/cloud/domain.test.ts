import assert from 'node:assert/strict'
import test from 'node:test'
import { applyScenario, assessMigration, cidrContains, cidrsOverlap, createSimulation, defaultConfig, estimateCost, generateKubernetes, generateTerraform, simulationReducer } from './domain.ts'

test('CIDR parsing detects containment and overlap', () => {
  assert.equal(cidrContains('10.42.0.0/16', '10.42.20.0/24'), true)
  assert.equal(cidrContains('10.42.0.0/24', '10.43.0.0/24'), false)
  assert.equal(cidrsOverlap('10.42.20.0/24', '10.42.20.128/25'), true)
  assert.equal(cidrsOverlap('10.42.20.0/24', '10.42.21.0/24'), false)
})

test('assessment blocks non-converging replication and public database exposure', () => {
  const checks = assessMigration({ ...defaultConfig, transactionsPerSecond: 2000, averageTransactionKB: 32, targetApplyMBps: 1, databasePubliclyAccessible: true })
  assert.equal(checks.find(item => item.id === 'convergence')?.status, 'FAIL')
  assert.equal(checks.find(item => item.id === 'exposure')?.status, 'FAIL')
})

test('simulation pause, network interruption, backlog and cutover guards are deterministic', () => {
  const config = { ...defaultConfig, databaseSizeGB: 0.001, transactionsPerSecond: 100, averageTransactionKB: 10, targetApplyMBps: 10 }
  let first = createSimulation(config, 42)
  first = simulationReducer(first, { type: 'START' })
  first = simulationReducer(first, { type: 'NETWORK', available: false })
  first = simulationReducer(first, { type: 'TICK', config, seconds: 10 })
  assert.ok(first.backlogMB > 0)
  const paused = simulationReducer(first, { type: 'PAUSE' })
  assert.deepEqual(simulationReducer(paused, { type: 'TICK', config, seconds: 10 }), paused)
  const blocked = simulationReducer(first, { type: 'CUTOVER' })
  assert.equal(blocked.applicationRoute, 'SOURCE')
  let second = createSimulation(config, 42)
  second = simulationReducer(second, { type: 'START' })
  second = simulationReducer(second, { type: 'NETWORK', available: false })
  second = simulationReducer(second, { type: 'TICK', config, seconds: 10 })
  assert.deepEqual(first, second)
})

test('repair, catch-up, validation and cutover reach target only after guards pass', () => {
  const config = { ...defaultConfig, databaseSizeGB: 0.0001, transactionsPerSecond: 0, targetApplyMBps: 50 }
  let state = simulationReducer(createSimulation(config), { type: 'START' })
  state = simulationReducer(state, { type: 'TICK', config, seconds: 10 })
  state = simulationReducer(state, { type: 'TICK', config, seconds: 10 })
  state = simulationReducer(state, { type: 'MISMATCH', enabled: true })
  state = simulationReducer(state, { type: 'VALIDATE' })
  assert.equal(state.validationComplete, false)
  state = simulationReducer(state, { type: 'MISMATCH', enabled: false })
  state = simulationReducer(state, { type: 'VALIDATE' })
  state = simulationReducer(state, { type: 'CUTOVER' })
  assert.equal(state.phase, 'COMPLETED')
  assert.equal(state.applicationRoute, 'TARGET')
})

test('cost formula and artifact generators remain bounded and provider-aware', () => {
  const result = estimateCost(defaultConfig, { databaseHourly: 1, applicationHourly: 0.1, workerHourly: 0.2, storageGBMonth: 0.1, backupGBMonth: 0.05, transferGB: 0.02, monitoringMonth: 10 })
  assert.ok(result.monthly > 0)
  assert.ok(result.highAvailabilityImpact > 0)
  assert.ok(generateTerraform(defaultConfig)['main.tf'].includes('publicly_accessible = false'))
  assert.ok(generateTerraform({ ...defaultConfig, provider: 'AZURE' })['UNSUPPORTED.txt'].includes('not generated'))
  assert.ok(generateKubernetes(defaultConfig, 2, '100m', '192Mi', '10Gi').includes('readinessProbe'))
  assert.equal(applyScenario('constrained').bandwidthMbps, 80)
})
