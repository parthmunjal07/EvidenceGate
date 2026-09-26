import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { FamilyEvidenceViewDto, InvestigationLinkDto, ReplayStatusResponse, ResultDto, RuntimeTraceEvent } from "../api/types";
import type { NavigationContext } from "../state/navigation";
import type { PageKey } from "../state/types";
import { EmptyState, PageHeading } from "../components/common/Primitives";
import { useEvidence } from "../state/EvidenceContext";
import { useTimeZone } from "../state/TimeZoneContext";
import { compareTimeAsc, compareTimeDesc, contextSummary, formatEvidenceDateTime, formatEvidenceDateTimeCompact, formatEvidenceRange, friendlyCategory, formatTimeZoneLabel, latestObservedTime, normalizeFamilyName, pluralize, timestampMs } from "../utils/formatting";
import { completeTraceRange, filterLatestReplayEvidence, loadLatestReplayMarker, replayMarkerMatches, type LatestReplayMarker } from "../utils/latestReplayScope";

type ScopeData = { views: FamilyEvidenceViewDto[]; links: InvestigationLinkDto[]; results: ResultDto[]; marker: LatestReplayMarker; replay: ReplayStatusResponse };
type Activity = { key: string; time: string; title: string; detail: string; action: string; page: PageKey; context: NavigationContext };
type ScopeChoice = "latest" | "all";

