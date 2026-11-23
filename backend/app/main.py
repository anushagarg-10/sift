import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, sessionmaker

from app import db as db_module
from app.config import Settings, get_settings
from app.evals import load_golden, run_eval
from app.ingest import IngestError, parse_csv
from app.llm.providers import LLMProvider, get_provider
from app.models import Dataset, Enrichment, EvalRun, Record
from app.schemas import (
    AppConfig,
    DatasetCreated,
    DatasetDetail,
    DatasetOut,
    EvalRunOut,
    RecordPage,
)
from app.services import dataset_stats, enrich_dataset

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_: FastAPI):
    db_module.init_db()
    yield


app = FastAPI(
    title="Sift API",
    description="Ingest customer feedback CSVs, enrich them with an LLM, and evaluate the results.",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in get_settings().cors_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)


# Dependencies (overridden in tests)
def get_llm_provider(settings: Settings = Depends(get_settings)) -> LLMProvider:
    return get_provider(settings)


def get_session_factory() -> sessionmaker:
    return db_module.SessionLocal


def _get_dataset(db: Session, dataset_id: int) -> Dataset:
    dataset = db.get(Dataset, dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return dataset


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/config", response_model=AppConfig)
def config(provider: LLMProvider = Depends(get_llm_provider)) -> AppConfig:
    return AppConfig(provider=provider.name, model=provider.model)


@app.post("/datasets", response_model=DatasetCreated, status_code=201)
async def upload_dataset(
    file: UploadFile = File(...),
    name: str | None = Form(None),
    db: Session = Depends(db_module.get_db),
    settings: Settings = Depends(get_settings),
) -> Dataset:
    filename = file.filename or "upload.csv"
    if not filename.lower().endswith(".csv"):
        raise HTTPException(status_code=415, detail="Only .csv files are supported")

    raw = await file.read(settings.max_upload_bytes + 1)
    if len(raw) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="File is too large")

    try:
        parsed = parse_csv(raw, max_text_chars=settings.max_text_chars)
    except IngestError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    dataset = Dataset(
        name=(name or Path(filename).stem).strip()[:255] or "Untitled",
        filename=filename[:255],
        row_count=len(parsed.rows),
        rejected_count=len(parsed.rejected),
        rejected_rows=parsed.rejected,
    )
    dataset.records = [
        Record(external_id=r.external_id, text=r.text, customer=r.customer, channel=r.channel)
        for r in parsed.rows
    ]
    db.add(dataset)
    db.commit()
    db.refresh(dataset)
    return dataset


@app.get("/datasets", response_model=list[DatasetOut])
def list_datasets(db: Session = Depends(db_module.get_db)) -> list[Dataset]:
    return list(db.scalars(select(Dataset).order_by(Dataset.created_at.desc(), Dataset.id.desc())))


@app.get("/datasets/{dataset_id}", response_model=DatasetDetail)
def get_dataset(dataset_id: int, db: Session = Depends(db_module.get_db)) -> dict:
    dataset = _get_dataset(db, dataset_id)
    out = DatasetCreated.model_validate(dataset).model_dump()
    out["stats"] = dataset_stats(db, dataset_id)
    return out


@app.delete("/datasets/{dataset_id}", status_code=204)
def delete_dataset(dataset_id: int, db: Session = Depends(db_module.get_db)) -> None:
    db.delete(_get_dataset(db, dataset_id))
    db.commit()


@app.get("/datasets/{dataset_id}/records", response_model=RecordPage)
def list_records(
    dataset_id: int,
    sentiment: str | None = None,
    category: str | None = None,
    min_urgency: int | None = Query(None, ge=1, le=5),
    status: str | None = Query(None, pattern="^(ok|failed)$"),
    q: str | None = Query(None, max_length=200),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(db_module.get_db),
) -> dict:
    _get_dataset(db, dataset_id)
    stmt = select(Record).where(Record.dataset_id == dataset_id)
    if any(v is not None for v in (sentiment, category, min_urgency, status)):
        stmt = stmt.join(Enrichment)
    if sentiment:
        stmt = stmt.where(Enrichment.sentiment == sentiment)
    if category:
        stmt = stmt.where(Enrichment.category == category)
    if min_urgency:
        stmt = stmt.where(Enrichment.urgency >= min_urgency)
    if status:
        stmt = stmt.where(Enrichment.status == status)
    if q:
        stmt = stmt.where(Record.text.ilike(f"%{q}%"))

    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    items = db.scalars(
        stmt.options(joinedload(Record.enrichment)).order_by(Record.id).limit(limit).offset(offset)
    ).all()
    return {"total": total, "items": items}


@app.post("/datasets/{dataset_id}/enrich", response_model=DatasetOut, status_code=202)
def start_enrichment(
    dataset_id: int,
    background: BackgroundTasks,
    db: Session = Depends(db_module.get_db),
    provider: LLMProvider = Depends(get_llm_provider),
    session_factory: sessionmaker = Depends(get_session_factory),
    settings: Settings = Depends(get_settings),
) -> Dataset:
    dataset = _get_dataset(db, dataset_id)
    if dataset.status == "processing":
        raise HTTPException(status_code=409, detail="Enrichment already in progress")
    dataset.status = "queued"
    db.commit()
    background.add_task(
        enrich_dataset,
        session_factory,
        dataset_id,
        provider,
        max_workers=settings.llm_max_workers,
        max_retries=settings.llm_max_retries,
    )
    return dataset


@app.post("/evals/run", response_model=EvalRunOut, status_code=201)
def create_eval_run(
    db: Session = Depends(db_module.get_db),
    provider: LLMProvider = Depends(get_llm_provider),
    settings: Settings = Depends(get_settings),
) -> EvalRun:
    report = run_eval(provider, load_golden(), max_retries=settings.llm_max_retries)
    run = EvalRun(provider=provider.name, model=provider.model, **report)
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


@app.get("/evals", response_model=list[EvalRunOut])
def list_eval_runs(db: Session = Depends(db_module.get_db)) -> list[EvalRun]:
    return list(db.scalars(select(EvalRun).order_by(EvalRun.id.desc()).limit(20)))
