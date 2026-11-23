"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { StatusBadge } from "@/components/ui";
import { api, type Dataset } from "@/lib/api";

export default function DatasetsPage() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [datasets, setDatasets] = useState<Dataset[] | null>(null);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [drag, setDrag] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .listDatasets()
      .then((d) => {
        setDatasets(d);
        setError(null);
      })
      .catch((e: Error) => {
        setDatasets([]);
        setError(e.message);
      });
  }, []);

  useEffect(load, [load]);

  async function uploadFile(file: File) {
    setBusy(true);
    setError(null);
    try {
      const ds = await api.upload(file, name.trim() || undefined);
      router.push(`/datasets/${ds.id}`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  async function uploadSample() {
    const res = await fetch("/sample-feedback.csv");
    const blob = await res.blob();
    await uploadFile(new File([blob], "sample-feedback.csv", { type: "text/csv" }));
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Datasets</h1>
          <p className="subtitle">
            Upload customer feedback as CSV. Rows are validated, stored in Postgres, then enriched
            by an LLM with schema-checked JSON output.
          </p>
        </div>
      </div>

      <div className="grid grid-2" style={{ marginBottom: 24 }}>
        <div className="card stack">
          <h2>Upload a CSV</h2>
          <div
            className={`dropzone ${drag ? "drag" : ""}`}
            onClick={() => inputRef.current?.click()}
            onDragOver={(e) => {
              e.preventDefault();
              setDrag(true);
            }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDrag(false);
              const f = e.dataTransfer.files[0];
              if (f) uploadFile(f);
            }}
          >
            <strong>{busy ? "Uploading..." : "Drop a .csv here"}</strong> or click to browse
            <div className="small" style={{ marginTop: 6 }}>
              Required columns: <code>id</code>, <code>text</code>. Optional:{" "}
              <code>customer</code>, <code>channel</code>.
            </div>
          </div>
          <input
            ref={inputRef}
            type="file"
            accept=".csv,text/csv"
            hidden
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) uploadFile(f);
              e.target.value = "";
            }}
          />
          <div className="row">
            <input
              className="input"
              style={{ flex: 1 }}
              placeholder="Dataset name (optional)"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
            <button className="btn" onClick={uploadSample} disabled={busy}>
              Use sample data
            </button>
          </div>
          {error && <div className="alert">{error}</div>}
        </div>

        <div className="card stack small">
          <h2>How it works</h2>
          <ol className="list" style={{ fontSize: 14, display: "grid", gap: 6 }}>
            <li>
              <strong>Ingest.</strong> The FastAPI service parses the CSV, rejects bad rows with a
              reason (missing fields, duplicates, oversized text) and keeps the rest.
            </li>
            <li>
              <strong>Enrich.</strong> Each record is classified for sentiment, category, urgency
              and a one-line summary. Output is validated with Pydantic and retried if it fails.
            </li>
            <li>
              <strong>Evaluate.</strong> The same pipeline runs against a labelled golden set to
              track accuracy, latency and token cost over time.
            </li>
          </ol>
        </div>
      </div>

      <div className="card">
        <h2>All datasets</h2>
        {datasets === null ? (
          <p className="muted">Loading...</p>
        ) : datasets.length === 0 ? (
          <div className="empty">No datasets yet. Upload a CSV or try the sample data.</div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Status</th>
                  <th>Rows</th>
                  <th>Rejected</th>
                  <th>Uploaded</th>
                </tr>
              </thead>
              <tbody>
                {datasets.map((d) => (
                  <tr
                    key={d.id}
                    className="clickable"
                    onClick={() => router.push(`/datasets/${d.id}`)}
                  >
                    <td>
                      <Link href={`/datasets/${d.id}`}>
                        <strong>{d.name}</strong>
                      </Link>
                      <div className="summary mono">{d.filename}</div>
                    </td>
                    <td>
                      <StatusBadge status={d.status} />
                    </td>
                    <td>{d.row_count}</td>
                    <td className={d.rejected_count ? "" : "muted"}>{d.rejected_count}</td>
                    <td className="muted small">{new Date(d.created_at).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