export function OverviewPage({ navigate }: { navigate: (page: PageKey, context?: NavigationContext) => void }) {
  const { state } = useEvidence();
  const { zone } = useTimeZone();
  const [allViews, setAllViews] = useState<FamilyEvidenceViewDto[]>([]);
  const [allLinks, setAllLinks] = useState<InvestigationLinkDto[]>([]);
  const [allResults, setAllResults] = useState<ResultDto[]>([]);
  const [latest, setLatest] = useState<ScopeData | null>(null);
  const [scope, setScope] = useState<ScopeChoice>("all");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    void (async () => {
      try {
        const [investigations, results, replay] = await Promise.all([
          api.investigations(controller.signal), api.allResults(controller.signal), api.replayStatus(controller.signal),
        ]);
        if (controller.signal.aborted) return;
        setAllViews(investigations.family_views);
        setAllLinks(investigations.links);
        setAllResults(results);
        const marker = loadLatestReplayMarker();
        if (!marker || !replayMarkerMatches(marker, replay)) {
          setLatest(null);
          setScope("all");
          setError(null);
          setLoading(false);
          return;
        }
        const trace: RuntimeTraceEvent[] = [];
        let cursor = marker.startSequence;
        let latestSequence = cursor;
        while (cursor < marker.endSequence) {
          const page = await api.runtimeTrace(cursor, controller.signal);
          latestSequence = page.latest_sequence;
          if (!page.events.length || page.events[0]!.sequence !== cursor + 1) throw new Error("The latest replay trace is incomplete");
          trace.push(...page.events.filter((event) => event.sequence <= marker.endSequence));
          cursor = page.events.at(-1)!.sequence;
          if (trace.length > 5000) throw new Error("The latest replay trace is no longer retained");
        }
        if (!completeTraceRange(trace, marker, latestSequence)) throw new Error("The latest replay trace is incomplete");
        const scoped = filterLatestReplayEvidence(results, trace, investigations.family_views, investigations.links);
        setLatest({ ...scoped, marker, replay });
        setScope("latest");
        setError(null);
        setLoading(false);
      } catch (reason) {
        if (controller.signal.aborted) return;
        setLatest(null);
        setScope("all");
        setError(reason instanceof Error ? reason.message : "Latest replay attribution is unavailable");
        setLoading(false);
      }
    })();
    return () => controller.abort();
  }, [state.replay?.finished_at]);

  const scopedData = scope === "latest" && latest ? latest : null;
  const views = useMemo(() => loading ? [] : scopedData?.views ?? allViews, [loading, scopedData, allViews]);
  const links = useMemo(() => loading ? [] : scopedData?.links ?? allLinks, [loading, scopedData, allLinks]);
  const results = useMemo(() => loading ? [] : scopedData?.results ?? allResults, [loading, scopedData, allResults]);
  const resultById = useMemo(() => new Map(results.map((result) => [result.result_id, result])), [results]);
  const viewById = useMemo(() => new Map(views.map((view) => [view.family_view_id, view])), [views]);
  const orderedViews = [...views].sort((a, b) => compareTimeDesc(a.time_end, b.time_end));
  const limitedByView = new Map(views.map((view) => [view.family_view_id, viewLimitCount(view, resultById)]));
  const limitedCount = [...limitedByView.values()].filter((count) => count > 0).length;
  const families = [...new Set(views.map((view) => view.family))];
  const lastObserved = new Map<string, string>();
  for (const view of views) {
    const current = lastObserved.get(view.family);
    if (!current || timestampMs(view.time_end) > timestampMs(current)) lastObserved.set(view.family, view.time_end);
  }
  const relatedByFamily = new Map<string, Set<string>>();
  for (const link of links) {
    const left = viewById.get(link.left_family_view_id);
    const right = viewById.get(link.right_family_view_id);
    if (!left || !right) continue;
    (relatedByFamily.get(left.family) ?? relatedByFamily.set(left.family, new Set()).get(left.family)!).add(right.family);
    (relatedByFamily.get(right.family) ?? relatedByFamily.set(right.family, new Set()).get(right.family)!).add(left.family);
  }
  const familyRows = families.map((family) => {
    const familyViews = views.filter((view) => view.family === family);
    const limits = familyViews.filter((view) => (limitedByView.get(view.family_view_id) ?? 0) > 0).length;
    return { family, familyViews, limits, related: [...(relatedByFamily.get(family) ?? [])], last: lastObserved.get(family) ?? "" };
  }).sort((a, b) => compareTimeDesc(a.last, b.last));
  const relatedPairs = [...new Map(links.map((link) => {
    const left = viewById.get(link.left_family_view_id)?.family;
    const right = viewById.get(link.right_family_view_id)?.family;
    return [`${left ?? ""}\u0000${right ?? ""}`, { link, left, right }];
  })).values()];

  const activity: Activity[] = [
    ...orderedViews.slice(0, 5).map((view) => {
      const sourceResults = view.source_result_ids.map((id) => resultById.get(id)).filter((result): result is ResultDto => Boolean(result));
      const context = [...new Set(sourceResults.map(contextSummary))].slice(0, 2).join(" · ");
      return { key: `view-${view.family_view_id}`, time: view.time_end, title: `${friendlyCategory(view.family)} evidence`, detail: context || "Observed network context", action: "Open evidence", page: "alerts" as const, context: { familyViewId: view.family_view_id } };
    }),
    ...links.map((link) => {
      const left = viewById.get(link.left_family_view_id);
      const right = viewById.get(link.right_family_view_id);
      const contributingTimes = [...link.source_result_ids.map((id) => resultById.get(id)?.created_time ?? ""), left?.time_end ?? "", right?.time_end ?? ""].filter(Boolean);
      const time = latestObservedTime(contributingTimes);
      return { key: `link-${link.link_id}`, time, title: `${friendlyCategory(left?.family ?? "Family evidence")} + ${friendlyCategory(right?.family ?? "Family evidence")}`, detail: "Related through shared passive source observations", action: "Open investigation", page: "investigations" as const, context: { linkId: link.link_id } };
    }),
  ].filter((item) => item.time).sort((a, b) => compareTimeDesc(a.time, b.time)).slice(0, 5);
  const latestActivityTime = latestObservedTime([...views.map((view) => view.time_end), ...results.map((result) => result.created_time)]);
  const observedStarts = views.map((view) => view.time_start).filter(Boolean);
  const observedEnds = views.map((view) => view.time_end).filter(Boolean);
  const rangeStart = observedStarts.sort(compareTimeAsc)[0] ?? "";
  const rangeEnd = observedEnds.sort(compareTimeDesc)[0] ?? "";
  const visibility = summarizeVisibility(results);
  const scopeLabel = loading ? "Checking latest replay" : scopedData ? "Latest replay" : "All retained evidence";
  const replayTitle = loading ? "Checking replay lineage…" : scopedData ? `${sourceLabel(scopedData.marker.sourceType)} · ${scenarioLabel(scopedData.marker.scenario)}` : "Across retained family evidence";
  const rangeText = loading ? "Loading observed window…" : views.length ? formatEvidenceRange(rangeStart, rangeEnd, zone) : "No observed window available";

  return <section className="page active-page overview-page" aria-labelledby="overview-title">
    <PageHeading titleId="overview-title" title="Security evidence" deck="Passive network evidence requiring analyst review." />
    <section className="overview-scope-bar" aria-label="Evidence scope and observed window">
      <div><span className="eyebrow">Evidence scope</span><strong>{replayTitle}</strong><span>{scopeLabel}</span></div>
      <div><span className="eyebrow">Observed window</span><strong>{rangeText}</strong><span>{views.length ? `${pluralize(views.length, "evidence episode")} · ${formatTimeZoneLabel(zone)} display` : "No family evidence in this scope"}</span></div>
      <label>Scope<select aria-label="Evidence scope" disabled={loading} value={scope} onChange={(event) => setScope(event.target.value as ScopeChoice)}><option value="latest" disabled={!latest}>Latest replay{!latest ? " unavailable" : ""}</option><option value="all">All retained evidence</option></select></label>
    </section>
    {!loading && !latest && <p className="scope-explanation">Latest replay evidence could not be safely linked to retained Results. Showing all retained evidence.</p>}
    {error && <div className="stream-notice" role="status">{error}. All retained evidence is shown; no replay scope was inferred from timestamps.</div>}

    <div className="overview-metrics overview-metrics-strip" aria-label="Evidence summary">
      <Metric label="Evidence episodes" value={views.length} detail="family evidence views" onClick={() => navigate("alerts")} />
      <Metric label="With evidence limits" value={limitedCount} detail="episodes with reported limits" onClick={() => navigate("alerts")} />
      <Metric label="Related evidence" value={links.length} detail={`${pluralize(links.length, "investigation relationship")}`} onClick={() => navigate("investigations")} />
      <Metric label="Families represented" value={families.length} detail="with evidence in this scope" onClick={() => navigate("alerts")} />
    </div>

    <div className="overview-attention-grid">
      <section className="panel overview-review-panel">
        <div className="overview-section-head"><div><span className="eyebrow">Analyst attention</span><h2>Needs review</h2><p>{scopeLabel} · evidence episodes ordered by observed time.</p></div><button className="text-button" onClick={() => navigate("alerts")}>Review queue →</button></div>
        {loading ? <p className="overview-loading">Attributing retained evidence to the latest replay…</p> : orderedViews.length ? <div className="overview-review-list">{orderedViews.slice(0, 6).map((view) => {
          const sourceRows = view.source_result_ids.map((id) => resultById.get(id)).filter((item): item is ResultDto => Boolean(item));
          const contexts = [...new Set(sourceRows.map(contextSummary))].slice(0, 2);
          const limits = limitedByView.get(view.family_view_id) ?? 0;
          return <article className="overview-review-row" key={view.family_view_id}>
            <div className="review-row-main"><div className="review-title-line"><h3>{friendlyCategory(view.family)}</h3>{limits > 0 && <span className="episode-limit-tag">{pluralize(limits, "reported limit")}</span>}</div>
              <p>{contexts.join(" · ") || "Observed network context unavailable"}</p>
              <div className="review-row-meta"><span>{pluralize(view.findings.length, "finding")}</span><time title={`Observed: ${formatEvidenceDateTime(view.time_start, zone)}`}>{formatEvidenceRange(view.time_start, view.time_end, zone)}</time></div>
            </div><button className="text-button" onClick={() => navigate("alerts", { familyViewId: view.family_view_id })}>Open evidence →</button>
          </article>;
        })}</div> : <EmptyState>{error ? "Retained evidence is unavailable." : "No family evidence is available in this scope."}</EmptyState>}
      </section>

      <section className="panel overview-context-panel">
        <div className="overview-section-head"><div><span className="eyebrow">Sensor constraints</span><h2>What the sensor could not establish</h2><p>Limits attached to evidence in this scope.</p></div></div>
        <div className="visibility-summary-list">{visibility.visibility.map((item) => <div key={item.label}><span className={`visibility-mark ${item.status.toLowerCase().replaceAll(" ", "-")}`} aria-hidden="true">{item.status === "Available" ? "✓" : item.status === "Degraded" ? "△" : "○"}</span><span>{item.label}</span><strong>{item.status}</strong></div>)}</div>
        <div className="quality-summary-list"><h3>Capture quality</h3>{visibility.quality.some((item) => item.status !== "Not reported") ? visibility.quality.filter((item) => item.status !== "Not reported").map((item) => <div key={item.label}><span>{item.label}</span><strong className={item.status === "Degraded" ? "quality-degraded" : ""}>{item.status}</strong></div>) : <p className="quality-not-reported">Capture quality was not reported for this scope.</p>}</div>
        <p className="scope-limit-note">{pluralize(limitedCount, "episode")} with reported evidence limits in this scope.</p>
        <div className="related-evidence-list"><h3>Related evidence</h3>{relatedPairs.length ? relatedPairs.map(({ link, left, right }) => <article key={link.link_id}><div><strong>{friendlyCategory(left ?? "Family evidence")} + {friendlyCategory(right ?? "Family evidence")}</strong><span>{pluralize(link.shared_source_observation_ids.length, "shared source observation")}</span></div><button className="text-button" onClick={() => navigate("investigations", { linkId: link.link_id })}>Open investigation →</button></article>) : <p>No related family evidence is indexed in this scope.</p>}</div>
      </section>
    </div>

    <section className="overview-family-section overview-family-list-section">
      <div className="overview-section-head"><div><span className="eyebrow">Evidence by family</span><h2>Family evidence</h2><p>Only families represented in the selected evidence scope.</p></div><button className="text-button" onClick={() => navigate("alerts")}>View all evidence →</button></div>
      {loading ? <p className="overview-loading">Family evidence is being scoped.</p> : familyRows.length ? <div className="family-evidence-list" role="table" aria-label="Evidence by family"><div className="family-evidence-head" role="row"><span role="columnheader">Family</span><span role="columnheader">Episodes</span><span role="columnheader" title="Episodes with reported visibility, quality or missing-evidence limits.">Limits</span><span role="columnheader">Related</span><span role="columnheader">Last observed · {formatTimeZoneLabel(zone)}</span><span /></div>{familyRows.map((row) => <div className="family-evidence-row" role="row" key={row.family}><strong role="cell">{normalizeFamilyName(row.family)}</strong><span role="cell">{row.familyViews.length}</span><span role="cell" title="Episodes with reported visibility, quality or missing-evidence limits.">{row.limits ? `${row.limits} / ${row.familyViews.length}` : "—"}</span><span role="cell">{row.related.length ? row.related.map(normalizeFamilyName).join(" · ") : "—"}</span><time role="cell" title={`Observed: ${formatEvidenceDateTime(row.last, zone)}`}>{formatEvidenceDateTimeCompact(row.last, zone)}</time><button className="text-button" onClick={() => navigate("alerts", { family: row.family })}>Review →</button></div>)}</div> : <EmptyState>No families have evidence in this scope.</EmptyState>}
    </section>

    <section className="panel overview-activity-panel">
      <div className="overview-section-head"><div><span className="eyebrow">Observed activity</span><h2>Recent evidence</h2><p>Observed evidence times · {formatTimeZoneLabel(zone)}.</p></div><button className="text-button" onClick={() => navigate("results")}>Browse evidence →</button></div>
      {activity.length ? <ol className="overview-activity-list">{activity.map((item) => <li key={item.key}><time title={`Observed: ${formatEvidenceDateTime(item.time, zone)}`}>{formatEvidenceDateTime(item.time, zone)}</time><div><strong>{item.title}</strong><p>{item.detail}</p></div><button className="text-button" onClick={() => navigate(item.page, item.context)}>{item.action} →</button></li>)}</ol> : <EmptyState>No recent activity is available in this scope.</EmptyState>}
      <p className="latest-observed-note">Latest observed activity: {latestActivityTime ? formatEvidenceDateTime(latestActivityTime, zone) : "Time unavailable"}</p>
    </section>

    <details className="overview-runtime-details"><summary>System &amp; benchmark details</summary><div className="runtime-details-content">
      <p>Controlled development benchmark · 50 observations/s · 30 s · 0 input/runtime drops.</p>
      <p>Passive sensor · read-only. Runtime counters: {state.replay ? `${state.replay.records_read} records read · ${state.replay.observations_emitted} observations emitted` : "unavailable"}.</p>
      <details><summary>Benchmark measurements</summary><p>Processing p50 / p95 / p99: 186.3378 / 883.2264 / 1,017.04 ms. End-to-end evidence p50 / p95 / p99: 312.552 / 983.132 / 1,165.4749 ms. Peak RSS: 244,203,520 bytes.</p></details>
      <button className="text-button" onClick={() => navigate("replay")}>Open Traffic Lab →</button>
    </div></details>
  </section>;
}

