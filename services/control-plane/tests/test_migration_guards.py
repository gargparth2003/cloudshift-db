import app.migration as migration
from app.state_machine import MigrationState


def test_duplicate_active_start_does_not_recreate_replication(monkeypatch) -> None:
    monkeypatch.setattr(
        migration,
        "migration_record",
        lambda *_: {"state": MigrationState.CONTINUOUS_REPLICATION},
    )
    monkeypatch.setattr(
        migration,
        "replication_metrics",
        lambda *_: {"state": MigrationState.CONTINUOUS_REPLICATION, "ready_tables": 13},
    )
    monkeypatch.setattr(
        migration,
        "transition",
        lambda *_: (_ for _ in ()).throw(AssertionError("duplicate start transitioned state")),
    )
    result = migration.start_migration(object(), "task")
    assert result["state"] == MigrationState.CONTINUOUS_REPLICATION
    assert result["ready_tables"] == 13
