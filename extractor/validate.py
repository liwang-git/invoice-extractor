"""Code checks for extracted invoice data.

Design rule: code decides, the model only reads. Every accept, reject or
flag decision in the pipeline is made here, in plain Python.
"""

from decimal import Decimal


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
