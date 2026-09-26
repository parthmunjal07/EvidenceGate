import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { FamilyEvidenceViewDto, InvestigationLinkDto } from "../api/types";
import { EmptyState, PageHeading } from "../components/common/Primitives";
import type { PageKey } from "../state/types";
import { formatShortTime, summarizeReference } from "../utils/formatting";

export function InvestigationsPage({ navigate }: { navigate: (page: PageKey) => void }) {
  const [views, setViews] = useState<FamilyEvidenceViewDto[]>([]);
  const [links, setLinks] = useState<InvestigationLinkDto[]>([]);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    void api.investigations(controller.signal).then((value) => {
      if (!controller.signal.aborted) { setViews(value.family_views); setLinks(value.links); setError(null); }
    }).catch((reason: unknown) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Investigation evidence is unavailable"); });
    return () => controller.abort();
  }, []);
  const byId = useMemo(() => new Map(views.map((view) => [view.family_view_id, view])), [views]);
  return <section className="page active-page" aria-labelledby="investigations-title">
    <PageHeading titleId="investigations-title" title="Investigations" deck="Cross-family links show exact shared passive source observations for joint review." meta={<span className="quiet-tag">Factual relation · no causal inference</span>} />
    {error && <div className="stream-notice" role="status">Investigation links could not be loaded: {error}</div>}
    <section className="investigation-intro"><div><span className="eyebrow">FAMILY COMPOSITION ≠ INVESTIGATION LINK</span><p>A family evidence view groups independent mechanism Results. An investigation link connects two different family views only when they share source-observation lineage.</p></div><button className="text-button" onClick={() => navigate("alerts")}>Open Analyst Queue →</button></section>
    {links.length ? <div className="investigation-cards">{links.map((link) => {
      const left = byId.get(link.left_family_view_id);
      const right = byId.get(link.right_family_view_id);
      if (!left || !right) return null;
      return <article className="investigation-link-card" key={link.link_id}>
        <div className="investigation-family-pair">
          <FamilyEpisode view={left} onOpen={() => navigate("alerts")} />
          <div className="relation-column"><span className="relation-line" /><strong>SHARED PASSIVE<br />OBSERVATION</strong><span>{link.shared_source_observation_ids.length} shared source {link.shared_source_observation_ids.length === 1 ? "observation" : "observations"}</span><span className="relation-line" /></div>
          <FamilyEpisode view={right} onOpen={() => navigate("alerts")} />
        </div>
        <div className="investigation-claim"><div><strong>Why linked</strong><p>Both family views include source evidence derived from the same passive observation.</p></div><div><strong>Claim guard</strong><p>For joint investigation only. This relation does not establish causality, a common attacker, campaign membership, attack progression, or maliciousness probability.</p></div></div>
      </article>;
    })}</div> : <section className="panel investigation-empty"><EmptyState>{error ? "Investigation data is unavailable." : "No exact shared-observation links are currently indexed."}</EmptyState></section>}
    <div className="investigation-footer"><span>{views.length} family views · {links.length} factual links</span><button className="text-button" onClick={() => navigate("results")}>Browse source Results →</button></div>
  </section>;
}

function FamilyEpisode({ view, onOpen }: { view: FamilyEvidenceViewDto; onOpen: () => void }) {
  return <button className="family-episode" onClick={onOpen}>
    <span className="eyebrow">FAMILY EVIDENCE</span><strong>{view.family}</strong><span>{view.findings.length} independent {view.findings.length === 1 ? "finding" : "findings"}</span><span>{view.entity_references.map((value) => summarizeReference(value)).join(", ") || "Entity unavailable"}</span><time>{formatShortTime(view.time_start)}</time>
  </button>;
}
