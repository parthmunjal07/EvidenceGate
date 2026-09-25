import { useEvidence } from "../state/EvidenceContext";
import type { PageKey } from "../state/types";
import { PageHeading, EmptyState } from "../components/common/Primitives";
import { formatShortTime, friendlyCategory, summarizeReference, whySurfaced } from "../utils/formatting";
import type { SihAlertProjection } from "../api/types";

export function OverviewPage({ navigate, onAlert }: { navigate: (page: PageKey) => void; onAlert: (alert: SihAlertProjection) => void }) {
  const { state } = useEvidence();
  const replay = state.replay ?? state.runtime?.replay;
  const dgaIssue = Boolean(state.runtime && state.runtime.dga_model_readiness !== "VERIFIED_READY");
  const issueCount = Number(dgaIssue) + state.statusItems.filter((item) => item.result_type === "ANALYTIC_UNAVAILABLE" && !(dgaIssue && item.mechanism_id === "DGA-A1-M1")).length;
  const recent = state.alerts.slice(0, 6);
  const latestResult = state.latestResult ?? [...state.results.values()].sort((a, b) => Date.parse(b.created_time) - Date.parse(a.created_time))[0] ?? null;
  const runtimeLabel = replay?.state === "RUNNING" ? "Replaying" : state.runtime?.state === "ONLINE" ? "Online" : state.runtime?.state || "Connecting";
  return <section className="page active-page" aria-labelledby="overview-title">
    <PageHeading titleId="overview-title" title="Overview" deck="What needs your attention right now?" />
    <div className="metric-grid overview-metrics" aria-label="Operational summary">
      <Metric label="Runtime" value={runtimeLabel} detail={replay?.state === "RUNNING" ? "Controlled traffic is being processed" : "Passive · read-only"} />
      <Metric label="Needs review" value={state.alerts.length} detail="Evidence items in the current window" />
      <Metric label="Evidence limitations" value={issueCount} detail={issueCount ? "Quality or capability context is available" : "No capability issues"} />
      <Metric label="Last activity" value={latestResult ? formatShortTime(latestResult.created_time) : "—"} detail={latestResult ? "Most recent evidence result" : "No recent results"} />
    </div>
    <section className="panel overview-table-panel">
      <div className="panel-head compact"><div><h2>Recent analyst activity</h2><p>Why each item was brought to your attention.</p></div><button className="text-button" onClick={() => navigate("alerts")}>View analyst queue →</button></div>
      {recent.length ? <div className="table-wrap"><table className="data-table analyst-table"><thead><tr>{["Time", "Category", "Entity / peer", "Why surfaced", "Context"].map((name) => <th key={name}>{name}</th>)}</tr></thead><tbody>
        {recent.map((alert) => {
          const context = alert.quality && Object.values(alert.quality).some((value) => value === "DEGRADED") ? "Quality degraded" : alert.visibility?.unavailable?.length ? "Visibility limited" : "—";
          return <tr key={alert.alert_id} className="selectable-row" tabIndex={0} onClick={() => { navigate("alerts"); onAlert(alert); }} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); navigate("alerts"); onAlert(alert); } }}>
            <td><time>{formatShortTime(alert.timestamp)}</time></td><td>{friendlyCategory(alert.threat_class)}</td>
            <td title={alert.entity_or_flow_reference}>{summarizeReference(alert.entity_or_flow_reference, alert.mechanism_id)}</td>
            <td><span className="why-surfaced-summary" title={whySurfaced(alert.mechanism_id, alert.supporting_evidence.structured)}>{whySurfaced(alert.mechanism_id, alert.supporting_evidence.structured)}</span></td><td>{context}</td>
          </tr>;
        })}
      </tbody></table></div> : <div className="overview-empty"><EmptyState>No alerts need review.</EmptyState><button className="text-button" onClick={() => navigate("replay")}>Run a controlled replay →</button></div>}
    </section>
  </section>;
}
function Metric({ label, value, detail }: { label: string; value: string | number; detail: string }) {
  return <article className="metric-card"><span className="metric-label">{label}</span><strong>{value}</strong><small>{detail}</small></article>;
}
