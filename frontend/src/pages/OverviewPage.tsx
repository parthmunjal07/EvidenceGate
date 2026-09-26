import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { FamilyEvidenceViewDto, InvestigationLinkDto, ResultDto } from "../api/types";
import type { NavigationContext } from "../state/navigation";
import type { PageKey } from "../state/types";
import { PageHeading, EmptyState } from "../components/common/Primitives";
import { useEvidence } from "../state/EvidenceContext";
import { contextSummary, formatShortTime, friendlyCategory, mechanismLabel, pluralize } from "../utils/formatting";

const threatFamilies = ["DDoS", "C2 / Beaconing", "DGA + DNS", "Encrypted Sessions", "Reconnaissance", "Data Transfer"];
type Activity = { key: string; time: string; title: string; detail: string; action: string; page: PageKey; context: NavigationContext };

export function OverviewPage({ navigate }: { navigate: (page: PageKey, context?: NavigationContext) => void }) {
  const { state } = useEvidence();
  const [views, setViews] = useState<FamilyEvidenceViewDto[]>([]);
  const [links, setLinks] = useState<InvestigationLinkDto[]>([]);
  const [results, setResults] = useState<ResultDto[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    void Promise.all([api.investigations(controller.signal), api.allResults(controller.signal)])
      .then(([investigation, resultRows]) => {
        if (controller.signal.aborted) return;
        setViews(investigation.family_views);
        setLinks(investigation.links);
        setResults(resultRows);
        setError(null);
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Evidence overview is unavailable");
      });
    return () => controller.abort();
  }, [state.orderedResults.length, state.replay?.finished_at]);

  const resultById = useMemo(() => new Map(results.map((result) => [result.result_id, result])), [results]);
  const viewById = useMemo(() => new Map(views.map((view) => [view.family_view_id, view])), [views]);
  const orderedViews = [...views].sort((a, b) => b.time_end.localeCompare(a.time_end));
  const orderedResults = [...results].sort((a, b) => b.created_time.localeCompare(a.created_time));
  const limitedViewIds = new Set(views.filter((view) => viewIsLimited(view, resultById)).map((view) => view.family_view_id));
  const latestActivityTime = [orderedResults[0]?.created_time, orderedViews[0]?.time_end].filter((time): time is string => Boolean(time)).sort().at(-1);
  const recentViews = orderedViews.slice(0, 4);

  const familyCards = threatFamilies.map((family) => {
    const familyViews = views.filter((view) => view.family === family);
    const limited = familyViews.filter((view) => limitedViewIds.has(view.family_view_id)).length;
    const findings = [...new Set(familyViews.flatMap((view) => view.findings.map((finding) => finding.title)))];
    const viewIds = new Set(familyViews.map((view) => view.family_view_id));
    const related = new Set(links.flatMap((link) => {
      if (viewIds.has(link.left_family_view_id)) return [viewById.get(link.right_family_view_id)?.family].filter((item): item is string => Boolean(item));
      if (viewIds.has(link.right_family_view_id)) return [viewById.get(link.left_family_view_id)?.family].filter((item): item is string => Boolean(item));
      return [];
    }));
    return { family, familyViews, limited, findings, related: [...related] };
  });

  const activity: Activity[] = [
    ...orderedResults.slice(0, 5).map((result) => ({
      key: `result-${result.result_id}`, time: result.created_time,
      title: friendlyCategory(result.family),
      detail: `${mechanismLabel(result.mechanism_id || result.lane_id)} · ${contextSummary(result)}`,
      action: "Open evidence", page: "results" as const, context: { resultId: result.result_id },
    })),
    ...links.map((link) => {
      const time = link.source_result_ids.map((id) => resultById.get(id)?.created_time).filter((value): value is string => Boolean(value)).sort().at(-1)
        ?? [viewById.get(link.left_family_view_id)?.time_end, viewById.get(link.right_family_view_id)?.time_end].filter((value): value is string => Boolean(value)).sort().at(-1)
        ?? "";
      const left = viewById.get(link.left_family_view_id);
      const right = viewById.get(link.right_family_view_id);
      return { key: `link-${link.link_id}`, time, title: `${friendlyCategory(left?.family ?? "Family evidence")} + ${friendlyCategory(right?.family ?? "Family evidence")}`,
        detail: "Shared passive source context indexed", action: "Open investigation", page: "investigations" as const, context: { linkId: link.link_id } };
    }),
  ].filter((item) => item.time).sort((a, b) => b.time.localeCompare(a.time)).slice(0, 6);

  const visibility = summarizeVisibility(results);
  const replay = state.replay ?? state.runtime?.replay;
  const runtime = state.runtime;
  const observedFamilies = familyCards.filter((item) => item.familyViews.length > 0).map((item) => item.family);

  return <section className="page active-page overview-page" aria-labelledby="overview-title">
    <PageHeading titleId="overview-title" title="Overview" deck="Current passive-network evidence, investigation context and sensor limitations." meta={<span className="live-label"><i />{runtime?.state === "REPLAYING" ? "Replay in progress" : "Online"}</span>} />
    {error && <div className="stream-notice" role="status">Evidence summary could not be loaded: {error}</div>}

    <section className="overview-metrics" aria-label="Evidence attention summary">
      <Metric label="Evidence requiring review" value={views.length} detail="family evidence episodes" onClick={() => navigate("alerts")} />
      <Metric label="Related investigations" value={links.length} detail="factual relationships" onClick={() => navigate("investigations")} />
      <Metric label="Evidence limitations" value={limitedViewIds.size} detail="episodes with visibility or quality limits" onClick={() => navigate("alerts")} />
      <Metric label="Latest observed activity" value={formatShortTime(latestActivityTime)} detail="from recorded evidence" onClick={() => navigate("results")} />
    </section>
    <div className="overview-family-glance"><strong>Families with current evidence</strong><span>{observedFamilies.map(familyDisplayLabel).join(" · ") || "None currently observed"}</span><button className="text-button" onClick={() => navigate("alerts")}>Open family posture →</button></div>

    <div className="overview-attention-grid">
      <section className="panel overview-review-panel">
        <div className="overview-section-head"><div><span className="eyebrow">Attention summary</span><h2>Needs review</h2><p>Recent family evidence episodes, ordered by observed activity.</p></div><button className="text-button" onClick={() => navigate("alerts")}>Review all family evidence →</button></div>
        {recentViews.length ? <div className="overview-review-list">{recentViews.map((view) => {
          const sourceRows = view.source_result_ids.map((id) => resultById.get(id)).filter((item): item is ResultDto => Boolean(item));
          const contexts = [...new Set(sourceRows.map(contextSummary))].slice(0, 2);
          const limitCount = viewLimitCount(view, resultById);
          return <article className="overview-review-row" key={view.family_view_id}>
            <div className="review-row-main"><div className="review-title-line"><h3>{familyDisplayLabel(view.family)} evidence</h3><span className={limitCount ? "evidence-state limited" : "evidence-state"}>{limitCount ? "Limited evidence" : "Evidence observed"}</span></div>
              <p>{contexts.join(" · ") || "Observed network context"}</p>
              <div className="review-row-meta"><span>{pluralize(view.findings.length, "finding")}</span><span>{limitCount ? pluralize(limitCount, "evidence limit") : "No reported evidence limits"}</span><time>{formatShortTime(view.time_start)}{view.time_end !== view.time_start ? `–${formatShortTime(view.time_end)}` : ""}</time></div>
            </div><button className="text-button" onClick={() => navigate("alerts", { familyViewId: view.family_view_id })}>Open evidence →</button>
          </article>;
        })}</div> : <EmptyState>{error ? "Evidence episodes are unavailable." : "No family evidence episodes are currently available."}</EmptyState>}
      </section>

      <VisibilityCard data={visibility} limitedCount={limitedViewIds.size} activity={activity.slice(0, 2)} onOpen={() => navigate("alerts")} navigate={navigate} />
    </div>

    <section className="overview-family-section">
      <div className="overview-section-head"><div><span className="eyebrow">Current evidence</span><h2>Threat-family posture</h2><p>Family states reflect composed evidence views, not registered capability.</p></div><button className="text-button" onClick={() => navigate("alerts")}>View all evidence →</button></div>
      <div className="overview-family-grid">{familyCards.map(({ family, familyViews, limited, findings, related }) => {
        const status = !familyViews.length ? "No current evidence" : limited ? "Limited evidence" : "Evidence observed";
        return <button type="button" className="overview-family-card-v2" key={family} onClick={() => navigate("alerts", { family })}>
          <span className={`evidence-state${limited ? " limited" : ""}${!familyViews.length ? " quiet" : ""}`}>{status}</span>
          <h3>{familyDisplayLabel(family)}</h3>
          <div className="family-card-stats"><span><strong>{familyViews.length}</strong> {pluralize(familyViews.length, "episode")}</span>{familyViews.length > 0 && <span><strong>{familyViews.reduce((sum, view) => sum + view.findings.length, 0)}</strong> findings</span>}</div>
          {limited > 0 && <p className="family-limits">{pluralize(limited, "episode")} with visibility or quality limits</p>}
          {findings.length > 0 && <p className="family-findings">{findings.slice(0, 3).join(" · ")}</p>}
          {related.length > 0 && <p className="family-related">Related: {related.map(familyDisplayLabel).join(" · ")}</p>}
          <span className="family-card-action">View family evidence →</span>
        </button>;
      })}</div>
    </section>

    <section className="panel overview-activity-panel">
      <div className="overview-section-head"><div><span className="eyebrow">Chronology</span><h2>Recent security activity</h2><p>Recorded Results and factual investigation relationships.</p></div><button className="text-button" onClick={() => navigate("results")}>Browse evidence →</button></div>
      {activity.length ? <ol className="overview-activity-list">{activity.map((item) => <li key={item.key}><time>{formatShortTime(item.time)}</time><div><strong>{item.title}</strong><p>{item.detail}</p></div><button className="text-button" onClick={() => navigate(item.page, item.context)}>{item.action} →</button></li>)}</ol> : <EmptyState>{error ? "Recent activity is unavailable." : "No recent evidence activity is available."}</EmptyState>}
    </section>

    <details className="overview-runtime-details"><summary>System performance · Controlled benchmark 50 observations/s · 30 seconds · zero input/runtime drops</summary><div className="runtime-details-content">
      <p>Passive sensor · read-only{runtime?.replay?.source_type ? ` · ${runtime.replay.source_type.replaceAll("_", " ").toLowerCase()}` : ""}</p>
      <p>Latest replay: {replay ? `${replay.records_read} records read · ${replay.observations_emitted} observations emitted` : "No replay counters available"}</p>
      <p>Controlled benchmark: 50 observations/s for 30 seconds, zero input/runtime drops under the declared mixed workload. Development workload; not a production SLA.</p>
      <details><summary>Benchmark measurements</summary><p>Processing p50 / p95 / p99: 186.3378 / 883.2264 / 1,017.04 ms. End-to-end evidence p50 / p95 / p99: 312.552 / 983.132 / 1,165.4749 ms. Peak RSS: 244,203,520 bytes.</p></details>
      <button className="text-button" onClick={() => navigate("replay")}>Open Traffic Lab →</button>
    </div></details>
  </section>;
}

