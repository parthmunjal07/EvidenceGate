import type { SihAlertProjection } from "../../api/types";
import { dgaScoreNote } from "../../utils/copy";
import { formatTimestamp, friendlyCategory, humanEvidenceRows, mechanismLabel, prerequisiteLabel, shortId, summarizeReference, whySurfaced } from "../../utils/formatting";
import { ClaimCeiling, CodeBlock, InspectorSection, KeyValueList, QualitySnapshotView, VisibilitySnapshotView } from "../common/Primitives";
import { Header, Inspector } from "./InspectorShell";
import { useTimeZone } from "../../state/TimeZoneContext";

export function AlertInspector({ alert, onClose, onResult }: { alert: SihAlertProjection | null; onClose: () => void; onResult: (id: string) => void }) {
  const { zone } = useTimeZone();
  const developerUi = import.meta.env.VITE_EVIDENCEGATE_DEV_UI === "true";
  const evidenceRows = alert ? humanEvidenceRows(alert.supporting_evidence.structured) : [];
  return <Inspector label="Alert investigation" selected={Boolean(alert)} onClose={onClose} placeholder="Select an alert" description="Review why it surfaced, the observed evidence, and any limits on interpretation.">
    {alert && <>
      <Header kicker={friendlyCategory(alert.threat_class)} title={mechanismLabel(alert.mechanism_id)} subtitle={summarizeReference(alert.entity_or_flow_reference, alert.mechanism_id)} onClose={onClose} />
      <div className="review-badge">REVIEW</div>
      <InspectorSection title="Why this was surfaced"><p className="inspect-summary prominent-summary">{whySurfaced(alert.mechanism_id, alert.supporting_evidence.structured)}</p></InspectorSection>
      <InspectorSection title="What was observed"><KeyValueList rows={[["Evidence basis", alert.confidence_basis === "MODEL_SCORE" ? "Lexical model score" : alert.confidence_basis === "STATISTICAL_SUPPORT" ? "Statistical support" : "Observed evidence"], ["Observed time", formatTimestamp(alert.timestamp, zone)], ...evidenceRows]} /></InspectorSection>
      <InspectorSection title="Evidence basis"><p className="inspect-summary">{alert.confidence_basis === "MODEL_SCORE" ? dgaScoreNote(alert.confidence_score) : alert.confidence_basis === "STATISTICAL_SUPPORT" ? "Statistical support describes the evidence basis; it is not a probability of malicious activity." : "Directly observed evidence is presented without an attack probability."}</p></InspectorSection>
      <div className="inspect-section"><ClaimCeiling text={alert.claim_ceiling} /></div>
      <InspectorSection title="Visibility and quality"><VisibilitySnapshotView value={alert.visibility} /><QualitySnapshotView value={alert.quality} /></InspectorSection>
      {(alert.supporting_evidence.structured.missing_prerequisites || alert.supporting_evidence.structured.missing_evidence) && <InspectorSection title="Missing evidence"><p>{prerequisiteLabel(String(alert.supporting_evidence.structured.missing_prerequisites ?? alert.supporting_evidence.structured.missing_evidence))}</p></InspectorSection>}
      {Array.isArray(alert.supporting_evidence.structured.hard_negative_alternatives) && <InspectorSection title="What else could explain it?"><ul>{(alert.supporting_evidence.structured.hard_negative_alternatives as string[]).filter((item) => typeof item === "string").map((item) => <li key={item}>{item}</li>)}</ul></InspectorSection>}
      <InspectorSection title="What to review next"><div className="source-links">{alert.source_result_ids.map((_, index) => <button className="inline-link source-link" key={index} onClick={() => onResult(alert.source_result_ids[index]!)}>Open contributing Result {index + 1} →</button>)}</div></InspectorSection>
      {developerUi && <details className="technical-details"><summary>Developer details</summary>
        <KeyValueList rows={[["SIH threat class", alert.threat_class], ["Mechanism ID", alert.mechanism_id], ["Raw entity reference", alert.entity_or_flow_reference], ["Result type", alert.result_type], ["Evidence basis enum", alert.confidence_basis], ["Policy version", alert.policy_version], ["Raw claim policy", alert.claim_ceiling]]} />
        <CodeBlock label="Structured evidence" value={alert.supporting_evidence.structured} /><CodeBlock label="Exact visibility" value={alert.visibility} /><CodeBlock label="Exact quality" value={alert.quality} />
        <KeyValueList rows={[["Model refs", alert.model_refs.join(" · ") || "None supplied"], ["Parser refs", alert.parser_refs.join(" · ") || "None supplied"], ["Governing IDs", alert.governing_ids.join(" · ") || "None supplied"], ["Quality refs", alert.quality_refs.join(" · ") || "None supplied"], ["Provenance refs", alert.provenance_refs.join(" · ") || "None supplied"]]} />
        <div className="source-links">{alert.source_result_ids.map((id) => <button className="inline-link source-link" key={id} onClick={() => onResult(id)}>View result {shortId(id)} →</button>)}</div><CodeBlock label="Source result IDs" value={alert.supporting_evidence.source_observation_ids} />
      </details>}
    </>}
  </Inspector>;
}
