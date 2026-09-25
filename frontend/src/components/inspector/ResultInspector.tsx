import type { ResultDto } from "../../api/types";
import {
  formatTimestamp,
  readable,
  shortModelRef,
  summarizeEvidence,
  familyLabel,
  mechanismLabel,
  prerequisiteLabel,
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
import { dgaScoreNote, nonDgaProbabilityNote } from "../../utils/copy";
export function ResultInspector({
  result,
  onClose,
}: {
  result: ResultDto | null;
  onClose: () => void;
}) {
  const score = result?.evidence.dga_labelled_lexical_resemblance_score;
  return (
    <Inspector
      label="Result inspector"
      selected={Boolean(result)}
      onClose={onClose}
      placeholder="Select a result"
      description="Inspect observed facts, derived evidence, missing prerequisites, claim limit, and provenance."
    >
      {result && (
        <>
          <Header
            kicker="Scientific result"
            title={readable(result.result_type)}
            subtitle={`${familyLabel(result.family.toLowerCase())} Â· ${mechanismLabel(result.mechanism_id || result.lane_id)}`}
            onClose={onClose}
          />
          <InspectorSection title="Identity">
            <KeyValueList
              rows={[
                ["Timestamp", formatTimestamp(result.created_time)],
                ["Scientific status", result.status_snapshot.scientific_status],
                [
                  "Integration status",
                  result.status_snapshot.integration_status,
                ],
                ["Readiness", result.status_snapshot.readiness],
                [
                  "Governance version",
                  result.status_snapshot.governance_version,
                ],
                [
                  "Quality degraded",
                  result.status_snapshot.quality_degraded ? "Yes" : "No",
                ],
              ]}
            />
          </InspectorSection>
          <InspectorSection title="Observed facts">
            <KeyValueList
              rows={[
                ["Entity / flow", summarizeReference(result.entity_reference, result.mechanism_id)],
                [
                  "Evidence interval",
                  result.evidence_interval
                    ?.map(formatTimestamp)
                    .join(" â€” ") || "Not specified",
                ],
              ]}
            />
          </InspectorSection>
          <InspectorSection title="Derived evidence">
            <p className="inspect-summary">
              {summarizeEvidence(result.evidence)}
            </p>
            {result.evidence_items.length > 0 && (
              <p>{result.evidence_items.join(" · ")}</p>
            )}
            <InspectorSection title="Technical evidence details" secondary>
              <CodeBlock label="Structured evidence" value={result.evidence} />
              <CodeBlock label="Evidence items" value={result.evidence_items} />
            </InspectorSection>
          </InspectorSection>
          <InspectorSection title="Confidence semantics">
            <p className="confidence-note">
              {result.lane_id === "dga.m1"
                ? dgaScoreNote(typeof score === "number" ? score : null)
                : nonDgaProbabilityNote}
            </p>
          </InspectorSection>
          <InspectorSection title="Visibility & quality">
            <span className="field-label">Visibility classes</span>
            <VisibilitySnapshotView value={result.visibility_snapshot} />
            <span className="field-label">Source quality facts</span>
            <QualitySnapshotView value={result.quality_snapshot} />
          </InspectorSection>
          <InspectorSection title="Missing evidence & prerequisites">
            {result.missing_prerequisites.length
              ? <p>{result.missing_prerequisites.map(prerequisiteLabel).join(" · ")}</p>
              : <p>No missing prerequisites reported.</p>}
          </InspectorSection>
          <InspectorSection title="Claim limit">
            <ClaimCeiling text={result.claim_ceiling} />
          </InspectorSection>
          <InspectorSection
            title="Model, parser & governing references"
            secondary
          >
            <KeyValueList rows={[["Result ID", result.result_id], ["Lane ID", result.lane_id], ["Mechanism ID", result.mechanism_id || "Not supplied"], ["Source observation IDs", result.source_observation_ids.join(" Â· ") || "None supplied"]]} />
            <KeyValueList
              rows={[
                [
                  "Model refs",
                  result.model_refs.join(" Â· ") || "None supplied",
                ],
                [
                  "Parser refs",
                  result.parser_refs.join(" Â· ") || "None supplied",
                ],
                [
                  "Provenance refs",
                  result.provenance_refs.join(" Â· ") || "None supplied",
                ],
                [
                  "Quality refs",
                  result.quality_refs.join(" Â· ") || "None supplied",
                ],
                [
                  "Source IDs",
                  result.source_ids.join(" Â· ") || "None supplied",
                ],
                [
                  "Governing decision IDs",
                  result.governing_ids.join(" Â· ") || "None supplied",
                ],
                ["Config hash", result.config_hash || "Not supplied"],
                ["State version", result.state_version ?? "Not supplied"],
                [
                  "Model",
                  result.lane_id === "dga.m1"
                    ? shortModelRef(result.model_refs)
                    : "â€”",
                ],
              ]}
            />
            <CodeBlock
              label="Full technical references"
              value={[
                ...result.model_refs,
                ...result.parser_refs,
                ...result.governing_ids,
                ...result.quality_refs,
                ...result.provenance_refs,
              ]}
            />
          </InspectorSection>
        </>
      )}
    </Inspector>
  );
}
