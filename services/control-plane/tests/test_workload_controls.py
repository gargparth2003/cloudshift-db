import asyncio

import pytest
from fastapi import HTTPException

from app import workload as service


def test_duplicate_workload_start_is_rejected_before_database_work() -> None:
    original = service.workload.state
    service.workload.state = "RUNNING"
    try:
        with pytest.raises(HTTPException, match="already active") as error:
            asyncio.run(service.start_workload(service.WorkloadConfig()))
        assert error.value.status_code == 409
    finally:
        service.workload.state = original


def test_invalid_pause_resume_and_probe_stop_are_rejected() -> None:
    workload_state, workload_run = service.workload.state, service.workload.run_id
    probe_state, probe_run = service.probe.state, service.probe.run_id
    service.workload.state, service.workload.run_id = "STOPPED", None
    service.probe.state, service.probe.run_id = "STOPPED", None
    try:
        for operation in (service.pause_workload, service.resume_workload, service.stop_workload, service.stop_probe):
            with pytest.raises(HTTPException) as error:
                asyncio.run(operation())
            assert error.value.status_code == 409
    finally:
        service.workload.state, service.workload.run_id = workload_state, workload_run
        service.probe.state, service.probe.run_id = probe_state, probe_run
