import pytest

from app.ingest import IngestError, parse_csv


def test_parses_valid_rows_and_normalises_whitespace():
    raw = b"id,text,customer,channel\n1,  Hello   there ,Acme,EMAIL\n2,Second row,,\n"
    result = parse_csv(raw)
    assert [r.external_id for r in result.rows] == ["1", "2"]
    assert result.rows[0].text == "Hello there"
    assert result.rows[0].channel == "email"
    assert result.rows[1].customer is None
    assert result.rejected == []


def test_headers_are_case_insensitive_and_bom_is_stripped():
    raw = "\ufeffID,Text\n1,hi there\n".encode()
    assert parse_csv(raw).rows[0].text == "hi there"


def test_rejects_bad_rows_but_keeps_good_ones():
    raw = b"id,text\n1,ok\n,no id\n3,\n1,duplicate id\n5,way too long\n6,extra,cell\n"
    result = parse_csv(raw, max_text_chars=8)
    assert [r.external_id for r in result.rows] == ["1"]
    reasons = {r["line"]: r["reason"] for r in result.rejected}
    assert reasons == {
        3: "Missing id",
        4: "Missing text",
        5: "Duplicate id '1'",
        6: "Text longer than 8 characters",
        7: "Too many columns",
    }


@pytest.mark.parametrize(
    "raw, message",
    [
        (b"", "empty"),
        (b"id,body\n1,x\n", "Missing required column(s): text"),
        (b"id,text\n", "no data rows"),
        ("id,text\n1,caf\xe9\n".encode("latin-1"), "UTF-8"),
    ],
)
def test_file_level_errors(raw, message):
    with pytest.raises(IngestError, match=message.replace("(", r"\(").replace(")", r"\)")):
        parse_csv(raw)
