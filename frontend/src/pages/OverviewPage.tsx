import { useState } from "react";
import { useEvidence } from "../state/EvidenceContext";
import type { PageKey } from "../state/types";
import { PageHeading, EmptyState } from "../components/common/Primitives";
import { formatShortTime, friendlyCategory, summarizeReference, whySurfaced } from "../utils/formatting";
import type { SihAlertProjection } from "../api/types";

export function OverviewPage({ navigate, onAlert }: { navigate: (page: PageKey) => void; onAlert: (alert: SihAlertProjection) => void }) {
  const { state } = useEvidence();
  const [howOpen, setHowOpen] = useState(false);
  const dgaIssue = Boolean(state.runtime && state.runtime.dga_model_readiness !== "VERIFIED_READY");
  const dgaStatusPresent = state.statusItems.some((item) => item.mechanism_id === "DGA-A1-M1");
  const issueCount = state.statusItems.length + Number(dgaIssue && !dgaStatusPresent);
  const recent = state.alerts.slice(0, 5);
  const latestResult = state.latestResult ?? [...state.results.values()].sort((a, b) => Date.parse(b.created_time) - Date.parse(a.created_time))[0] ?? null;
  const runtimeLabel = state.pageError ? "Offline" : state.runtime ? "Online" : "Connecting";
  return <section className="page active-page" aria-labelledby="overview-title">
    <PageHeading titleId="overview-title" title="Overview" deck="A clear view of recent evidence and analyst review." meta={<button className="text-button" onClick={() => setHowOpen(true)}>How it works</button>} />
    <div className="metric-grid overview-metrics" aria-label="Operational summary">
      <Metric label="Runtime" value={runtimeLabel} detail="Passive, read-only" />
      <Metric label="Needs review" value={state.alerts.length} detail="Items awaiting analyst review" />
      <Metric label="Evidence limitations" value={issueCount} detail={issueCount ? "Review system and evidence status" : "No reported limitations"} />
      <Metric label="Last activity" value={latestResult ? formatShortTime(latestResult.created_time) : "—"} detail={latestResult ? "Most recent evidence result" : "No recent activity"} />
    </div>
    <section className="panel overview-table-panel">
      <div className="panel-head compact"><div><h2>Recent review items</h2><p>Evidence brought forward for analyst review.</p></div><button className="text-button" onClick={() => navigate("alerts")}>Open analyst queue &rarr;</button></div>
      {recent.length ? <div className="recent-review-list">{recent.map((alert) => {
        const context = Object.values(alert.quality).some((value) => value === "DEGRADED") ? "Quality degraded" : alert.visibility?.unavailable?.length || alert.visibility?.degraded?.length ? "Visibility limited" : "Review";
        return <button type="button" key={alert.alert_id} className="recent-review-item" onClick={() => { navigate("alerts"); onAlert(alert); }}>
          <time>{formatShortTime(alert.timestamp)}</time><span className="review-item-category">{friendlyCategory(alert.threat_class)}</span><strong>{summarizeReference(alert.entity_or_flow_reference, alert.mechanism_id)}</strong><span>{whySurfaced(alert.mechanism_id, alert.supporting_evidence.structured)}</span><span className="review-item-status">{context}</span>
        </button>;
      })}</div> : <div className="overview-empty"><EmptyState>No alerts need review right now.</EmptyState><button className="text-button" onClick={() => navigate("replay")}>Run a controlled replay &rarr;</button></div>}
    </section>
    {howOpen && <div className="trace-modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setHowOpen(false); }}><section className="trace-modal how-modal" role="dialog" aria-modal="true" aria-labelledby="how-title"><div className="trace-modal-head"><div><h2 id="how-title">How EvidenceGate works</h2><p>Passive analysis creates evidence for review. It does not make an autonomous response.</p></div><button className="inspector-close" aria-label="Close explanation" onClick={() => setHowOpen(false)}>&times;</button></div><ol className="how-steps"><li>Observed traffic</li><li>Visibility checks</li><li>Bounded analytics</li><li>Evidence result</li></ol><div className="how-outcomes"><div><strong>Analyst review</strong><span>When evidence is available for review</span></div><div><strong>System status</strong><span>When evidence quality, visibility, or capability is limited</span></div></div></section></div>}
  </section>;
}
function Metric({ label, value, detail }: { label: string; value: string | number; detail: string }) {
  return <article className="metric-card"><span className="metric-label">{label}</span><strong>{value}</strong><small>{detail}</small></article>;
}
