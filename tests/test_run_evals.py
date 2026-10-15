import run_evals


def test_exact_match_has_no_mismatches():
    expected = {"vendor": "A", "invoice_number": "1", "invoice_date": "2026-01-01",
                "total": 10.1, "category": "Travel", "needs_review": False}
    assert run_evals.mismatched_fields(dict(expected), expected) == []


def test_missing_and_wrong_fields_are_reported():
    expected = {"vendor": "A", "invoice_number": "1", "invoice_date": "2026-01-01",
                "total": 10.0, "category": "Travel", "needs_review": False}
    actual = {"vendor": "B", "invoice_number": "1", "invoice_date": "2026-01-01",
              "total": 10.0, "needs_review": False}  # no category
    assert run_evals.mismatched_fields(actual, expected) == ["vendor", "category"]


def test_total_null_only_matches_null():
    base = {"vendor": "A", "invoice_number": "1", "invoice_date": "2026-01-01",
            "category": "Travel", "needs_review": True}
    assert run_evals.mismatched_fields({**base, "total": None}, {**base, "total": None}) == []
    assert run_evals.mismatched_fields({**base, "total": 0}, {**base, "total": None}) == ["total"]


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