function Metric({ label, value, detail, onClick }: { label: string; value: string | number; detail: string; onClick: () => void }) {
  return <button className="overview-metric" type="button" onClick={onClick}><span>{label}</span><strong>{value}</strong><small>{detail}</small></button>;
}

function VisibilityCard({ data, limitedCount, activity, onOpen, navigate }: { data: ReturnType<typeof summarizeVisibility>; limitedCount: number; activity: Activity[]; onOpen: () => void; navigate: (page: PageKey, context?: NavigationContext) => void }) {
  return <section className="panel visibility-health-card">
    <div className="overview-section-head"><div><span className="eyebrow">Sensor visibility</span><h2>Evidence health</h2></div></div>
    <div className="visibility-summary-list">{data.visibility.map((item) => <div key={item.label}><span className={`visibility-mark ${item.status.toLowerCase().replaceAll(" ", "-")}`} aria-hidden="true">{item.status === "Available" ? "✓" : item.status === "Degraded" ? "△" : "○"}</span><span>{item.label}</span><strong>{item.status}</strong></div>)}</div>
    <div className="quality-summary-list"><h3>Capture quality</h3>{data.quality.map((item) => <div key={item.label}><span>{item.label}</span><strong className={item.status === "Degraded" ? "quality-degraded" : ""}>{item.status}</strong></div>)}</div>
    <div className="visibility-limit-footer"><span>{pluralize(limitedCount, "family episode")} with reported limits</span><button className="text-button" onClick={onOpen}>Review evidence →</button></div>
    <div className="visibility-activity-preview"><div><h3>Latest activity</h3><button className="text-button" onClick={() => navigate("results")}>All activity →</button></div>
      {activity.length ? activity.map((item) => <button className="visibility-activity-row" type="button" key={item.key} onClick={() => navigate(item.page, item.context)}><time>{formatShortTime(item.time)}</time><span><strong>{item.title}</strong><small>{item.detail}</small></span><b aria-hidden="true">›</b></button>) : <p>No recent evidence activity.</p>}
    </div>
  </section>;
}

