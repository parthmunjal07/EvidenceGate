import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { FamilyEvidenceViewDto, InvestigationLinkDto } from "../api/types";
import { EmptyState, PageHeading } from "../components/common/Primitives";
import type { PageKey } from "../state/types";
import type { NavigationContext } from "../state/navigation";
import { formatShortTime, summarizeReference } from "../utils/formatting";

export function InvestigationsPage({ navigate, initialLinkId, initialFamily }: { navigate: (page: PageKey, context?: NavigationContext) => void; initialLinkId?: string; initialFamily?: string }) {
  const [views, setViews] = useState<FamilyEvidenceViewDto[]>([]);
  const [links, setLinks] = useState<InvestigationLinkDto[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(initialLinkId ?? null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    void api.investigations(controller.signal).then((value) => {
      if (!controller.signal.aborted) { setViews(value.family_views); setLinks(value.links); setError(null); }
    }).catch((reason: unknown) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Investigation evidence is unavailable"); });
    return () => controller.abort();
  }, []);
  const byId = useMemo(() => new Map(views.map((view) => [view.family_view_id, view])), [views]);
  const sorted = useMemo(() => [...links].sort((a, b) => {
    const left = byId.get(a.left_family_view_id)?.time_end ?? "";
    const right = byId.get(b.left_family_view_id)?.time_end ?? "";
    return right.localeCompare(left);
  }), [links, byId]);
  const focused = initialFamily ? sorted.filter((link) => {
    const a = byId.get(link.left_family_view_id)?.family;
    const b = byId.get(link.right_family_view_id)?.family;
    return a === initialFamily || b === initialFamily;
  }) : sorted;
  const selected = focused.find((link) => link.link_id === selectedId) ?? focused[0] ?? null;
  const left = selected ? byId.get(selected.left_family_view_id) : undefined;
  const right = selected ? byId.get(selected.right_family_view_id) : undefined;
  return <section className="page active-page" aria-labelledby="investigations-title">
    <PageHeading titleId="investigations-title" title="Investigations" deck="Review factual relationships between family evidence views." meta={<span className="quiet-tag">Shared source observation</span>} />
    {error && <div className="stream-notice" role="status">Investigation links could not be loaded: {error}</div>}
    <section className="investigation-intro"><div><span className="eyebrow">FACTUAL CONTEXT ONLY</span><p>Links identify exact passive source observations shared by two family views. They do not establish causality, common attacker, campaign membership, attack progression, or maliciousness probability.</p></div><button className="text-button" onClick={() => navigate("alerts")}>Open Analyst Queue →</button></section>
    {focused.length ? <div className="investigation-review-layout">
      <section className="panel investigation-list" aria-label="Investigation relationships">{focused.map((link) => { const a = byId.get(link.left_family_view_id); const b = byId.get(link.right_family_view_id); return a && b ? <button type="button" className={`investigation-row${link.link_id === selected?.link_id ? " selected" : ""}`} key={link.link_id} onClick={() => setSelectedId(link.link_id)}><strong>{a.family} ↔ {b.family}</strong><span>{summarizeReference(a.entity_references[0] ?? "")} · {summarizeReference(b.entity_references[0] ?? "")}</span><span>{link.shared_source_observation_ids.length} shared observation{link.shared_source_observation_ids.length === 1 ? "" : "s"}</span><time>{formatShortTime(a.time_end)}</time><small>Review →</small></button> : null; })}</section>
      {selected && left && right && <section className="panel investigation-detail" aria-label="Selected investigation relationship">
        <div className="investigation-detail-head"><span className="eyebrow">JOINT INVESTIGATION CONTEXT</span><h2>{left.family} ↔ {right.family}</h2><p>{selected.shared_source_observation_ids.length} exact shared source observation{selected.shared_source_observation_ids.length === 1 ? "" : "s"} · {formatShortTime(left.time_start)}</p></div>
        <div className="investigation-families"><FamilyEvidence view={left} onOpen={() => navigate("alerts", { familyViewId: left.family_view_id })} /><span className="investigation-connector" aria-hidden="true">↔<small>same source</small></span><FamilyEvidence view={right} onOpen={() => navigate("alerts", { familyViewId: right.family_view_id })} /></div>
        <section className="shared-source-facts"><h3>Why linked</h3><p>Both family views include evidence derived from the same passive source observation.</p><p>Shared observations: {selected.shared_source_observation_ids.length}</p><details><summary>Show source lineage</summary><ul>{selected.shared_source_observation_ids.map((id) => <li key={id}>{id}</li>)}</ul></details></section>
        <div className="family-actions"><button className="secondary-button" onClick={() => navigate("results", { sourceResultIds: selected.source_result_ids })}>Open {selected.source_result_ids.length} source Results →</button><button className="text-button" onClick={() => navigate("alerts", { familyViewId: left.family_view_id })}>Open {left.family} family evidence</button><button className="text-button" onClick={() => navigate("alerts", { familyViewId: right.family_view_id })}>Open {right.family} family evidence</button></div>
      </section>}
    </div> : <section className="panel investigation-empty"><EmptyState>{error ? "Investigation data is unavailable." : "No exact shared-observation links are currently indexed."}</EmptyState></section>}
    <div className="investigation-footer"><span>{views.length} family views · {links.length} factual links</span><button className="text-button" onClick={() => navigate("results")}>Browse source Results →</button></div>
  </section>;
}

function FamilyEvidence({ view, onOpen }: { view: FamilyEvidenceViewDto; onOpen: () => void }) {
  return <article className="investigation-family-card"><div><span className="family-level-mark" aria-hidden="true">F</span><span className="eyebrow">FAMILY EVIDENCE</span></div><h3>{view.family}</h3><p>{view.findings.length} independent findings · {view.entity_references.length} entities</p><strong>{view.entity_references.slice(0, 2).map((value) => summarizeReference(value)).join(" · ") || "Entity unavailable"}{view.entity_references.length > 2 ? ` +${view.entity_references.length - 2} more` : ""}</strong><button className="text-button" onClick={onOpen}>Open family evidence →</button></article>;
}
