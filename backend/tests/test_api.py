from app.llm.providers import ProviderError, ProviderResponse
from tests.conftest import SAMPLE, upload


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_config_reports_active_provider(client):
    assert client.get("/config").json() == {"provider": "mock", "model": "keyword-baseline"}


def test_upload_reports_rejected_rows(client):
    res = upload(client, "id,text\n1,Great app\n2,\n3,App crashes\n", name="Week 1")
    assert res.status_code == 201
    body = res.json()
    assert body["name"] == "Week 1"
    assert body["row_count"] == 2
    assert body["rejected_count"] == 1
    assert body["rejected_rows"] == [{"line": 3, "id": "2", "reason": "Missing text"}]


def test_upload_rejects_non_csv_and_bad_headers(client):
    assert upload(client, "hello", filename="notes.txt").status_code == 415
    res = upload(client, "foo,bar\n1,2\n")
    assert res.status_code == 422
    assert "Missing required column" in res.json()["detail"]


def test_full_pipeline_with_sample_file(client):
    created = upload(client, SAMPLE.read_bytes()).json()
    ds_id = created["id"]
    assert created["row_count"] >= 20

    res = client.post(f"/datasets/{ds_id}/enrich")
    assert res.status_code == 202
    # TestClient runs background tasks before returning, so results are ready.

    detail = client.get(f"/datasets/{ds_id}").json()
    assert detail["status"] == "enriched"
    stats = detail["stats"]
    assert stats["enriched"] == created["row_count"]
    assert stats["failed"] == 0
    assert sum(stats["by_category"].values()) == stats["enriched"]
    assert set(stats["by_sentiment"]) <= {"positive", "neutral", "negative"}

    page = client.get(f"/datasets/{ds_id}/records", params={"limit": 5}).json()
    assert page["total"] == created["row_count"]
    assert len(page["items"]) == 5
    assert page["items"][0]["enrichment"]["provider"] == "mock"


def test_record_filters(client):
    csv = (
        "id,text\n"
        "1,I was charged twice! Refund immediately\n"
        "2,Love the new dashboard thanks\n"
        "3,Please add dark mode\n"
    )
    ds_id = upload(client, csv).json()["id"]
    client.post(f"/datasets/{ds_id}/enrich")

    def ids(**params):
        page = client.get(f"/datasets/{ds_id}/records", params=params).json()
        return [r["external_id"] for r in page["items"]]

    assert ids(category="billing") == ["1"]
    assert ids(sentiment="positive") == ["2"]
    assert ids(min_urgency=4) == ["1"]
    assert ids(q="dark") == ["3"]
    assert client.get(f"/datasets/{ds_id}/records", params={"min_urgency": 9}).status_code == 422


def test_failed_rows_are_stored_with_error(client, use_provider):
    class Flaky:
        name, model = "flaky", "flaky-1"

        def classify(self, text):
            if "boom" in text:
                raise ProviderError("Model declined to classify this message")
            return ProviderResponse(
                raw={
                    "sentiment": "neutral",
                    "category": "other",
                    "urgency": 1,
                    "summary": "Fine.",
                    "confidence": 0.5,
                }
            )

    use_provider(Flaky())
    ds_id = upload(client, "id,text\n1,all good\n2,boom\n").json()["id"]
    client.post(f"/datasets/{ds_id}/enrich")

    stats = client.get(f"/datasets/{ds_id}").json()["stats"]
    assert (stats["enriched"], stats["failed"]) == (1, 1)
    failed = client.get(f"/datasets/{ds_id}/records", params={"status": "failed"}).json()
    assert failed["items"][0]["enrichment"]["error"] == "Model declined to classify this message"


def test_re_enrichment_replaces_previous_results(client):
    ds_id = upload(client, "id,text\n1,hello\n").json()["id"]
    client.post(f"/datasets/{ds_id}/enrich")
    client.post(f"/datasets/{ds_id}/enrich")
    assert client.get(f"/datasets/{ds_id}").json()["stats"]["enriched"] == 1


def test_list_and_delete(client):
    a = upload(client, "id,text\n1,a\n", name="A").json()["id"]
    upload(client, "id,text\n1,b\n", name="B")
    assert [d["name"] for d in client.get("/datasets").json()] == ["B", "A"]
    assert client.delete(f"/datasets/{a}").status_code == 204
    assert client.get(f"/datasets/{a}").status_code == 404
    assert len(client.get("/datasets").json()) == 1


def test_eval_run_is_persisted(client):
    run = client.post("/evals/run").json()
    assert run["provider"] == "mock"
    assert run["cases"] >= 20
    m = run["metrics"]
    assert m["schema_valid_rate"] == 1.0
    for key in ("sentiment_accuracy", "category_accuracy", "urgency_within_1"):
        assert 0.0 <= m[key] <= 1.0
    assert client.get("/evals").json()[0]["id"] == run["id"]
