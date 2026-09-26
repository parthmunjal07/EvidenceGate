import type { ResultDto } from "../../api/types";
import { dgaScoreNote } from "../../utils/copy";
import { formatTimestamp, friendlyCategory, humanEvidenceRows, mechanismLabel, prerequisiteLabel, summarizeReference, whySurfaced } from "../../utils/formatting";
import { ClaimCeiling, InspectorSection, KeyValueList, QualitySnapshotView, VisibilitySnapshotView } from "../common/Primitives";
import { Header, Inspector } from "./InspectorShell";

export function ResultInspector({ result, onClose }: { result: ResultDto | null; onClose: () => void }) {
  const evidenceRows = result ? humanEvidenceRows(result.evidence) : [];
  if (!result) return null;
  return <Inspector key={result.result_id} variant="modal" label="Evidence record" selected onClose={onClose} placeholder="Select an evidence record" description="Inspect the observed facts, evidence conditions, and supporting details.">
    {result && <>
      <Header kicker={`${friendlyCategory(result.family)} · ${result.result_type.replaceAll("_", " ").toLowerCase()}`} title={mechanismLabel(result.mechanism_id || result.lane_id)} subtitle={`${summarizeReference(result.entity_reference, result.mechanism_id)} · ${formatTimestamp(result.created_time)}`} onClose={onClose} />
      <InspectorSection title="Why this was surfaced"><p className="inspect-summary prominent-summary">{whySurfaced(result.mechanism_id || result.lane_id, result.evidence)}</p></InspectorSection>
      <InspectorSection title="What was observed"><KeyValueList rows={[["Result", result.result_type.replaceAll("_", " ").toLowerCase()], ["Recorded", formatTimestamp(result.created_time)], ["Entity / peer", summarizeReference(result.entity_reference, result.mechanism_id)]]} /><div className="fact-grid">{evidenceRows.map(([label, value]) => <div key={label}><span>{label}</span><strong>{value}</strong></div>)}</div></InspectorSection>
      <InspectorSection title="Evidence interpretation"><ClaimCeiling text={result.claim_ceiling} />{result.lane_id === "dga.m1" ? <p className="inspect-summary">{dgaScoreNote(typeof result.evidence.dga_labelled_lexical_resemblance_score === "number" ? result.evidence.dga_labelled_lexical_resemblance_score : null)}</p> : <p className="inspect-summary">Observed evidence; no attack probability is implied.</p>}</InspectorSection>
      {result.missing_prerequisites.length > 0 && <InspectorSection title="Missing evidence"><p>{result.missing_prerequisites.map(prerequisiteLabel).join(" · ")}</p></InspectorSection>}
      <InspectorSection title="Sensor visibility and quality"><details className="sensor-details"><summary>Show all sensor visibility</summary><VisibilitySnapshotView value={result.visibility_snapshot} /><QualitySnapshotView value={result.quality_snapshot} /></details></InspectorSection>
    </>}
  </Inspector>;
}
