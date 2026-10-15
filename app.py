"""Minimal HTTP wrapper around the pipeline.

    uvicorn app:app --reload

POST /extract with {"text": "<invoice text>"} returns the processed JSON:
the extracted fields, a category, and needs_review / review_reason.

A 200 means the pipeline ran, even if the invoice was flagged for review;
the body says whether a human should look. Errors are for requests the
service could not process at all.

Every request that reaches the model is recorded in
runs/api-<YYYYMMDD>.jsonl (RUNS_DIR overrides the folder): tokens, estimated
cost, latency and outcome, never the invoice text.
"""

import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import anthropic
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from extractor.models import UnknownInvoice, current_model_id, get_model_fns
from extractor.pipeline import run_pipeline
from extractor.usage_log import append_record, make_record

app = FastAPI(title="invoice-extractor")
log = logging.getLogger(__name__)


class ExtractRequest(BaseModel):
    text: str = Field(min_length=1, description="Plain-text invoice")


def _log_path():
    runs_dir = Path(os.environ.get("RUNS_DIR", Path(__file__).resolve().parent / "runs"))
    return runs_dir / f"api-{datetime.now(timezone.utc):%Y%m%d}.jsonl"


# A plain `def`, not `async def`: the model call blocks, and FastAPI runs
# plain functions in a worker thread so one slow call doesn't stall the rest.
@app.post("/extract")
def extract(request: ExtractRequest):
    usage = []  # token counts from each API call, filled in by the model functions
    # Which model runs is decided by the MODEL setting, same as run_evals.py.
    extract_fn, categorize_fn = get_model_fns(on_usage=usage.append)
    started = time.perf_counter()
    http_status, review_reason, error = 200, None, None
    try:
        result = run_pipeline(request.text, extract_fn, categorize_fn)
        review_reason = result["review_reason"]
        return result
    except UnknownInvoice as err:
        http_status, error = 400, type(err).__name__
        raise HTTPException(status_code=400, detail=err.args[0])
    except NotImplementedError as err:
        http_status, error = 501, type(err).__name__
        raise HTTPException(status_code=501, detail=str(err))
    except anthropic.APIError as err:
        # Name the failure type only; never echo request or credential details.
        http_status, error = 502, type(err).__name__
        raise HTTPException(status_code=502,
                            detail=f"model call failed: {type(err).__name__}")
    finally:
        # Runs on success and on every error path above, so calls that were
        # billed and then failed are still recorded.
        try:
            append_record(_log_path(), make_record(
                current_model_id(), usage,
                (time.perf_counter() - started) * 1000,
                http_status, review_reason, error))
        except OSError as err:
            # A broken log must not turn a good extraction into an error.
            log.warning("could not write usage log: %s", err)
