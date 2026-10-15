"""Code checks for extracted invoice data.

Design rule: code decides, the model only reads. Every accept, reject or
flag decision in the pipeline is made here, in plain Python.
"""

import json
import math
import re
from datetime import datetime
from decimal import Decimal

# The fields LLM step 1 must return. category comes later (LLM step 2), and
# needs_review / review_reason are set by code, so none of those belong here.
EXTRACT_KEYS = {"vendor", "invoice_number", "invoice_date",
                "line_items", "tax", "total"}
LINE_ITEM_KEYS = {"description", "amount"}
DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")


def _is_number(value):
    """True for a finite JSON number of either sign.

    bool is excluded on purpose: in Python, True is an int (True == 1).
    Non-finite values are excluded because json.loads accepts NaN and Infinity.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(value)


def _is_amount(value):
    """True for a finite, non-negative JSON number (tax and total)."""
    return _is_number(value) and value >= 0


def _is_text(value):
    return isinstance(value, str) and value.strip() != ""


def _check_keys(obj, expected, where):
    problems = []
    for key in sorted(expected - obj.keys()):
        problems.append(f"{where}: missing key '{key}'")
    for key in sorted(obj.keys() - expected):
        problems.append(f"{where}: unexpected key '{key}'")
    return problems


def check_schema(data):
    """Check the shape of the model's extraction output.

    Returns a list of human-readable problems; an empty list means valid.
    Collecting every problem (rather than stopping at the first) gives a
    reviewer the full picture in one go.
    """
    if not isinstance(data, dict):
        return [f"top level: expected an object, got {type(data).__name__}"]

    problems = _check_keys(data, EXTRACT_KEYS, "top level")

    for key in ("vendor", "invoice_number"):
        if key in data and not _is_text(data[key]):
            problems.append(f"{key}: expected a non-empty string")

    if "invoice_date" in data:
        date = data["invoice_date"]
        # fullmatch for the exact shape, then strptime to reject 2026-02-30.
        if not isinstance(date, str) or not DATE_PATTERN.fullmatch(date):
            problems.append("invoice_date: expected YYYY-MM-DD")
        else:
            try:
                datetime.strptime(date, "%Y-%m-%d")
            except ValueError:
                problems.append(f"invoice_date: {date} is not a real date")

    if "line_items" in data:
        items = data["line_items"]
        if not isinstance(items, list) or not items:
            problems.append("line_items: expected a non-empty list")
        else:
            for i, item in enumerate(items):
                where = f"line_items[{i}]"
                if not isinstance(item, dict):
                    problems.append(f"{where}: expected an object")
                    continue
                problems += _check_keys(item, LINE_ITEM_KEYS, where)
                if "description" in item and not _is_text(item["description"]):
                    problems.append(f"{where}.description: expected a non-empty string")
                # Negative is allowed here: credits and discounts are normal
                # line items. tax and total below stay non-negative.
                if "amount" in item and not _is_number(item["amount"]):
                    problems.append(f"{where}.amount: expected a number")

    if "tax" in data and not _is_amount(data["tax"]):
        problems.append("tax: expected a non-negative number")

    # total is the one field allowed to be null: "this invoice states no total".
    if "total" in data and data["total"] is not None and not _is_amount(data["total"]):
        problems.append("total: expected a non-negative number or null")

    return problems


def _money(value):
    """Turn a JSON number into an exact Decimal.

    Going through str() matters: Decimal(64.9) keeps the float's binary
    error (64.900000000000005684...), while Decimal("64.9") is exactly 64.9.
    """
    return Decimal(str(value))


def check_totals(data):
    """Check that line items plus tax equal the stated total.

    Expects data that has already passed check_schema. Returns None when the
    numbers add up, "missing_total" when the invoice states no total, or
    "total_mismatch" when the sum differs from the total by any amount.
    """
    if data["total"] is None:
        return "missing_total"

    computed = sum(_money(item["amount"]) for item in data["line_items"])
    computed += _money(data["tax"])

    if computed != _money(data["total"]):
        return "total_mismatch"
    return None


def _parse_and_check(raw):
    """Parse the model's raw text and check its schema.

    Returns (data, problems). Unparseable text is just another schema
    problem, so it gets the same single retry as a missing key would.
    """
    if not isinstance(raw, str):
        return None, [f"model output: expected text, got {type(raw).__name__}"]
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as err:
        return None, [f"model output: not valid JSON ({err.msg})"]
    return data, check_schema(data)


def process(invoice_text, extract_fn):
    """Run extraction with the code checks around it.

    extract_fn takes the invoice text and returns the model's raw JSON text.
    Passing it in (rather than calling a model here) lets tests use a fake.

    - Schema failure: retry once. If the retry also fails, flag
      "invalid_output" and return only the flags and the problems, so
      unvalidated model output never travels further down the pipeline.
    - Schema passes: never retry. Set needs_review / review_reason from
      check_totals; a total mismatch goes to a human, not back to the model.
    """
    data, problems = _parse_and_check(extract_fn(invoice_text))
    if problems:
        data, problems = _parse_and_check(extract_fn(invoice_text))
    if problems:
        return {
            "needs_review": True,
            "review_reason": "invalid_output",
            "problems": problems,
        }

    reason = check_totals(data)
    return {**data, "needs_review": reason is not None, "review_reason": reason}
