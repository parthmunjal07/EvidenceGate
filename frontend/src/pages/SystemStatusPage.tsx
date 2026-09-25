import { useState, type ReactNode } from "react";
import { useEvidence } from "../state/EvidenceContext";
import {
  ClaimCeiling,
  CodeBlock,
  EmptyState,
  KeyValueList,
  PageHeading,
  QualitySnapshotView,
  VisibilitySnapshotView,
} from "../components/common/Primitives";
import { Header, Inspector } from "../components/inspector/InspectorShell";
import {
  familyLabel,
  formatTimestamp,
  mechanismLabel,
  prerequisiteLabel,
  readable,
  shortId,
  summarizeReference,
} from "../utils/formatting";
import type { RuntimeTarget, SihStatusProjection } from "../api/types";

function resultTypeLabel(value: string) {
  const labels: Record<string, string> = {
    INSUFFICIENT_EVIDENCE: "Insufficient evidence",
    QUALITY_DEGRADED: "Quality degraded",
    ANALYTIC_UNAVAILABLE: "Analytic unavailable",
    PREREQUISITE_MISSING: "Prerequisite missing",
    REVIEW_FINDING: "Review finding",
  };
  return labels[value] ?? readable(value);
}

function statusFamily(mechanismId: string) {
  const prefix = mechanismId.split("-")[0] ?? "";
  const families: Record<string, string> = {
    DDOS: "ddos", C2: "c2", DGA: "dga", DNS: "dns_tunnelling",
    ENC: "encrypted_session", RECON: "recon", CAT6: "unusual_transfer",
  };
  return familyLabel(families[prefix] ?? prefix);
}

function TechnicalDisclosure({ children, label }: { children: ReactNode; label: string }) {
  const [open, setOpen] = useState(false);
  return <details className="technical-details" onToggle={(event) => setOpen(event.currentTarget.open)}>
    <summary>{label}</summary>{open && children}
  </details>;
}

function StatusRecord({
  item,
  selected,
  onSelect,
}: {
  item: SihStatusProjection;
  selected: boolean;
  onSelect: () => void;
}) {
  const reason = item.missing_prerequisites.map(prerequisiteLabel).join(" · ");
  return <button className={`status-record-summary${selected ? " selected" : ""}`} type="button" aria-pressed={selected} onClick={onSelect}>
    <span className={`status-priority ${item.priority.toLowerCase()}`}>{item.priority === "ATTENTION" ? "Attention" : "Info"}</span>
    <span className="status-record-main">
      <strong>{resultTypeLabel(item.result_type)}</strong>
      <span>{statusFamily(item.mechanism_id)} · {mechanismLabel(item.mechanism_id)}</span>
      <span className="status-entity">{summarizeReference(item.entity_or_flow_reference, item.mechanism_id)}</span>
      {reason && <span className="status-missing">Missing: {reason}</span>}
    </span>
    <time>{formatTimestamp(item.timestamp)}</time>
  </button>;
}

function StatusInspector({
  item,
  onClose,
  onResult,
}: {
  item: SihStatusProjection | null;
  onClose: () => void;
  onResult: (id: string) => void;
}) {
  return <Inspector label="Status record inspector" selected={Boolean(item)} onClose={onClose} placeholder="Select a status record" description="Inspect missing evidence, quality, visibility, claim limits, and technical provenance.">
    {item && <>
      <Header kicker="System and evidence status" title={resultTypeLabel(item.result_type)} subtitle={`${statusFamily(item.mechanism_id)} · ${mechanismLabel(item.mechanism_id)}`} onClose={onClose} />
      <div className="inspect-section"><KeyValueList rows={[["Priority", item.priority === "ATTENTION" ? "Attention" : "Info"], ["Recorded", formatTimestamp(item.timestamp)], ["Entity / flow", summarizeReference(item.entity_or_flow_reference, item.mechanism_id)]]} /></div>
      <section className="inspect-section"><div className="inspect-section-head"><h3>Missing evidence</h3></div><p className="inspect-summary">{item.missing_prerequisites.length ? item.missing_prerequisites.map(prerequisiteLabel).join(" · ") : "No missing prerequisites reported."}</p></section>
      <section className="inspect-section"><div className="inspect-section-head"><h3>Visibility</h3></div><VisibilitySnapshotView value={item.visibility} /></section>
      <section className="inspect-section"><div className="inspect-section-head"><h3>Capture quality</h3></div><QualitySnapshotView value={item.quality} /></section>
      <section className="inspect-section"><div className="inspect-section-head"><h3>Claim limit</h3></div><ClaimCeiling text={item.claim_ceiling} /></section>
      {item.source_result_ids.length > 0 && <section className="inspect-section"><span className="field-label">Source result</span><div className="source-links">{item.source_result_ids.map((id) => <button className="inline-link source-link" key={id} onClick={() => onResult(id)}>View {shortId(id)} →</button>)}</div><TechnicalDisclosure label="Full source identifiers"><CodeBlock label="Source result IDs" value={item.source_result_ids} /></TechnicalDisclosure></section>}
      <section className="inspect-section"><TechnicalDisclosure label="Technical details"><KeyValueList rows={[
        ["Status ID", item.status_id], ["Schema", item.schema_version], ["Policy", item.policy_version],
        ["Mechanism ID", item.mechanism_id], ["Result type", item.result_type], ["Status kind", readable(item.status_kind)],
        ["Missing prerequisites", item.missing_prerequisites.map(prerequisiteLabel).join(" · ") || "None supplied"],
        ["Governing IDs", item.governing_ids.join(" · ") || "None supplied"],
        ["Provenance refs", item.provenance_refs.join(" · ") || "None supplied"],
        ["Quality refs", item.quality_refs.join(" · ") || "None supplied"], ["Parser refs", item.parser_refs.join(" · ") || "None supplied"],
      ]} /><CodeBlock label="Entity reference" value={item.entity_or_flow_reference} /><CodeBlock label="Supporting evidence" value={item.supporting_evidence} /></TechnicalDisclosure></section>
    </>}
  </Inspector>;
}

