"use client";

import { useEffect, useState } from "react";
import { Kpi } from "@/components/ui";
import { api, label, pct, type EvalRun } from "@/lib/api";

export default function EvalsPage() {
  const [runs, setRuns] = useState<EvalRun[] | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .listEvals()
      .then(setRuns)
      .catch((e: Error) => {
        setRuns([]);
        setError(e.message);
      });
  }, []);

  async function run() {
    setRunning(true);
    setError(null);
    try {
      const r = await api.runEval();
      setRuns((prev) => [r, ...(prev ?? [])]);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setRunning(false);
    }
  }

  const latest = runs?.[0];
  const previous = runs?.[1];

  function delta(key: "sentiment_accuracy" | "category_accuracy" | "urgency_within_1") {
    if (!latest || !previous) return undefined;
    const d = Math.round((latest.metrics[key] - previous.metrics[key]) * 100);
    return d === 0 ? "no change vs previous" : `${d > 0 ? "+" : ""}${d} pts vs previous`;
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Evals</h1>
          <p className="subtitle">
            Runs the enrichment pipeline against a hand-labelled golden set and scores every field.
            The same check runs in CI as a quality gate.
          </p>
        </div>
        <button className="btn btn-primary" onClick={run} disabled={running}>
          {running ? "Running..." : "Run eval"}
        </button>
      </div>

      {error && (
        <div className="alert" style={{ marginBottom: 16 }}>
          {error}
        </div>
      )}

      {runs === null ? (
        <p className="muted">Loading...</p>
      ) : !latest ? (
        <div className="card empty">No eval runs yet. Click Run eval to score the current model.</div>
      ) : (
        <div className="stack" style={{ gap: 24 }}>
          <div>
            <div className="small muted" style={{ marginBottom: 8 }}>
              Latest run #{latest.id} · {latest.provider} ·{" "}
              <span className="mono">{latest.model}</span> · {latest.cases} cases ·{" "}
              {new Date(latest.created_at).toLocaleString()}
            </div>
            <div className="kpis">
              <Kpi label="Schema valid" value={pct(latest.metrics.schema_valid_rate)} />
              <Kpi
                label="Category"
                value={pct(latest.metrics.category_accuracy)}
                sub={delta("category_accuracy")}
              />
              <Kpi
                label="Sentiment"
                value={pct(latest.metrics.sentiment_accuracy)}
                sub={delta("sentiment_accuracy")}
              />
              <Kpi
                label="Urgency ±1"
                value={pct(latest.metrics.urgency_within_1)}
                sub={
                  latest.metrics.urgency_mae === null
                    ? undefined
                    : `MAE ${latest.metrics.urgency_mae}`
                }
              />
              <Kpi label="Avg latency" value={`${latest.metrics.avg_latency_ms} ms`} />
              <Kpi
                label="Tokens"
                value={(latest.metrics.input_tokens + latest.metrics.output_tokens).toLocaleString()}
              />
            </div>
          </div>

          <div className="card">
            <h2>Misses in the latest run ({latest.failures.length})</h2>
            {latest.failures.length === 0 ? (
              <div className="empty">Every case matched on all fields.</div>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Case</th>
                      <th>Text</th>
                      <th>Expected</th>
                      <th>Got</th>
                    </tr>
                  </thead>
                  <tbody>
                    {latest.failures.map((f) => (
                      <tr key={f.id}>
                        <td className="mono small">{f.id}</td>
                        <td className="text-cell small">{f.text}</td>
                        {f.error ? (
                          <td colSpan={2} className="small" style={{ color: "var(--neg)" }}>
                            {f.error}
                          </td>
                        ) : (
                          <>
                            <td className="small">
                              {f.expected && <Triple {...f.expected} />}
                            </td>
                            <td className="small">
                              {f.got && f.expected && <Triple {...f.got} compare={f.expected} />}
                            </td>
                          </>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <div className="card">
            <h2>History</h2>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Run</th>
                    <th>Model</th>
                    <th>Category</th>
                    <th>Sentiment</th>
                    <th>Urgency ±1</th>
                    <th>Valid</th>
                    <th>When</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((r) => (
                    <tr key={r.id}>
                      <td>#{r.id}</td>
                      <td className="small">
                        {r.provider} · <span className="mono">{r.model}</span>
                      </td>
                      <td>{pct(r.metrics.category_accuracy)}</td>
                      <td>{pct(r.metrics.sentiment_accuracy)}</td>
                      <td>{pct(r.metrics.urgency_within_1)}</td>
                      <td>{pct(r.metrics.schema_valid_rate)}</td>
                      <td className="muted small">{new Date(r.created_at).toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function Triple({
  sentiment,
  category,
  urgency,
  compare,
}: {
  sentiment: string;
  category: string;
  urgency: number;
  compare?: { sentiment: string; category: string; urgency: number };
}) {
  const miss = { color: "var(--neg)", fontWeight: 600 };
  return (
    <span>
      <span style={compare && compare.category !== category ? miss : undefined}>
        {label(category)}
      </span>
      {" · "}
      <span style={compare && compare.sentiment !== sentiment ? miss : undefined}>
        {sentiment}
      </span>
      {" · "}
      <span style={compare && Math.abs(compare.urgency - urgency) > 1 ? miss : undefined}>
        u{urgency}
      </span>
    </span>
  );
}
