"""The whole pipeline in one function, shared by run_evals.py and app.py.

Design rule: code decides, the model only reads. The model functions are
passed in; every accept / flag decision is made in extractor/validate.py.
"""

from extractor.validate import process


def run_pipeline(invoice_text, extract_fn, categorize_fn):
    """LLM step 1 + code checks (process), then LLM step 2 for the category.

    Step 2 is skipped when step 1 was flagged "invalid_output": there is no
    trustworthy extraction to categorise.
    """
    result = process(invoice_text, extract_fn)
    if result["review_reason"] != "invalid_output":
        result["category"] = categorize_fn(invoice_text)
    return result
