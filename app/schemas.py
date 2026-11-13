import math
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MetricName = Field(min_length=1, max_length=50, pattern=r"^[a-z][a-z0-9_]*$")


class DeviceCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    location: str | None = Field(default=None, max_length=200)


class DeviceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    location: str | None
    created_at: datetime
    last_seen_at: datetime | None


class DeviceCreated(DeviceOut):
    api_key: str = Field(description="Shown only once. The server stores a SHA-256 hash.")


class ReadingIn(BaseModel):
    metric: str = MetricName
    value: float
    ts: datetime | None = Field(default=None, description="Defaults to the time of ingestion")

    @field_validator("value")
    @classmethod
    def finite(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("value must be a finite number")
        return v

    @field_validator("ts")
    @classmethod
    def aware(cls, v: datetime | None) -> datetime | None:
        """Store every timestamp in UTC (naive values are assumed to be UTC)."""
        if v is None:
            return v
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc)


class IngestRequest(BaseModel):
    readings: list[ReadingIn] = Field(min_length=1)


class IngestResult(BaseModel):
    accepted: int
    alerts_triggered: int


class RuleCreate(BaseModel):
    device_id: int | None = None
    metric: str = MetricName
    operator: Literal["gt", "lt"]
    threshold: float


class RuleOut(RuleCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    enabled: bool


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    rule_id: int
    device_id: int
    metric: str
    value: float
    threshold: float
    ts: datetime
    acknowledged: bool


class StatPoint(BaseModel):
    bucket: datetime
    count: int
    mean: float
    min: float
    max: float


class StatsResponse(BaseModel):
    device_id: int
    metric: str
    bucket: str
    points: list[StatPoint]


class Anomaly(BaseModel):
    ts: datetime
    value: float
    rolling_mean: float
    z_score: float


class AnomalyResponse(BaseModel):
    device_id: int
    metric: str
    window: int
    threshold: float
    checked: int
    anomalies: list[Anomaly]
