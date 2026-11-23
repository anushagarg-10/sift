"""Offline evaluation of a provider against a hand-labelled golden set.

Run from the CLI to gate CI on quality:

    python -m app.evals --min-category 0.8 --min-sentiment 0.8
"""

import argparse
import csv
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from app.llm.providers import LLMProvider
from app.services import enrich_text

GOLDEN_PATH = Path(__file__).resolve().parent.parent / "evals" / "golden.csv"


@dataclass
class GoldenCase:
    id: str
    text: str
    sentiment: str
    category: str
    urgency: int


def load_golden(path: Path = GOLDEN_PATH) -> list[GoldenCase]:
    with path.open(newline="", encoding="utf-8") as f:
        return [
            GoldenCase(
                id=row["id"],
                text=row["text"],
                sentiment=row["sentiment"],
                category=row["category"],
                urgency=int(row["urgency"]),
            )
            for row in csv.DictReader(f)
        ]


def run_eval(provider: LLMProvider, cases: list[GoldenCase], max_retries: int = 1) -> dict:
    n = len(cases)
    valid = sentiment_ok = category_ok = urgency_close = 0
    abs_err = 0
    latency = in_tok = out_tok = 0
    failures: list[dict] = []

    for case in cases:
        outcome = enrich_text(provider, case.text, max_retries=max_retries)
        latency += outcome.latency_ms
        in_tok += outcome.input_tokens
        out_tok += outcome.output_tokens

        if not outcome.ok:
            failures.append({"id": case.id, "text": case.text, "error": outcome.error})
            continue

        r = outcome.result
        valid += 1
        s_ok = r.sentiment == case.sentiment
        c_ok = r.category == case.category
        u_err = abs(r.urgency - case.urgency)
        sentiment_ok += s_ok
        category_ok += c_ok
        urgency_close += u_err <= 1
        abs_err += u_err

        if not (s_ok and c_ok and u_err <= 1):
            failures.append(
                {
                    "id": case.id,
                    "text": case.text,
                    "expected": {
                        "sentiment": case.sentiment,
                        "category": case.category,
                        "urgency": case.urgency,
                    },
                    "got": {"sentiment": r.sentiment, "category": r.category, "urgency": r.urgency},
                }
            )

    def ratio(x: int, d: int = n) -> float:
        return round(x / d, 3) if d else 0.0

    metrics = {
        "schema_valid_rate": ratio(valid),
        "sentiment_accuracy": ratio(sentiment_ok),
        "category_accuracy": ratio(category_ok),
        "urgency_within_1": ratio(urgency_close),
        "urgency_mae": round(abs_err / valid, 3) if valid else None,
        "avg_latency_ms": round(latency / n) if n else 0,
        "input_tokens": in_tok,
        "output_tokens": out_tok,
    }
    return {"cases": n, "metrics": metrics, "failures": failures}


def main(argv: list[str] | None = None) -> int:
    from app.config import get_settings
    from app.llm.providers import get_provider

    p = argparse.ArgumentParser(description="Run the golden-set eval")
    p.add_argument("--min-sentiment", type=float, default=0.0)
    p.add_argument("--min-category", type=float, default=0.0)
    p.add_argument("--min-urgency", type=float, default=0.0, help="min urgency_within_1")
    p.add_argument("--min-valid", type=float, default=1.0, help="min schema_valid_rate")
    args = p.parse_args(argv)

    settings = get_settings()
    provider = get_provider(settings)
    report = run_eval(provider, load_golden(), max_retries=settings.llm_max_retries)
    m = report["metrics"]
    print(json.dumps({"provider": provider.name, "model": provider.model, **report}, indent=2))

    checks = {
        "schema_valid_rate": (m["schema_valid_rate"], args.min_valid),
        "sentiment_accuracy": (m["sentiment_accuracy"], args.min_sentiment),
        "category_accuracy": (m["category_accuracy"], args.min_category),
        "urgency_within_1": (m["urgency_within_1"], args.min_urgency),
    }
    failed = {k: v for k, v in checks.items() if v[0] < v[1]}
    for name, (got, want) in failed.items():
        print(f"FAIL {name}: {got} < {want}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
