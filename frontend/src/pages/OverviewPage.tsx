import { useEvidence } from "../state/EvidenceContext";
import type { PageKey } from "../state/types";
import { EvidenceFlow } from "../components/flow/EvidenceFlow";
import { PageHeading, EmptyState } from "../components/common/Primitives";
import {
  formatQuality,
  formatShortTime,
  confidenceBasisLabel,
  shortModelRef,
  summarizeTableEvidence,
  summarizeReference,
  threatClassLabel,
} from "../utils/formatting";
import type { SihAlertProjection } from "../api/types";

export function OverviewPage({
  navigate,
  onAlert,
}: {
  navigate: (page: PageKey) => void;
  onAlert: (alert: SihAlertProjection) => void;
}) {
  const { state } = useEvidence();
  const replay = state.replay ?? state.runtime?.replay;
  const degraded = state.statusItems.filter(
    (item) => item.result_type === "QUALITY_DEGRADED",
  ).length;
  const unavailable = state.statusItems.filter(
    (item) => item.result_type === "ANALYTIC_UNAVAILABLE",
  ).length;
  const recent = state.alerts.slice(0, 6);
  const runtimeLabel = replay?.state === "RUNNING"
    ? "Replaying"
    : state.runtime?.state === "ONLINE"
      ? "Online"
      : state.runtime?.state || "Connecting";

  return (
    <section className="page active-page" aria-labelledby="overview-title">
      <PageHeading
        titleId="overview-title"
        title="Overview"
        deck="Monitor evidence and review activity."
      />
      <div className="metric-grid" aria-label="Runtime summary">
        <Metric
          label="Runtime"
          value={runtimeLabel}
          detail={replay?.scenario ? `Replay · ${replay.scenario}` : "Passive analysis"}
        />
        <Metric
          label="Analyst alerts"
          value={state.alerts.length}
          detail="In the current result window"
        />
        <Metric
          label="Quality issues"
          value={degraded}
          detail="Degraded quality records"
        />
        <Metric
          label="Unavailable analytics"
          value={unavailable}
          detail="Across registered targets"
        />
      </div>
      <section className="panel overview-table-panel">
        <div className="panel-head compact">
          <h2>Recent alerts</h2>
          <button className="text-button" onClick={() => navigate("alerts")}>
            View all alerts <span aria-hidden="true">→</span>
          </button>
        </div>
        {recent.length ? (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  {["Time", "Threat class", "Mechanism", "Entity", "Evidence", "Confidence basis", "Quality", "Priority"].map((item) => (
                    <th key={item}>{item}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {recent.map((alert) => (
                  <tr
                    key={alert.alert_id}
                    className="selectable-row"
                    tabIndex={0}
                    onClick={() => {
                      navigate("alerts");
                      onAlert(alert);
                    }}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        navigate("alerts");
                        onAlert(alert);
                      }
                    }}
                  >
                    <td>{formatShortTime(alert.timestamp)}</td>
                    <td>{threatClassLabel(alert.threat_class)}</td>
                    <td><code>{alert.mechanism_id}</code></td>
                    <td title={alert.entity_or_flow_reference}>
                      <span className="reference-summary">{summarizeReference(alert.entity_or_flow_reference)}</span>
                    </td>
                    <td className="evidence-cell">
                      <span className="cell-summary">
                        {summarizeTableEvidence(alert.supporting_evidence.structured)}
                        {alert.confidence_basis === "MODEL_SCORE" && (
                          <code> · {shortModelRef(alert.model_refs)}</code>
                        )}
                      </span>
                    </td>
                    <td>{confidenceBasisLabel(alert.confidence_basis)}</td>
                    <td>{formatQuality(alert.quality)}</td>
                    <td className="priority-text">Review</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="overview-empty">
            <EmptyState>No recent alerts.</EmptyState>
            <button className="text-button" onClick={() => navigate("replay")}>
              Run a replay <span aria-hidden="true">→</span>
            </button>
          </div>
        )}
      </section>
      <EvidenceFlow
        result={state.latestResult}
        replaying={replay?.state === "RUNNING"}
      />
    </section>
  );
}

function Metric({
  label,
  value,
  detail,
}: {
  label: string;
  value: string | number;
  detail: string;
}) {
  return (
    <article className="metric-card">
      <span className="metric-label">{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </article>
  );
}
