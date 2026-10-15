"""Model functions: the swappable "reader" parts of the pipeline.

Design rule: the model is a function passed in. Everything here has the
signature `fn(invoice_text) -> ...` so tests and CI can use the stub at zero
cost, and the real model can be swapped in by changing one setting (MODEL).
"""

import json
import os
import random
import time
from functools import partial
from pathlib import Path

from extractor.validate import EXTRACT_KEYS

CASES_DIR = Path(__file__).resolve().parent.parent / "evals" / "cases"
SEED = "invoice-extractor"  # fixed, so a corrupted run is reproducible

# The one place the Anthropic model ID lives. Override with ANTHROPIC_MODEL.
ANTHROPIC_MODEL = "claude-haiku-5-5"

# Copy of CATEGORIES from scripts/build_case.py (which can't be imported: it
# regenerates the case files on import). A test keeps the two in step.
CATEGORIES = ["Software & SaaS", "Professional Services", "Office Supplies",
              "Travel", "Facilities & Utilities", "Telecom"]

EXTRACT_PROMPT = """You extract fields from a plain-text invoice.
Reply with ONLY a JSON object, no prose and no code fences, with exactly these keys:
  "vendor": string
  "invoice_number": string, or null if the invoice prints no invoice number
  "invoice_date": string, YYYY-MM-DD
  "line_items": list of {"description": string, "amount": number}
  "tax": number (0 if none is stated)
  "total": number, or null if the invoice states no total
Copy amounts as written. Do not compute or correct anything, and do not invent an invoice number."""

CATEGORY_PROMPT = ("You assign an expense category to an invoice. Reply with "
                   "ONLY one of these exact strings, nothing else:\n"
                   + "\n".join(CATEGORIES))


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
        # A model that invents a number where there is none is a real failure.
        data["invoice_number"] = ("X" if data["invoice_number"] is None
                                  else data["invoice_number"] + "X")
    if rng.random() < corrupt:
        data["invoice_date"] = "2000-01-01"
    if rng.random() < corrupt:
        # Also makes the totals check disagree: corruption ripples downstream.
        data["total"] = 1.0 if data["total"] is None else data["total"] + 1.0
    if rng.random() < corrupt:
        data["line_items"][0]["amount"] += 1.0
    if rng.random() < corrupt:
        data["tax"] += 0.5

    return json.dumps(data)


def stub_categorize(invoice_text, corrupt=0.0):
    """Stand-in for LLM step 2: returns an expense category."""
    expected = _expected_for(invoice_text)["category"]
    if _rng(invoice_text, "category").random() >= corrupt:
        return expected
    others = sorted({c["category"] for c in _load_cases().values()} - {expected})
    return _rng(invoice_text, "category-pick").choice(others)


def _call_anthropic(system, invoice_text, client=None):
    """Make one Anthropic API call. The only function that touches the SDK.

    Returns the reply text plus what Session 4's cost log needs: token counts
    and wall-clock latency. `client` is injectable so tests use a fake and
    never reach the paid API.
    """
    if client is None:
        # Imported here so the stub path (and pytest) works without these
        # packages and without a key.
        import anthropic
        from dotenv import load_dotenv

        load_dotenv()  # puts ANTHROPIC_API_KEY from .env into os.environ
        client = anthropic.Anthropic()  # reads the key from the environment

    started = time.perf_counter()
    response = client.messages.create(
        model=os.environ.get("ANTHROPIC_MODEL", ANTHROPIC_MODEL),
        max_tokens=1024,
        system=system,
        messages=[{"role": "user", "content": invoice_text}],
    )
    return {
        # The reply can start with a thinking block; keep only text blocks.
        "text": "".join(b.text for b in response.content if b.type == "text"),
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "latency_s": time.perf_counter() - started,
    }


def anthropic_extract(invoice_text):
    """LLM step 1 via the Anthropic API. Same signature as stub_extract.

    Returns the raw reply text, unmodified: if the model adds fences or prose,
    process() sees invalid JSON and applies its retry/flag rules.
    """
    return _call_anthropic(EXTRACT_PROMPT, invoice_text)["text"]


def anthropic_categorize(invoice_text):
    """LLM step 2 via the Anthropic API. Not validated against CATEGORIES:
    a wrong or invented category simply scores as wrong in the eval."""
    return _call_anthropic(CATEGORY_PROMPT, invoice_text)["text"].strip()


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
    if model == "anthropic":
        return anthropic_extract, anthropic_categorize
    if model == "bedrock":
        return bedrock_extract, bedrock_categorize
    raise ValueError(
        f"unknown MODEL {model!r}; expected 'stub', 'anthropic' or 'bedrock'")
