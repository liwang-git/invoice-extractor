"""Run every eval case through the pipeline and score it.

Usage:
    python run_evals.py
    MODEL=stub STUB_CORRUPT=0.3 python run_evals.py
    EVAL_THRESHOLD=95 python run_evals.py

Exit code is 0 if accuracy >= EVAL_THRESHOLD (default 90), otherwise 1.
CI only sees the exit code, so this is what turns a drop in quality into a
red build instead of a number nobody reads.
"""

import json
import os
import sys
from decimal import Decimal
from pathlib import Path

from extractor.models import get_model_fns
from extractor.validate import process

CASES_DIR = Path(__file__).resolve().parent / "evals" / "cases"
FIELDS = ["vendor", "invoice_number", "invoice_date", "total",
          "category", "needs_review"]


def _normalise(field, value):
    """Make values comparable. Money goes through Decimal, never raw floats.

    vendor ignores letter case: invoices print names in capitals, and
    capitalisation isn't what we're measuring. Everything else is exact.
    """
    if field == "total" and value is not None:
        return Decimal(str(value))
    if field == "vendor" and isinstance(value, str):
        return value.strip().casefold()
    return value


def mismatched_fields(actual, expected):
    """Return the names of the fields where actual differs from expected.

    A field the pipeline didn't produce (e.g. after "invalid_output") counts
    as wrong.
    """
    wrong = []
    for field in FIELDS:
        if field not in actual:
            wrong.append(field)
        elif _normalise(field, actual[field]) != _normalise(field, expected[field]):
            wrong.append(field)
    return wrong


def run_case(case_dir, extract_fn, categorize_fn):
    text = (case_dir / "invoice.txt").read_text()
    expected = json.loads((case_dir / "expected.json").read_text())
    result = process(text, extract_fn)
    # LLM step 2. Skipped for flagged-invalid output: nothing to categorise.
    if result["review_reason"] != "invalid_output":
        result["category"] = categorize_fn(text)
    return mismatched_fields(result, expected)


def main():
    threshold = float(os.environ.get("EVAL_THRESHOLD", "90"))
    extract_fn, categorize_fn = get_model_fns()

    correct = total = 0
    for case_dir in sorted(CASES_DIR.iterdir()):
        wrong = run_case(case_dir, extract_fn, categorize_fn)
        correct += len(FIELDS) - len(wrong)
        total += len(FIELDS)
        status = "PASS" if not wrong else "FAIL"
        detail = f"  wrong: {', '.join(wrong)}" if wrong else ""
        print(f"{status}  {case_dir.name}{detail}")

    accuracy = 100 * correct / total
    print(f"\nAccuracy: {accuracy:.1f}% ({correct}/{total} fields), "
          f"threshold {threshold:g}%")
    if accuracy < threshold:
        print("FAILED: below threshold")
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
