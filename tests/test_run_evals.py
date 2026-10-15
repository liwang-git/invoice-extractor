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
