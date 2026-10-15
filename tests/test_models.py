import json
from pathlib import Path

import pytest

from extractor.models import (bedrock_extract, get_model_fns, stub_categorize,
                              stub_extract)
from extractor.validate import check_schema, process

CASES_DIR = Path(__file__).parent.parent / "evals" / "cases"
CASE_DIRS = sorted(CASES_DIR.iterdir())


def load(case_dir):
    text = (case_dir / "invoice.txt").read_text()
    expected = json.loads((case_dir / "expected.json").read_text())
    return text, expected


@pytest.mark.parametrize("case_dir", CASE_DIRS, ids=lambda p: p.name)
def test_stub_output_passes_through_process_unchanged(case_dir):
    text, expected = load(case_dir)
    result = process(text, stub_extract)
    assert result["vendor"] == expected["vendor"]
    assert result["needs_review"] == expected["needs_review"]
    assert result["review_reason"] == expected["review_reason"]


@pytest.mark.parametrize("case_dir", CASE_DIRS, ids=lambda p: p.name)
def test_stub_categorize_matches_expected(case_dir):
    text, expected = load(case_dir)
    assert stub_categorize(text) == expected["category"]


def test_full_corruption_changes_every_field_but_stays_schema_valid():
    text, expected = load(CASE_DIRS[0])
    data = json.loads(stub_extract(text, corrupt=1.0))
    assert check_schema(data) == []
    for field in ("vendor", "invoice_number", "invoice_date", "total",
                  "tax", "line_items"):
        assert data[field] != expected[field]
    assert stub_categorize(text, corrupt=1.0) != expected["category"]


def test_corruption_is_reproducible():
    text, _ = load(CASE_DIRS[0])
    assert stub_extract(text, corrupt=0.5) == stub_extract(text, corrupt=0.5)


def test_unknown_invoice_is_an_error():
    with pytest.raises(KeyError):
        stub_extract("not one of the eval invoices")


def test_bedrock_placeholder_raises():
    with pytest.raises(NotImplementedError):
        bedrock_extract("anything")


def test_model_setting_defaults_to_stub(monkeypatch):
    monkeypatch.delenv("MODEL", raising=False)
    extract_fn, _ = get_model_fns()
    text, _ = load(CASE_DIRS[0])
    assert check_schema(json.loads(extract_fn(text))) == []


def test_unknown_model_setting_is_an_error(monkeypatch):
    monkeypatch.setenv("MODEL", "gpt-whatever")
    with pytest.raises(ValueError):
        get_model_fns()


# --- Anthropic backend: always a fake client, never the paid API ---

class FakeClient:
    """Mimics client.messages.create(...) and records what it was given."""

    def __init__(self, text="{}"):
        self.calls = []
        self.messages = self
        self._text = text

    def create(self, **kwargs):
        self.calls.append(kwargs)
        from types import SimpleNamespace as NS
        return NS(content=[NS(type="thinking", thinking="hmm"),
                           NS(type="text", text=self._text)],
                  usage=NS(input_tokens=120, output_tokens=45))


def test_call_anthropic_returns_text_tokens_and_latency():
    from extractor.models import ANTHROPIC_MODEL, _call_anthropic
    client = FakeClient('{"a": 1}')
    result = _call_anthropic("sys prompt", "invoice body", client=client)
    assert result["text"] == '{"a": 1}'
    assert result["input_tokens"] == 120
    assert result["output_tokens"] == 45
    assert result["latency_s"] >= 0
    call = client.calls[0]
    assert call["model"] == ANTHROPIC_MODEL
    assert call["system"] == "sys prompt"
    assert call["messages"] == [{"role": "user", "content": "invoice body"}]


def test_model_id_can_be_overridden(monkeypatch):
    from extractor.models import _call_anthropic
    monkeypatch.setenv("ANTHROPIC_MODEL", "some-other-model")
    client = FakeClient()
    _call_anthropic("s", "t", client=client)
    assert client.calls[0]["model"] == "some-other-model"


def test_anthropic_wrappers_return_text_only(monkeypatch):
    import extractor.models as models
    reply = {"text": "  Travel \n", "input_tokens": 1,
             "output_tokens": 1, "latency_s": 0.0}
    monkeypatch.setattr(models, "_call_anthropic",
                        lambda system, text, client=None, on_usage=None: reply)
    assert models.anthropic_extract("x") == "  Travel \n"   # untouched
    assert models.anthropic_categorize("x") == "Travel"      # stripped


def test_model_setting_selects_anthropic_without_calling_it(monkeypatch):
    import extractor.models as models
    monkeypatch.setenv("MODEL", "anthropic")
    extract_fn, categorize_fn = get_model_fns()
    assert extract_fn.func is models.anthropic_extract
    assert categorize_fn.func is models.anthropic_categorize


def test_categories_copy_matches_build_script():
    import re
    import extractor.models as models
    source = (Path(__file__).parent.parent / "scripts" / "build_case.py").read_text()
    block = re.search(r"CATEGORIES = \[(.*?)\]", source, re.S).group(1)
    assert re.findall(r'"([^"]+)"', block) == models.CATEGORIES


def test_on_usage_receives_token_counts_from_each_call():
    from extractor.models import _call_anthropic
    seen = []
    _call_anthropic("s", "t", client=FakeClient(), on_usage=seen.append)
    assert seen == [{"input_tokens": 120, "output_tokens": 45}]


def test_current_model_id(monkeypatch):
    from extractor.models import ANTHROPIC_MODEL, current_model_id
    monkeypatch.delenv("MODEL", raising=False)
    assert current_model_id() == "stub"
    monkeypatch.setenv("MODEL", "anthropic")
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    assert current_model_id() == ANTHROPIC_MODEL
    monkeypatch.setenv("ANTHROPIC_MODEL", "other-model")
    assert current_model_id() == "other-model"
