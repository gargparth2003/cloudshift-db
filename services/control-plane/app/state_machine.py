from enum import StrEnum


class MigrationState(StrEnum):
    DRAFT = "DRAFT"
    ASSESSING = "ASSESSING"
    ASSESSMENT_FAILED = "ASSESSMENT_FAILED"
    READY = "READY"
    INITIAL_SYNC = "INITIAL_SYNC"
    CONTINUOUS_REPLICATION = "CONTINUOUS_REPLICATION"
    VALIDATING = "VALIDATING"
    READY_FOR_CUTOVER = "READY_FOR_CUTOVER"
    CUTOVER_IN_PROGRESS = "CUTOVER_IN_PROGRESS"
    COMPLETED = "COMPLETED"
    PAUSED = "PAUSED"
    FAILED = "FAILED"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
    CANCELLED = "CANCELLED"


ALLOWED_TRANSITIONS: dict[MigrationState, frozenset[MigrationState]] = {
    MigrationState.DRAFT: frozenset({MigrationState.ASSESSING, MigrationState.CANCELLED}),
    MigrationState.ASSESSING: frozenset({MigrationState.READY, MigrationState.ASSESSMENT_FAILED, MigrationState.FAILED}),
    MigrationState.ASSESSMENT_FAILED: frozenset({MigrationState.ASSESSING, MigrationState.CANCELLED}),
    MigrationState.READY: frozenset({MigrationState.INITIAL_SYNC, MigrationState.CANCELLED}),
    MigrationState.INITIAL_SYNC: frozenset({MigrationState.CONTINUOUS_REPLICATION, MigrationState.PAUSED, MigrationState.FAILED, MigrationState.RECOVERY_REQUIRED}),
    MigrationState.CONTINUOUS_REPLICATION: frozenset({MigrationState.VALIDATING, MigrationState.PAUSED, MigrationState.FAILED, MigrationState.RECOVERY_REQUIRED}),
    MigrationState.VALIDATING: frozenset({MigrationState.CONTINUOUS_REPLICATION, MigrationState.READY_FOR_CUTOVER, MigrationState.FAILED}),
    MigrationState.READY_FOR_CUTOVER: frozenset({MigrationState.CUTOVER_IN_PROGRESS, MigrationState.VALIDATING, MigrationState.CANCELLED}),
    MigrationState.CUTOVER_IN_PROGRESS: frozenset({MigrationState.COMPLETED, MigrationState.FAILED, MigrationState.RECOVERY_REQUIRED}),
    MigrationState.PAUSED: frozenset({MigrationState.INITIAL_SYNC, MigrationState.CONTINUOUS_REPLICATION, MigrationState.CANCELLED, MigrationState.FAILED}),
    MigrationState.FAILED: frozenset({MigrationState.RECOVERY_REQUIRED, MigrationState.CANCELLED}),
    MigrationState.RECOVERY_REQUIRED: frozenset({MigrationState.PAUSED, MigrationState.CONTINUOUS_REPLICATION, MigrationState.FAILED, MigrationState.CANCELLED}),
    MigrationState.COMPLETED: frozenset(),
    MigrationState.CANCELLED: frozenset(),
}


def validate_transition(current: MigrationState, requested: MigrationState) -> None:
    if requested not in ALLOWED_TRANSITIONS[current]:
        raise ValueError(f"invalid migration transition: {current} -> {requested}")
