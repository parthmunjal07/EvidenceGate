import { useEvidence } from "../state/EvidenceContext";
import {
  EmptyState,
  PageHeading,
  ClaimCeiling,
  CodeBlock,
  KeyValueList,
} from "../components/common/Primitives";
import { formatTimestamp, pretty, readable } from "../utils/formatting";

export function SystemStatusPage({
  onResult,
}: {
  onResult: (id: string) => void;
}) {
  const { state } = useEvidence();
  const runtime = state.runtime;
  if (!runtime)
    return (
      <section className="page active-page">
        <PageHeading
          eyebrow="RUNTIME / CAPABILITY / DATA QUALITY"
          title="System & Evidence Status"
          deck="Loading runtime…"
        />
      </section>
    );
  const replay = state.replay ?? runtime.replay;
  const cards: Array<[string, string | number, string]> = [
    [
      "Runtime",
      runtime.state,
      runtime.state === "ONLINE" ? "connected" : "replaying",
    ],
    ["Database", runtime.database_status, "connected"],
    [
      "Alert policy",
      runtime.alert_policy_version || "Unavailable",
      runtime.alert_policy_active ? "active" : "inactive",
    ],
    ["Default targets", runtime.default_target_count, "registered"],
    [
      "DGA model",
      runtime.dga_model_readiness,
      runtime.dga_model_readiness === "VERIFIED_READY"
        ? "verified"
        : "readiness issue",
    ],
    ["Active ML", "DGA-A1/M1-R1", "only active ML"],
    [
      "Input source",
      replay?.source_type || "No replay source",
      replay?.scenario || "idle",
    ],
    ["Live subscribers", runtime.live_subscriber_count, "event streams"],
  ];
  const groups = new Map<string, typeof runtime.targets>();
  for (const target of runtime.targets) {
    const family = target.lane_id.split(".")[0] ?? "other";
    groups.set(family, [...(groups.get(family) ?? []), target]);
  }
  return (
    <section className="page active-page" aria-labelledby="system-title">
      <PageHeading
        eyebrow="RUNTIME / CAPABILITY / DATA QUALITY"
        title="System & Evidence Status"
        deck="Runtime readiness and the evidence conditions under which analytic results are produced."
        meta={
          <span className="quiet-tag">
            Runtime read {new Date().toLocaleTimeString()}
          </span>
        }
      />
      <div className="system-cards">
        {cards.map(([label, value, detail]) => (
          <article className="system-card" key={label}>
            <span className="metric-label">{label}</span>
            <strong
              className="system-value"
              title={
                label === "DGA model"
                  ? (runtime.dga_model_failure_reason ?? undefined)
                  : undefined
              }
            >
              {value}
            </strong>
            <small>{detail}</small>
          </article>
        ))}
      </div>
      <section className="panel target-panel">
        <div className="panel-head compact">
          <div>
            <p className="eyebrow">REGISTERED DEFAULT TARGETS</p>
            <h2>Analytic capability</h2>
            <p>
              Target registration and implementation type are shown directly
              from runtime state.
            </p>
          </div>
          <span className="count-badge">
            {runtime.default_target_count} targets
          </span>
        </div>
        <div className="target-groups">
          {[...groups].map(([family, targets]) => (
            <section className="target-group" key={family}>
              <h3>
                {family === "dns_tunnelling"
                  ? "DNS Tunnelling"
                  : family === "encrypted_session"
                    ? "Encrypted Sessions"
                    : family === "unusual_transfer"
                      ? "Unusual Transfer"
                      : family.toUpperCase()}
              </h3>
              {targets.map((target) => (
                <div className="target-row" key={target.lane_id}>
                  <code className="lane-name">{target.lane_id}</code>
                  <span className="target-mechanism">
                    {target.mechanism_id || "No mechanism ID"}
                  </span>
                  <span
                    className={`target-status ${target.implementation === "REGISTERED_SHELL" ? "shell" : "active"}`}
                  >
                    {target.implementation === "REGISTERED_SHELL"
                      ? "Registered shell"
                      : target.implementation === "ACTIVE_LEXICAL_MODEL_LANE"
                        ? "Active lexical model lane"
                        : "Active factual mechanism"}
                  </span>
                </div>
              ))}
            </section>
          ))}
        </div>
      </section>
      <section className="panel status-records-panel">
        <div className="panel-head compact">
          <div>
            <p className="eyebrow">VERSIONED OPERATIONAL PROJECTION</p>
            <h2>System and evidence records</h2>
            <p>
              Quality, readiness, and evidence lifecycle status remain distinct
              from analyst alerts.
            </p>
          </div>
          <span className="count-badge">
            {state.statusItems.length} records
          </span>
        </div>
        <div className="status-record-list">
          {state.statusItems.length ? (
            state.statusItems.map((item) => (
              <article className="status-record" key={item.status_id}>
                <div className="status-record-head">
                  <span
                    className={`status-priority ${item.priority.toLowerCase()}`}
                  >
                    {item.priority}
                  </span>
                  <time>{formatTimestamp(item.timestamp)}</time>
                </div>
                <strong>
                  {readable(item.status_kind)} · {item.mechanism_id}
                </strong>
                <p className="status-entity">{item.entity_or_flow_reference}</p>
                <KeyValueList
                  rows={[
                    ["Result type", readable(item.result_type)],
                    [
                      "Missing prerequisites",
                      item.missing_prerequisites.join(" · ") || "None supplied",
                    ],
                    ["Visibility", pretty(item.visibility)],
                    ["Quality", pretty(item.quality)],
                  ]}
                />
                <details className="status-claim">
                  <summary>Claim ceiling and supporting evidence</summary>
                  <ClaimCeiling text={item.claim_ceiling} />
                  <CodeBlock
                    label="SUPPORTING EVIDENCE"
                    value={item.supporting_evidence}
                  />
                </details>
                <div className="status-sources">
                  <span className="field-label">SOURCE RESULTS</span>
                  <div className="source-links">
                    {item.source_result_ids.map((id) => (
                      <button
                        className="inline-link source-link"
                        key={id}
                        onClick={() => onResult(id)}
                      >
                        {id}
                      </button>
                    ))}
                  </div>
                </div>
              </article>
            ))
          ) : (
            <EmptyState>
              No system or evidence status records in the current result window.
            </EmptyState>
          )}
        </div>
      </section>
      <section className="panel method-note">
        <p className="eyebrow">INTERPRETATION</p>
        <p>
          Quality describes conditions of capture and parsing. Visibility
          describes which evidence classes were available. Neither is an alert
          severity or a global posture score.
        </p>
      </section>
    </section>
  );
}
