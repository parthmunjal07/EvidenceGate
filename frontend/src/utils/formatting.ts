import type {
  ConfidenceBasis,
  QualitySnapshot,
  SihAlertProjection,
  VisibilitySnapshot,
} from "../api/types";
import { dgaScoreNote, nonDgaProbabilityNote } from "./copy";

export const pretty = (value: unknown) =>
  JSON.stringify(value ?? null, null, 2);
export const readable = (value: unknown) => {
  const text = String(value ?? "—").replaceAll("_", " ").toLowerCase();
  return text.length ? `${text[0]?.toUpperCase()}${text.slice(1)}` : text;
};
export function threatClassLabel(value: string) {
  const labels: Record<string, string> = {
    C2: "C2",
    DGA: "DGA",
    DOS: "DDoS",
    DNS_TUNNELING: "DNS tunnelling",
    RECONNAISSANCE: "Reconnaissance",
  };
  return labels[value] ?? readable(value);
}
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
export function summarizeReference(value: string) {
  try {
    const parsed: unknown = JSON.parse(value);
    if (Array.isArray(parsed)) return parsed.map(String).join(" · ");
    if (parsed && typeof parsed === "object") {
      return Object.entries(parsed)
        .map(([key, item]) => `${key.replaceAll("_", " ")}: ${String(item)}`)
        .join(" · ");
    }
  } catch {
    // Plain entity names are already suitable for table display.
  }
  return value;
}
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
export function summarizeTableEvidence(evidence: Record<string, unknown>) {
  const factual = Object.fromEntries(
    Object.entries(evidence).filter(
      ([key]) => !/claim[_ ]?(ceiling|limit)/i.test(key),
    ),
  );
  return summarizeEvidence(factual);
}
export function confidenceText(
  basis: ConfidenceBasis,
  score: number | null,
) {
  if (basis === "MODEL_SCORE")
    return dgaScoreNote(score);
  const label = basis === "STATISTICAL_SUPPORT" ? "Statistical support" : "Observed evidence";
  return `${label}. ${nonDgaProbabilityNote}`;
}
export function confidenceBasisLabel(basis: ConfidenceBasis) {
  if (basis === "MODEL_SCORE") return "Model score";
  if (basis === "STATISTICAL_SUPPORT") return "Statistical support";
  return "Observed evidence";
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
