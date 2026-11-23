// Typed client for the Sift FastAPI backend.

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type DatasetStatus = "ingested" | "queued" | "processing" | "enriched" | "error";

export interface Dataset {
  id: number;
  name: string;
  filename: string;
  status: DatasetStatus;
  row_count: number;
  rejected_count: number;
  created_at: string;
}

export interface RejectedRow {
  line: number;
  id?: string | null;
  reason: string;
}

export interface DatasetStats {
  enriched: number;
  failed: number;
  by_sentiment: Record<string, number>;
  by_category: Record<string, number>;
  by_urgency: Record<string, number>;
  avg_confidence: number | null;
  high_urgency: number;
  input_tokens: number;
  output_tokens: number;
  avg_latency_ms: number | null;
}

export interface DatasetDetail extends Dataset {
  rejected_rows: RejectedRow[];
  stats: DatasetStats;
}

export interface Enrichment {
  status: "ok" | "failed";
  sentiment: string | null;
  category: string | null;
  urgency: number | null;
  summary: string | null;
  confidence: number | null;
  error: string | null;
  provider: string;
  model: string;
  attempts: number;
  latency_ms: number;
}

export interface RecordRow {
  id: number;
  external_id: string;
  text: string;
  customer: string | null;
  channel: string | null;
  enrichment: Enrichment | null;
}

export interface RecordPage {
  total: number;
  items: RecordRow[];
}

export interface EvalMetrics {
  schema_valid_rate: number;
  sentiment_accuracy: number;
  category_accuracy: number;
  urgency_within_1: number;
  urgency_mae: number | null;
  avg_latency_ms: number;
  input_tokens: number;
  output_tokens: number;
}

export interface EvalFailure {
  id: string;
  text: string;
  error?: string;
  expected?: { sentiment: string; category: string; urgency: number };
  got?: { sentiment: string; category: string; urgency: number };
}

export interface EvalRun {
  id: number;
  provider: string;
  model: string;
  cases: number;
  metrics: EvalMetrics;
  failures: EvalFailure[];
  created_at: string;
}

export interface AppConfig {
  provider: string;
  model: string;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { cache: "no-store", ...init });
  } catch {
    throw new ApiError(0, `Cannot reach the API at ${API_URL}. Is the backend running?`);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* keep statusText */
    }
    throw new ApiError(res.status, detail);
  }
  return (res.status === 204 ? undefined : await res.json()) as T;
}

export const api = {
  config: () => request<AppConfig>("/config"),
  listDatasets: () => request<Dataset[]>("/datasets"),
  getDataset: (id: number) => request<DatasetDetail>(`/datasets/${id}`),
  deleteDataset: (id: number) => request<void>(`/datasets/${id}`, { method: "DELETE" }),
  enrich: (id: number) => request<Dataset>(`/datasets/${id}/enrich`, { method: "POST" }),
  upload: (file: File, name?: string) => {
    const form = new FormData();
    form.append("file", file);
    if (name) form.append("name", name);
    return request<DatasetDetail>("/datasets", { method: "POST", body: form });
  },
  records: (id: number, params: Record<string, string | number | undefined>) => {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== "") qs.set(k, String(v));
    }
    return request<RecordPage>(`/datasets/${id}/records?${qs}`);
  },
  runEval: () => request<EvalRun>("/evals/run", { method: "POST" }),
  listEvals: () => request<EvalRun[]>("/evals"),
};

export const CATEGORIES = ["billing", "bug", "feature_request", "account", "shipping", "other"];
export const SENTIMENTS = ["positive", "neutral", "negative"];

export const label = (s: string) => s.replace(/_/g, " ");
export const pct = (x: number | null | undefined) =>
  x === null || x === undefined ? "n/a" : `${Math.round(x * 100)}%`;
