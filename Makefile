COMPOSE := docker compose --project-name cloudshift-parth --profile core
OBSERVABILITY_COMPOSE := docker compose --project-name cloudshift-parth --profile core --profile observability

.PHONY: bootstrap up down reset reset-demo evidence capture-demo backup-target restore-verify restore-cleanup reliability-target benchmark lab-postgres lab-postgres-reset lab-shards lab-redis lab-mongo lab-prometheus lab-graph observability-up observability-down health logs seed workload workload-status probe-start probe-stop test test-integration test-e2e test-replication test-validation test-browser test-public lint build build-public config status

bootstrap:
	@test -f .env || cp .env.example .env
	@$(COMPOSE) config --quiet

up: bootstrap
	@$(COMPOSE) up --build --detach

down:
	@$(COMPOSE) down

reset:
	@./scripts/reset-demo.sh "$(CONFIRM)"

reset-demo: reset

evidence:
	@./scripts/capture-evidence.py

capture-demo: evidence

benchmark:
	@./scripts/benchmark.py

backup-target:
	@./scripts/backup.py create target

restore-verify:
	@test -n "$(ARCHIVE)" || (printf 'ARCHIVE is required\n' >&2; exit 2)
	@./scripts/backup.py restore "$(ARCHIVE)"

restore-cleanup:
	@./scripts/backup.py cleanup

reliability-target:
	@./scripts/reliability.py target-interruption

lab-postgres:
	@$(COMPOSE) exec -T control-plane python -m app.postgres_lab

lab-postgres-reset:
	@$(COMPOSE) exec -T control-plane python -m app.postgres_lab reset

lab-shards:
	@docker compose --project-name cloudshift-parth --profile distributed up -d --wait shard-north shard-south shard-west
	@./scripts/shard-lab.py

lab-redis:
	@docker compose --project-name cloudshift-parth --profile academic-redis up -d --wait redis-lab
	@./scripts/redis-lab.py

lab-mongo:
	@docker compose --project-name cloudshift-parth --profile academic-mongo up -d --wait mongo-lab
	@./scripts/mongo-lab.py

lab-prometheus:
	@./scripts/prometheus-lab.py

lab-graph:
	@docker compose --project-name cloudshift-parth --profile academic-graph up -d --wait neo4j-lab
	@./scripts/neo4j-lab.py

observability-up:
	@$(OBSERVABILITY_COMPOSE) up --detach prometheus

observability-down:
	@$(OBSERVABILITY_COMPOSE) stop prometheus

health:
	@./scripts/health.sh

logs:
	@$(COMPOSE) logs --tail=100

seed:
	@./scripts/seed.sh

workload:
	@set -a; . ./.env; set +a; curl --fail --silent --show-error \
		-H "x-cloudshift-token: $$CONTROL_API_TOKEN" -H "content-type: application/json" \
		-d '{"profile":"BALANCED","rate":5}' \
		http://127.0.0.1:$${CLOUDSHIFT_WORKLOAD_PORT:-18002}/api/v1/workload/start
	@printf '\n'

workload-status:
	@curl --fail --silent --show-error http://127.0.0.1:$${CLOUDSHIFT_WORKLOAD_PORT:-18002}/api/v1/workload
	@printf '\n'

probe-start:
	@set -a; . ./.env; set +a; curl --fail --silent --show-error \
		-H "x-cloudshift-token: $$CONTROL_API_TOKEN" -H "content-type: application/json" \
		-d '{"sample_interval_ms":250,"write_interval_ms":1000}' \
		http://127.0.0.1:$${CLOUDSHIFT_WORKLOAD_PORT:-18002}/api/v1/probe/start
	@printf '\n'

probe-stop:
	@set -a; . ./.env; set +a; curl --fail --silent --show-error -X POST \
		-H "x-cloudshift-token: $$CONTROL_API_TOKEN" \
		http://127.0.0.1:$${CLOUDSHIFT_WORKLOAD_PORT:-18002}/api/v1/probe/stop
	@printf '\n'

test:
	@$(COMPOSE) exec -T control-plane python -m pytest -q

test-integration:
	@./tests/integration/verify-foundation.sh

test-e2e:
	@./tests/integration/verify-completed-state.sh

test-replication:
	@./tests/integration/verify-logical-replication.sh

test-validation:
	@./tests/integration/verify-validation-mismatch.sh

test-browser:
	@cd apps/console && npm run test:browser

test-public: build-public
	@cd apps/console && npm run test:public

lint:
	@python3 -m compileall -q services scripts
	@cd apps/console && npm run typecheck
	@$(COMPOSE) config --quiet

build:
	@$(COMPOSE) build

build-public:
	@cd apps/console && npm run build:public

config:
	@$(COMPOSE) config --quiet

status:
	@$(COMPOSE) ps
