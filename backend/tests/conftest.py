import os
import tempfile
from pathlib import Path

# Must be set before the app (and its engine) are imported.
# CI points TEST_DATABASE_URL at a real Postgres service; locally we fall back to SQLite.
_tmp = Path(tempfile.mkdtemp()) / "test.db"
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", f"sqlite:///{_tmp}")
os.environ["LLM_PROVIDER"] = "mock"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import db as db_module  # noqa: E402
from app.main import app, get_llm_provider  # noqa: E402

SAMPLE = Path(__file__).resolve().parents[1] / "sample_data" / "feedback.csv"


@pytest.fixture(autouse=True)
def fresh_db():
    from app import models  # noqa: F401

    db_module.Base.metadata.drop_all(bind=db_module.engine)
    db_module.Base.metadata.create_all(bind=db_module.engine)
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def use_provider():
    """Swap the LLM provider for the duration of a test."""

    def _set(provider):
        app.dependency_overrides[get_llm_provider] = lambda: provider
        return provider

    return _set


def upload(client, content: str | bytes, filename: str = "feedback.csv", name: str | None = None):
    if isinstance(content, str):
        content = content.encode()
    data = {"name": name} if name else {}
    return client.post("/datasets", files={"file": (filename, content, "text/csv")}, data=data)
