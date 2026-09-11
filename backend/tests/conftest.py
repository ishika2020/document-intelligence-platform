"""Shared pytest fixtures. Isolates tests from the developer's local DB by
pointing DATABASE_URL at a throwaway SQLite file before the app is imported."""
import os
from pathlib import Path

TEST_DB_PATH = Path(__file__).resolve().parent / "_test_data" / "test.db"
TEST_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
if TEST_DB_PATH.exists():
    TEST_DB_PATH.unlink()

os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH.as_posix()}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

SAMPLE_DOCS_DIR = Path(__file__).resolve().parent.parent.parent / "sample_documents"


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def sample_docs_dir() -> Path:
    return SAMPLE_DOCS_DIR
