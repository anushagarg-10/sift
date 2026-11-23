from app.evals import GoldenCase, load_golden, main, run_eval
from app.llm.providers import ProviderResponse
from app.llm.schema import CATEGORIES, SENTIMENTS


class Fixed:
    name, model = "fixed", "fixed-1"

    def __init__(self, raw):
        self.raw = raw

    def classify(self, text):
        return ProviderResponse(raw=self.raw)


def test_golden_set_labels_are_valid():
    cases = load_golden()
    assert len(cases) >= 20
    assert len({c.id for c in cases}) == len(cases)
    for c in cases:
        assert c.sentiment in SENTIMENTS
        assert c.category in CATEGORIES
        assert 1 <= c.urgency <= 5
    # every category is represented, so per-class regressions are visible
    assert {c.category for c in cases} == set(CATEGORIES)


def test_metrics_are_computed_correctly():
    cases = [
        GoldenCase("a", "x", "negative", "billing", 5),
        GoldenCase("b", "y", "positive", "other", 1),
    ]
    raw = {
        "sentiment": "negative",
        "category": "billing",
        "urgency": 4,
        "summary": "Summary.",
        "confidence": 0.8,
    }
    report = run_eval(Fixed(raw), cases)
    m = report["metrics"]
    assert m["schema_valid_rate"] == 1.0
    assert m["sentiment_accuracy"] == 0.5
    assert m["category_accuracy"] == 0.5
    assert m["urgency_within_1"] == 0.5
    assert m["urgency_mae"] == 2.0
    assert [f["id"] for f in report["failures"]] == ["b"]


def test_invalid_outputs_count_against_schema_valid_rate():
    cases = [GoldenCase("a", "x", "neutral", "other", 1)]
    report = run_eval(Fixed({"sentiment": "meh"}), cases, max_retries=0)
    assert report["metrics"]["schema_valid_rate"] == 0.0
    assert "error" in report["failures"][0]


def test_cli_exit_code_gates_on_thresholds(capsys):
    assert main(["--min-category", "0.0"]) == 0
    assert main(["--min-category", "1.01"]) == 1
    assert "FAIL category_accuracy" in capsys.readouterr().err
