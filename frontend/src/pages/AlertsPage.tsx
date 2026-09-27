import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { FamilyEvidenceViewDto, InvestigationLinkDto, ResultDto, SihAlertProjection } from "../api/types";
import { EmptyState, PageHeading } from "../components/common/Primitives";
import { Header as InspectorHeader, Inspector } from "../components/inspector/InspectorShell";
import { ResultInspector } from "../components/inspector/ResultInspector";
import { ObservationDetail } from "../components/replay/NetworkObservationsSection";
import { useEvidence } from "../state/EvidenceContext";
import { compareTimeAsc, compareTimeDesc, contextSummary, formatEvidenceRange, formatTimeZoneLabel, formatTimestamp, friendlyCategory, groupFamilyFindings, pluralize, prerequisiteLabel, readable } from "../utils/formatting";
import { useTimeZone } from "../state/TimeZoneContext";
import type { PageKey } from "../state/types";
import type { NavigationContext } from "../state/navigation";
import { cachedObservationIds, readCachedObservation, readCachedObservations } from "../utils/replayEvidenceCache";

export function AlertsPage({ initialAlert, clearInitial, navigate, initialFamilyViewId, initialFamily, returnResultId }: { initialAlert: SihAlertProjection | null; clearInitial: () => void; navigate: (page: PageKey, context?: NavigationContext) => void; initialFamilyViewId?: string; initialFamily?: string; returnResultId?: string }) {
  const developerUi = import.meta.env.VITE_EVIDENCEGATE_DEV_UI === "true";
  const { state, dispatch } = useEvidence();
  const { zone } = useTimeZone();
  const [views, setViews] = useState<FamilyEvidenceViewDto[]>([]);
  const [links, setLinks] = useState<InvestigationLinkDto[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [family, setFamily] = useState(initialFamily ?? "");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedResultId, setSelectedResultId] = useState<string | null>(null);
  const [sourceObservationId, setSourceObservationId] = useState<string | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    void Promise.all([api.familyEvidence(controller.signal), api.investigations(controller.signal)])
      .then(([evidence, investigation]) => {
        setViews(evidence.family_views);
        setLinks(investigation.links);
        const alertResultId = initialAlert?.source_result_ids[0];
        const fromAlert = alertResultId ? evidence.family_views.find((view) => view.source_result_ids.includes(alertResultId)) : undefined;
        const fromFamily = initialFamily ? evidence.family_views.find((view) => view.family === initialFamily) : undefined;
        setSelectedId(initialFamilyViewId && evidence.family_views.some((view) => view.family_view_id === initialFamilyViewId) ? initialFamilyViewId : fromAlert?.family_view_id ?? fromFamily?.family_view_id ?? null);
        setLoadError(null);
      })
      .catch((error: unknown) => { if (!controller.signal.aborted) setLoadError(error instanceof Error ? error.message : "Family evidence is unavailable"); });
    return () => controller.abort();
  }, [initialAlert, initialFamilyViewId, initialFamily]);

  const resultById = useMemo(() => new Map(state.orderedResults.flatMap((id) => {
    const result = state.results.get(id);
    return result ? [[id, result] as const] : [];
  })), [state.orderedResults, state.results]);
  const selectedResult = selectedResultId ? state.results.get(selectedResultId) ?? null : null;
  const sourceIds = selectedResult ? cachedObservationIds(selectedResult.source_observation_ids) : [];
  const sourceObservations = selectedResult ? readCachedObservations(selectedResult.source_observation_ids) : [];
  const cachedSource = sourceObservationId ? readCachedObservation(sourceObservationId) : null;
  const families = [...new Set(views.map((view) => view.family))];
  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();
    return views.filter((view) => (!family || view.family === family) && (!query || [view.family, ...view.entity_references, ...view.findings.flatMap((finding) => [finding.title, ...finding.statements])].join(" ").toLowerCase().includes(query))).sort((a, b) => compareTimeDesc(a.time_end, b.time_end));
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
  const closeFamily = () => {
    if (returnResultId) navigate("results", { resultId: returnResultId });
    else setSelectedId(null);
  };
  const reviewResult = async (id: string) => {
    setSelectedResultId(id);
    if (state.results.has(id)) return;
    try { dispatch({ type: "results", value: [await api.result(id)] }); }
    catch { setLoadError("The selected Result could not be loaded."); }
  };

  return <section className="page active-page" aria-labelledby="alerts-title">
    <PageHeading titleId="alerts-title" title="Analyst queue" deck="Review family evidence episodes while keeping each source Result independent." meta={<span>Evidence supports review; it does not confirm malicious activity.</span>} />
    <div className="filter-bar analyst-filter-bar">
      <p className="analyst-time-note">Observed window: {filtered.length ? formatEvidenceRange(filtered.map((view) => view.time_start).sort(compareTimeAsc)[0], filtered.map((view) => view.time_end).sort(compareTimeDesc)[0], zone) : `No observed time available · ${formatTimeZoneLabel(zone)}`}.</p>
      <label className="search-control"><span aria-hidden="true">⌕</span><input type="search" placeholder="Search address, domain, finding or family" aria-label="Search analyst queue" value={search} onChange={(event) => setSearch(event.target.value)} /></label>
      <label>Family<select value={family} onChange={(event) => setFamily(event.target.value)}><option value="">All families</option>{families.map((item) => <option key={item}>{item}</option>)}</select></label>
      <span className="result-total" role="status" aria-live="polite">{pluralize(filtered.length, "episode")}</span>
    </div>
    {loadError && <div className="stream-notice" role="status">Family evidence could not be loaded: {loadError}</div>}
    <section className="panel family-queue-panel">
      {filtered.length ? <div className="table-wrap"><table className="data-table family-queue-table"><thead><tr>{[`Observed time · ${formatTimeZoneLabel(zone)}`, "Family", "Context", "Findings", "Evidence gaps", "Related", "Action"].map((name) => <th key={name}>{name}</th>)}</tr></thead><tbody>
        {filtered.map((view) => {
          const viewResults = view.source_result_ids.map((id) => resultById.get(id)).filter((item): item is ResultDto => Boolean(item));
          const viewContext = [...new Set(viewResults.map(contextSummary))].slice(0, 2).join(" · ") || "Observed network context";
          const viewLinks = links.filter((link) => link.left_family_view_id === view.family_view_id || link.right_family_view_id === view.family_view_id);
          const gaps = new Set([...view.limitations, ...view.missing_evidence]).size;
          return <tr key={view.family_view_id} className={`selectable-row${selectedId === view.family_view_id ? " selected" : ""}`} tabIndex={0} onClick={() => openFamily(view.family_view_id)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); openFamily(view.family_view_id); } }}>
            <td><time title={`Observed: ${formatTimestamp(view.time_start, zone)}`}>{formatEvidenceRange(view.time_start, view.time_end, zone)}</time></td>
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

    {selected && <Inspector variant="modal" label="Family evidence episode" selected onClose={closeFamily} placeholder="" description="">
      <div className="family-episode">
        <InspectorHeader kicker="Family evidence episode" title={friendlyCategory(selected.family)} subtitle={episodeContext} onClose={closeFamily} {...(returnResultId ? { onBack: closeFamily, backLabel: "Back to source Result" } : {})} />
        <div className="episode-summary">
          <div><span>Observed time</span><strong>{formatEvidenceRange(selected.time_start, selected.time_end, zone)}</strong></div>
          <div><span>Findings</span><strong>{pluralize(selected.findings.length, "independent finding")}</strong></div>
          <div><span>Evidence limits</span><strong>{pluralize(limitationCount, "limit")}</strong></div>
          <div><span>Related</span><strong>{pluralize(related.length, "investigation link")}</strong></div>
        </div>
        <div className="episode-actions"><span>{pluralize(selected.source_result_ids.length, "source Result")} retained</span>{related.length > 0 && <button className="secondary-button" onClick={() => navigate("investigations", related.length === 1 ? { linkId: related[0]!.link_id } : { family: selected.family })}>Open investigation{related.length === 1 ? "" : "s"}</button>}</div>

        <section className="episode-section"><h3>Episode summary</h3><p>This view groups family Results that share observed source context. The underlying mechanism Results remain separate.</p></section>

        <section className="episode-section"><h3>Findings</h3><div className="finding-groups">{groupedFindings.map((group) => {
          const measurementSummary = latestMeasurementSummary(group.findings.flatMap((finding) => {
            const result = resultById.get(finding.source_result_id);
            return result ? [result] : [];
          }));
          return <details className="finding-group" key={group.title}>
          <summary><span>{group.title}{group.findings.length > 1 && <small className="incremental-label">Incremental measurement{measurementSummary ? ` · ${measurementSummary}` : ""}</small>}</span><span className="finding-group-count">{pluralize(group.findings.length, "measurement")}</span></summary>
          <ol>{group.findings.map((finding) => {
            const sourceResult = resultById.get(finding.source_result_id);
            return <li key={finding.source_result_id}>
              <div><strong>{finding.title}</strong><span>{readable(finding.result_type)}</span></div>
              {sourceResult && <time>{formatTimestamp(sourceResult.created_time)}</time>}
              {finding.statements.filter((statement) => !selected.source_observation_ids.includes(statement) && !/^state:/i.test(statement.trim())).map((statement) => <p key={statement}>{statement}</p>)}
              {sourceResult && Array.isArray(sourceResult.evidence.hard_negative_alternatives) && <p className="episode-alternatives"><strong>Other possible explanations: </strong>{(sourceResult.evidence.hard_negative_alternatives as unknown[]).filter((item): item is string => typeof item === "string").join(" · ")}</p>}
              <button className="text-button" onClick={() => void reviewResult(finding.source_result_id)}>Review →</button>
            </li>;
          })}</ol>
        </details>;})}</div></section>

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

        {developerUi && <details className="episode-disclosure"><summary>Developer source lineage</summary><ul>{selected.source_observation_ids.map((id) => <li key={id}>{id}</li>)}</ul></details>}
      </div>
    </Inspector>}
    <ResultInspector result={selectedResult} onClose={() => setSelectedResultId(null)} onBack={() => setSelectedResultId(null)} availableSourceCount={sourceIds.length} sourceObservations={sourceObservations} onOpenSource={(index) => setSourceObservationId(sourceIds[index] ?? null)} onOpenFamily={() => setSelectedResultId(null)} onOpenInvestigation={() => { if (selectedResult) navigate("investigations", { family: friendlyCategory(selectedResult.family) }); }} />
    {cachedSource && <ObservationDetail row={{ observation: cachedSource.observation, source: cachedSource.source }} routes={cachedSource.routes} results={cachedSource.results} close={() => setSourceObservationId(null)} navigate={(_page, context) => { if (context?.resultId) { setSourceObservationId(null); void reviewResult(context.resultId); } }} />}
  </section>;
}

function latestMeasurementSummary(results: ResultDto[]): string | null {
  const latest = [...results].sort((a, b) => compareTimeDesc(a.created_time, b.created_time))[0];
  if (!latest) return null;
  const evidence = latest.evidence;
  const lowerBound = evidence.apparent_source_cardinality_lower_bound ?? evidence.unique_sources;
  if (latest.lane_id === "ddos.source_diversity" && typeof lowerBound === "number") {
    return `latest observed lower bound: ${lowerBound} apparent source${lowerBound === 1 ? "" : "s"}`;
  }
  const measurements = typeof evidence.measurements === "object" && evidence.measurements !== null && !Array.isArray(evidence.measurements)
    ? evidence.measurements as Record<string, unknown> : null;
  if (latest.lane_id.startsWith("recon.") && measurements) {
    const labels: Array<[string, string]> = [["distinct_hosts", "hosts"], ["distinct_ports", "ports/services"], ["distinct_host_port_pairs", "host × service pairs"], ["attempt_count", "attempts"]];
    const values = labels.flatMap(([key, label]) => typeof measurements[key] === "number" ? [`${measurements[key]} ${label}`] : []);
    return values.length ? `latest: ${values.join(" · ")}` : null;
  }
  return null;
}
