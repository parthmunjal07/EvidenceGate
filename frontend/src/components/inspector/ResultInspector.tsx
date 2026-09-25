import type { ResultDto } from "../../api/types";
import { dgaScoreNote } from "../../utils/copy";
import { formatTimestamp, friendlyCategory, humanEvidenceRows, mechanismLabel, prerequisiteLabel, summarizeReference, whySurfaced } from "../../utils/formatting";
import { ClaimCeiling, CodeBlock, InspectorSection, KeyValueList, QualitySnapshotView, VisibilitySnapshotView } from "../common/Primitives";
import { Header, Inspector } from "./InspectorShell";

export function ResultInspector({ result, onClose }: { result: ResultDto | null; onClose: () => void }) {
  const evidenceRows = result ? humanEvidenceRows(result.evidence) : [];
  return <Inspector label="Evidence investigation" selected={Boolean(result)} onClose={onClose} placeholder="Select a result" description="Inspect the finding, its evidence, and its interpretation limits.">
    {result && <>
      <Header kicker={friendlyCategory(result.family)} title={mechanismLabel(result.mechanism_id || result.lane_id)} subtitle={summarizeReference(result.entity_reference, result.mechanism_id)} onClose={onClose} />
      <InspectorSection title="Why this was surfaced"><p className="inspect-summary prominent-summary">{whySurfaced(result.mechanism_id || result.lane_id, result.evidence)}</p></InspectorSection>
      <InspectorSection title="What was observed"><KeyValueList rows={[["Result", result.result_type.replaceAll("_", " ").toLowerCase()], ["Recorded", formatTimestamp(result.created_time)], ["Entity / peer", summarizeReference(result.entity_reference, result.mechanism_id)], ...evidenceRows]} /></InspectorSection>
      <InspectorSection title="Evidence basis"><p className="inspect-summary">{result.lane_id === "dga.m1" ? dgaScoreNote(typeof result.evidence.dga_labelled_lexical_resemblance_score === "number" ? result.evidence.dga_labelled_lexical_resemblance_score : null) : "Observed evidence; no attack probability is implied."}</p></InspectorSection>
      <div className="inspect-section"><ClaimCeiling text={result.claim_ceiling} /></div>
      {result.missing_prerequisites.length > 0 && <InspectorSection title="Missing evidence"><p>{result.missing_prerequisites.map(prerequisiteLabel).join(" · ")}</p></InspectorSection>}
      <InspectorSection title="Visibility and quality"><VisibilitySnapshotView value={result.visibility_snapshot} /><QualitySnapshotView value={result.quality_snapshot} /></InspectorSection>
      <details className="technical-details"><summary>Technical details</summary>
        <KeyValueList rows={[["Result ID", result.result_id], ["Taxonomy", result.taxonomy.join(" · ")], ["Raw entity reference", result.entity_reference], ["Lane ID", result.lane_id], ["Mechanism ID", result.mechanism_id || "Not supplied"], ["Result type", result.result_type], ["Governance version", result.governance_version], ["Raw claim policy", result.claim_ceiling], ["Source observation IDs", result.source_observation_ids.join(" · ") || "None supplied"], ["Config hash", result.config_hash || "Not supplied"], ["State version", result.state_version ?? "Not supplied"]]} />
        <CodeBlock label="Structured evidence" value={result.evidence} /><CodeBlock label="Exact visibility" value={result.visibility_snapshot} /><CodeBlock label="Exact quality" value={result.quality_snapshot} />
        <KeyValueList rows={[["Model refs", result.model_refs.join(" · ") || "None supplied"], ["Parser refs", result.parser_refs.join(" · ") || "None supplied"], ["Governing IDs", result.governing_ids.join(" · ") || "None supplied"], ["Quality refs", result.quality_refs.join(" · ") || "None supplied"], ["Provenance refs", result.provenance_refs.join(" · ") || "None supplied"], ["Source IDs", result.source_ids.join(" · ") || "None supplied"]]} />
      </details>
    </>}
  </Inspector>;
}
