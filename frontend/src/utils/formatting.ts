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
export function summarizeReference(value: string, mechanismId?: string | null) {
  try {
    const parsed: unknown = JSON.parse(value);
    if (mechanismId === "DDOS-A-B0" && Array.isArray(parsed) && parsed.length === 4
      && typeof parsed[0] === "string" && typeof parsed[1] === "string"
      && parsed[2] === 6 && Array.isArray(parsed[3]) && parsed[3].length === 2) {
      const tuple = parsed[3];
      const endpoint = (entry: unknown): string | null => {
        if (!Array.isArray(entry) || entry.length !== 2 || typeof entry[0] !== "string"
          || typeof entry[1] !== "number" || !Number.isInteger(entry[1])) return null;
        return `${entry[0]}:${entry[1]}`;
      };
      const first = endpoint(tuple[0]);
      const second = endpoint(tuple[1]);
      if (first && second) return `Target ${parsed[0]} · ${parsed[1]} · TCP · ${first} ↔ ${second}`;
    }
    if (Array.isArray(parsed)) return parsed.every((item) => item === null || ["string", "number", "boolean"].includes(typeof item))
      ? parsed.map(safeReferenceValue).join(" · ")
      : `Structured value · ${parsed.length} items`;
    if (parsed && typeof parsed === "object") {
      const entries = Object.entries(parsed);
      if (entries.every(([, item]) => item === null || ["string", "number", "boolean"].includes(typeof item))) {
        return entries.map(([key, item]) => `${readable(key)}: ${safeReferenceValue(item)}`).join(" · ");
      }
      return entries.length ? `Structured reference · ${entries.length} fields` : "Structured reference";
    }
  } catch {
    // Plain entity names are already suitable for table display.
  }
  return value;
}
function safeReferenceValue(value: unknown): string {
  if (value === null) return "Unknown";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) return value.every((item) => item === null || ["string", "number", "boolean"].includes(typeof item))
    ? value.map(safeReferenceValue).join(" · ") : `Structured value · ${value.length} items`;
  return "Structured value";
}

export function familyLabel(value: string) {
  const labels: Record<string, string> = {
    ddos: "DDoS", c2: "C2 beaconing", dga: "DGA",
    dns_tunnelling: "DNS tunnelling", encrypted_session: "Encrypted sessions",
    recon: "Reconnaissance", unusual_transfer: "Data transfer",
  };
  return labels[value] ?? readable(value);
}

export function mechanismLabel(value: string) {
  const labels: Record<string, string> = {
    "DDOS-A-B0": "SYN state", "DDOS-B-B0": "UDP demand",
    "DDOS-CV-B0": "Reflection evidence", "DDOS-D-B0": "Source diversity",
    "DDOS-E1-B0": "ICMP demand", "DDOS-E2-B0": "Fragment demand",
    "DDOS-E3-B0": "Connection churn", "C2-M1": "Flow recurrence",
    "DGA-A1-M1": "Lexical model", "DNS-T1": "DNS tunnelling evidence",
    "ENC-A": "TLS handshake evidence", "RECON-H": "Horizontal host breadth",
    "RECON-V": "Vertical port breadth", "RECON-2D": "Host and port exploration",
    "RECON-TCP": "TCP attempt and response evidence", "CAT6-EX-M1": "Transfer magnitude",
  };
  return labels[value] ?? value;
}

export function prerequisiteLabel(value: string) {
  const labels: Record<string, string> = {
    reverse_tcp_state: "Reverse TCP state",
    REVERSE_TCP_STATE: "Reverse TCP state",
  };
  return labels[value] ?? readable(value);
}

export function shortId(value: string) {
  return value.length > 14 ? `${value.slice(0, 6)}…${value.slice(-5)}` : value;
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
