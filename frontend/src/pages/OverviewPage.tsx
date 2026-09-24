import { useEvidence } from "../state/EvidenceContext";
import type { PageKey } from "../state/types";
import { EvidenceFlow } from "../components/flow/EvidenceFlow";
import { PageHeading, EmptyState } from "../components/common/Primitives";
import {
  formatQuality,
  formatShortTime,
  shortModelRef,
  summarizeEvidence,
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
  return (
    <section className="page active-page" aria-labelledby="overview-title">
      <PageHeading
        eyebrow="OPERATIONS / OVERVIEW"
        title="Evidence overview"
        deck="A live view of passive observations, persisted results, and analyst attention."
        meta={
          <>
            <span className="live-label">
              <i />
              LIVE RUNTIME
            </span>
            <span>Updated {new Date().toLocaleTimeString()}</span>
          </>
        }
      />
      <div className="metric-grid" aria-label="Runtime summary">
        <Metric
          label="Input / replay state"
          value={
            replay?.state === "RUNNING"
              ? "REPLAYING"
              : (state.runtime?.state ?? "—")
          }
          detail={
            replay?.scenario
              ? `${replay.source_type || "Source"} · ${replay.scenario}`
              : `${state.runtime?.default_target_count ?? "—"} targets ready · ${state.runtime?.scenarios.length ?? "—"} replay scenarios`
          }
        />
        <Metric
          label="Analyst attention"
          value={state.alerts.length}
          detail="in newest 500 results"
        />
        <Metric
          label="Quality degraded"
          value={degraded}
          detail={`Evidence status records: ${state.statusItems.length}`}
        />
        <Metric
          label="Analytic unavailable"
          value={unavailable}
          detail={`Across ${state.runtime?.default_target_count ?? "—"} registered targets`}
        />
      </div>
      <EvidenceFlow
        result={state.latestResult}
        replaying={replay?.state === "RUNNING"}
      />
      <section className="panel overview-table-panel">
        <div className="panel-head compact">
          <div>
            <p className="eyebrow">LATEST REVIEW FINDINGS</p>
            <h2>Recent analyst attention</h2>
          </div>
          <button className="text-button" onClick={() => navigate("alerts")}>
            Open analyst queue <span aria-hidden="true">→</span>
          </button>
        </div>
        {recent.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  {[
                    "TIME",
                    "CLASS",
                    "MECHANISM",
                    "ENTITY / FLOW",
                    "EVIDENCE SUMMARY",
                    "BASIS",
                    "QUALITY",
                    "",
                  ].map((item, i) => (
                    <th key={`${item}-${i}`}>{item}</th>
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
                    <td>{alert.threat_class}</td>
                    <td>{alert.mechanism_id}</td>
                    <td>{alert.entity_or_flow_reference}</td>
                    <td className="evidence-cell">
                      {summarizeEvidence(alert.supporting_evidence.structured)}
                      {alert.confidence_basis === "MODEL_SCORE"
                        ? ` · ${shortModelRef(alert.model_refs)}`
                        : ""}
                    </td>
                    <td>{alert.confidence_basis}</td>
                    <td>{formatQuality(alert.quality)}</td>
                    <td className="row-arrow">→</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState>
            No analyst attention records in the current result window.
          </EmptyState>
        )}
      </section>
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
