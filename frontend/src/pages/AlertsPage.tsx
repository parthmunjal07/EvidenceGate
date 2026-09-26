import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { FamilyEvidenceViewDto, InvestigationLinkDto, ResultDto, SihAlertProjection } from "../api/types";
import { EmptyState, PageHeading } from "../components/common/Primitives";
import { Header as InspectorHeader, Inspector } from "../components/inspector/InspectorShell";
import { useEvidence } from "../state/EvidenceContext";
import { contextSummary, formatShortTime, formatTimestamp, friendlyCategory, groupFamilyFindings, pluralize, prerequisiteLabel, readable } from "../utils/formatting";
import type { PageKey } from "../state/types";
import type { NavigationContext } from "../state/navigation";

export function AlertsPage({ initialAlert, clearInitial, openResult, navigate, initialFamilyViewId, initialFamily }: { initialAlert: SihAlertProjection | null; clearInitial: () => void; openResult: (id: string) => void; navigate: (page: PageKey, context?: NavigationContext) => void; initialFamilyViewId?: string; initialFamily?: string }) {
  const { state } = useEvidence();
  const [views, setViews] = useState<FamilyEvidenceViewDto[]>([]);
  const [links, setLinks] = useState<InvestigationLinkDto[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [family, setFamily] = useState(initialFamily ?? "");
  const [loadError, setLoadError] = useState<string | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    void Promise.all([api.familyEvidence(controller.signal), api.investigations(controller.signal)])
      .then(([evidence, investigation]) => {
        setViews(evidence.family_views);
        setLinks(investigation.links);
        const alertResultId = initialAlert?.source_result_ids[0];
        const fromAlert = alertResultId ? evidence.family_views.find((view) => view.source_result_ids.includes(alertResultId)) : undefined;
        setSelectedId(initialFamilyViewId && evidence.family_views.some((view) => view.family_view_id === initialFamilyViewId) ? initialFamilyViewId : fromAlert?.family_view_id ?? null);
        setLoadError(null);
      })
      .catch((error: unknown) => { if (!controller.signal.aborted) setLoadError(error instanceof Error ? error.message : "Family evidence is unavailable"); });
    return () => controller.abort();
  }, [state.orderedResults.length, initialAlert, initialFamilyViewId]);

  const resultById = useMemo(() => new Map(state.orderedResults.flatMap((id) => {
    const result = state.results.get(id);
    return result ? [[id, result] as const] : [];
  })), [state.orderedResults, state.results]);
  const families = [...new Set(views.map((view) => view.family))];
  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();
    return views.filter((view) => (!family || view.family === family) && (!query || [view.family, ...view.entity_references, ...view.findings.flatMap((finding) => [finding.title, ...finding.statements])].join(" ").toLowerCase().includes(query)));
  }, [views, search, family]);
  const selected = filtered.find((view) => view.family_view_id === selectedId) ?? null;
  const related = selected ? links.filter((link) => link.left_family_view_id === selected.family_view_id || link.right_family_view_id === selected.family_view_id) : [];
  const viewsById = useMemo(() => new Map(views.map((view) => [view.family_view_id, view])), [views]);
  const sourceResults = selected?.source_result_ids.map((id) => resultById.get(id)).filter((item): item is ResultDto => Boolean(item)) ?? [];
  const contexts = [...new Set(sourceResults.map(contextSummary))];
  const episodeContext = contexts.slice(0, 2).join(" · ") || "Observed network context";
  const groupedFindings = selected ? groupFamilyFindings(selected.findings) : [];
  const limitationCount = selected ? new Set([...selected.limitations, ...selected.missing_evidence]).size : 0;

  const openFamily = (viewId: string) => { setSelectedId(viewId); clearInitial(); };
  const openSourceResults = () => {
    if (selected) navigate("results", { sourceResultIds: selected.source_result_ids });
  };

  return <section className="page active-page" aria-labelledby="alerts-title">
    <PageHeading titleId="alerts-title" title="Analyst queue" deck="Review family evidence episodes while keeping each source Result independent." meta={<span>Evidence supports review; it does not confirm malicious activity.</span>} />
    <div className="filter-bar analyst-filter-bar">
      <label className="search-control"><span aria-hidden="true">⌕</span><input type="search" placeholder="Search address, domain, finding or family" aria-label="Search analyst queue" value={search} onChange={(event) => setSearch(event.target.value)} /></label>
      <label>Family<select value={family} onChange={(event) => setFamily(event.target.value)}><option value="">All families</option>{families.map((item) => <option key={item}>{item}</option>)}</select></label>
      <span className="result-total" role="status" aria-live="polite">{pluralize(filtered.length, "episode")}</span>
    </div>
    {loadError && <div className="stream-notice" role="status">Family evidence could not be loaded: {loadError}</div>}
    <section className="panel family-queue-panel">
      {filtered.length ? <div className="table-wrap"><table className="data-table family-queue-table"><thead><tr>{["Time", "Family", "Context", "Findings", "Evidence gaps", "Related", "Action"].map((name) => <th key={name}>{name}</th>)}</tr></thead><tbody>
        {filtered.map((view) => {
          const viewResults = view.source_result_ids.map((id) => resultById.get(id)).filter((item): item is ResultDto => Boolean(item));
          const viewContext = [...new Set(viewResults.map(contextSummary))].slice(0, 2).join(" · ") || "Observed network context";
          const viewLinks = links.filter((link) => link.left_family_view_id === view.family_view_id || link.right_family_view_id === view.family_view_id);
          const gaps = new Set([...view.limitations, ...view.missing_evidence]).size;
          return <tr key={view.family_view_id} className={`selectable-row${selectedId === view.family_view_id ? " selected" : ""}`} tabIndex={0} onClick={() => openFamily(view.family_view_id)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); openFamily(view.family_view_id); } }}>
            <td><time>{formatShortTime(view.time_start)}{view.time_end !== view.time_start && <>–{formatShortTime(view.time_end)}</>}</time></td>
            <td><strong>{friendlyCategory(view.family)}</strong></td>
            <td title={viewContext}>{viewContext}</td>
            <td>{pluralize(view.findings.length, "finding")}</td>
            <td>{gaps ? pluralize(gaps, "limit") : "None reported"}</td>
            <td>{pluralize(viewLinks.length, "link")}</td>
            <td><button className="text-button" onClick={(event) => { event.stopPropagation(); openFamily(view.family_view_id); }}>Open evidence →</button></td>
          </tr>;
        })}
      </tbody></table></div> : <EmptyState>{loadError ? "Family evidence is unavailable." : "No family evidence matches these filters."}</EmptyState>}
    </section>

    {selected && <Inspector variant="modal" label="Family evidence episode" selected onClose={() => setSelectedId(null)} placeholder="" description="">
      <div className="family-episode">
        <InspectorHeader kicker="Family evidence episode" title={friendlyCategory(selected.family)} subtitle={episodeContext} onClose={() => setSelectedId(null)} />
        <div className="episode-summary">
          <div><span>Activity</span><strong>{formatTimestamp(selected.time_start)}{selected.time_end !== selected.time_start ? ` – ${formatTimestamp(selected.time_end)}` : ""}</strong></div>
          <div><span>Findings</span><strong>{pluralize(selected.findings.length, "independent finding")}</strong></div>
          <div><span>Evidence limits</span><strong>{pluralize(limitationCount, "limit")}</strong></div>
          <div><span>Related</span><strong>{pluralize(related.length, "investigation link")}</strong></div>
        </div>
        <div className="episode-actions"><button className="primary-button" onClick={openSourceResults}>Open source Results ({selected.source_result_ids.length})</button>{related.length > 0 && <button className="secondary-button" onClick={() => navigate("investigations", related.length === 1 ? { linkId: related[0]!.link_id } : { family: selected.family })}>Open investigation{related.length === 1 ? "" : "s"}</button>}</div>

        <section className="episode-section"><h3>Episode summary</h3><p>This view groups family Results that share observed source context. The underlying mechanism Results remain separate.</p></section>

        <section className="episode-section"><h3>Findings</h3><div className="finding-groups">{groupedFindings.map((group) => <details className="finding-group" key={group.title}>
          <summary><span>{group.title}</span><span className="finding-group-count">{pluralize(group.findings.length, "source Result")}</span></summary>
          <ol>{group.findings.map((finding) => {
            const sourceResult = resultById.get(finding.source_result_id);
            return <li key={finding.source_result_id}>
              <div><strong>{finding.title}</strong><span>{readable(finding.result_type)}</span></div>
              {sourceResult && <time>{formatTimestamp(sourceResult.created_time)}</time>}
              {finding.statements.filter((statement) => !selected.source_observation_ids.includes(statement) && !/^state:/i.test(statement.trim())).map((statement) => <p key={statement}>{statement}</p>)}
              <button className="text-button" onClick={() => openResult(finding.source_result_id)}>View source Result →</button>
            </li>;
          })}</ol>
        </details>)}</div></section>

        {selected.missing_evidence.length > 0 && <section className="episode-section"><h3>Evidence gaps</h3><ul>{selected.missing_evidence.map((item) => <li key={item}>{prerequisiteLabel(item)}</li>)}</ul></section>}
        {selected.limitations.length > 0 && <section className="episode-section"><h3>What this does not establish</h3><ul>{selected.limitations.map((item) => <li key={item}>{item}</li>)}</ul></section>}

        <details className="episode-disclosure"><summary>Visibility and quality</summary>
          <p>{selected.visibility_summary.length ? selected.visibility_summary.map((value) => value.replaceAll("_", " ").toLowerCase()).join(" · ") : "No visibility summary is available."}</p>
          <p>{selected.quality_summary.length ? selected.quality_summary.map((value) => value.replaceAll("_", " ").toLowerCase()).join(" · ") : "No quality summary is available."}</p>
        </details>

        <section className="episode-section related-episodes"><h3>Related investigations</h3>{related.length ? related.map((link) => {
          const otherId = link.left_family_view_id === selected.family_view_id ? link.right_family_view_id : link.left_family_view_id;
          const other = viewsById.get(otherId);
          return other ? <article key={link.link_id}><div><strong>{friendlyCategory(other.family)} evidence</strong><span>{pluralize(link.shared_source_observation_ids.length, "shared observation")}</span></div><button className="text-button" onClick={() => navigate("investigations", { linkId: link.link_id })}>Open investigation →</button></article> : null;
        }) : <p>No exact shared-observation relationship is currently indexed.</p>}</section>

        <details className="episode-disclosure"><summary>Show source lineage</summary><ul>{selected.source_observation_ids.map((id) => <li key={id}>{id}</li>)}</ul></details>
      </div>
    </Inspector>}
  </section>;
}
