import { copyFile, mkdir } from 'node:fs/promises'

const source = new URL('../dist-public/index.html', import.meta.url)
const output = new URL('../dist-public/', import.meta.url)

await copyFile(source, new URL('404.html', output))

const routes = [
  'replay',
  'database-engineering-lab',
  'platform',
  'migration-studio/planner',
  'migration-studio/sandbox',
  'migration-studio/command-center',
  'infrastructure/builder',
  'infrastructure/network',
  'infrastructure/terraform',
  'infrastructure/kubernetes',
  'operations/reliability',
  'operations/incidents',
  'operations/disaster-recovery',
  'optimization/cost',
  'optimization/comparison',
  'optimization/feasibility',
  'documentation/architecture',
]

for (const route of routes) {
  const directory = new URL(`${route}/`, output)
  await mkdir(directory, { recursive: true })
  await copyFile(source, new URL('index.html', directory))
}
