"""The validation and retry layer around the LLM, tested with scripted fake providers."""

from app.llm.providers import MockProvider, ProviderError, ProviderResponse
from app.llm.schema import LLMUsage
from app.services import enrich_text

GOOD = {
    "sentiment": "negative",
    "category": "billing",
    "urgency": 4,
    "summary": "  Customer   was charged twice. ",
    "confidence": 0.9,
}


class ScriptedProvider:
    """Returns the given responses in order; an Exception in the list is raised."""

    name = "scripted"
    model = "scripted-1"

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = 0

    def classify(self, text):
        self.calls += 1
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return ProviderResponse(raw=item, usage=LLMUsage(input_tokens=100, output_tokens=20))


def test_valid_output_passes_and_is_normalised():
    out = enrich_text(ScriptedProvider(GOOD), "text")
    assert out.ok
    assert out.result.summary == "Customer was charged twice."
    assert out.attempts == 1
    assert (out.input_tokens, out.output_tokens) == (100, 20)


def test_out_of_range_output_is_retried_then_accepted():
    bad = {**GOOD, "urgency": 9}
    provider = ScriptedProvider(bad, GOOD)
    out = enrich_text(provider, "text", max_retries=1)
    assert out.ok
    assert out.attempts == 2
    assert out.input_tokens == 200  # tokens from both attempts are counted


def test_persistently_invalid_output_fails_with_readable_error():
    bad = {**GOOD, "category": "complaints", "confidence": 1.7}
    out = enrich_text(ScriptedProvider(bad, bad), "text", max_retries=1)
    assert not out.ok
    assert out.attempts == 2
    assert "category" in out.error and "confidence" in out.error


def test_missing_field_is_rejected():
    partial = {k: v for k, v in GOOD.items() if k != "summary"}
    out = enrich_text(ScriptedProvider(partial), "text", max_retries=0)
    assert not out.ok and "summary" in out.error


def test_provider_errors_are_not_retried():
    provider = ScriptedProvider(ProviderError("Model declined"), GOOD)
    out = enrich_text(provider, "text", max_retries=3)
    assert not out.ok
    assert out.error == "Model declined"
    assert provider.calls == 1


def test_mock_provider_always_produces_schema_valid_output():
    provider = MockProvider()
    for text in ["", "!!!", "x" * 5000, "I love it", "charged twice, refund now!"]:
        assert enrich_text(provider, text or "?").ok
