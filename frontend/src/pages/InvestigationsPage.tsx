import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { FamilyEvidenceViewDto, InvestigationLinkDto, ResultDto } from "../api/types";
import { EmptyState, PageHeading } from "../components/common/Primitives";
import type { PageKey } from "../state/types";
import type { NavigationContext } from "../state/navigation";
import { contextSummary, formatShortTime, formatTimestamp, friendlyCategory, groupInvestigationLinks, mechanismLabel, pluralize, summarizeTableEvidence } from "../utils/formatting";

export function InvestigationsPage({ navigate, initialLinkId, initialFamily }: { navigate: (page: PageKey, context?: NavigationContext) => void; initialLinkId?: string; initialFamily?: string }) {
  const [views, setViews] = useState<FamilyEvidenceViewDto[]>([]);
  const [links, setLinks] = useState<InvestigationLinkDto[]>([]);
  const [results, setResults] = useState<ResultDto[]>([]);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    void Promise.all([api.investigations(controller.signal), api.allResults(controller.signal)])
      .then(([value, resultRows]) => {
        if (!controller.signal.aborted) {
          setViews(value.family_views);
          setLinks(value.links);
          setResults(resultRows);
          setError(null);
        }
      })
      .catch((reason: unknown) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Investigation evidence is unavailable"); });
    return () => controller.abort();
  }, []);

  const groups = useMemo(() => groupInvestigationLinks(links, views), [links, views]);
  const byId = useMemo(() => new Map(views.map((view) => [view.family_view_id, view])), [views]);
  const resultsById = useMemo(() => new Map(results.map((result) => [result.result_id, result])), [results]);
  const focused = initialFamily ? groups.filter((group) => group.leftFamily === initialFamily || group.rightFamily === initialFamily) : groups;
  const initialLink = initialLinkId ? focused.find((group) => group.links.some((link) => link.link_id === initialLinkId)) : undefined;
  const selected = focused.find((group) => group.key === selectedKey) ?? initialLink ?? focused[0] ?? null;
  const selectedLinks = selected?.links ?? [];
  const contributingIds = [...new Set(selectedLinks.flatMap((link) => link.source_result_ids))];
  const timelineResults = contributingIds.map((id) => resultsById.get(id)).filter((result): result is ResultDto => Boolean(result)).sort((a, b) => a.created_time.localeCompare(b.created_time) || a.result_id.localeCompare(b.result_id));
  const observationIds = [...new Set(selectedLinks.flatMap((link) => link.shared_source_observation_ids))];
  const selectedViews = [...new Map(selectedLinks.flatMap((link) => [byId.get(link.left_family_view_id), byId.get(link.right_family_view_id)]).filter((view): view is FamilyEvidenceViewDto => Boolean(view)).map((view) => [view.family_view_id, view])).values()];
  const rangeStart = selectedViews.map((view) => view.time_start).sort()[0];
  const rangeEnd = selectedViews.map((view) => view.time_end).sort().at(-1);

  return <section className="page active-page" aria-labelledby="investigations-title">
    <PageHeading titleId="investigations-title" title="Investigations" deck="Review separate family evidence connected by exact shared source observations." meta={<span className="quiet-tag">Joint-review context</span>} />
    {error && <div className="stream-notice" role="status">Investigation data could not be loaded: {error}</div>}
    {focused.length ? <div className="investigation-workspace">
      <nav className="panel investigation-context-list" aria-label="Investigation family pairs">
        <div className="context-list-head"><h2>Related family evidence</h2><span>{pluralize(focused.length, "pair")}</span></div>
        {focused.map((group) => {
          const ids = [...new Set(group.links.flatMap((link) => link.source_result_ids))];
          const firstContext = ids.map((id) => resultsById.get(id)).find((item): item is ResultDto => Boolean(item));
          return <button type="button" key={group.key} className={`investigation-pair-row${group.key === selected?.key ? " selected" : ""}`} aria-pressed={group.key === selected?.key} onClick={() => setSelectedKey(group.key)}>
            <strong>{friendlyCategory(group.leftFamily)} <span aria-hidden="true">+</span> {friendlyCategory(group.rightFamily)}</strong>
            {firstContext && <span className="pair-context">{contextSummary(firstContext)}</span>}
            <span className="pair-meta">{pluralize(group.links.length, "factual link")} · {formatShortTime(group.latestTime)}</span>
          </button>;
        })}
      </nav>

      {selected && <article className="panel investigation-workspace-detail" aria-label="Selected investigation workspace">
        <header className="investigation-workspace-head">
          <div><p className="object-level-label">Investigation relationship</p><h2>{friendlyCategory(selected.leftFamily)} <span>+</span> {friendlyCategory(selected.rightFamily)}</h2><p>Separate family evidence shares passive source context.</p></div>
          <button className="secondary-button" onClick={() => navigate("results", { sourceResultIds: contributingIds })}>Open source Results ({contributingIds.length})</button>
        </header>

        <div className="investigation-fact-strip">
          <div><span>Period</span><strong>{rangeStart ? formatTimestamp(rangeStart) : "Time unavailable"}{rangeEnd && rangeStart !== rangeEnd ? ` – ${formatTimestamp(rangeEnd)}` : ""}</strong></div>
          <div><span>Families</span><strong>2</strong></div>
          <div><span>Factual links</span><strong>{pluralize(selectedLinks.length, "link")}</strong></div>
          <div><span>Shared observations</span><strong>{pluralize(observationIds.length, "observation")}</strong></div>
        </div>

        <p className="relationship-guard">These links support joint review only. They do not establish causality or a common attacker.</p>

        <div className="relationship-summary-visual" aria-label={`${friendlyCategory(selected.leftFamily)} and ${friendlyCategory(selected.rightFamily)} share passive source observations`}>
          <div>{friendlyCategory(selected.leftFamily)}<small>Family evidence</small></div><span className="relationship-line"><i>same observed source context</i></span><div>{friendlyCategory(selected.rightFamily)}<small>Family evidence</small></div>
        </div>

        <section className="investigation-timeline-section"><div className="workspace-section-heading"><h3>Chronology</h3><span>{pluralize(timelineResults.length, "source Result")}</span></div>
          {timelineResults.length ? <ol className="investigation-timeline">{timelineResults.map((result) => <li key={result.result_id}>
            <time>{formatTimestamp(result.created_time)}</time>
            <div className="timeline-result"><div><strong>{friendlyCategory(result.family)}</strong><span>{mechanismLabel(result.mechanism_id || result.lane_id)}</span></div><p>{contextSummary(result)}</p><p className="timeline-summary">{summarizeTableEvidence(result.evidence)}</p><button className="text-button" onClick={() => navigate("results", { resultId: result.result_id })}>View source Result →</button></div>
          </li>)}</ol> : <EmptyState>Source Results are not available for this relationship.</EmptyState>}
        </section>

        <section className="investigation-family-section"><div className="workspace-section-heading"><h3>Family evidence</h3><span>{pluralize(selectedViews.length, "view")}</span></div>
          <div className="investigation-family-grid">{selectedViews.map((view) => <FamilyEvidence key={view.family_view_id} view={view} resultsById={resultsById} onOpen={() => navigate("alerts", { familyViewId: view.family_view_id })} />)}</div>
        </section>

        <section className="factual-links-section"><div className="workspace-section-heading"><h3>Why these are related</h3><span>Exact links retained</span></div><p>The API reports a separate factual link for each pair of family evidence views. Each link is listed independently below.</p>
          <div className="factual-link-list">{selectedLinks.map((link) => <article key={link.link_id}><div><strong>{pluralize(link.shared_source_observation_ids.length, "shared observation")}</strong><span>Shared source observations occur in both family views.</span></div><details><summary>Show source lineage</summary><dl><div><dt>Link ID</dt><dd>{link.link_id}</dd></div><div><dt>Shared observation IDs</dt><dd>{link.shared_source_observation_ids.join(" · ") || "None"}</dd></div><div><dt>Source Result IDs</dt><dd>{link.source_result_ids.join(" · ") || "None"}</dd></div></dl></details></article>)}</div>
        </section>
      </article>}
    </div> : <section className="panel investigation-empty"><EmptyState>{error ? "Investigation data is unavailable." : "No exact shared-observation links are currently indexed."}</EmptyState></section>}
  </section>;
}

function FamilyEvidence({ view, resultsById, onOpen }: { view: FamilyEvidenceViewDto; resultsById: Map<string, ResultDto>; onOpen: () => void }) {
  const contexts = [...new Set(view.source_result_ids.map((id) => resultsById.get(id)).filter((item): item is ResultDto => Boolean(item)).map(contextSummary))];
  return <article className="investigation-family-summary"><div><strong>{friendlyCategory(view.family)}</strong><span>{pluralize(view.findings.length, "finding")}</span></div><p>{contexts.slice(0, 2).join(" · ") || "Observed context unavailable"}</p><p>{formatShortTime(view.time_start)}{view.time_end !== view.time_start ? `–${formatShortTime(view.time_end)}` : ""}</p><button className="text-button" onClick={onOpen}>Open family evidence →</button></article>;
}
