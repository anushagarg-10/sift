import { Suspense } from "react";
import { DatasetView } from "./DatasetView";

export default function DatasetPage({ params }: PageProps<"/datasets/[id]">) {
  return (
    <Suspense fallback={<p className="muted">Loading dataset...</p>}>
      <DatasetView params={params} />
    </Suspense>
  );
}
