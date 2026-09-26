import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { FamilyEvidenceViewDto, InvestigationLinkDto, ResultDto } from "../api/types";
import { EmptyState, PageHeading } from "../components/common/Primitives";
import type { PageKey } from "../state/types";
import type { NavigationContext } from "../state/navigation";
import { useTimeZone } from "../state/TimeZoneContext";
import { compareTimeAsc, compareTimeDesc, contextSummary, formatEvidenceRange, formatTimestamp, friendlyCategory, groupInvestigationLinks, mechanismLabel, pluralize } from "../utils/formatting";

export function InvestigationsPage({ navigate, initialLinkId, initialFamily }: { navigate: (page: PageKey, context?: NavigationContext) => void; initialLinkId?: string; initialFamily?: string }) {
  const { zone } = useTimeZone();
  const [views, setViews] = useState<FamilyEvidenceViewDto[]>([]);
  const [links, setLinks] = useState<InvestigationLinkDto[]>([]);
  const [results, setResults] = useState<ResultDto[]>([]);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    void Promise.all([api.investigations(controller.signal), api.allResults(controller.signal)])
      .then(([value, resultRows]) => {
        if (!controller.signal.aborted) { setViews(value.family_views); setLinks(value.links); setResults(resultRows); setError(null); }
      })
      .catch((reason: unknown) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Investigation evidence is unavailable"); });
    return () => controller.abort();
  }, []);

  const groups = useMemo(() => groupInvestigationLinks(links, views), [links, views]);
  const viewsById = useMemo(() => new Map(views.map((view) => [view.family_view_id, view])), [views]);
  const resultsById = useMemo(() => new Map(results.map((result) => [result.result_id, result])), [results]);
  const focused = initialFamily ? groups.filter((group) => group.leftFamily === initialFamily || group.rightFamily === initialFamily) : groups;
  const initialLink = initialLinkId ? focused.find((group) => group.links.some((link) => link.link_id === initialLinkId)) : undefined;
  const selected = focused.find((group) => group.key === selectedKey) ?? initialLink ?? focused[0] ?? null;
  const selectedLinks = selected?.links ?? [];
  const contributingIds = [...new Set(selectedLinks.flatMap((link) => link.source_result_ids))];
  const timelineResults = contributingIds.map((id) => resultsById.get(id)).filter((result): result is ResultDto => Boolean(result)).sort((a, b) => compareTimeAsc(a.created_time, b.created_time) || a.result_id.localeCompare(b.result_id));
  const observationIds = [...new Set(selectedLinks.flatMap((link) => link.shared_source_observation_ids))];
  const selectedViews = [...new Map(selectedLinks.flatMap((link) => [viewsById.get(link.left_family_view_id), viewsById.get(link.right_family_view_id)]).filter((view): view is FamilyEvidenceViewDto => Boolean(view)).map((view) => [view.family_view_id, view])).values()];
  const familyOrder = selected ? [selected.leftFamily, selected.rightFamily] : [];
  const familySummaries = [...new Set(selectedViews.map((view) => view.family))].sort((a, b) => familyOrder.indexOf(a) - familyOrder.indexOf(b)).map((family) => {
    const familyViews = selectedViews.filter((view) => view.family === family);
    const findingCount = familyViews.reduce((count, view) => count + view.findings.length, 0);
    const start = familyViews.map((view) => view.time_start).sort(compareTimeAsc)[0];
    const end = familyViews.map((view) => view.time_end).sort(compareTimeDesc)[0];
    return { family, familyViews, findingCount, start, end };
  });
  const rangeStart = selectedViews.map((view) => view.time_start).sort(compareTimeAsc)[0];
  const rangeEnd = selectedViews.map((view) => view.time_end).sort(compareTimeDesc)[0];
  const contexts = [...new Set(timelineResults.map(contextSummary))];
  const groupedTimeline = [...timelineResults.reduce((groups, result) => {
    const rows = groups.get(result.created_time) ?? [];
    rows.push(result);
    groups.set(result.created_time, rows);
    return groups;
  }, new Map<string, ResultDto[]>())].sort(([a], [b]) => compareTimeAsc(a, b));
  const visibleTimelineGroups = groupedTimeline.slice(-4);
  const visibleTimelineIds = new Set(visibleTimelineGroups.flatMap(([, rows]) => rows.map((row) => row.result_id)));
  const earlierTimelineResults = timelineResults.filter((result) => !visibleTimelineIds.has(result.result_id));

  return <section className="page active-page" aria-labelledby="investigations-title">
    <PageHeading titleId="investigations-title" title="Investigations" deck="Chronology of separate family evidence connected by exact shared source observations." meta={<span className="quiet-tag">Joint-review context</span>} />
    {error && <div className="stream-notice" role="status">Investigation data could not be loaded: {error}</div>}
    {focused.length ? <div className="investigation-workspace">
      <nav className="panel investigation-context-list" aria-label="Investigation family pairs">
        <div className="context-list-head"><h2>Related family evidence</h2><span>{pluralize(focused.length, "pair")}</span></div>
        {focused.map((group) => {
          const ids = [...new Set(group.links.flatMap((link) => link.source_result_ids))];
          const firstContext = ids.map((id) => resultsById.get(id)).find((item): item is ResultDto => Boolean(item));
          return <button type="button" key={group.key} className={`investigation-pair-row${group.key === selected?.key ? " selected" : ""}`} aria-pressed={group.key === selected?.key} onClick={() => setSelectedKey(group.key)}>
            <strong>{familyName(group.leftFamily)} <span aria-hidden="true">+</span> {familyName(group.rightFamily)}</strong>
            {firstContext && <span className="pair-context">{contextSummary(firstContext)}</span>}
            <span className="pair-meta">{pluralize(group.links.length, "shared-context relationship")} · {formatTimestamp(group.latestTime)}</span>
          </button>;
        })}
      </nav>

      {selected && <article className="panel investigation-workspace-detail" aria-label="Selected investigation workspace">
        <header className="investigation-workspace-head">
          <div><p className="object-level-label">Joint investigation context</p><h2>{familyName(selected.leftFamily)} <span>+</span> {familyName(selected.rightFamily)}</h2><p>{contexts.slice(0, 2).join(" · ") || "Shared passive source context"}</p></div>
          <button className="secondary-button" onClick={() => navigate("results", { sourceResultIds: contributingIds })}>Open source evidence ({contributingIds.length})</button>
        </header>

        <div className="investigation-fact-strip">
          <div><span>Observed period</span><strong>{formatEvidenceRange(rangeStart, rangeEnd, zone)}</strong></div>
          <div><span>Relationships</span><strong>{pluralize(selectedLinks.length, "factual link")}</strong></div>
          <div><span>Family evidence views</span><strong>{pluralize(selectedViews.length, "view")}</strong></div>
          <div><span>Source Results</span><strong>{pluralize(contributingIds.length, "Result")}</strong></div>
        </div>
        <p className="relationship-guard">Shared passive context only. No causality or common attacker is inferred.</p>

        <div className="investigation-core-grid">
        <div className="investigation-evidence-side">
        <section className="investigation-family-section"><div className="workspace-section-heading"><h3>Contributing family evidence</h3><span>{pluralize(selectedViews.length, "view")}</span></div>
          <div className="investigation-family-grid">{familySummaries.map((summary) => <article className="investigation-family-summary grouped" key={summary.family}>
            <div><strong>{familyName(summary.family)}</strong><span>{pluralize(summary.familyViews.length, "evidence episode")}</span></div>
            <p>{pluralize(summary.findingCount, "finding")} · {formatEvidenceRange(summary.start, summary.end, zone)}</p>
            <details><summary>View {summary.familyViews.length} individual {summary.familyViews.length === 1 ? "episode" : "episodes"}</summary>
              <ul className="investigation-episode-list">{summary.familyViews.map((view) => {
                const viewContexts = [...new Set(view.source_result_ids.map((id) => resultsById.get(id)).filter((item): item is ResultDto => Boolean(item)).map(contextSummary))];
                return <li key={view.family_view_id}><span>{viewContexts[0] ?? "Observed context unavailable"} · {pluralize(view.findings.length, "finding")}</span><button className="text-button" onClick={() => navigate("alerts", { familyViewId: view.family_view_id })}>Open evidence →</button></li>;
              })}</ul>
            </details>
          </article>)}</div>
        </section>

        <section className="factual-links-section"><div className="workspace-section-heading"><h3>Why related</h3><span>Factual relationship</span></div>
          <p>{pluralize(observationIds.length, "exact passive source observation")} {observationIds.length === 1 ? "is" : "are"} shared across the contributing family evidence. This supports joint review only.</p>
          <details className="factual-link-disclosure"><summary>View {selectedLinks.length} factual {selectedLinks.length === 1 ? "link" : "links"}</summary>
            <div className="factual-link-list">{selectedLinks.map((link) => {
              const time = link.source_result_ids.map((id) => resultsById.get(id)?.created_time).filter((value): value is string => Boolean(value)).sort(compareTimeAsc)[0]
                ?? viewsById.get(link.left_family_view_id)?.time_start ?? "";
              return <article key={link.link_id}><div><strong>{time ? formatTimestamp(time) : "Time unavailable"} · {pluralize(link.shared_source_observation_ids.length, "shared observation")}</strong><span>{familyName(viewsById.get(link.left_family_view_id)?.family ?? "Family evidence")} + {familyName(viewsById.get(link.right_family_view_id)?.family ?? "Family evidence")}</span></div>
                <details><summary>Show technical lineage</summary><dl><div><dt>Link ID</dt><dd>{link.link_id}</dd></div><div><dt>Observation IDs</dt><dd>{link.shared_source_observation_ids.join(" · ") || "None"}</dd></div><div><dt>Source Result IDs</dt><dd>{link.source_result_ids.join(" · ") || "None"}</dd></div></dl></details>
              </article>;
            })}</div>
          </details>
        </section>
        </div>

        <section className="investigation-timeline-section"><div className="workspace-section-heading"><h3>Chronology</h3><span>{pluralize(timelineResults.length, "source Result")}</span></div>
          {timelineResults.length ? <ol className="investigation-timeline">{visibleTimelineGroups.map(([time, rows]) => <li key={time}>
            <time>{formatTimestamp(time)}</time>
            <div className="timeline-event-group">{rows.slice(0, 3).map((result) => {
              const sharesObservation = selectedLinks.some((link) => link.source_result_ids.includes(result.result_id));
              return <article className="timeline-result compact" key={result.result_id}><div><strong>{friendlyCategory(result.family)}</strong><span>{mechanismLabel(result.mechanism_id || result.lane_id)}</span></div><p>{contextSummary(result)}</p>{sharesObservation && <span className="timeline-context-badge">Shared source context</span>}<button className="text-button" onClick={() => navigate("results", { resultId: result.result_id })}>View source evidence →</button></article>;
            })}{rows.length > 3 && <details className="timeline-more-results"><summary>View {rows.length - 3} more Results at this time</summary>{rows.slice(3).map((result) => <div key={result.result_id}><span>{friendlyCategory(result.family)} · {mechanismLabel(result.mechanism_id || result.lane_id)}</span><button className="text-button" onClick={() => navigate("results", { resultId: result.result_id })}>Open evidence →</button></div>)}</details>}</div>
          </li>)}</ol> : <EmptyState>Source Results are not available for this relationship.</EmptyState>}
          {earlierTimelineResults.length > 0 && <details className="earlier-chronology"><summary>View {earlierTimelineResults.length} earlier source Results</summary><ol>{earlierTimelineResults.map((result) => <li key={result.result_id}><time>{formatTimestamp(result.created_time)}</time><span>{friendlyCategory(result.family)} · {mechanismLabel(result.mechanism_id || result.lane_id)} · {contextSummary(result)}</span><button className="text-button" onClick={() => navigate("results", { resultId: result.result_id })}>Open evidence →</button></li>)}</ol></details>}
        </section>
        </div>
      </article>}
    </div> : <section className="panel investigation-empty"><EmptyState>{error ? "Investigation data is unavailable." : "No exact shared-observation links are currently indexed."}</EmptyState></section>}
  </section>;
}

function familyName(value: string) { return friendlyCategory(value).replace(/ evidence$/i, ""); }
