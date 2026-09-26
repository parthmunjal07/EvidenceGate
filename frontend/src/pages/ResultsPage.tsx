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
import { useEffect } from "react";
import { api } from "../api/client";

export function ResultsPage({
  initialResultId = null,
  sourceResultIds = [],
}: {
  initialResultId?: string | null;
  sourceResultIds?: string[];
}) {
  const { state, loadOlder, dispatch } = useEvidence();
  const [search, setSearch] = useState("");
  const [family, setFamily] = useState("");
  const [resultType, setResultType] = useState("");
  const [selectedId, setSelectedId] = useState(initialResultId);
  const sourceIdKey = sourceResultIds.join("\u0000");
  const stableSourceIds = useMemo(() => sourceIdKey ? sourceIdKey.split("\u0000") : [], [sourceIdKey]);
  const missingSourceIds = useMemo(() => stableSourceIds.filter((id) => !state.results.has(id)), [stableSourceIds, state.results]);
  useEffect(() => {
    if (!missingSourceIds.length) return;
    const controller = new AbortController();
    void Promise.all(missingSourceIds.map((id) => api.result(id, controller.signal)))
      .then((results) => { if (!controller.signal.aborted) dispatch({ type: "results", value: results }); })
      .catch(() => undefined);
    return () => controller.abort();
  }, [missingSourceIds, dispatch]);
  const all = state.orderedResults
    .map((id) => state.results.get(id))
    .filter((item): item is ResultDto => Boolean(item));
  const scoped = sourceResultIds.length ? all.filter((item) => sourceResultIds.includes(item.result_id)) : all;
  const items = useMemo(
    () => filterResults(scoped, { search, family, resultType }),
    [scoped, search, family, resultType],
  );
  const families = [...new Set(all.map((item) => item.family))].sort();
  const selected = selectedId ? (state.results.get(selectedId) ?? null) : null;
  return (
    <section className="page active-page" aria-labelledby="results-title">
      <PageHeading
        titleId="results-title"
        title="Evidence"
        deck="Search independent mechanism Results. Select a row to open its evidence details."
      />
      {sourceResultIds.length > 0 && <div className="results-callout">Showing {sourceResultIds.length} source Result{sourceResultIds.length === 1 ? "" : "s"} from the selected family or investigation.</div>}
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
      <div className="results-layout">
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
      </div>
      <ResultInspector result={selected} onClose={() => setSelectedId(null)} />
    </section>
  );
}
