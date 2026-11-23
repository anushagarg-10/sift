"""The contract between the LLM and the rest of the app.

`EnrichmentDraft` is the shape we ask the model to produce (structured output).
`EnrichmentResult` is the stricter shape we accept into the database. Keeping the
two separate means the model-facing schema stays simple, while business rules
(ranges, lengths, normalisation) are enforced in our own code where they are
testable.
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

Sentiment = Literal["positive", "neutral", "negative"]
Category = Literal["billing", "bug", "feature_request", "account", "shipping", "other"]

SENTIMENTS: tuple[str, ...] = Sentiment.__args__  # type: ignore[attr-defined]
CATEGORIES: tuple[str, ...] = Category.__args__  # type: ignore[attr-defined]


class EnrichmentDraft(BaseModel):
    sentiment: Sentiment
    category: Category
    urgency: int = Field(description="1 (no rush) to 5 (drop everything)")
    summary: str = Field(description="One sentence, under 160 characters")
    confidence: float = Field(description="0.0 to 1.0")


class EnrichmentResult(BaseModel):
    sentiment: Sentiment
    category: Category
    urgency: int = Field(ge=1, le=5)
    summary: str = Field(min_length=3, max_length=200)
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("summary")
    @classmethod
    def strip_summary(cls, v: str) -> str:
        return " ".join(v.split())


class LLMUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
