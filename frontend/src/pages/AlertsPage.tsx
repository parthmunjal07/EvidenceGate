import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { FamilyEvidenceViewDto, InvestigationLinkDto, SihAlertProjection } from "../api/types";
import { EmptyState, PageHeading } from "../components/common/Primitives";
import { Header as InspectorHeader, Inspector } from "../components/inspector/InspectorShell";
import { useEvidence } from "../state/EvidenceContext";
import { formatTimestamp, formatShortTime, mechanismLabel, summarizeReference } from "../utils/formatting";
import type { PageKey } from "../state/types";
import type { NavigationContext } from "../state/navigation";

export function AlertsPage({ initialAlert, clearInitial, openResult, navigate, initialFamilyViewId }: { initialAlert: SihAlertProjection | null; clearInitial: () => void; openResult: (id: string) => void; navigate: (page: PageKey, context?: NavigationContext) => void; initialFamilyViewId?: string }) {
  const { state } = useEvidence();
  const [views, setViews] = useState<FamilyEvidenceViewDto[]>([]);
  const [links, setLinks] = useState<InvestigationLinkDto[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [family, setFamily] = useState("");
  const [loadError, setLoadError] = useState<string | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    void Promise.all([api.familyEvidence(controller.signal), api.investigations(controller.signal)])
      .then(([evidence, investigation]) => {
        setViews(evidence.family_views);
        setLinks(investigation.links);
        const alertResultId = initialAlert?.source_result_ids[0];
        const fromAlert = alertResultId ? evidence.family_views.find((view) => view.source_result_ids.includes(alertResultId)) : undefined;
        setSelectedId((current) => initialFamilyViewId && evidence.family_views.some((view) => view.family_view_id === initialFamilyViewId) ? initialFamilyViewId : fromAlert?.family_view_id ?? (current && evidence.family_views.some((view) => view.family_view_id === current) ? current : null));
        setLoadError(null);
      })
      .catch((error: unknown) => { if (!controller.signal.aborted) setLoadError(error instanceof Error ? error.message : "Family evidence is unavailable"); });
    return () => controller.abort();
  }, [state.orderedResults.length, initialAlert, initialFamilyViewId]);
  const families = [...new Set(views.map((view) => view.family))];
  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();
    return views.filter((view) => (!family || view.family === family) && (!query || [view.family, ...view.entity_references, ...view.findings.flatMap((finding) => [finding.title, ...finding.statements])].join(" ").toLowerCase().includes(query)));
  }, [views, search, family]);
  const selected = filtered.find((view) => view.family_view_id === selectedId) ?? null;
  const related = selected ? links.filter((link) => link.left_family_view_id === selected.family_view_id || link.right_family_view_id === selected.family_view_id) : [];
  const firstRelated = related[0];
  const viewsById = useMemo(() => new Map(views.map((view) => [view.family_view_id, view])), [views]);
  const limitationCount = selected ? new Set([...selected.limitations, ...selected.missing_evidence]).size : 0;
  return <section className="page active-page" aria-labelledby="alerts-title">
    <PageHeading titleId="alerts-title" title="Analyst queue" deck="Independent mechanism findings grouped into family evidence for review." meta={<span>Family composition preserves each source Result and does not combine scientific claims.</span>} />
    <div className="filter-bar analyst-filter-bar">
      <label className="search-control"><span aria-hidden="true">⌕</span><input type="search" placeholder="Search entity or evidence" aria-label="Search analyst queue" value={search} onChange={(event) => setSearch(event.target.value)} /></label>
      <label>Category<select value={family} onChange={(event) => setFamily(event.target.value)}><option value="">All categories</option>{families.map((item) => <option key={item}>{item}</option>)}</select></label>
      <span className="result-total" role="status" aria-live="polite">{filtered.length} {filtered.length === 1 ? "evidence item" : "evidence items"}</span>
    </div>
    {loadError && <div className="stream-notice" role="status">Family evidence could not be loaded: {loadError}</div>}
    <div className="investigation-layout analyst-layout">
      <section className="panel table-panel">
        {filtered.length ? <div className="table-wrap"><table className="data-table analyst-table"><thead><tr>{["Time", "Family", "Primary entity", "Findings", "Related", "Action"].map((name) => <th key={name}>{name}</th>)}</tr></thead><tbody>{filtered.map((view) => { const relation = links.find((link) => link.left_family_view_id === view.family_view_id || link.right_family_view_id === view.family_view_id); const otherId = relation ? (relation.left_family_view_id === view.family_view_id ? relation.right_family_view_id : relation.left_family_view_id) : null; const other = otherId ? viewsById.get(otherId) : undefined; return <tr key={view.family_view_id} className="selectable-row" tabIndex={0} onClick={() => { setSelectedId(view.family_view_id); clearInitial(); }} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); setSelectedId(view.family_view_id); clearInitial(); } }}>
          <td><time>{formatShortTime(view.time_start)}</time></td><td>{view.family} evidence</td><td>{summarizeReference(view.entity_references[0] ?? "") || "Entity unavailable"}{view.entity_references.length > 1 ? ` +${view.entity_references.length - 1} more` : ""}</td><td><strong>{view.findings.length}</strong> independent {view.findings.length === 1 ? "finding" : "findings"}{(view.limitations.length + view.missing_evidence.length) ? ` · ${new Set([...view.limitations, ...view.missing_evidence]).size} limitation${new Set([...view.limitations, ...view.missing_evidence]).size === 1 ? "" : "s"}` : ""}</td><td>{relation && other ? <button className="text-button" onClick={(event) => { event.stopPropagation(); navigate("investigations", { linkId: relation.link_id }); }}>{other.family} +{relation.shared_source_observation_ids.length}</button> : <span className="quiet-tag">—</span>}</td><td><button className="text-button" onClick={(event) => { event.stopPropagation(); setSelectedId(view.family_view_id); clearInitial(); }}>Review →</button></td>
        </tr>; })}</tbody></table></div> : <EmptyState>{loadError ? "Family evidence is unavailable." : "No family evidence matches these filters."}</EmptyState>}
      </section>
      {selected && <Inspector variant="modal" label="Family evidence" selected onClose={() => setSelectedId(null)} placeholder="" description="">
        <div className="inspector-content"><InspectorHeader kicker={`${selected.family} evidence`} title={selected.entity_references.map((value) => summarizeReference(value)).join(", ") || "Entity unavailable"} subtitle={`${formatTimestamp(selected.time_start)}${selected.time_end !== selected.time_start ? ` – ${formatTimestamp(selected.time_end)}` : ""}`} onClose={() => setSelectedId(null)} /><span className="review-badge">REVIEW</span>
          <div className="review-counts"><strong>{selected.findings.length} independent {selected.findings.length === 1 ? "finding" : "findings"}</strong>{limitationCount > 0 && <span>{limitationCount} evidence limitation{limitationCount === 1 ? "" : "s"}</span>}</div>
          <div className="mechanism-chips">{selected.findings.map((finding) => <span key={finding.source_result_id}>{mechanismLabel(finding.title)}</span>)}</div>
          <div className="family-actions"><button className="secondary-button" onClick={() => navigate("results", { sourceResultIds: selected.source_result_ids })}>Evidence ({selected.source_result_ids.length}) →</button>{firstRelated && <button className="text-button" onClick={() => navigate("investigations", { linkId: firstRelated.link_id })}>Related investigation →</button>}</div>
          <section className="inspect-section"><div className="inspect-section-head"><h3>Why this was surfaced</h3></div><p>Related {selected.family} behaviours were recorded in the same passive evidence lineage.</p></section>
          <section className="inspect-section"><div className="inspect-section-head"><h3>Observed evidence</h3></div><ul className="family-finding-list">{selected.findings.map((finding) => <li key={finding.source_result_id}><strong>{finding.title}</strong>{finding.statements.map((statement, index) => <p key={`${finding.source_result_id}-${index}`}>{statement}</p>)}<button className="inline-link source-link" onClick={() => openResult(finding.source_result_id)}>View source evidence →</button></li>)}</ul></section>
          {selected.missing_evidence.length > 0 && <section className="inspect-section"><div className="inspect-section-head"><h3>Missing evidence</h3></div><ul>{selected.missing_evidence.map((item) => <li key={item}>{item}</li>)}</ul></section>}
          <section className="inspect-section"><div className="inspect-section-head"><h3>What this evidence supports</h3></div><p>The individual network behaviours listed above were observed.</p></section>
          {selected.limitations.length > 0 && <section className="inspect-section"><div className="inspect-section-head"><h3>What it does not establish</h3></div><ul>{selected.limitations.map((item) => <li key={item}>{item}</li>)}</ul></section>}
          <section className="inspect-section"><div className="inspect-section-head"><h3>Visibility and quality</h3></div>{selected.visibility_summary.length || selected.quality_summary.length ? <ul>{[...selected.visibility_summary, ...selected.quality_summary].map((item) => <li key={item}>{item}</li>)}</ul> : <p>No degraded visibility or quality conditions are summarized for this family view.</p>}</section>
          <section className="inspect-section related-evidence"><div className="inspect-section-head"><h3>Related investigations</h3><button className="text-button" onClick={() => navigate("investigations")}>Open Investigations →</button></div>{related.length ? related.map((link) => { const otherId = link.left_family_view_id === selected.family_view_id ? link.right_family_view_id : link.left_family_view_id; const other = viewsById.get(otherId); return other ? <article key={link.link_id}><strong>{other.family} evidence</strong><p>Shared passive observation · {link.shared_source_observation_ids.length} source {link.shared_source_observation_ids.length === 1 ? "observation" : "observations"}</p><small>For joint investigation only.</small></article> : null; }) : <p>No cross-family shared observation is currently indexed.</p>}</section>
        </div>
      </Inspector>}
    </div>
  </section>;
}