function Metric({ label, value, detail, onClick }: { label: string; value: string | number; detail: string; onClick: () => void }) {
  return <button className="overview-metric" type="button" onClick={onClick}><span>{label}</span><strong>{value}</strong><small>{detail}</small></button>;
}

function summarizeVisibility(results: ResultDto[]) {
  const visibilityValues = new Set(results.flatMap((result) => [
    ...result.visibility_snapshot.available.map((value) => `available:${value}`),
    ...result.visibility_snapshot.unavailable.map((value) => `unavailable:${value}`),
    ...result.visibility_snapshot.degraded.map((value) => `degraded:${value}`),
  ]));
  const candidates = [["Forward facts", "FORWARD_FACTS"], ["Reverse facts", "REVERSE_FACTS"], ["Clear DNS fields", "CLEAR_DNS_FIELDS"], ["Packet facts", "PACKET_FACTS"], ["Flow facts", "FLOW_FACTS"], ["TLS handshake metadata", "TLS_HANDSHAKE_METADATA"]];
  const visibility = candidates.filter(([, key]) => [...visibilityValues].some((value) => value.endsWith(`:${key}`))).slice(0, 4).map(([label, key]) => {
    const values = [...visibilityValues].filter((value) => value.endsWith(`:${key}`));
    const hasUnavailable = values.some((value) => value.startsWith("unavailable:") || value.startsWith("degraded:"));
    const hasAvailable = values.some((value) => value.startsWith("available:"));
    const status = values.some((value) => value.startsWith("degraded:")) ? "Degraded" : hasUnavailable && hasAvailable ? "Partially available" : hasUnavailable ? "Unavailable" : "Available";
    return { label, status };
  });
  const qualityKeys = [["Packet loss", "packet_loss"], ["Sampling", "sampling"], ["Parser", "parser"], ["Capture gaps", "capture_gap"]];
  const quality = qualityKeys.map(([label, key]) => {
    const values = results.map((result) => result.quality_snapshot[key as keyof ResultDto["quality_snapshot"]]);
    const status = values.includes("DEGRADED") ? "Degraded" : values.length && values.every((value) => value === "CLEAR") ? "Clear" : "Not reported";
    return { label, status };
  });
  return { visibility: visibility.length ? visibility : [{ label: "Visibility summary", status: results.length ? "Not reported" : "No evidence in scope" }], quality };
}

function viewLimitCount(view: FamilyEvidenceViewDto, resultsById: Map<string, ResultDto>) {
  const limits = new Set(view.missing_evidence);
  for (const id of view.source_result_ids) {
    const result = resultsById.get(id);
    if (!result) continue;
    if (Object.values(result.quality_snapshot).includes("DEGRADED")) limits.add("quality");
    if (result.visibility_snapshot.unavailable.length || result.visibility_snapshot.degraded.length) limits.add("visibility");
  }
  return limits.size;
}

function sourceLabel(value: string) { return /pcap/i.test(value) ? "Raw PCAP" : value.replaceAll("_", " "); }
function scenarioLabel(value: string) {
  const labels: Record<string, string> = { mixed_ddos_recon: "DDoS + Reconnaissance", c2_recurrence: "C2 recurrence", dga_lexical: "DGA lexical evidence", ddos_one_way: "DDoS one-way visibility", raw_pcap_ddos_recon: "DDoS + Reconnaissance" };
  return labels[value] ?? value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}
