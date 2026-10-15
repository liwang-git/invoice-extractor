"""Call the endpoint function directly: no HTTP client dependency needed."""

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

import app as app_module
from extractor import models

CASES = sorted(models.CASES_DIR.iterdir())


def request_for(case_dir):
    return app_module.ExtractRequest(text=(case_dir / "invoice.txt").read_text())


def test_known_invoice_returns_processed_json(monkeypatch):
    monkeypatch.setenv("MODEL", "stub")
    monkeypatch.setenv("STUB_CORRUPT", "0")
    result = app_module.extract(request_for(CASES[0]))
    assert result["vendor"] == "Northwind Cloud Hosting"
    assert result["category"] == "Software & SaaS"
    assert result["needs_review"] is False and result["review_reason"] is None


def test_flagged_invoice_is_a_normal_result_not_an_error(monkeypatch):
    monkeypatch.setenv("MODEL", "stub")
    monkeypatch.setenv("STUB_CORRUPT", "0")
    mismatch = next(c for c in CASES if c.name == "inv_010")
    result = app_module.extract(request_for(mismatch))
    assert result["needs_review"] is True
    assert result["review_reason"] == "total_mismatch"


def test_unknown_text_with_stub_is_a_400(monkeypatch):
    monkeypatch.setenv("MODEL", "stub")
    with pytest.raises(HTTPException) as err:
        app_module.extract(app_module.ExtractRequest(text="not an eval invoice"))
    assert err.value.status_code == 400
    assert err.value.detail.startswith("the stub model only knows")  # no stray quotes
    assert "MODEL=anthropic" in err.value.detail


def test_bedrock_placeholder_is_a_501(monkeypatch):
    monkeypatch.setenv("MODEL", "bedrock")
    with pytest.raises(HTTPException) as err:
        app_module.extract(request_for(CASES[0]))
    assert err.value.status_code == 501


def test_empty_text_is_rejected_by_validation():
    with pytest.raises(ValidationError):
        app_module.ExtractRequest(text="")
