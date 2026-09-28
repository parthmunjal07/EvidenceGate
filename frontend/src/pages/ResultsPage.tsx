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
import {
  normalizeFamilyName,
  RESULT_FAMILY_OPTIONS,
  resultCountLabel,
  resultEvidenceStateLabel,
} from "../utils/formatting";
import { useEffect } from "react";
import { api } from "../api/client";
import { useTimeZone } from "../state/TimeZoneContext";
import {
  compareTimeAsc,
  compareTimeDesc,
  formatEvidenceRange,
  formatTimeZoneLabel,
} from "../utils/formatting";
import {
  cachedObservationIds,
  readCachedObservation,
  readCachedObservations,
} from "../utils/replayEvidenceCache";
import { ObservationDetail } from "../components/replay/NetworkObservationsSection";
import type { PageKey } from "../state/types";
import type { NavigationContext } from "../state/navigation";

export function ResultsPage({
  initialResultId = null,
  sourceResultIds = [],
  navigate,
}: {
  initialResultId?: string | null;
  sourceResultIds?: string[];
  navigate?: (page: PageKey, context?: NavigationContext) => void;
}) {
  const { state, loadOlder, dispatch } = useEvidence();
  const { zone } = useTimeZone();
  const [search, setSearch] = useState("");
  const [family, setFamily] = useState("");
  const [resultType, setResultType] = useState("");
  const [selectedId, setSelectedId] = useState(initialResultId);
  const [sourceObservationId, setSourceObservationId] = useState<string | null>(
    null,
  );
  const sourceIdKey = sourceResultIds.join("\u0000");
  const stableSourceIds = useMemo(
    () => (sourceIdKey ? sourceIdKey.split("\u0000") : []),
    [sourceIdKey],
  );
  const missingSourceIds = useMemo(
    () => stableSourceIds.filter((id) => !state.results.has(id)),
    [stableSourceIds, state.results],
  );
  useEffect(() => {
    if (!missingSourceIds.length) return;
    const controller = new AbortController();
    void api
      .allResults(controller.signal)
      .then((results) => {
        if (!controller.signal.aborted)
          dispatch({ type: "results", value: results });
      })
      .catch(() => undefined);
    return () => controller.abort();
  }, [missingSourceIds, dispatch]);
  const all = state.orderedResults
    .map((id) => state.results.get(id))
    .filter((item): item is ResultDto => Boolean(item));
  const scoped = sourceResultIds.length
    ? all.filter((item) => sourceResultIds.includes(item.result_id))
    : all;
  const items = useMemo(
    () => filterResults(scoped, { search, family, resultType }),
    [scoped, search, family, resultType],
  );
  const selected = selectedId ? (state.results.get(selectedId) ?? null) : null;
  const cachedSourceIds = selected
    ? cachedObservationIds(selected.source_observation_ids)
    : [];
  const cachedSources = selected
    ? readCachedObservations(selected.source_observation_ids)
    : [];
  const cachedSource = sourceObservationId
    ? readCachedObservation(sourceObservationId)
    : null;
  const openFamily =
    selected && navigate
      ? () =>
          navigate("alerts", {
            family: normalizeFamilyName(selected.family),
            returnResultId: selected.result_id,
          })
      : undefined;
  const openInvestigation =
    selected && navigate
      ? () =>
          navigate("investigations", {
            family: normalizeFamilyName(selected.family),
          })
      : undefined;
  return (
    <section className="page active-page" aria-labelledby="results-title">
      <PageHeading
        titleId="results-title"
        title="Evidence"
        deck={`What an individual analytic observed. Each row is one independent Result · display zone ${formatTimeZoneLabel(zone)}.`}
      />
      {all.length > 0 && (
        <p className="analyst-time-note">
          Currently loaded Result time range:{" "}
          {formatEvidenceRange(
            all.map((result) => result.created_time).sort(compareTimeAsc)[0],
            all.map((result) => result.created_time).sort(compareTimeDesc)[0],
            zone,
          )}
          .
        </p>
      )}
      {sourceResultIds.length > 0 && (
        <div className="results-callout">
          Showing {sourceResultIds.length} source Result
          {sourceResultIds.length === 1 ? "" : "s"} from the selected family or
          investigation.
        </div>
      )}
      <div className="results-callout">
        <span>{resultsSourceNote}</span>
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
          Family
          <select value={family} onChange={(e) => setFamily(e.target.value)}>
            <option value="">All families</option>
            {RESULT_FAMILY_OPTIONS.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </label>
        <label>
          Evidence state
          <select
            value={resultType}
            onChange={(e) => setResultType(e.target.value)}
          >
            <option value="">All states</option>
            {[
              "REVIEW_FINDING",
              "QUALITY_DEGRADED",
              "INSUFFICIENT_EVIDENCE",
              "PREREQUISITE_MISSING",
              "ANALYTIC_UNAVAILABLE",
              "PLUGIN_STATUS",
            ].map((value) => (
              <option value={value} key={value}>
                {resultEvidenceStateLabel(value)}
              </option>
            ))}
          </select>
        </label>
        <span className="result-total" role="status" aria-live="polite">
          {resultCountLabel(items.length)}
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
            <EmptyState>
              {all.length
                ? "No Results match these filters."
                : "No Results are available yet. Run a controlled replay to create demo activity."}
            </EmptyState>
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
      <ResultInspector
        result={selected}
        onClose={() => setSelectedId(null)}
        availableSourceCount={cachedSourceIds.length}
        sourceObservations={cachedSources}
        onOpenSource={(index) =>
          setSourceObservationId(cachedSourceIds[index] ?? null)
        }
        {...(openFamily ? { onOpenFamily: openFamily } : {})}
        {...(openInvestigation
          ? { onOpenInvestigation: openInvestigation }
          : {})}
      />
      {cachedSource && (
        <ObservationDetail
          row={{
            observation: cachedSource.observation,
            source: cachedSource.source,
          }}
          routes={cachedSource.routes}
          results={cachedSource.results}
          close={() => setSourceObservationId(null)}
          navigate={(_page, context) => {
            if (context?.resultId) {
              setSourceObservationId(null);
              setSelectedId(context.resultId);
            }
          }}
        />
      )}
    </section>
  );
}
