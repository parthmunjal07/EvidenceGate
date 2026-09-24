import type { ResultDto } from "../../api/types";
import { useReducedMotion } from "../../hooks/useReducedMotion";
import { FlowStage } from "./FlowStage";

const stages = ["observation", "quality", "router", "analytics", "results"];
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
  const active = result
    ? [...stages, ...(alert ? ["projection"] : status ? ["status"] : [])]
    : [];
  const detail = result
    ? `${result.lane_id} · ${alert ? "SIH alert projection" : status ? "evidence status projection" : "no SIH projection"}`
    : replaying
      ? "Replay running · waiting for persisted result events"
      : "Awaiting replay or live result";
  return (
    <section className="panel flow-panel" aria-labelledby="flow-title">
      <div className="panel-head">
        <div>
          <p className="eyebrow">OBSERVATION TO PRESENTATION</p>
          <h2 id="flow-title">Evidence flow</h2>
          <p>
            Each stage keeps its own meaning. A single observation may yield
            zero, one, or multiple independent results.
          </p>
        </div>
        <span className="quiet-tag">{detail}</span>
      </div>
      <div className="flow-scroll">
        <svg
          className="evidence-flow"
          viewBox="0 0 1080 258"
          role="img"
          aria-labelledby="flow-title flow-desc"
        >
          <desc id="flow-desc">
            Passive observations move through canonicalization, visibility and
            quality assessment, zero-to-many routing, and immutable results.
            Alert and status projections remain separate.
          </desc>
          <defs>
            <marker
              id="arrow"
              markerWidth="8"
              markerHeight="8"
              refX="6"
              refY="4"
              orient="auto"
            >
              <path d="M0 0L8 4L0 8Z" fill="#aab5bd" />
            </marker>
          </defs>
          <path
            className="flow-connector"
            d="M150 112H210M355 112H415M565 112H625M765 112H825M955 112H976"
            markerEnd="url(#arrow)"
          />
          <path
            className="flow-connector branch"
            d="M976 112V85H990M976 112V187H990"
            markerEnd="url(#arrow)"
          />
          <FlowStage
            name="observation"
            index="01 · INPUT"
            x={16}
            y={72}
            title={["Passive", "observation"]}
            active={active.includes("observation")}
          />
          <FlowStage
            name="quality"
            index="02 · CONTEXT"
            x={210}
            y={72}
            title={["Visibility", "& quality"]}
            active={active.includes("quality")}
          />
          <FlowStage
            name="router"
            index="03 · ROUTING"
            x={415}
            y={72}
            title={["Capability", "router"]}
            active={active.includes("router")}
          />
          <FlowStage
            name="analytics"
            index="04 · ANALYSIS"
            x={625}
            y={52}
            title={
              result
                ? [result.family, result.lane_id]
                : [
                    "16 targets",
                    "DDoS · C2 · DGA",
                    "DNS · Encrypted",
                    "Recon · Transfer",
                  ]
            }
            active={active.includes("analytics")}
          />
          <FlowStage
            name="results"
            index="05 · AUTHORITY"
            x={825}
            y={72}
            title={["Immutable", "results"]}
            active={active.includes("results")}
          />
          <FlowStage
            name="projection"
            index="ELIGIBLE REVIEW"
            x={990}
            y={50}
            title={["SIH alert", "projection"]}
            active={active.includes("projection")}
            presentation
          />
          <FlowStage
            name="status"
            index="LIFECYCLE"
            x={990}
            y={153}
            title={["Evidence", "status"]}
            active={active.includes("status")}
            presentation
          />
          <text className="branch-label" x="490" y="205">
            ONE OBSERVATION · ZERO-TO-MANY ROUTING
          </text>
          <text className="flow-caption" x="16" y="250">
            RESULTS ARE THE SCIENTIFIC AUTHORITY
          </text>
          <text className="flow-caption right" x="1068" y="250">
            ALERTS AND STATUS STAY SEPARATE
          </text>
          {result && !reduced && (
            <circle
              key={result.result_id}
              className="flow-pulse"
              r="5"
              cx="82"
              cy="112"
            >
              <animateMotion
                dur="1900ms"
                fill="freeze"
                path={`M 0 0 L 225 0 L 430 0 L 640 0 L 840 0${alert || status ? ` L 894 ${alert ? -27 : 75}` : ""}`}
              />
            </circle>
          )}
        </svg>
      </div>
      <div className="flow-legend">
        <span>
          <i className="legend-swatch source" />
          source observation
        </span>
        <span>
          <i className="legend-swatch evidence" />
          immutable evidence
        </span>
        <span>
          <i className="legend-swatch presentation" />
          analyst presentation
        </span>
        <small role="status" aria-live="polite">
          {result
            ? `Persisted result received for ${result.lane_id}.`
            : "Live flow activates from persisted result notifications."}
        </small>
      </div>
    </section>
  );
}
