"""Model functions: the swappable "reader" parts of the pipeline.

Design rule: the model is a function passed in. Everything here has the
signature `fn(invoice_text) -> ...` so tests and CI can use the stub at zero
cost, and the real model can be swapped in by changing one setting (MODEL).
"""

import json
import os
import random
from functools import partial
from pathlib import Path

from extractor.validate import EXTRACT_KEYS

CASES_DIR = Path(__file__).resolve().parent.parent / "evals" / "cases"
SEED = "invoice-extractor"  # fixed, so a corrupted run is reproducible


def _load_cases():
    """Map invoice text -> expected.json for every eval case."""
    cases = {}
    for case_dir in sorted(CASES_DIR.iterdir()):
        text = (case_dir / "invoice.txt").read_text()
        cases[text] = json.loads((case_dir / "expected.json").read_text())
    return cases


def _expected_for(invoice_text):
    try:
        return _load_cases()[invoice_text]
    except KeyError:
        raise KeyError("stub model only knows the invoices in evals/cases") from None


def _rng(invoice_text, salt):
    # Seeding with a string is deterministic (unlike hash(), which varies
    # between Python runs), so the same corruption happens every time.
    return random.Random(f"{SEED}:{salt}:{invoice_text}")


def stub_extract(invoice_text, corrupt=0.0):
    """Stand-in for LLM step 1: returns the right answer as raw JSON text.

    `corrupt` is the chance (0..1) that each checked field is wrong, so we can
    watch the accuracy score drop. Corrupted values are still schema-valid:
    this simulates a model that reads confidently but wrongly, which only the
    eval (not the schema check) can catch.
    """
    data = {k: v for k, v in _expected_for(invoice_text).items()
            if k in EXTRACT_KEYS}
    rng = _rng(invoice_text, "extract")

    if rng.random() < corrupt:
        data["vendor"] += " Ltd"
    if rng.random() < corrupt:
        data["invoice_number"] += "X"
    if rng.random() < corrupt:
        data["invoice_date"] = "2000-01-01"
    if rng.random() < corrupt:
        # Also makes the totals check disagree: corruption ripples downstream.
        data["total"] = 1.0 if data["total"] is None else data["total"] + 1.0

    return json.dumps(data)


def stub_categorize(invoice_text, corrupt=0.0):
    """Stand-in for LLM step 2: returns an expense category."""
    expected = _expected_for(invoice_text)["category"]
    if _rng(invoice_text, "category").random() >= corrupt:
        return expected
    others = sorted({c["category"] for c in _load_cases().values()} - {expected})
    return _rng(invoice_text, "category-pick").choice(others)


def bedrock_extract(invoice_text):
    """Placeholder for the real model. Same signature as stub_extract."""
    raise NotImplementedError(
        "Bedrock is blocked at the AWS account level; use MODEL=stub for now."
    )


def bedrock_categorize(invoice_text):
    raise NotImplementedError(
        "Bedrock is blocked at the AWS account level; use MODEL=stub for now."
    )


def get_model_fns():
    """Pick (extract_fn, categorize_fn) from the MODEL setting.

    MODEL is the one place the model choice lives. STUB_CORRUPT (0..1) only
    affects the stub.
    """
    model = os.environ.get("MODEL", "stub")
    if model == "stub":
        corrupt = float(os.environ.get("STUB_CORRUPT", "0"))
        return (partial(stub_extract, corrupt=corrupt),
                partial(stub_categorize, corrupt=corrupt))
    if model == "bedrock":
        return bedrock_extract, bedrock_categorize
    raise ValueError(f"unknown MODEL {model!r}; expected 'stub' or 'bedrock'")
