"""Enrichment pipeline: call the provider, validate, retry, persist."""

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from pydantic import ValidationError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.llm.providers import LLMProvider, ProviderError
from app.llm.schema import EnrichmentResult
from app.models import Dataset, Enrichment, Record

log = logging.getLogger(__name__)


@dataclass
class EnrichOutcome:
    result: EnrichmentResult | None
    error: str | None
    attempts: int
    input_tokens: int
    output_tokens: int
    latency_ms: int

    @property
    def ok(self) -> bool:
        return self.result is not None


def _format_validation_error(exc: ValidationError) -> str:
    parts = [f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()]
    return "Schema validation failed: " + "; ".join(parts)


def enrich_text(provider: LLMProvider, text: str, max_retries: int = 1) -> EnrichOutcome:
    """Classify one text. Output that fails validation is retried up to `max_retries` times."""
    attempts = 0
    in_tok = out_tok = 0
    error: str | None = None
    started = time.perf_counter()

    while attempts <= max_retries:
        attempts += 1
        try:
            response = provider.classify(text)
        except ProviderError as exc:
            error = str(exc)
            break  # transport-level retries are handled by the SDK itself
        in_tok += response.usage.input_tokens
        out_tok += response.usage.output_tokens
        try:
            result = EnrichmentResult.model_validate(response.raw)
        except ValidationError as exc:
            error = _format_validation_error(exc)
            log.warning("Invalid LLM output (attempt %d): %s", attempts, error)
            continue
        return EnrichOutcome(
            result, None, attempts, in_tok, out_tok, int((time.perf_counter() - started) * 1000)
        )

    return EnrichOutcome(
        None, error, attempts, in_tok, out_tok, int((time.perf_counter() - started) * 1000)
    )


def enrich_dataset(
    session_factory: sessionmaker,
    dataset_id: int,
    provider: LLMProvider,
    max_workers: int = 4,
    max_retries: int = 1,
) -> None:
    """Enrich every record in a dataset. Runs in a background task with its own session."""
    with session_factory() as db:
        dataset = db.get(Dataset, dataset_id)
        if dataset is None:
            return
        dataset.status = "processing"
        db.execute(
            delete(Enrichment).where(
                Enrichment.record_id.in_(select(Record.id).where(Record.dataset_id == dataset_id))
            )
        )
        db.commit()

        records = list(db.scalars(select(Record).where(Record.dataset_id == dataset_id)))
        texts = [(r.id, r.text) for r in records]

    try:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            outcomes = list(
                pool.map(lambda item: (item[0], enrich_text(provider, item[1], max_retries)), texts)
            )

        with session_factory() as db:
            for record_id, outcome in outcomes:
                db.add(_to_row(record_id, outcome, provider))
            dataset = db.get(Dataset, dataset_id)
            dataset.status = "enriched"
            db.commit()
    except Exception:
        log.exception("Enrichment failed for dataset %s", dataset_id)
        with session_factory() as db:
            dataset = db.get(Dataset, dataset_id)
            if dataset:
                dataset.status = "error"
                db.commit()
        raise


def _to_row(record_id: int, outcome: EnrichOutcome, provider: LLMProvider) -> Enrichment:
    r = outcome.result
    return Enrichment(
        record_id=record_id,
        status="ok" if r else "failed",
        sentiment=r.sentiment if r else None,
        category=r.category if r else None,
        urgency=r.urgency if r else None,
        summary=r.summary if r else None,
        confidence=r.confidence if r else None,
        error=outcome.error,
        provider=provider.name,
        model=provider.model,
        attempts=outcome.attempts,
        input_tokens=outcome.input_tokens,
        output_tokens=outcome.output_tokens,
        latency_ms=outcome.latency_ms,
    )


def dataset_stats(db: Session, dataset_id: int) -> dict:
    rows = (
        db.execute(select(Enrichment).join(Record).where(Record.dataset_id == dataset_id))
        .scalars()
        .all()
    )
    ok = [e for e in rows if e.status == "ok"]

    def count(attr: str) -> dict[str, int]:
        out: dict[str, int] = {}
        for e in ok:
            key = str(getattr(e, attr))
            out[key] = out.get(key, 0) + 1
        return dict(sorted(out.items()))

    return {
        "enriched": len(ok),
        "failed": len(rows) - len(ok),
        "by_sentiment": count("sentiment"),
        "by_category": count("category"),
        "by_urgency": count("urgency"),
        "avg_confidence": round(sum(e.confidence for e in ok) / len(ok), 3) if ok else None,
        "high_urgency": sum(1 for e in ok if e.urgency >= 4),
        "input_tokens": sum(e.input_tokens for e in rows),
        "output_tokens": sum(e.output_tokens for e in rows),
        "avg_latency_ms": round(sum(e.latency_ms for e in rows) / len(rows)) if rows else None,
    }
