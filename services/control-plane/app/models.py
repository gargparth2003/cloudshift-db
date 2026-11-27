from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel


class HealthState(StrEnum):
    AVAILABLE = "AVAILABLE"
    DEGRADED = "DEGRADED"
    UNREACHABLE = "UNREACHABLE"


class DatabaseHealth(BaseModel):
    endpoint_id: str
    resource_name: str
    database_name: str | None = None
    postgres_version: str | None = None
    state: HealthState
    latency_ms: float
    observed_at: datetime
    error: str | None = None


class ServiceHealth(BaseModel):
    service: str
    deployment_mode: str
    state: HealthState
    observed_at: datetime
    databases: list[DatabaseHealth]


class EndpointSummary(BaseModel):
    id: str
    resource_name: str
    environment: str
    role: str
    database_name: str


class ColumnInfo(BaseModel):
    name: str
    data_type: str
    nullable: bool
    default: str | None


class TableInfo(BaseModel):
    schema_name: str
    table_name: str
    estimated_rows: int
    total_bytes: int
    columns: list[ColumnInfo]


class SchemaDiscovery(BaseModel):
    endpoint_id: str
    observed_at: datetime
    tables: list[TableInfo]
    settings: dict[str, Any]


class ErrorBody(BaseModel):
    code: str
    message: str
    correlation_id: str
