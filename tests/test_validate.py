import json
from pathlib import Path

import pytest

from extractor.validate import EXTRACT_KEYS, check_schema, check_totals

CASES_DIR = Path(__file__).parent.parent / "evals" / "cases"
CASE_DIRS = sorted(CASES_DIR.iterdir())


def load_expected(case_dir):
    return json.loads((case_dir / "expected.json").read_text())


def extraction_only(expected):
    """The part of expected.json that LLM step 1 is responsible for."""
    return {k: v for k, v in expected.items() if k in EXTRACT_KEYS}


def valid_extraction():
    """A known-good extraction to break one field at a time."""
    return {
        "vendor": "Northwind Cloud Hosting",
        "invoice_number": "NCH-20931",
        "invoice_date": "2026-09-01",
        "line_items": [{"description": "Compute plan", "amount": 420.0}],
        "tax": 0.0,
        "total": 420.0,
    }


# --- check_schema ---------------------------------------------------------

@pytest.mark.parametrize("case_dir", CASE_DIRS, ids=lambda p: p.name)
def test_check_schema_accepts_every_expected_case(case_dir):
    assert check_schema(extraction_only(load_expected(case_dir))) == []


def test_check_schema_accepts_null_total():
    data = valid_extraction()
    data["total"] = None
    assert check_schema(data) == []


def test_check_schema_rejects_non_object():
    assert check_schema(["not", "a", "dict"]) == [
        "top level: expected an object, got list"
    ]


def test_check_schema_reports_missing_and_unexpected_keys():
    data = valid_extraction()
    del data["total"]
    data["category"] = "Travel"  # belongs to LLM step 2, not step 1
    assert check_schema(data) == [
        "top level: missing key 'total'",
        "top level: unexpected key 'category'",
    ]


# Each row breaks exactly one field, so a failure points at one rule.
@pytest.mark.parametrize("field, bad_value, problem", [
    ("vendor", "", "vendor: expected a non-empty string"),
    ("invoice_number", 20931, "invoice_number: expected a non-empty string"),
    ("invoice_date", "09/01/2026", "invoice_date: expected YYYY-MM-DD"),
    ("invoice_date", "2026-02-30", "invoice_date: 2026-02-30 is not a real date"),
    ("line_items", [], "line_items: expected a non-empty list"),
    ("tax", "0.00", "tax: expected a non-negative number"),
    ("tax", True, "tax: expected a non-negative number"),
    ("total", -420.0, "total: expected a non-negative number or null"),
    ("total", float("nan"), "total: expected a non-negative number or null"),
])
def test_check_schema_rejects_bad_field(field, bad_value, problem):
    data = valid_extraction()
    data[field] = bad_value
    assert check_schema(data) == [problem]


def test_check_schema_checks_inside_line_items():
    data = valid_extraction()
    data["line_items"] = [
        {"description": "Compute plan", "amount": "420.00"},
        {"amount": 85.5},
        "Priority support",
    ]
    assert check_schema(data) == [
        "line_items[0].amount: expected a non-negative number",
        "line_items[1]: missing key 'description'",
        "line_items[2]: expected an object",
    ]


# --- check_totals ---------------------------------------------------------


# parametrize turns one test function into one test per eval case, so a
# failure report names the exact invoice that broke (e.g. [inv_010]).
@pytest.mark.parametrize("case_dir", CASE_DIRS, ids=lambda p: p.name)
def test_check_totals_matches_expected(case_dir):
    expected = load_expected(case_dir)
    assert check_totals(expected) == expected["review_reason"]