export function SystemStatusPage({ onResult }: { onResult: (id: string) => void }) {
  const { state } = useEvidence();
  const [expandedFamily, setExpandedFamily] = useState<string | null>(null);
  const [selectedStatusId, setSelectedStatusId] = useState<string | null>(null);
  const runtime = state.runtime;
  if (!runtime) return <section className="page active-page"><PageHeading titleId="system-title" title="System status" deck="Runtime, analytic readiness and evidence quality." /></section>;

  const replay = state.replay ?? runtime.replay;
  const groups = new Map<string, RuntimeTarget[]>();
  for (const target of runtime.targets) {
    const family = target.lane_id.split(".")[0] ?? "other";
    groups.set(family, [...(groups.get(family) ?? []), target]);
  }
  const familyCount = groups.size;
  const dgaReady = runtime.dga_model_readiness === "VERIFIED_READY";
  const familyState = (family: string, targets: RuntimeTarget[]) => {
    if (family === "dga") return dgaReady ? "Model ready" : readable(runtime.dga_model_readiness);
    return targets.some((target) => target.implementation === "REGISTERED_SHELL") ? "Registered" : "Active";
  };
  const implementationLabel = (target: RuntimeTarget) => target.implementation === "ACTIVE_LEXICAL_MODEL_LANE"
    ? "Lexical model evidence"
    : target.implementation === "REGISTERED_SHELL" ? "Registered shell" : "Factual evidence";
  const selectedStatus = state.statusItems.find((item) => item.status_id === selectedStatusId) ?? null;

  return <section className="page active-page" aria-labelledby="system-title">
    <PageHeading titleId="system-title" title="System status" deck="Runtime readiness and evidence status." />
    <div className="system-summary" aria-label="Operational summary">
      <span><small>Runtime</small><strong>{runtime.state === "ONLINE" ? "Online" : "Replaying"}</strong></span>
      <span><small>Analytic families</small><strong>{familyCount}</strong></span>
      <span><small>Mechanisms</small><strong>{runtime.targets.length}</strong></span>
      <span><small>DGA model</small><strong>{dgaReady ? "Verified" : readable(runtime.dga_model_readiness)}</strong></span>
      <span><small>Alert policy</small><strong>{runtime.alert_policy_active ? "Active" : "Inactive"}</strong></span>
      <span><small>Input source</small><strong>{replay?.source_type || "Not reported"}</strong></span>
    </div>
    <section className="panel target-panel">
      <div className="panel-head compact"><div><h2>Analytic capabilities</h2><p>Current operational coverage.</p></div><span className="count-badge">{familyCount} families · {runtime.targets.length} mechanisms</span></div>
      <div className="family-list">
        {[...groups].map(([family, targets]) => {
          const expanded = expandedFamily === family;
          return <section className="family-item" key={family}>
            <button className="family-summary" type="button" aria-expanded={expanded} aria-controls={`family-${family}`} onClick={() => setExpandedFamily(expanded ? null : family)}>
              <strong>{familyLabel(family)}</strong><span className="family-state">{familyState(family, targets)}</span>
              <span>{targets.length} {targets.length === 1 ? "mechanism" : "mechanisms"}</span><span className="family-chevron" aria-hidden="true">{expanded ? "−" : "+"}</span>
            </button>
            {expanded && <div className="family-mechanisms" id={`family-${family}`}>{targets.map((target) => <div className="mechanism-row" key={target.lane_id}>
              <strong>{mechanismLabel(target.mechanism_id || target.lane_id)}</strong><span>{implementationLabel(target)}</span>
              <code>{target.lane_id}</code><code>{target.mechanism_id || "No mechanism ID"}</code>
            </div>)}</div>}
          </section>;
        })}
      </div>
    </section>
    <section className="panel status-records-panel">
      <div className="panel-head compact"><div><h2>System and evidence status</h2><p>Issues affecting evidence or analytic readiness.</p></div><span className="count-badge">{state.statusItems.length} {state.statusItems.length === 1 ? "record" : "records"}</span></div>
      <div className="status-inspection-layout">
        <div className="status-record-list">
          {state.statusItems.length ? state.statusItems.map((item) => <StatusRecord key={item.status_id} item={item} selected={item.status_id === selectedStatusId} onSelect={() => setSelectedStatusId(item.status_id)} />)
            : <EmptyState>No system or evidence status records in the current result window.</EmptyState>}
        </div>
        <StatusInspector item={selectedStatus} onClose={() => setSelectedStatusId(null)} onResult={onResult} />
      </div>
    </section>
    <details className="quality-help"><summary>About quality and visibility</summary><p>Quality describes conditions of capture and parsing. Visibility describes which evidence classes were available. Neither is an alert severity or a global posture score.</p></details>
    <details className="policy-details"><summary>Policy and runtime metadata</summary><KeyValueList rows={[
      ["Alert policy", runtime.alert_policy_version || "Not reported"], ["Database", readable(runtime.database_status)],
      ["Live subscribers", runtime.live_subscriber_count], ["Runtime target count", runtime.default_target_count],
      ["Input adapter", replay?.source_type || "Not reported"], ["DGA model status", readable(runtime.dga_model_readiness)],
      ...(runtime.dga_model_failure_reason ? [["DGA readiness detail", runtime.dga_model_failure_reason] as [string, string]] : []),
    ]} /></details>
  </section>;
}
