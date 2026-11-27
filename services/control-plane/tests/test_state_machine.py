import pytest

from app.state_machine import MigrationState, validate_transition


def test_valid_core_path() -> None:
    path = [
        MigrationState.DRAFT,
        MigrationState.ASSESSING,
        MigrationState.READY,
        MigrationState.INITIAL_SYNC,
        MigrationState.CONTINUOUS_REPLICATION,
        MigrationState.VALIDATING,
        MigrationState.READY_FOR_CUTOVER,
        MigrationState.CUTOVER_IN_PROGRESS,
        MigrationState.COMPLETED,
    ]
    for current, requested in zip(path, path[1:]):
        validate_transition(current, requested)


def test_invalid_transition_is_rejected() -> None:
    with pytest.raises(ValueError, match="invalid migration transition"):
        validate_transition(MigrationState.DRAFT, MigrationState.COMPLETED)


@pytest.mark.parametrize("terminal", [MigrationState.COMPLETED, MigrationState.CANCELLED])
@pytest.mark.parametrize("requested", list(MigrationState))
def test_terminal_states_cannot_roll_back(terminal: MigrationState, requested: MigrationState) -> None:
    with pytest.raises(ValueError, match="invalid migration transition"):
        validate_transition(terminal, requested)


def test_pause_and_recovery_paths_are_explicit() -> None:
    validate_transition(MigrationState.CONTINUOUS_REPLICATION, MigrationState.PAUSED)
    validate_transition(MigrationState.PAUSED, MigrationState.CONTINUOUS_REPLICATION)
    validate_transition(MigrationState.FAILED, MigrationState.RECOVERY_REQUIRED)
    validate_transition(MigrationState.RECOVERY_REQUIRED, MigrationState.PAUSED)
