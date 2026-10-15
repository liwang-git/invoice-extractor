"""Call the endpoint function directly: no HTTP client dependency needed."""

import anthropic
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


# --- usage log ---------------------------------------------------------------

import json
import threading

from extractor import usage_log

SECRET_VALUES = ["Cedar Park Janitorial", "CPJ-7764", "Weekly office cleaning"]


def api_rows(runs_dir):
    (path,) = list(runs_dir.glob("api-*.jsonl"))
    return [json.loads(line) for line in path.read_text().splitlines()]


def fake_billed_model(monkeypatch, model_id="claude-haiku-5-5"):
    """Stub answers, reporting 100 in / 50 out tokens on every call."""
    def get_fns(on_usage=None):
        def extract(text):
            on_usage({"input_tokens": 100, "output_tokens": 50})
            return models.stub_extract(text)

        def categorize(text):
            on_usage({"input_tokens": 100, "output_tokens": 50})
            return models.stub_categorize(text)

        return extract, categorize

    monkeypatch.setattr(app_module, "get_model_fns", get_fns)
    monkeypatch.setattr(app_module, "current_model_id", lambda: model_id)


def test_success_is_logged_with_tokens_and_cost(runs_dir, monkeypatch):
    fake_billed_model(monkeypatch)
    app_module.extract(request_for(CASES[0]))
    (row,) = api_rows(runs_dir)
    assert row["model"] == "claude-haiku-5-5"
    assert (row["input_tokens"], row["output_tokens"]) == (200, 100)
    assert row["cost_usd"] == pytest.approx(0.00007)
    assert row["http_status"] == 200
    assert row["review_reason"] is None and row["error"] is None
    assert row["latency_ms"] >= 0
    assert row["timestamp"].endswith("+00:00")


def test_flagged_invoice_logs_its_review_reason(runs_dir, monkeypatch):
    monkeypatch.setenv("MODEL", "stub")
    monkeypatch.setenv("STUB_CORRUPT", "0")
    mismatch = next(c for c in CASES if c.name == "inv_010")
    app_module.extract(request_for(mismatch))
    (row,) = api_rows(runs_dir)
    assert row["http_status"] == 200
    assert row["review_reason"] == "total_mismatch"
    assert row["model"] == "stub" and row["cost_usd"] == 0


def test_failures_are_logged_with_error_type(runs_dir, monkeypatch):
    monkeypatch.setenv("MODEL", "stub")
    with pytest.raises(HTTPException):
        app_module.extract(app_module.ExtractRequest(text="not an eval invoice"))
    (row,) = api_rows(runs_dir)
    assert row["http_status"] == 400
    assert row["error"] == "UnknownInvoice"


def test_a_billed_call_that_then_fails_is_still_recorded(runs_dir, monkeypatch):
    def get_fns(on_usage=None):
        def extract(text):
            on_usage({"input_tokens": 300, "output_tokens": 0})
            raise anthropic.APIError("boom", request=None, body=None)
        return extract, lambda t: "x"

    monkeypatch.setattr(app_module, "get_model_fns", get_fns)
    monkeypatch.setattr(app_module, "current_model_id", lambda: "claude-haiku-5-5")
    with pytest.raises(HTTPException) as err:
        app_module.extract(request_for(CASES[0]))
    assert err.value.status_code == 502
    assert err.value.detail == "model call failed: APIError"
    (row,) = api_rows(runs_dir)
    assert row["input_tokens"] == 300 and row["http_status"] == 502
    assert row["error"] == "APIError"


def test_log_never_contains_invoice_text(runs_dir, monkeypatch):
    fake_billed_model(monkeypatch)
    cedar = next(c for c in CASES if c.name == "inv_010")
    app_module.extract(request_for(cedar))
    (path,) = list(runs_dir.glob("api-*.jsonl"))
    raw = path.read_text()
    for value in SECRET_VALUES:
        assert value not in raw


def test_a_broken_log_does_not_break_the_request(runs_dir, monkeypatch):
    monkeypatch.setenv("MODEL", "stub")
    monkeypatch.setenv("STUB_CORRUPT", "0")

    def broken(path, record):
        raise OSError("disk full")

    monkeypatch.setattr(app_module, "append_record", broken)
    result = app_module.extract(request_for(CASES[0]))
    assert result["vendor"] == "Northwind Cloud Hosting"


def test_concurrent_writes_do_not_interleave(tmp_path):
    path = tmp_path / "log.jsonl"
    padding = "x" * 5000  # long lines make interleaving likely if unguarded

    def write(i):
        usage_log.append_record(path, {"i": i, "padding": padding})

    threads = [threading.Thread(target=write, args=(i,)) for i in range(60)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert sorted(r["i"] for r in rows) == list(range(60))
