import type { ResultDto } from "../../api/types";
import {
  formatTimestamp,
  readable,
  shortModelRef,
  summarizeEvidence,
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
      description="Inspect observed facts, derived evidence, missing prerequisites, claim ceiling, and provenance."
    >
      {result && (
        <>
          <Header
            kicker="IMMUTABLE SCIENTIFIC RESULT"
            title={readable(result.result_type).toUpperCase()}
            subtitle={`${result.family} Â· ${result.lane_id}`}
            onClose={onClose}
          />
          <InspectorSection title="Identity">
            <KeyValueList
              rows={[
                ["Result ID", result.result_id],
                ["Timestamp", formatTimestamp(result.created_time)],
                [
                  "Lane / mechanism",
                  `${result.lane_id} / ${result.mechanism_id || "â€”"}`,
                ],
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
                ["Entity / flow", result.entity_reference],
                [
                  "Source observation IDs",
                  result.source_observation_ids.join(" Â· ") || "None supplied",
                ],
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
            <CodeBlock label="STRUCTURED EVIDENCE" value={result.evidence} />
            {result.evidence_items.length > 0 && (
              <CodeBlock label="EVIDENCE ITEMS" value={result.evidence_items} />
            )}
          </InspectorSection>
          <InspectorSection title="Confidence semantics">
            <p className="confidence-note">
              {result.lane_id === "dga.m1"
                ? `DGA-labelled lexical resemblance score: ${typeof score === "number" ? score.toFixed(6) : "not supplied"}. Not calibrated attack probability.`
                : "Numeric attack probability is not defined by this analytic."}
            </p>
          </InspectorSection>
          <InspectorSection title="Visibility & quality">
            <span className="field-label">VISIBILITY CLASSES</span>
            <VisibilitySnapshotView value={result.visibility_snapshot} />
            <span className="field-label">SOURCE QUALITY FACTS</span>
            <QualitySnapshotView value={result.quality_snapshot} />
          </InspectorSection>
          <InspectorSection title="Missing evidence & prerequisites">
            <CodeBlock
              label="MISSING PREREQUISITES"
              value={result.missing_prerequisites}
            />
          </InspectorSection>
          <InspectorSection title="Claim ceiling">
            <ClaimCeiling text={result.claim_ceiling} />
          </InspectorSection>
          <InspectorSection
            title="Model, parser & governing references"
            secondary
          >
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
              label="FULL TECHNICAL REFERENCES"
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
