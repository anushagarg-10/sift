"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { use, useCallback, useEffect, useState } from "react";
import { Bars, Kpi, Sentiment, StatusBadge, Urgency } from "@/components/ui";
import {
  api,
  CATEGORIES,
  label,
  pct,
  SENTIMENTS,
  type DatasetDetail,
  type RecordPage,
} from "@/lib/api";

const PAGE_SIZE = 25;

interface Filters {
  sentiment: string;
  category: string;
  min_urgency: string;
  status: string;
  q: string;
}

const EMPTY: Filters = { sentiment: "", category: "", min_urgency: "", status: "", q: "" };

export function DatasetView({ params }: { params: Promise<{ id: string }> }) {
  const { id: rawId } = use(params);
  const id = Number(rawId);
  const router = useRouter();

  const [dataset, setDataset] = useState<DatasetDetail | null>(null);
  const [records, setRecords] = useState<RecordPage | null>(null);
  const [filters, setFilters] = useState<Filters>(EMPTY);
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const busy = dataset?.status === "queued" || dataset?.status === "processing";

  const loadDataset = useCallback(
    () =>
      api
        .getDataset(id)
        .then(setDataset)
        .catch((e: Error) => setError(e.message)),
    [id],
  );

  useEffect(() => {
    loadDataset();
  }, [loadDataset]);

  // Poll while the background enrichment job is running.
  useEffect(() => {
    if (!busy) return;
    const t = setInterval(loadDataset, 1500);
    return () => clearInterval(t);
  }, [busy, loadDataset]);

  const status = dataset?.status;
  useEffect(() => {
    if (!status || status === "queued" || status === "processing") return;
    api
      .records(id, { ...filters, limit: PAGE_SIZE, offset })
      .then(setRecords)
      .catch((e: Error) => setError(e.message));
  }, [id, filters, offset, status]);

  function setFilter(key: keyof Filters, value: string) {
    setOffset(0);
    setFilters((f) => ({ ...f, [key]: f[key] === value && key !== "q" ? "" : value }));
  }

  async function enrich() {
    setError(null);
    try {
      const ds = await api.enrich(id);
      setDataset((d) => (d ? { ...d, status: ds.status } : d));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function remove() {
    if (!confirm(`Delete "${dataset?.name}" and all of its records?`)) return;
    await api.deleteDataset(id);
    router.push("/");
  }

  if (error && !dataset) {
    return (
      <div className="stack">
        <div className="alert">{error}</div>
        <Link href="/" className="btn" style={{ alignSelf: "flex-start" }}>
          Back to datasets
        </Link>
      </div>
    );
  }
  if (!dataset) return <p className="muted">Loading dataset...</p>;

  const s = dataset.stats;
  const hasResults = s.enriched + s.failed > 0;
  const activeFilters = Object.values(filters).some(Boolean);

  return (
    <div className="stack" style={{ gap: 24 }}>
      <div className="page-head" style={{ marginBottom: 0 }}>
        <div>
          <div className="small muted" style={{ marginBottom: 4 }}>
            <Link href="/">Datasets</Link> /
          </div>
          <div className="row">
            <h1>{dataset.name}</h1>
            <StatusBadge status={dataset.status} />
          </div>
          <p className="subtitle mono small">{dataset.filename}</p>
        </div>
        <div className="row">
          <button className="btn btn-ghost" onClick={remove} disabled={busy}>
            Delete
          </button>
          <button className="btn btn-primary" onClick={enrich} disabled={busy}>
            {busy ? "Enriching..." : hasResults ? "Re-run enrichment" : "Run enrichment"}
          </button>
        </div>
      </div>

      {error && <div className="alert">{error}</div>}

      <div className="kpis">
        <Kpi label="Rows" value={dataset.row_count} sub={`${dataset.rejected_count} rejected`} />
        <Kpi
          label="Enriched"
          value={s.enriched}
          sub={s.failed ? `${s.failed} failed validation` : "0 failed"}
        />
        <Kpi label="High urgency" value={s.high_urgency} sub="urgency 4 or 5" />
        <Kpi label="Avg confidence" value={pct(s.avg_confidence)} />
        <Kpi
          label="Tokens"
          value={(s.input_tokens + s.output_tokens).toLocaleString()}
          sub={`${s.input_tokens.toLocaleString()} in / ${s.output_tokens.toLocaleString()} out`}
        />
        <Kpi
          label="Avg latency"
          value={s.avg_latency_ms === null ? "n/a" : `${s.avg_latency_ms} ms`}
          sub="per record"
        />
      </div>

      {hasResults && (
        <div className="grid grid-3">
          <div className="card">
            <h2>By category</h2>
            <Bars
              data={s.by_category}
              order={CATEGORIES}
              onSelect={(k) => setFilter("category", k)}
            />
          </div>
          <div className="card">
            <h2>By sentiment</h2>
            <Bars
              data={s.by_sentiment}
              order={SENTIMENTS}
              onSelect={(k) => setFilter("sentiment", k)}
            />
          </div>
          <div className="card">
            <h2>By urgency</h2>
            <Bars
              data={s.by_urgency}
              order={["5", "4", "3", "2", "1"]}
              onSelect={(k) => setFilter("min_urgency", k)}
            />
          </div>
        </div>
      )}

      {dataset.rejected_rows.length > 0 && (
        <details className="card">
          <summary style={{ cursor: "pointer", fontWeight: 550 }}>
            {dataset.rejected_rows.length} row(s) rejected during ingestion
          </summary>
          <ul className="list" style={{ marginTop: 10 }}>
            {dataset.rejected_rows.map((r) => (
              <li key={r.line}>
                Line {r.line}
                {r.id ? ` (id ${r.id})` : ""}: {r.reason}
              </li>
            ))}
          </ul>
        </details>
      )}

      <div className="card">
        <div className="row" style={{ justifyContent: "space-between", marginBottom: 12 }}>
          <h2 style={{ margin: 0 }}>Records</h2>
          <div className="row">
            <input
              className="input"
              placeholder="Search text"
              value={filters.q}
              onChange={(e) => setFilter("q", e.target.value)}
            />
            <select
              className="select"
              value={filters.category}
              onChange={(e) => setFilter("category", e.target.value)}
            >
              <option value="">All categories</option>
              {CATEGORIES.map((c) => (
                <option key={c} value={c}>
                  {label(c)}
                </option>
              ))}
            </select>
            <select
              className="select"
              value={filters.sentiment}
              onChange={(e) => setFilter("sentiment", e.target.value)}
            >
              <option value="">All sentiment</option>
              {SENTIMENTS.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
            <select
              className="select"
              value={filters.status}
              onChange={(e) => setFilter("status", e.target.value)}
            >
              <option value="">Any result</option>
              <option value="ok">Valid</option>
              <option value="failed">Failed</option>
            </select>
            {activeFilters && (
              <button className="btn btn-ghost" onClick={() => setFilters(EMPTY)}>
                Clear
              </button>
            )}
          </div>
        </div>

        {busy ? (
          <div className="empty">Enrichment in progress. Results will appear here.</div>
        ) : !records ? (
          <p className="muted">Loading...</p>
        ) : records.items.length === 0 ? (
          <div className="empty">No records match these filters.</div>
        ) : (
          <>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Feedback</th>
                    <th>Category</th>
                    <th>Sentiment</th>
                    <th>Urgency</th>
                    <th>Conf.</th>
                  </tr>
                </thead>
                <tbody>
                  {records.items.map((r) => {
                    const e = r.enrichment;
                    return (
                      <tr key={r.id}>
                        <td className="mono small">{r.external_id}</td>
                        <td className="text-cell">
                          {r.text}
                          {e?.summary && <div className="summary">{e.summary}</div>}
                          {e?.status === "failed" && (
                            <div className="summary" style={{ color: "var(--neg)" }}>
                              {e.error}
                            </div>
                          )}
                          {(r.customer || r.channel) && (
                            <div className="summary small">
                              {[r.customer, r.channel].filter(Boolean).join(" · ")}
                            </div>
                          )}
                        </td>
                        <td>
                          {e?.category ? (
                            <span className="badge">{label(e.category)}</span>
                          ) : (
                            <span className="muted">n/a</span>
                          )}
                        </td>
                        <td>
                          <Sentiment value={e?.sentiment ?? null} />
                        </td>
                        <td>
                          <Urgency value={e?.urgency ?? null} />
                        </td>
                        <td className="small">{pct(e?.confidence)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <div className="pager">
              <span>
                {offset + 1} to {Math.min(offset + PAGE_SIZE, records.total)} of {records.total}
              </span>
              <div className="row">
                <button
                  className="btn"
                  disabled={offset === 0}
                  onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                >
                  Previous
                </button>
                <button
                  className="btn"
                  disabled={offset + PAGE_SIZE >= records.total}
                  onClick={() => setOffset(offset + PAGE_SIZE)}
                >
                  Next
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
