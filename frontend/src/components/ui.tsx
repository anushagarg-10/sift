import { label, type DatasetStatus } from "@/lib/api";

export function Kpi({ label, value, sub }: { label: string; value: React.ReactNode; sub?: string }) {
  return (
    <div className="kpi">
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{value}</div>
      {sub && <div className="kpi-sub">{sub}</div>}
    </div>
  );
}

export function Bars({
  data,
  order,
  onSelect,
}: {
  data: Record<string, number>;
  order?: string[];
  onSelect?: (key: string) => void;
}) {
  const keys = order ?? Object.keys(data);
  const max = Math.max(1, ...Object.values(data));
  return (
    <div className="bars">
      {keys.map((k) => {
        const n = data[k] ?? 0;
        return (
          <div
            key={k}
            className="bar-row"
            onClick={onSelect ? () => onSelect(k) : undefined}
            style={onSelect ? { cursor: "pointer" } : undefined}
            title={onSelect ? `Filter by ${label(k)}` : undefined}
          >
            <span>{label(k)}</span>
            <div className="bar-track">
              <div className="bar-fill" style={{ width: `${(n / max) * 100}%` }} />
            </div>
            <span className="bar-count">{n}</span>
          </div>
        );
      })}
    </div>
  );
}

export function StatusBadge({ status }: { status: DatasetStatus }) {
  const cls =
    status === "enriched"
      ? "positive"
      : status === "error"
        ? "error"
        : status === "queued" || status === "processing"
          ? "warn pulse"
          : "";
  return (
    <span className={`badge ${cls}`}>
      <span className="dot" />
      {status}
    </span>
  );
}

export function Sentiment({ value }: { value: string | null }) {
  if (!value) return <span className="muted">n/a</span>;
  return <span className={`badge ${value}`}>{value}</span>;
}

export function Urgency({ value }: { value: number | null }) {
  if (value === null) return <span className="muted">n/a</span>;
  return (
    <span className={`urgency ${value >= 4 ? "high" : ""}`} title={`Urgency ${value} of 5`}>
      {[1, 2, 3, 4, 5].map((i) => (
        <span key={i} className={i <= value ? "on" : ""} />
      ))}
    </span>
  );
}