function summarizeVisibility(results: ResultDto[]) {
  const visibilityValues = new Set(results.flatMap((result) => [
    ...result.visibility_snapshot.available.map((value) => `available:${value}`),
    ...result.visibility_snapshot.unavailable.map((value) => `unavailable:${value}`),
    ...result.visibility_snapshot.degraded.map((value) => `degraded:${value}`),
  ]));
  const candidates = [
    ["Forward facts", "FORWARD_FACTS"], ["Reverse facts", "REVERSE_FACTS"], ["Clear DNS fields", "CLEAR_DNS_FIELDS"],
    ["Packet facts", "PACKET_FACTS"], ["Flow facts", "FLOW_FACTS"], ["TLS handshake metadata", "TLS_HANDSHAKE_METADATA"],
  ];
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
  return { visibility: visibility.length ? visibility : [{ label: "Visibility summary", status: results.length ? "Not reported" : "No recent results" }], quality };
}

function viewLimitCount(view: FamilyEvidenceViewDto, resultsById: Map<string, ResultDto>) {
  const limits = new Set(view.missing_evidence);
  let hasVisibilityLimit = false;
  let hasQualityLimit = false;
  for (const id of view.source_result_ids) {
    const result = resultsById.get(id);
    if (!result) continue;
    if (result.quality_snapshot.packet_loss === "DEGRADED" || result.quality_snapshot.sampling === "DEGRADED" || result.quality_snapshot.parser === "DEGRADED" || result.quality_snapshot.capture_gap === "DEGRADED") hasQualityLimit = true;
    if (result.visibility_snapshot.unavailable.length || result.visibility_snapshot.degraded.length) hasVisibilityLimit = true;
  }
  if (hasVisibilityLimit) limits.add("visibility");
  if (hasQualityLimit) limits.add("quality");
  return limits.size;
}

function viewIsLimited(view: FamilyEvidenceViewDto, resultsById: Map<string, ResultDto>) { return viewLimitCount(view, resultsById) > 0; }

function familyDisplayLabel(family: string) {
  const labels: Record<string, string> = { DDoS: "DDoS", "C2 / Beaconing": "C2 / Beaconing", "DGA + DNS": "DGA + DNS", "Encrypted Sessions": "Encrypted Sessions", Reconnaissance: "Reconnaissance", "Data Transfer": "Data Transfer" };
  return labels[family] ?? friendlyCategory(family);
}
