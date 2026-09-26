import { useMemo, useState } from "react";
import { EmptyState, PageHeading } from "../components/common/Primitives";
import {
  ResultInspector,
  ResultTable,
} from "../components/inspector/Inspectors";
import { useEvidence } from "../state/EvidenceContext";
import { filterResults } from "../utils/filters";
import type { ResultDto } from "../api/types";
import { resultsSourceNote } from "../utils/copy";
import { friendlyCategory } from "../utils/formatting";

export function ResultsPage({
  initialResultId = null,
}: {
  initialResultId?: string | null;
}) {
  const { state, loadOlder } = useEvidence();
  const [search, setSearch] = useState("");
  const [family, setFamily] = useState("");
  const [resultType, setResultType] = useState("");
  const [selectedId, setSelectedId] = useState(initialResultId);
  const all = state.orderedResults
    .map((id) => state.results.get(id))
    .filter((item): item is ResultDto => Boolean(item));
  const items = useMemo(
    () => filterResults(all, { search, family, resultType }),
    [all, search, family, resultType],
  );
  const families = [...new Set(all.map((item) => item.family))].sort();
  const selected = selectedId ? (state.results.get(selectedId) ?? null) : null;
  return (
    <section className="page active-page" aria-labelledby="results-title">
      <PageHeading
        titleId="results-title"
        title="Evidence"
        deck="Search and inspect the recorded observations and analytic results."
      />
      <div className="results-callout">
        <span>
          {resultsSourceNote}
        </span>
      </div>
      <div className="filter-bar">
        <label className="search-control">
          <span aria-hidden="true">⌕</span>
          <input
            type="search"
            placeholder="Search entity, family or finding"
            aria-label="Search evidence results"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
        <label>
          Category
          <select value={family} onChange={(e) => setFamily(e.target.value)}>
            <option value="">All categories</option>
            {families.map((value) => (
              <option key={value} value={value}>{friendlyCategory(value)}</option>
            ))}
          </select>
        </label>
        <label>
          Result type
          <select
            value={resultType}
            onChange={(e) => setResultType(e.target.value)}
          >
            <option value="">All result types</option>
            {[
              "REVIEW_FINDING",
              "QUALITY_DEGRADED",
              "INSUFFICIENT_EVIDENCE",
              "PREREQUISITE_MISSING",
              "ANALYTIC_UNAVAILABLE",
              "PLUGIN_STATUS",
            ].map((value) => (
              <option value={value} key={value}>
                {value.replaceAll("_", " ").toLowerCase().replace(/^./, (char) => char.toUpperCase())}
              </option>
            ))}
          </select>
        </label>
        <span className="result-total" role="status" aria-live="polite">
          {items.length} {items.length === 1 ? "record" : "records"}
        </span>
      </div>
      {state.streamState === "reconnecting" && (
        <div className="stream-notice" role="status">
          Live stream reconnecting; durable REST results remain available.
        </div>
      )}
      <div className="investigation-layout results-layout">
        <section className="panel table-panel">
          {items.length ? (
            <ResultTable
              results={items}
              selectedId={selected?.result_id ?? null}
              onSelect={(result) => setSelectedId(result.result_id)}
            />
          ) : (
            <EmptyState>{all.length ? "No evidence records match these filters." : "No evidence records are available yet. Run a controlled replay to create demo activity."}</EmptyState>
          )}
          {state.nextCursor && (
            <button
              className="secondary-button load-more"
              onClick={() => void loadOlder()}
            >
              Load older results
            </button>
          )}
        </section>
        <ResultInspector
          result={selected}
          onClose={() => setSelectedId(null)}
        />
      </div>
    </section>
  );
}
