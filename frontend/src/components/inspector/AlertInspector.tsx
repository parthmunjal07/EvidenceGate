import type { SihAlertProjection } from "../../api/types";
import {
  confidenceText,
  formatTimestamp,
  readable,
  summarizeEvidence,
  threatClassLabel,
  shortId,
  summarizeReference,
} from "../../utils/formatting";
import {
  ClaimCeiling,
  CodeBlock,
  InspectorSection,
  KeyValueList,
  QualitySnapshotView,
  VisibilitySnapshotView,
} from "../common/Primitives";
import { Header, Inspector } from "./InspectorShell";
export function AlertInspector({
  alert,
  onClose,
  onResult,
}: {
  alert: SihAlertProjection | null;
  onClose: () => void;
  onResult: (id: string) => void;
}) {
  return (
    <Inspector
      label="Evidence inspector"
      selected={Boolean(alert)}
      onClose={onClose}
      placeholder="Select an alert"
      description="Choose a row to inspect its evidence, confidence meaning, visibility, quality, and source result."
    >
      {alert && (
        <>
          <Header
            kicker="Analyst attention record"
            title={threatClassLabel(alert.threat_class)}
            subtitle={threatClassLabel(alert.threat_class)}
            onClose={onClose}
          />
          <InspectorSection title="Identity">
            <KeyValueList
              rows={[
                ["Entity / flow", summarizeReference(alert.entity_or_flow_reference, alert.mechanism_id)],
                ["Timestamp", formatTimestamp(alert.timestamp)],
                ["Priority", "Review Â· analyst attention"],
                ["Result type", readable(alert.result_type)],
              ]}
            />
          </InspectorSection>
          <InspectorSection title="Supporting evidence">
            <p className="inspect-summary">
              {summarizeEvidence(alert.supporting_evidence.structured)}
            </p>
            {alert.supporting_evidence.evidence_items.length > 0 && <p>{alert.supporting_evidence.evidence_items.join(" · ")}</p>}
            <InspectorSection title="Technical evidence details" secondary>
              <CodeBlock label="Structured evidence" value={alert.supporting_evidence.structured} />
              <CodeBlock label="Evidence items" value={alert.supporting_evidence.evidence_items} />
              <CodeBlock label="Source observation IDs" value={alert.supporting_evidence.source_observation_ids} />
            </InspectorSection>
          </InspectorSection>
          <InspectorSection title="Confidence semantics">
            <p className="confidence-note">
              {confidenceText(
                alert.confidence_basis,
                alert.confidence_score,
              )}
            </p>
          </InspectorSection>
          <InspectorSection title="Visibility & quality">
            <span className="field-label">Visibility classes</span>
            <VisibilitySnapshotView value={alert.visibility} />
            <span className="field-label">Source quality facts</span>
            <QualitySnapshotView value={alert.quality} />
          </InspectorSection>
          <InspectorSection title="Claim limit">
            <ClaimCeiling text={alert.claim_ceiling} />
          </InspectorSection>
          <InspectorSection title="Governance & provenance" secondary>
            <KeyValueList
              rows={[
                [
                  "Model refs",
                  alert.model_refs.join(" Â· ") || "None supplied",
                ],
                [
                  "Parser refs",
                  alert.parser_refs.join(" Â· ") || "None supplied",
                ],
                [
                  "Governing IDs",
                  alert.governing_ids.join(" Â· ") || "None supplied",
                ],
                [
                  "Quality refs",
                  alert.quality_refs.join(" Â· ") || "None supplied",
                ],
                [
                  "Provenance refs",
                  alert.provenance_refs.join(" Â· ") || "None supplied",
                ],
              ]}
            />
            <div className="source-links">
              {alert.source_result_ids.map((id) => (
                <button
                  className="inline-link source-link"
                  key={id}
                  onClick={() => onResult(id)}
                >
                  View {shortId(id)} →
                </button>
              ))}
            </div>
            <CodeBlock label="Full source result IDs" value={alert.source_result_ids} />
          </InspectorSection>
        </>
      )}
    </Inspector>
  );
}
