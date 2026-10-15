# invoice-extractor

## What this is

A deliberately small learning project. The owner is learning how an LLM workflow, evals, CI and Terraform fit together, not building a product. Favour clarity over cleverness, and treat every change as a chance to explain a concept.

The pipeline:
1. **Input:** a plain-text invoice.
2. **LLM step 1:** extract fields to JSON.
3. **Code checks:** validate the schema, then check that line items plus tax equal the total. Retry the model once on a schema failure, otherwise flag the invoice for human review.
4. **LLM step 2:** assign an expense category from a fixed list.
5. **Output:** JSON, plus a per-run log of tokens, cost, latency and pass/fail.

Design rule: **code decides, the model only reads.** Every accept, reject or flag decision lives in Python, never in a prompt.

## Environment

- Intel MacBook Pro (x86_64), macOS Sequoia. No Homebrew; tools were installed from official installers.
- Python virtual environment at `.venv`. Use `python` and `pip` only inside it.
- Tests run with `pytest`.
- Bedrock calls are **blocked at the AWS account level** while a support case is open. Until that's resolved, all model calls go through a stub. Do not try to call Bedrock unless asked.

## Layout

```
evals/cases/<id>/invoice.txt      synthetic invoice
evals/cases/<id>/expected.json    correct answer for that invoice
scripts/build_case.py             generates the cases above (the source of truth)
extractor/                        pipeline code
tests/                            pytest tests
```

Edit `scripts/build_case.py` and rerun it rather than hand-editing the generated files.

## expected.json schema

```json
{
  "vendor": "string",
  "invoice_number": "string",
  "invoice_date": "YYYY-MM-DD",
  "line_items": [{"description": "string", "amount": 0.0}],
  "tax": 0.0,
  "total": 0.0,
  "category": "one of CATEGORIES",
  "needs_review": false,
  "review_reason": null
}
```

- `total` is `null` when the invoice has no stated total.
- `review_reason` is one of `null`, `"missing_total"`, `"total_mismatch"` or `"invalid_output"`.
- `CATEGORIES` is defined at the top of `scripts/build_case.py`: Software & SaaS, Professional Services, Office Supplies, Travel, Facilities & Utilities, Telecom.

## Rules

- **Money:** compare amounts as `Decimal` or integer cents, never as raw floats.
- **The model is a function passed in** (for example `extract_fn`), so tests and CI run against a stub at zero cost and the real model can be swapped in later. The model ID is one setting, not scattered through the code.
- **Synthetic data only.** No real invoices, no employer data.
- **No secrets in the repo.** Use environment variables; `.env` is git-ignored.
- **Keep it minimal:** plain functions over classes, the standard library over new packages. Say why before adding any dependency.

## How to work with me

- **Before writing code,** state the plan in a few plain-language sentences and wait for my go-ahead on anything larger than one file.
- **Work in small steps.** One function or one test file at a time.
- **After each step,** tell me what changed and why, how to run it, and one concept worth understanding from it. I'm aiming for literacy: I want to be able to explain this code to an engineer.
- **Run `pytest` before saying a step is done,** and show the result.
- **Commit after each working step** with a clear message. Don't push; I'll push.
- **If something is a judgment call,** such as whether to retry on a total mismatch, ask me rather than deciding silently.