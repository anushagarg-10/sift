from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class RejectedRow(BaseModel):
    line: int
    id: str | None = None
    reason: str


class DatasetOut(ORM):
    id: int
    name: str
    filename: str
    status: str
    row_count: int
    rejected_count: int
    created_at: datetime


class DatasetCreated(DatasetOut):
    rejected_rows: list[RejectedRow]


class DatasetStats(BaseModel):
    enriched: int
    failed: int
    by_sentiment: dict[str, int]
    by_category: dict[str, int]
    by_urgency: dict[str, int]
    avg_confidence: float | None
    high_urgency: int
    input_tokens: int
    output_tokens: int
    avg_latency_ms: int | None


class DatasetDetail(DatasetCreated):
    stats: DatasetStats


class EnrichmentOut(ORM):
    status: str
    sentiment: str | None
    category: str | None
    urgency: int | None
    summary: str | None
    confidence: float | None
    error: str | None
    provider: str
    model: str
    attempts: int
    latency_ms: int


class RecordOut(ORM):
    id: int
    external_id: str
    text: str
    customer: str | None
    channel: str | None
    enrichment: EnrichmentOut | None


class RecordPage(BaseModel):
    total: int
    items: list[RecordOut]


class EvalRunOut(ORM):
    id: int
    provider: str
    model: str
    cases: int
    metrics: dict
    failures: list
    created_at: datetime


class AppConfig(BaseModel):
    provider: str
    model: str
