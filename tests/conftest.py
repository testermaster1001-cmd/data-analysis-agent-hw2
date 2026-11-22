from pathlib import Path
import pytest

from src.data.store import DatasetStore

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def sales_store():
    return DatasetStore.from_csv(ROOT / "data" / "sample_sales.csv")
