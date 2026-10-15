import json
from pathlib import Path

import pytest

from extractor.models import (bedrock_extract, get_model_fns, stub_categorize,
                              stub_extract)
from extractor.validate import check_schema, process

CASES_DIR = Path(__file__).parent.parent / "evals" / "cases"
CASE_DIRS = sorted(CASES_DIR.iterdir())


def load(case_dir):
    text = (case_dir / "invoice.txt").read_text()
    expected = json.loads((case_dir / "expected.json").read_text())
    return text, expected


@pytest.mark.parametrize("case_dir", CASE_DIRS, ids=lambda p: p.name)
def test_stub_output_passes_through_process_unchanged(case_dir):
    text, expected = load(case_dir)
    result = process(text, stub_extract)
    assert result["vendor"] == expected["vendor"]
    assert result["needs_review"] == expected["needs_review"]
    assert result["review_reason"] == expected["review_reason"]


@pytest.mark.parametrize("case_dir", CASE_DIRS, ids=lambda p: p.name)
def test_stub_categorize_matches_expected(case_dir):
    text, expected = load(case_dir)
    assert stub_categorize(text) == expected["category"]


def test_full_corruption_changes_every_field_but_stays_schema_valid():
    text, expected = load(CASE_DIRS[0])
    data = json.loads(stub_extract(text, corrupt=1.0))
    assert check_schema(data) == []
    for field in ("vendor", "invoice_number", "invoice_date", "total"):
        assert data[field] != expected[field]
    assert stub_categorize(text, corrupt=1.0) != expected["category"]


def test_corruption_is_reproducible():
    text, _ = load(CASE_DIRS[0])
    assert stub_extract(text, corrupt=0.5) == stub_extract(text, corrupt=0.5)


def test_unknown_invoice_is_an_error():
    with pytest.raises(KeyError):
        stub_extract("not one of the eval invoices")


def test_bedrock_placeholder_raises():
    with pytest.raises(NotImplementedError):
        bedrock_extract("anything")


def test_model_setting_defaults_to_stub(monkeypatch):
    monkeypatch.delenv("MODEL", raising=False)
    extract_fn, _ = get_model_fns()
    text, _ = load(CASE_DIRS[0])
    assert check_schema(json.loads(extract_fn(text))) == []


def test_unknown_model_setting_is_an_error(monkeypatch):
    monkeypatch.setenv("MODEL", "gpt-whatever")
    with pytest.raises(ValueError):
        get_model_fns()
