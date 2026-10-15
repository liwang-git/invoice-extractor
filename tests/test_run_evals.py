import run_evals


def make_expected(**overrides):
    base = {"vendor": "Mesa Wireless", "invoice_number": "ab-1",
            "invoice_date": "2026-01-01",
            "line_items": [{"description": "Plan", "amount": 9.9},
                          {"description": "Fee", "amount": 0.2}],
            "tax": 0.0, "total": 10.1, "category": "Telecom",
            "needs_review": False, "review_reason": None}
    return {**base, **overrides}


def test_exact_match_has_no_mismatches():
    expected = make_expected()
    assert run_evals.mismatched_fields(dict(expected), expected) == []


def test_missing_and_wrong_fields_are_reported():
    expected = make_expected()
    actual = make_expected(vendor="Other")
    del actual["category"]
    assert run_evals.mismatched_fields(actual, expected) == ["vendor", "category"]


def test_total_null_only_matches_null():
    base = make_expected(total=None, needs_review=True,
                         review_reason="missing_total")
    assert run_evals.mismatched_fields(dict(base), base) == []
    assert run_evals.mismatched_fields({**base, "total": 0}, base) == ["total"]


def test_vendor_ignores_case_but_other_text_fields_do_not():
    base = make_expected()
    assert run_evals.mismatched_fields({**base, "vendor": "MESA WIRELESS"}, base) == []
    assert run_evals.mismatched_fields({**base, "vendor": "Mesa Wireles"}, base) == ["vendor"]
    assert run_evals.mismatched_fields({**base, "invoice_number": "AB-1"}, base) == ["invoice_number"]


def test_line_items_compare_amounts_exactly_and_descriptions_loosely():
    base = make_expected()
    shouted = [{"description": "PLAN", "amount": 9.9},
               {"description": " fee ", "amount": 0.2}]
    assert run_evals.mismatched_fields({**base, "line_items": shouted}, base) == []

    wrong_amount = [{"description": "Plan", "amount": 9.91},
                    {"description": "Fee", "amount": 0.2}]
    assert run_evals.mismatched_fields({**base, "line_items": wrong_amount}, base) == ["line_items"]


def test_line_items_missing_extra_or_reordered_count_as_wrong():
    base = make_expected()
    items = base["line_items"]
    for bad in (items[:1], items + [{"description": "Extra", "amount": 1.0}],
                list(reversed(items))):
        assert run_evals.mismatched_fields({**base, "line_items": bad}, base) == ["line_items"]


def test_tax_is_compared_as_money():
    base = make_expected(tax=0.1)
    assert run_evals.mismatched_fields({**base, "tax": 0.1}, base) == []
    assert run_evals.mismatched_fields({**base, "tax": 0.2}, base) == ["tax"]


def test_review_reason_must_match_not_just_needs_review():
    base = make_expected(needs_review=True, review_reason="total_mismatch")
    swapped = {**base, "review_reason": "missing_total"}
    assert run_evals.mismatched_fields(swapped, base) == ["review_reason"]


def test_clean_stub_run_exits_zero(monkeypatch, capsys):
    monkeypatch.setenv("MODEL", "stub")
    monkeypatch.setenv("STUB_CORRUPT", "0")
    assert run_evals.main() == 0
    assert "Accuracy: 100.0%" in capsys.readouterr().out


def test_corrupted_stub_run_exits_one(monkeypatch, capsys):
    monkeypatch.setenv("MODEL", "stub")
    monkeypatch.setenv("STUB_CORRUPT", "1")
    assert run_evals.main() == 1
    assert "FAILED" in capsys.readouterr().out


# --- run log and summary ---------------------------------------------------

import json
from decimal import Decimal

import pytest


def read_log(runs_dir):
    (path,) = list(runs_dir.glob("*.jsonl"))
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_percentile_uses_nearest_rank():
    values = list(range(1, 21))  # 1..20
    assert run_evals.percentile(values, 50) == 10
    assert run_evals.percentile(values, 95) == 19
    assert run_evals.percentile(list(reversed(values)), 95) == 19  # order-free
    assert run_evals.percentile([7], 95) == 7


def test_run_writes_one_log_line_per_case(runs_dir, monkeypatch):
    monkeypatch.setenv("MODEL", "stub")
    monkeypatch.setenv("STUB_CORRUPT", "0")
    run_evals.main()
    rows = read_log(runs_dir)
    assert len(rows) == len(list(run_evals.CASES_DIR.iterdir()))
    first = rows[0]
    assert set(first) == {"case", "model", "input_tokens", "output_tokens",
                          "cost_usd", "latency_ms", "passed", "wrong_fields"}
    assert first["model"] == "stub"
    assert first["input_tokens"] == first["output_tokens"] == 0
    assert first["cost_usd"] == 0
    assert first["passed"] is True and first["wrong_fields"] == []


def test_log_records_failures(runs_dir, monkeypatch):
    monkeypatch.setenv("MODEL", "stub")
    monkeypatch.setenv("STUB_CORRUPT", "1")
    run_evals.main()
    assert not any(row["passed"] for row in read_log(runs_dir))


def fake_billed_model(monkeypatch, model_id):
    """A stub that also reports 100 in / 50 out tokens on every call."""
    from extractor import models

    def get_fns(on_usage=None):
        def extract(text):
            on_usage({"input_tokens": 100, "output_tokens": 50})
            return models.stub_extract(text)

        def categorize(text):
            on_usage({"input_tokens": 100, "output_tokens": 50})
            return models.stub_categorize(text)

        return extract, categorize

    monkeypatch.setattr(run_evals, "get_model_fns", get_fns)
    monkeypatch.setattr(run_evals, "current_model_id", lambda: model_id)


def test_tokens_are_summed_per_case_and_priced(runs_dir, monkeypatch, capsys):
    fake_billed_model(monkeypatch, "claude-haiku-5-5")
    run_evals.main()
    row = read_log(runs_dir)[0]
    assert row["input_tokens"] == 200 and row["output_tokens"] == 100  # extract + categorize
    # 200 * $0.10/M + 100 * $0.50/M = $0.00007
    assert Decimal(str(row["cost_usd"])) == Decimal("0.00007")
    out = capsys.readouterr().out
    assert "Avg cost per invoice: $0.000070" in out
    assert "p50" in out and "p95" in out


def test_unknown_model_logs_null_cost_and_says_so(runs_dir, monkeypatch, capsys):
    fake_billed_model(monkeypatch, "mystery-model")
    run_evals.main()
    assert read_log(runs_dir)[0]["cost_usd"] is None
    assert "Cost: n/a" in capsys.readouterr().out
