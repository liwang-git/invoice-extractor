"""Append-only usage log for the API: one JSON line per request.

Records metadata only (model, tokens, cost, latency, status). Never the
invoice text or the extracted values: they can hold names, amounts and
addresses, and a usage log has no need for them.
"""

import json
import threading
from datetime import datetime, timezone

from extractor.pricing import estimate_cost

# The API serves requests on worker threads. One lock around each write keeps
# two simultaneous requests from interleaving their lines.
_lock = threading.Lock()


def make_record(model, usage, latency_ms, http_status, review_reason=None, error=None):
    """Build one log line. `usage` is the list of per-API-call token counts."""
    tokens_in = sum(u["input_tokens"] for u in usage)
    tokens_out = sum(u["output_tokens"] for u in usage)
    cost = estimate_cost(model, tokens_in, tokens_out)
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": model,
        "input_tokens": tokens_in,
        "output_tokens": tokens_out,
        # Decimal -> float only here, at the JSON boundary.
        "cost_usd": None if cost is None else float(cost),
        "latency_ms": round(latency_ms, 1),
        "http_status": http_status,
        "review_reason": review_reason,
        "error": error,
    }


def append_record(path, record):
    line = json.dumps(record) + "\n"
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a") as f:
            f.write(line)
