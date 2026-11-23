"""CSV ingestion and row-level validation.

Good rows are kept, bad rows are reported back with a reason, so one malformed
line never sinks a whole upload.
"""

import csv
import io
from dataclasses import dataclass, field

REQUIRED_COLUMNS = {"id", "text"}
OPTIONAL_COLUMNS = {"customer", "channel"}


class IngestError(ValueError):
    """The file as a whole cannot be processed (bad encoding, missing headers, ...)."""


@dataclass
class ParsedRow:
    external_id: str
    text: str
    customer: str | None = None
    channel: str | None = None


@dataclass
class IngestResult:
    rows: list[ParsedRow] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = " ".join(value.split())
    return value or None


def parse_csv(raw: bytes, max_text_chars: int = 4000) -> IngestResult:
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise IngestError("File must be UTF-8 encoded CSV") from exc

    if not content.strip():
        raise IngestError("File is empty")

    reader = csv.DictReader(io.StringIO(content))
    headers = {h.strip().lower() for h in (reader.fieldnames or []) if h}
    missing = REQUIRED_COLUMNS - headers
    if missing:
        raise IngestError(f"Missing required column(s): {', '.join(sorted(missing))}")

    result = IngestResult()
    seen: set[str] = set()

    # Line 1 is the header, so data starts on line 2.
    for line_no, raw_row in enumerate(reader, start=2):
        row = {(k or "").strip().lower(): v for k, v in raw_row.items()}

        if None in raw_row:  # more cells than headers
            result.rejected.append({"line": line_no, "reason": "Too many columns"})
            continue

        external_id = _clean(row.get("id"))
        text = _clean(row.get("text"))

        if not external_id:
            reason = "Missing id"
        elif not text:
            reason = "Missing text"
        elif external_id in seen:
            reason = f"Duplicate id '{external_id}'"
        elif len(text) > max_text_chars:
            reason = f"Text longer than {max_text_chars} characters"
        else:
            reason = None

        if reason:
            result.rejected.append({"line": line_no, "id": external_id, "reason": reason})
            continue

        seen.add(external_id)
        result.rows.append(
            ParsedRow(
                external_id=external_id,
                text=text,
                customer=_clean(row.get("customer")),
                channel=(_clean(row.get("channel")) or "").lower() or None,
            )
        )

    if not result.rows and not result.rejected:
        raise IngestError("File has a header but no data rows")

    return result
