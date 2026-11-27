import type { MigrationEvent, ProbeSummary, PrometheusPoint, ReplayBundle, TableObservation, Topology, ValidationRun, WorkloadOperation, WorkloadStatus } from './types'

const task = 'parth-commerce-migration-001'

async function request<T>(path: string): Promise<T> {
  const response = await fetch(path, { headers: { accept: 'application/json' } })
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`)
  return response.json() as Promise<T>
}

async function operatorRequest<T>(path: string, token: string, body?: unknown): Promise<T> {
  const response = await fetch(path, {
    method: 'POST',
    headers: { accept: 'application/json', 'content-type': 'application/json', 'x-cloudshift-token': token },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(error.detail ?? `${response.status} ${response.statusText}`)
  }
  return response.json() as Promise<T>
}

export const api = {
  topology: () => request<Topology>(`/api/v1/migrations/${task}/topology`),
  tables: () => request<TableObservation[]>(`/api/v1/migrations/${task}/tables`),
  events: () => request<MigrationEvent[]>(`/api/v1/migrations/${task}/events?limit=100`),
  validations: () => request<ValidationRun[]>(`/api/v1/migrations/${task}/validations?limit=20`),
  workload: () => request<WorkloadStatus>('/workload-api/v1/workload'),
  workloadOperations: () => request<WorkloadOperation[]>('/workload-api/v1/workload/operations?limit=200'),
  workloadAction: (action: string, token: string, body?: unknown) => operatorRequest<WorkloadStatus>(`/workload-api/v1/workload/${action}`, token, body),
  probe: () => request<ProbeSummary>('/workload-api/v1/probe'),
  probeAction: (action: string, token: string, body?: unknown) => operatorRequest<ProbeSummary>(`/workload-api/v1/probe/${action}`, token, body),
  prometheusRange: async (query: string): Promise<PrometheusPoint[]> => {
    const end = Date.now() / 1000
    const start = end - 900
    const params = new URLSearchParams({ query, start: String(start), end: String(end), step: '15' })
    const result = await request<{ status: string; data: { result: Array<{ values: [number, string][] }> } }>(`/prometheus/api/v1/query_range?${params}`)
    return (result.data.result[0]?.values ?? []).map(([timestamp, value]) => ({ timestamp, value: Number(value) }))
  },
  replay: () => request<ReplayBundle>(`${import.meta.env.BASE_URL}data/replay-latest.json`),
}
