"""Minimal HTTP wrapper around the pipeline.

    uvicorn app:app --reload

POST /extract with {"text": "<invoice text>"} returns the processed JSON:
the extracted fields, a category, and needs_review / review_reason.

A 200 means the pipeline ran, even if the invoice was flagged for review;
the body says whether a human should look. Errors are for requests the
service could not process at all.
"""

import anthropic
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from extractor.models import UnknownInvoice, get_model_fns
from extractor.pipeline import run_pipeline

app = FastAPI(title="invoice-extractor")


class ExtractRequest(BaseModel):
    text: str = Field(min_length=1, description="Plain-text invoice")


# A plain `def`, not `async def`: the model call blocks, and FastAPI runs
# plain functions in a worker thread so one slow call doesn't stall the rest.
@app.post("/extract")
def extract(request: ExtractRequest):
    # Which model runs is decided by the MODEL setting, same as run_evals.py.
    extract_fn, categorize_fn = get_model_fns()
    try:
        result = run_pipeline(request.text, extract_fn, categorize_fn)
    except UnknownInvoice as err:
        raise HTTPException(status_code=400, detail=err.args[0])
    except NotImplementedError as err:
        raise HTTPException(status_code=501, detail=str(err))
    except anthropic.APIError as err:
        # Name the failure type only; never echo request or credential details.
        raise HTTPException(status_code=502,
                            detail=f"model call failed: {type(err).__name__}")
    return result
