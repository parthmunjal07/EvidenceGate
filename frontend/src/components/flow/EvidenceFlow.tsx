import type { ResultDto } from "../../api/types";
import { useReducedMotion } from "../../hooks/useReducedMotion";

const stages = [
  ["observation", "Observed traffic"],
  ["visibility", "Visibility checks"],
  ["analytics", "Analytics"],
  ["results", "Evidence result"],
] as const;

export function EvidenceFlow({
  result,
  replaying,
}: {
  result: ResultDto | null;
  replaying: boolean;
}) {
  const reduced = useReducedMotion();
  const alert = result?.result_type === "REVIEW_FINDING";
  const status =
    result &&
    [
      "QUALITY_DEGRADED",
      "PREREQUISITE_MISSING",
      "INSUFFICIENT_EVIDENCE",
      "ANALYTIC_UNAVAILABLE",
      "PLUGIN_STATUS",
    ].includes(result.result_type);
  const detail = result
    ? `${result.family} · ${result.mechanism_id || result.lane_id}`
    : replaying
      ? "Replay running"
      : "No activity yet";

  return (
    <section className="panel flow-panel" aria-labelledby="flow-title">
      <div className="panel-head compact">
        <div>
          <h2 id="flow-title">Live evidence path</h2>
          <p>Latest persisted result: {detail}</p>
        </div>
        <span className="flow-state" role="status" aria-live="polite">
          {replaying
            ? "Replay running"
            : result
              ? "Result received"
              : "Waiting for activity"}
        </span>
      </div>
      <div className="flow-path" role="group" aria-label="Live evidence path">
        {stages.map(([name, title], index) => (
          <div className="flow-step-wrap" key={name}>
            <div
              className={`flow-step${result ? " is-active" : ""}`}
              data-stage={name}
            >
              <span>{title}</span>
              {name === "analytics" && result && (
                <small>
                  {result.family} · {result.mechanism_id || result.lane_id}
                </small>
              )}
            </div>
            {index < stages.length - 1 && (
              <span className="flow-join" aria-hidden="true">
                <span
                  key={result?.result_id ?? "idle"}
                  className={`flow-pulse${!reduced && result ? " is-moving" : ""}`}
                />
              </span>
            )}
          </div>
        ))}
        <div
          className="flow-branches"
          aria-label="Presentation"
          key="presentation"
        >
          <span className={alert ? "is-active" : ""}>Analyst review</span>
          <span className={status ? "is-active" : ""}>System status</span>
        </div>
      </div>
    </section>
  );
}
