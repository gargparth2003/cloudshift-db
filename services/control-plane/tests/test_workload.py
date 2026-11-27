import pytest
from pydantic import ValidationError

from app.workload import WorkloadConfig, _percentile


def test_workload_rates_are_bounded() -> None:
    assert WorkloadConfig(profile="BALANCED", rate=25).rate == 25
    with pytest.raises(ValidationError, match="rate must be one of"):
        WorkloadConfig(profile="BALANCED", rate=7)


def test_latency_percentiles_use_observed_values() -> None:
    values = [1.0, 2.0, 3.0, 4.0, 100.0]
    assert _percentile(values, 0.50) == 3.0
    assert _percentile(values, 0.95) == 100.0
    assert _percentile([], 0.50) is None
