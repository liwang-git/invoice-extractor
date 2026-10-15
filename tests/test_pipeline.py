import json

from extractor.pipeline import run_pipeline

GOOD = json.dumps({
    "vendor": "Acme", "invoice_number": "A-1", "invoice_date": "2026-01-01",
    "line_items": [{"description": "Widget", "amount": 10.0}],
    "tax": 0.0, "total": 10.0,
})


def test_category_is_added_after_a_valid_extraction():
    result = run_pipeline("text", lambda t: GOOD, lambda t: "Office Supplies")
    assert result["category"] == "Office Supplies"
    assert result["needs_review"] is False


def test_categorize_is_not_called_for_invalid_output():
    calls = []

    def categorize(text):
        calls.append(text)
        return "Travel"

    result = run_pipeline("text", lambda t: "not json", categorize)
    assert result["review_reason"] == "invalid_output"
    assert "category" not in result
    assert calls == []
