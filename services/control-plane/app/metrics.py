from collections.abc import Iterable
from time import perf_counter

from prometheus_client import Counter, Histogram, REGISTRY
from prometheus_client.core import GaugeMetricFamily

from .config import Settings
from .database import check_health, connect, endpoints
from .models import HealthState

API_REQUESTS = Counter(
    "cloudshift_api_requests_total", "Control-plane HTTP requests", ["method", "route", "status"]
)
API_DURATION = Histogram(
    "cloudshift_api_request_duration_seconds", "Control-plane HTTP request duration", ["method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10),
)


class CloudShiftCollector:
    def __init__(self, settings: Settings):
        self.settings = settings

    def collect(self) -> Iterable[GaugeMetricFamily]:
        availability = GaugeMetricFamily(
            "cloudshift_database_available", "Database endpoint availability", labels=["endpoint"]
        )
        connections = GaugeMetricFamily(
            "cloudshift_database_connections", "Observed PostgreSQL connections", labels=["endpoint"]
        )
        for endpoint_id, endpoint in endpoints(self.settings).items():
            observation = check_health(endpoint)
            availability.add_metric(
                [endpoint_id], 1 if observation.state == HealthState.AVAILABLE else 0
            )
            try:
                with connect(endpoint) as connection:
                    count = connection.execute(
                        "SELECT count(*) AS count FROM pg_stat_activity WHERE datname=current_database()"
                    ).fetchone()["count"]
                connections.add_metric([endpoint_id], count)
            except Exception:
                connections.add_metric([endpoint_id], 0)
        yield availability
        yield connections

        state_metric = GaugeMetricFamily(
            "cloudshift_migration_state", "Current durable migration state", labels=["state"]
        )
        lag_metric = GaugeMetricFamily(
            "cloudshift_replication_wal_byte_lag", "Measured retained WAL bytes for the migration slot"
        )
        worker_metric = GaugeMetricFamily(
            "cloudshift_replication_worker_active", "Whether the logical subscription worker is active"
        )
        validation_mismatches = GaugeMetricFamily(
            "cloudshift_validation_latest_mismatches", "Mismatch count from the latest validation"
        )
        validation_duration = GaugeMetricFamily(
            "cloudshift_validation_latest_duration_seconds", "Duration of the latest completed validation"
        )
        cutover_fence = GaugeMetricFamily(
            "cloudshift_cutover_write_fence_duration_seconds", "Recorded control write-fence duration"
        )
        try:
            with connect(endpoints(self.settings)["control"]) as connection:
                migration = connection.execute(
                    "SELECT state::text FROM control.migration_tasks WHERE task_key='parth-commerce-migration-001'"
                ).fetchone()
                if migration:
                    state_metric.add_metric([migration["state"]], 1)
                validation = connection.execute(
                    """
                    SELECT extract(epoch FROM (run.completed_at-run.started_at)) AS duration_seconds,
                           COALESCE(sum(result.missing_rows+result.extra_rows+result.mismatched_rows),0) AS mismatches
                    FROM control.validation_runs run
                    LEFT JOIN control.validation_results result USING (validation_run_id)
                    WHERE run.completed_at IS NOT NULL
                    GROUP BY run.validation_run_id ORDER BY run.completed_at DESC LIMIT 1
                    """
                ).fetchone()
                if validation:
                    validation_mismatches.add_metric([], validation["mismatches"])
                    validation_duration.add_metric([], float(validation["duration_seconds"] or 0))
                cutover = connection.execute(
                    """
                    SELECT write_unavailability_ms FROM control.cutover_history
                    WHERE outcome='COMPLETED' ORDER BY completed_at DESC LIMIT 1
                    """
                ).fetchone()
                if cutover and cutover["write_unavailability_ms"] is not None:
                    cutover_fence.add_metric([], cutover["write_unavailability_ms"] / 1000)
        except Exception:
            pass
        try:
            with connect(endpoints(self.settings)["source"]) as connection:
                slot = connection.execute(
                    """
                    SELECT active,
                           pg_wal_lsn_diff(pg_current_wal_lsn(),confirmed_flush_lsn)::bigint AS lag
                    FROM pg_replication_slots WHERE slot_name='parth_cloudshift_slot'
                    """
                ).fetchone()
                if slot:
                    lag_metric.add_metric([], slot["lag"])
                    worker_metric.add_metric([], 1 if slot["active"] else 0)
        except Exception:
            pass
        yield state_metric
        yield lag_metric
        yield worker_metric
        yield validation_mismatches
        yield validation_duration
        yield cutover_fence


def register_collector(settings: Settings) -> None:
    REGISTRY.register(CloudShiftCollector(settings))


def observe_request(method: str, route: str, status: int, started: float) -> None:
    API_REQUESTS.labels(method, route, str(status)).inc()
    API_DURATION.labels(method, route).observe(perf_counter() - started)
