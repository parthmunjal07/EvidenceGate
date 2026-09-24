import type {
  ConfidenceBasis,
  QualitySnapshot,
  SihAlertProjection,
  VisibilitySnapshot,
} from "../api/types";

export const pretty = (value: unknown) =>
  JSON.stringify(value ?? null, null, 2);
export const readable = (value: unknown) =>
  String(value ?? "—")
    .replaceAll("_", " ")
    .toLowerCase();
export const formatTimestamp = (value: string | null | undefined) =>
  value
    ? new Date(value).toLocaleString([], {
        dateStyle: "medium",
        timeStyle: "medium",
      })
    : "—";
export const formatShortTime = (value: string | null | undefined) =>
  value
    ? new Date(value).toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      })
    : "—";
export function formatQuality(quality: QualitySnapshot) {
  const values = Object.values(quality);
  if (values.includes("DEGRADED")) return "Degraded";
  if (values.every((value) => value === "CLEAR")) return "Clear";
  return "Unknown";
}
export const availableCount = (visibility: VisibilitySnapshot) =>
  visibility.available.length;
export function summarizeEvidence(evidence: Record<string, unknown>) {
  if (evidence.evidence_kind === "DGA_LEXICAL_MODEL_EVIDENCE") {
    const score = evidence.dga_labelled_lexical_resemblance_score;
    return score === undefined
      ? "DGA lexical model evidence"
      : `DGA-labelled lexical resemblance score ${Number(score).toFixed(3)}`;
  }
  const pairs = Object.entries(evidence).slice(0, 2);
  return pairs.length
    ? pairs
        .map(
          ([key, value]) =>
            `${key.replaceAll("_", " ")}: ${typeof value === "object" ? "…" : String(value)}`,
        )
        .join(" · ")
    : "Structured evidence available";
}
export function confidenceText(
  basis: ConfidenceBasis,
  score: number | null,
  statement: string,
) {
  if (basis === "MODEL_SCORE")
    return `DGA-labelled lexical resemblance score: ${score == null ? "not present" : score.toFixed(6)}. Not calibrated attack probability.`;
  return `${basis}: ${statement}. Numeric attack probability is not defined by this analytic.`;
}
export function shortModelRef(refs: string[]) {
  const model = refs.find((value) => value.startsWith("model:DGA-A1-M1-R1"));
  const hash = refs.find((value) => value.startsWith("sha256:"));
  if (!model) return "";
  return `${model.replace("model:", "")}${hash ? ` · ${hash.slice(0, 15)}…${hash.slice(-6)}` : ""}`;
}
export function alertSearchText(alert: SihAlertProjection) {
  return [
    alert.threat_class,
    alert.mechanism_id,
    alert.entity_or_flow_reference,
    summarizeEvidence(alert.supporting_evidence.structured),
    alert.source_result_ids.join(" "),
  ]
    .join(" ")
    .toLowerCase();
}
