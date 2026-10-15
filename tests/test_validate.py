import json
from pathlib import Path

import pytest

from extractor.validate import EXTRACT_KEYS, check_review, check_schema, process

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


def test_check_schema_accepts_null_invoice_number():
    data = valid_extraction()
    data["invoice_number"] = None
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
    ("invoice_number", 20931, "invoice_number: expected a non-empty string or null"),
    ("invoice_number", "", "invoice_number: expected a non-empty string or null"),
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
        "line_items[0].amount: expected a number",
        "line_items[1]: missing key 'description'",
        "line_items[2]: expected an object",
    ]


def test_check_schema_allows_negative_line_item_amount():
    data = valid_extraction()
    data["line_items"].append({"description": "Loyalty credit", "amount": -25.0})
    assert check_schema(data) == []


def test_check_schema_still_rejects_negative_tax():
    data = valid_extraction()
    data["tax"] = -1.0
    assert check_schema(data) == ["tax: expected a non-negative number"]


# --- check_review (totals checks, then the invoice number) ---------------


# parametrize turns one test function into one test per eval case, so a
# failure report names the exact invoice that broke (e.g. [inv_010]).
@pytest.mark.parametrize("case_dir", CASE_DIRS, ids=lambda p: p.name)
def test_check_review_matches_expected(case_dir):
    expected = load_expected(case_dir)
    assert check_review(expected) == expected["review_reason"]


def test_money_problems_take_precedence_over_missing_number():
    data = valid_extraction()
    data["invoice_number"] = None
    data["total"] = 999.0
    assert check_review(data) == "total_mismatch"
    data["total"] = None
    assert check_review(data) == "missing_total"


def test_missing_number_alone_is_flagged():
    data = valid_extraction()
    data["invoice_number"] = None
    assert check_review(data) == "missing_invoice_number"


# --- process --------------------------------------------------------------

def fake_model(*responses):
    """Build a stand-in for the model that replays canned responses.

    Returns the fake extract_fn and the list it records calls into, so a
    test can assert how many times the "model" was asked. After the last
    response it keeps repeating that one.
    """
    calls = []

    def extract_fn(invoice_text):
        calls.append(invoice_text)
        return responses[min(len(calls), len(responses)) - 1]

    return extract_fn, calls


GOOD_OUTPUT = json.dumps(valid_extraction())


def test_process_valid_first_time_does_not_retry():
    extract_fn, calls = fake_model(GOOD_OUTPUT)
    result = process("invoice text", extract_fn)
    assert len(calls) == 1
    assert result == {**valid_extraction(), "needs_review": False, "review_reason": None}


def test_process_retries_once_then_succeeds():
    extract_fn, calls = fake_model("Sure! Here is the JSON: {", GOOD_OUTPUT)
    result = process("invoice text", extract_fn)
    assert calls == ["invoice text", "invoice text"]  # exactly one retry
    assert result == {**valid_extraction(), "needs_review": False, "review_reason": None}


def test_process_flags_invalid_output_when_retry_also_fails():
    broken = valid_extraction()
    del broken["total"]
    extract_fn, calls = fake_model(json.dumps(broken))
    result = process("invoice text", extract_fn)
    assert len(calls) == 2  # one try, one retry, then give up
    assert result == {
        "needs_review": True,
        "review_reason": "invalid_output",
        "problems": ["top level: missing key 'total'"],
    }


def test_process_does_not_retry_on_total_mismatch():
    mismatched = valid_extraction()
    mismatched["total"] = 999.0
    extract_fn, calls = fake_model(json.dumps(mismatched))
    result = process("invoice text", extract_fn)
    assert len(calls) == 1  # valid schema: the numbers go to a human, not the model
    assert result["needs_review"] is True
    assert result["review_reason"] == "total_mismatch"


@pytest.mark.parametrize("case_dir", CASE_DIRS, ids=lambda p: p.name)
def test_process_with_perfect_model_matches_expected(case_dir):
    # A "perfect" model returns exactly the expected extraction, so any
    # difference here comes from our code, not the model.
    expected = load_expected(case_dir)
    extract_fn, _ = fake_model(json.dumps(extraction_only(expected)))
    result = process((case_dir / "invoice.txt").read_text(), extract_fn)
    assert result["needs_review"] == expected["needs_review"]
    assert result["review_reason"] == expected["review_reason"]
