"""Run every eval case through the pipeline and score it.

Usage:
    python run_evals.py
    MODEL=stub STUB_CORRUPT=0.3 python run_evals.py
    EVAL_THRESHOLD=95 python run_evals.py

Each run also writes runs/<timestamp>.jsonl (one line per case: model,
tokens, estimated cost, latency, pass/fail). Override the folder with RUNS_DIR.

Exit code is 0 if accuracy >= EVAL_THRESHOLD (default 90), otherwise 1.
CI only sees the exit code, so this is what turns a drop in quality into a
red build instead of a number nobody reads.
"""

import json
import math
import os
import sys
import time
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from extractor.models import current_model_id, get_model_fns
from extractor.pipeline import run_pipeline
from extractor.pricing import estimate_cost

CASES_DIR = Path(__file__).resolve().parent / "evals" / "cases"
FIELDS = ["vendor", "invoice_number", "invoice_date", "line_items", "tax",
          "total", "category", "needs_review", "review_reason"]


def _text(value):
    """Ignore letter case and stray whitespace, nothing else."""
    return " ".join(value.split()).casefold()


def _normalise(field, value):
    """Make values comparable. Money goes through Decimal, never raw floats.

    vendor and line-item descriptions ignore letter case and spacing:
    invoices print them in varying styles and that isn't what we're
    measuring. Everything else is exact. Line items stay in order.
    """
    if field in ("tax", "total") and value is not None:
        return Decimal(str(value))
    if field == "vendor" and isinstance(value, str):
        return _text(value)
    if field == "line_items":
        return [(_text(item["description"]), Decimal(str(item["amount"])))
                for item in value]
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
    result = run_pipeline(text, extract_fn, categorize_fn)
    return mismatched_fields(result, expected)


def percentile(values, pct):
    """Nearest-rank percentile: the smallest value that at least pct% of the
    values are less than or equal to. With 20 values, p95 is the 19th fastest.
    """
    ordered = sorted(values)
    rank = math.ceil(pct / 100 * len(ordered))
    return ordered[max(rank, 1) - 1]


def main():
    threshold = float(os.environ.get("EVAL_THRESHOLD", "90"))
    runs_dir = Path(os.environ.get("RUNS_DIR", Path(__file__).resolve().parent / "runs"))
    runs_dir.mkdir(parents=True, exist_ok=True)
    log_path = runs_dir / f"{datetime.now():%Y%m%d-%H%M%S}.jsonl"

    usage = []  # token counts from each API call, filled in by the model functions
    extract_fn, categorize_fn = get_model_fns(on_usage=usage.append)
    model = current_model_id()

    correct = total = 0
    costs, latencies = [], []
    with open(log_path, "w") as log:
        for case_dir in sorted(CASES_DIR.iterdir()):
            usage.clear()
            started = time.perf_counter()
            wrong = run_case(case_dir, extract_fn, categorize_fn)
            latency_ms = (time.perf_counter() - started) * 1000

            tokens_in = sum(u["input_tokens"] for u in usage)
            tokens_out = sum(u["output_tokens"] for u in usage)
            cost = estimate_cost(model, tokens_in, tokens_out)
            costs.append(cost)
            latencies.append(latency_ms)

            # Decimal -> float only here, at the JSON boundary, for the log.
            log.write(json.dumps({
                "case": case_dir.name,
                "model": model,
                "input_tokens": tokens_in,
                "output_tokens": tokens_out,
                "cost_usd": None if cost is None else float(cost),
                "latency_ms": round(latency_ms, 1),
                "passed": not wrong,
                "wrong_fields": wrong,
            }) + "\n")

            correct += len(FIELDS) - len(wrong)
            total += len(FIELDS)
            status = "PASS" if not wrong else "FAIL"
            detail = f"  wrong: {', '.join(wrong)}" if wrong else ""
            print(f"{status}  {case_dir.name}{detail}")

    accuracy = 100 * correct / total
    print(f"\nAccuracy: {accuracy:.1f}% ({correct}/{total} fields), "
          f"threshold {threshold:g}%")

    if None in costs:
        print(f"Cost: n/a (no price for model {model!r} in extractor/pricing.py)")
    else:
        print(f"Avg cost per invoice: ${sum(costs) / len(costs):.6f} "
              f"({model}, {len(costs)} invoices, total ${sum(costs):.6f})")
    print(f"Latency per invoice: p50 {percentile(latencies, 50):.0f} ms, "
          f"p95 {percentile(latencies, 95):.0f} ms")
    print(f"Run log: {log_path}")

    if accuracy < threshold:
        print("FAILED: below threshold")
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
