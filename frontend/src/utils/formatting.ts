import type {
  ConfidenceBasis,
  FamilyEvidenceViewDto,
  FamilyFindingDto,
  InvestigationLinkDto,
  QualitySnapshot,
  ResultDto,
  SihAlertProjection,
  VisibilitySnapshot,
} from "../api/types";
import { dgaScoreNote, nonDgaProbabilityNote } from "./copy";

export type DisplayTimeZone = "local" | "utc";
export const TIME_ZONE_STORAGE_KEY = "evidencegate.time-zone";

export function getDisplayTimeZone(): DisplayTimeZone {
  return typeof localStorage !== "undefined" && localStorage.getItem(TIME_ZONE_STORAGE_KEY) === "utc" ? "utc" : "local";
}

export function timestampMs(value: string | null | undefined) {
  if (!value) return Number.NEGATIVE_INFINITY;
  const valueMs = Date.parse(value);
  return Number.isNaN(valueMs) ? Number.NEGATIVE_INFINITY : valueMs;
}

export function compareTimeAsc(a: string | null | undefined, b: string | null | undefined) {
  const left = timestampMs(a);
  const right = timestampMs(b);
  if (left === right) return 0;
  if (left === Number.NEGATIVE_INFINITY) return -1;
  if (right === Number.NEGATIVE_INFINITY) return 1;
  return left - right;
}

export function compareTimeDesc(a: string | null | undefined, b: string | null | undefined) {
  return compareTimeAsc(b, a);
}

export function latestObservedTime(values: Array<string | null | undefined>) {
  return values.filter((value): value is string => Boolean(value) && Number.isFinite(timestampMs(value))).sort(compareTimeDesc)[0] ?? "";
}

function zoneOptions(zone: DisplayTimeZone) {
  return zone === "utc" ? { timeZone: "UTC" } : { timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone };
}

export function formatTimeZoneLabel(zone: DisplayTimeZone = getDisplayTimeZone()) {
  if (zone === "utc") return "UTC";
  const timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const parts = new Intl.DateTimeFormat("en", { ...zoneOptions(zone), timeZoneName: "short" }).formatToParts(new Date());
  return normalizeTimeZoneLabel(timeZone, parts.find((part) => part.type === "timeZoneName")?.value ?? timeZone);
}

export function normalizeTimeZoneLabel(ianaZone: string, shortName: string) {
  return ianaZone === "Asia/Kolkata" || ianaZone === "Asia/Calcutta" ? "IST" : shortName;
}

function validDate(value: string | null | undefined) {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function datePart(value: string, zone: DisplayTimeZone) {
  return new Intl.DateTimeFormat("en-GB", { ...zoneOptions(zone), day: "2-digit", month: "short", year: "numeric" }).format(new Date(value));
}

function timePart(value: string, zone: DisplayTimeZone) {
  return new Intl.DateTimeFormat("en-GB", { ...zoneOptions(zone), hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" }).format(new Date(value));
}

export function formatEvidenceDateTime(value: string | null | undefined, zone: DisplayTimeZone = getDisplayTimeZone()) {
  const date = validDate(value);
  return date ? `${datePart(date.toISOString(), zone)} · ${timePart(date.toISOString(), zone)} ${formatTimeZoneLabel(zone)}` : "Time unavailable";
}

export function formatEvidenceDateTimeCompact(value: string | null | undefined, zone: DisplayTimeZone = getDisplayTimeZone()) {
  const date = validDate(value);
  return date ? `${datePart(date.toISOString(), zone)} · ${timePart(date.toISOString(), zone)}` : "Time unavailable";
}

export function formatEvidenceClockTime(value: string | null | undefined, zone: DisplayTimeZone = getDisplayTimeZone()) {
  const date = validDate(value);
  return date ? timePart(date.toISOString(), zone) : "Time unavailable";
}

export function formatEvidenceTableDate(value: string | null | undefined, zone: DisplayTimeZone = getDisplayTimeZone()) {
  const date = validDate(value);
  return date ? datePart(date.toISOString(), zone) : "Time unavailable";
}

export function formatEvidenceTableClock(value: string | null | undefined, zone: DisplayTimeZone = getDisplayTimeZone()) {
  const date = validDate(value);
  return date ? timePart(date.toISOString(), zone) : "Time unavailable";
}

export function normalizeFamilyName(value: string) {
  const normalized = familyLabel(value).replace(/\s+evidence$/i, "").trim().toLowerCase().replace(/^botnet\s+/, "");
  const names: Record<string, string> = {
    ddos: "DDoS", "ddos / reconnaissance": "DDoS + Reconnaissance", "ddos + reconnaissance": "DDoS + Reconnaissance",
    "c2 beaconing": "C2 / Beaconing", "c2 / beaconing": "C2 / Beaconing", c2: "C2 / Beaconing",
    dga: "DGA", "dga + dns": "DGA + DNS", "dns evidence": "DNS", "dns tunnelling": "DNS tunnelling",
    reconnaissance: "Reconnaissance", "encrypted sessions": "Encrypted Sessions", "encrypted session": "Encrypted Sessions", "encrypted-session": "Encrypted Sessions",
    "data transfer": "Data Transfer", "unusual transfer": "Data Transfer",
  };
  return names[normalized] ?? familyLabel(value).replace(/\s+evidence$/i, "");
}

export function formatEvidenceTime(value: string | null | undefined, zone: DisplayTimeZone = getDisplayTimeZone()) {
  const date = validDate(value);
  return date ? `${timePart(date.toISOString(), zone)} ${formatTimeZoneLabel(zone)}` : "Time unavailable";
}

export function formatEvidenceRange(start: string | null | undefined, end: string | null | undefined, zone: DisplayTimeZone = getDisplayTimeZone()) {
  if (!start) return "Time unavailable";
  if (!end || timestampMs(start) === timestampMs(end)) return formatEvidenceDateTime(start, zone);
  const startDate = validDate(start);
  const endDate = validDate(end);
  if (!startDate || !endDate) return "Time unavailable";
  const leftDate = datePart(startDate.toISOString(), zone);
  const rightDate = datePart(endDate.toISOString(), zone);
  return leftDate === rightDate
    ? `${leftDate} · ${timePart(startDate.toISOString(), zone)}–${timePart(endDate.toISOString(), zone)} ${formatTimeZoneLabel(zone)}`
    : `${leftDate} · ${timePart(startDate.toISOString(), zone)} – ${rightDate} · ${timePart(endDate.toISOString(), zone)} ${formatTimeZoneLabel(zone)}`;
}

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
    DOS: "DDoS evidence",
    DDOS: "DDoS evidence",
    DNS_TUNNELING: "DNS tunnelling",
    RECONNAISSANCE: "Reconnaissance evidence",
    DATA_EXFILTRATION: "Data transfer",
    ENCRYPTED_SESSION: "Encrypted-session evidence",
  };
  return labels[value] ?? readable(value);
}
export const formatTimestamp = formatEvidenceDateTime;
export const formatShortTime = formatEvidenceTime;
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
    if (Array.isArray(parsed) && parsed.length === 4 && typeof parsed[0] === "string"
      && typeof parsed[1] === "string" && typeof parsed[2] === "string"
      && typeof parsed[3] === "string" && /^(FORWARD|REVERSE)$/i.test(parsed[2])
      && !Number.isNaN(Date.parse(parsed[3]))) {
      const service = parsed[1].replace(/^service\//i, "").replaceAll("_", " ").toUpperCase();
      return `Target ${parsed[0]} · ${service}`;
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
  const flowId = value.match(/^flow:(.+)$/i);
  if (flowId) return `Flow ${flowId[1]}`;
  return value;
}

export function primaryEntityLabel(value: string) {
  const summary = summarizeReference(value);
  return summary.split(" · ", 1)[0] ?? summary;
}

export function observationLineageLabel(sourceObservationIds: string[]) {
  if (sourceObservationIds.length === 0) return null;
  return `Evidence from ${sourceObservationIds.length} observation${sourceObservationIds.length === 1 ? "" : "s"}`;
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
    recon: "Reconnaissance", unusual_transfer: "Data transfer", "data exfiltration": "Data transfer",
  };
  return labels[value.toLowerCase()] ?? readable(value);
}

export function mechanismLabel(value: string) {
  const labels: Record<string, string> = {
    "DDOS-A-B0": "SYN state pressure", "ddos.syn_state": "SYN state pressure",
    "DDOS-B-B0": "UDP demand", "ddos.udp_demand": "UDP demand",
    "DDOS-CV-B0": "Reflection-shaped traffic", "ddos.reflection_victim": "Reflection-shaped traffic",
    "DDOS-D-B0": "Source diversity evidence", "ddos.source_diversity": "Source diversity evidence",
    "DDOS-E1-B0": "ICMP demand", "ddos.icmp_demand": "ICMP demand",
    "DDOS-E2-B0": "Fragment demand", "ddos.fragment_demand": "Fragment demand",
    "DDOS-E3-B0": "TCP initiating activity", "ddos.connection_churn": "TCP initiating activity",
    "C2-M1": "Recurring communication pattern", "C2-A1-R1": "Recurring communication pattern", "c2.r1": "Recurring communication pattern", "c2.beacon": "Recurring communication pattern",
    "DGA-A1-M1": "DGA lexical evidence", "dga.m1": "DGA lexical evidence",
    "DNS-T1": "DNS name structure", "dns_tunnelling.t1": "DNS name structure",
    "ENC-A": "TLS handshake metadata", "ENC-A1": "TLS handshake metadata", "encrypted_session.enc_a": "TLS handshake metadata", "encrypted_session.a1": "TLS handshake metadata",
    "RECON-H": "Host discovery evidence", "recon.h": "Host discovery evidence", "RECON-V": "Service discovery evidence", "recon.v": "Service discovery evidence",
    "RECON-2D": "Host × service breadth", "recon.2d": "Host × service breadth",
    "RECON-TCP": "TCP initiating activity", "recon.tcp": "TCP initiating activity",
    "RECON-SCAN": "Host fan-out", "RECON-PROBE": "Host fan-out", "RECON-FANOUT": "Host fan-out", "RECON-SWEEP": "Host fan-out",
    "recon.scan": "Host fan-out", "recon.probe": "Host fan-out", "recon.fanout": "Host fan-out", "recon.sweep": "Host fan-out",
    "CAT6-EX-M1": "Directional transfer magnitude", "unusual_transfer.m1": "Directional transfer magnitude",
  };
  return labels[value] ?? "Evidence finding";
}

export function friendlyCategory(value: string) {
  const labels: Record<string, string> = {
    DOS: "DDoS evidence", DDOS: "DDoS evidence", C2: "C2 / beaconing evidence", DGA: "DGA evidence",
    BOTNET_C2_BEACONING: "C2 / beaconing evidence", C2_BEACONING: "C2 / beaconing evidence",
    DNS_TUNNELING: "DNS evidence", DNS_TUNNELLING: "DNS evidence",
    ENCRYPTED_SESSION: "Encrypted-session evidence", MALWARE_IN_ENCRYPTED_SESSION: "Encrypted-session evidence", RECONNAISSANCE: "Reconnaissance evidence",
    DATA_EXFILTRATION: "Data transfer", UNUSUAL_TRANSFER: "Data transfer",
    "DGA + DNS": "DGA + DNS", "DGA_+_DNS": "DGA + DNS", "C2_/_BEACONING": "C2 / Beaconing",
    ENCRYPTED_SESSIONS: "Encrypted Sessions", DATA_TRANSFER: "Data Transfer",
  };
  return labels[value.toUpperCase().replaceAll(" ", "_")] ?? threatClassLabel(value);
}

const evidenceNames: Record<string, string> = {
  bytes_c2s_per_second: "Client-to-server rate", bytes_s2c_per_second: "Server-to-client rate",
  unique_targets: "Distinct targets", unique_sources: "Distinct sources", unique_ports: "Distinct ports",
  recurrence_count: "Recurrence observations", recurrence_observations: "Recurrence observations",
  evidence_kind: "Evidence type", dga_labelled_lexical_resemblance_score: "DGA-labelled lexical resemblance score",
  packets_per_second: "Packet rate", syn_attempts: "SYN attempts", icmp_packets: "ICMP packets",
  apparent_source_cardinality_lower_bound: "Minimum apparent source count",
  packet_count: "Packets observed", byte_count: "Bytes observed",
  direction_scope: "Direction scope", documented_end_state: "Recorded end state",
  duration_seconds: "Measurement duration", domain: "Domain",
  observed_initiating_syn_count: "Observed initiating SYNs", observed_icmp_packet_count: "ICMP packets",
  observed_udp_packet_count: "UDP packets", observed_fragment_count: "Fragmented packets",
  domain_count: "Domains observed",
};
export function formatEvidenceValue(key: string, value: unknown) {
  if (/^(analytic_path|claim_ceiling|mechanism_id|lane_id|model_id|plugin_id|config_hash|source_observation_ids|capture_quality|attempt_capacity_reached|source_capacity_reached|exact_within_engineering_capacity|config_status|hard_negative_alternatives|source_visibility|missing_evidence|missing_prerequisites|missing_length_count|measured_length_count|measurement_is_lower_bound|observed_byte_count_for_length_available_packets)$/i.test(key)) return null;
  const label = evidenceNames[key] ?? readable(key);
  if (value === null || value === undefined) return null;
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    const friendlyValues: Record<string, string> = { DGA_LEXICAL_MODEL_EVIDENCE: "DGA lexical evidence", C2_COMMUNICATION_PATTERN_MEASUREMENT: "Recurring communication", RESPONSE_SHAPED_TRAFFIC: "Response-shaped traffic", CLIENT_TO_SERVER_ONLY: "Client to server only", EXPORTED: "Exported" };
    const shown = typeof value === "number" && /score|rate|per_second/i.test(key) ? Number(value).toFixed(3).replace(/0+$/, "").replace(/\.$/, "") : friendlyValues[String(value)] ?? String(value).replaceAll("_", " ").toLowerCase();
    return `${label}: ${shown}${key.endsWith("_per_second") ? " B/s" : ""}`;
  }
  return Array.isArray(value) ? `${label}: ${value.length} reported values` : `${label}: structured evidence reported`;
}

export function summarizeEvidence(evidence: Record<string, unknown>) {
  const rows = Object.entries(evidence).map(([key, value]) => formatEvidenceValue(key, value)).filter((v): v is string => Boolean(v));
  return rows.slice(0, 3).join(" · ") || "Evidence details available";
}
const primaryEvidenceKeys = new Set(["bytes_c2s_per_second", "bytes_s2c_per_second", "unique_targets", "unique_sources", "unique_ports", "recurrence_count", "recurrence_observations", "dga_labelled_lexical_resemblance_score", "packets_per_second", "syn_attempts", "icmp_packets", "apparent_source_cardinality_lower_bound", "packet_count", "byte_count", "observed_initiating_syn_count", "observed_icmp_packet_count", "observed_udp_packet_count", "observed_fragment_count", "direction_scope", "documented_end_state", "duration_seconds", "domain", "domain_count", "protocol"]);
export function whySurfaced(mechanismId: string, evidence: Record<string, unknown>) {
  const id = mechanismId.toLowerCase();
  if (id.includes("reflection_victim") || id.includes("ddos-cv") || evidence.evidence_kind === "RESPONSE_SHAPED_TRAFFIC") return "Response-shaped traffic was observed for this peer.";
  if (id.includes("source_diversity") || id.includes("ddos-d-b0")) {
    const count = evidence.apparent_source_cardinality_lower_bound ?? evidence.unique_sources;
    return typeof count === "number" ? `At least ${count} apparent source${count === 1 ? "" : "s"} ${count === 1 ? "was" : "were"} observed in the measurement window.` : "Apparent source distribution was measured for this peer.";
  }
  if (id.includes("connection_churn") || id.includes("ddos-e3-b0")) return "TCP initiating attempts were measured for this peer.";
  if (id.includes("syn_state") || id.includes("ddos-a-b0")) return "Captured TCP SYN and state evidence is available for this peer.";
  if (id.includes("udp_demand") || id.includes("ddos-b-b0")) return "UDP packet demand was measured for this peer.";
  if (id.includes("icmp_demand") || id.includes("ddos-e1-b0")) return "ICMP packet demand was measured for this peer.";
  if (id.includes("fragment_demand") || id.includes("ddos-e2-b0")) return "Fragmented packet demand was measured for this peer.";
  if (id.includes("unusual_transfer") || id.includes("cat6-ex-m1")) {
    const rate = evidence.bytes_c2s_per_second;
    if (typeof rate === "number") return `Client-to-server transfer was measured at ${Number(rate.toFixed(3))} B/s.`;
    return "Directional transfer magnitude was measured for this flow.";
  }
  if (id.includes("c2.") || id.includes("c2-m1") || id.includes("c2-a1")) return "Recurring communication was measured for this peer.";
  if (id.includes("dga") || id === "dga.m1") return "A domain’s lexical resemblance score was recorded for review.";
  if (id.includes("dns")) return "DNS name structure was measured for this domain.";
  if (id.includes("encrypted_session") || id.includes("enc-a")) return "TLS handshake metadata was recorded for this session.";
  if (id.includes("recon")) return `${mechanismLabel(mechanismId)} was measured for this source.`;
  return `${mechanismLabel(mechanismId)} evidence was recorded for review.`;
}

const handshakeFieldNames: Record<string, string> = {
  message_type: "Handshake message",
  sni: "Server name",
  ja4: "ClientHello fingerprint",
  alpn: "Application protocols",
  version: "TLS version",
  cipher_suite: "Cipher suite",
};
export function humanEvidenceRows(evidence: Record<string, unknown>): Array<[string, string]> {
  const rows: Array<[string, string]> = Object.entries(evidence)
    .filter(([key]) => primaryEvidenceKeys.has(key))
    .map(([key, value]) => {
      const formatted = formatEvidenceValue(key, value);
      if (!formatted) return null;
      const separator = formatted.indexOf(": ");
      return separator < 0 ? ["Observed evidence", formatted] as [string, string] : [formatted.slice(0, separator), formatted.slice(separator + 2)] as [string, string];
    })
    .filter((row): row is [string, string] => row !== null);
  const handshake = evidence.parsed_handshake_metadata;
  if (typeof handshake === "object" && handshake !== null && !Array.isArray(handshake)) {
    for (const [key, label] of Object.entries(handshakeFieldNames)) {
      const value = (handshake as Record<string, unknown>)[key];
      if (typeof value === "string" || typeof value === "number") rows.push([label, String(value)]);
      else if (Array.isArray(value) && value.every((item) => typeof item === "string")) rows.push([label, value.join(", ")]);
    }
  }
  const representation = objectValue(evidence.representation);
  const domain = stringValue(representation?.registrable_domain)
    ?? stringValue(representation?.qname_canonical)
    ?? stringValue(evidence.qname_canonical);
  if (domain && !rows.some(([label]) => label === "Domain")) {
    rows.unshift(["Domain", domain]);
  }
  if (evidence.tcp_reassembly_state === "COMPLETE_PREFIX") rows.push(["TCP reassembly", "Complete prefix observed"]);
  if (Array.isArray(evidence.gaps)) rows.push(["Reported capture gaps", evidence.gaps.length ? String(evidence.gaps.length) : "None"]);
  return rows.length || !Object.keys(evidence).length ? rows : [["Additional evidence", `${Object.keys(evidence).length} structured fields available`]];
}

const claimMeanings: Record<string, string> = {
  DNS_T1_STRUCTURAL_EVIDENCE_ONLY: "DNS query-name structure was measured for this domain.",
  OBSERVED_TCP_SYN_AND_CAPTURED_STATE_EVIDENCE_ONLY: "Observed TCP SYN activity and captured state are available as evidence.",
  NO_DDOS_CONFIRMED: "A DDoS attack is not confirmed.", NO_VICTIM_EXHAUSTION: "Victim resource exhaustion is not established.",
  NO_BACKLOG_EXHAUSTION: "Backlog exhaustion is not established.", NO_MALICIOUSNESS: "Malicious intent is not established.",
  NO_ATTACKER_IDENTITY: "Attacker identity is not established.", OBSERVED_UDP_DEMAND_ONLY: "Observed UDP demand is available as evidence.",
  NO_SERVICE_IMPACT: "Service impact is not established.", NO_COMPLETION_SEMANTICS: "Connection completion is not established.",
  RESPONSE_SHAPED_TRAFFIC_ONLY: "Response-shaped traffic was observed.", NO_AMPLIFICATION_RATIO: "An amplification ratio is not established.",
  NO_SPOOFING_CONFIRMED: "Source spoofing is not confirmed.", APPARENT_SOURCE_DISTRIBUTION_ONLY: "The apparent source distribution was observed.",
  NO_BOTNET_CONFIRMED: "A botnet is not confirmed.", NO_ATTRIBUTION: "Attribution is not established.",
  OBSERVED_ICMP_DEMAND_ONLY: "Observed ICMP demand is available as evidence.", OBSERVED_FRAGMENTED_PACKET_DEMAND_ONLY: "Observed fragmented-packet demand is available as evidence.",
  OBSERVED_TCP_INITIATING_ATTEMPT_MEASUREMENT_ONLY: "TCP initiating attempts were measured.", NO_RESOURCE_EXHAUSTION: "Resource exhaustion is not established.",
  NO_SCAN_CLASSIFICATION: "A scan classification is not established.", RECURRENT_COMMUNICATION_MEASUREMENT_ONLY: "Recurring communication was measured.",
  NOT_C2: "Command-and-control activity is not established.", NOT_MALWARE: "Malware is not established.",
  NO_MALWARE: "Malware is not established.",
  NO_C2: "Command-and-control activity is not established.",
  NOT_COMPROMISE: "Compromise is not established.", NOT_BENIGN: "Benign intent is not established.",
  DGA_LABELLED_LEXICAL_REVIEW_EVIDENCE_ONLY: "Lexical evidence is labelled for DGA review.", NO_MALWARE_CONFIRMATION: "Malware is not confirmed.",
  NO_INFECTION_INFERENCE: "Infection is not inferred.", NO_C2_INFERENCE: "Command-and-control activity is not inferred.",
  NO_DNS_TUNNEL_INFERENCE: "DNS tunnelling is not inferred.", NO_EXFILTRATION_INFERENCE: "Data exfiltration is not inferred.",
  NO_DOMAIN_OWNERSHIP_OR_INTENT: "Domain ownership or intent is not established.", OBSERVED_SCAN_ACTIVITY_EVIDENCE_ONLY: "Observed scan activity is available as evidence.",
  NO_AUTHORIZATION_INFERENCE: "Authorization is not inferred.", NO_COMPROMISE: "Compromise is not established.",
  VISIBLE_CLIENTHELLO_FINGERPRINT_CONTEXT_ONLY: "Visible ClientHello fingerprint context is available.",
  "PROHIBITS MALWARE_CONFIRMED, COMPROMISE, C2, EXFILTRATION, DECRYPTED_CONTENT": "The evidence does not establish malware, compromise, command-and-control, data exfiltration, or decrypted content.",
  TRANSFER_MAGNITUDE_ONLY: "Transfer magnitude is measured.", NO_UNUSUALNESS: "Unusualness is not established.",
  NO_DATA_SENSITIVITY: "Data sensitivity is not established.", NO_EXFILTRATION_CONFIRMED: "Exfiltration is not confirmed.", NO_THEFT: "Theft is not established.",
  RAW_OBSERVATION_ONLY: "Only the raw observation is available.", NO_DNS_TUNNEL_VERDICT: "A DNS tunnel verdict is not provided.", NO_EXFILTRATION: "Exfiltration is not established.", NO_SCIENTIFIC_CLAIMS: "No scientific claim is made.",
};
export function claimSemantics(raw: string) {
  const tokens = raw.split(";").map((token) => token.trim()).filter(Boolean);
  const known = tokens.map((token) => claimMeanings[token]).filter((value): value is string => Boolean(value));
  return { supports: known.slice(0, 1), limitations: known.slice(1), hasUnknown: tokens.length > known.length, raw };
}

export function prerequisiteLabel(value: string) {
  const labels: Record<string, string> = {
    reverse_tcp_state: "Reverse TCP state",
    REVERSE_TCP_STATE: "Reverse TCP state",
  };
  const c2History = value.match(/^(\d+) additional FLOW[_ ]START event\(s\)(?: was)? not available\.?$/i)
    ?? value.match(/^(\d+) additional FLOW_START event\(s\)$/i);
  if (c2History) {
    const count = Number(c2History[1]);
    return `Required recurrence history was unavailable (${count} additional connection-start ${count === 1 ? "observation" : "observations"}).`;
  }
  if (/\s/.test(value)) return value;
  return labels[value] ?? readable(value);
}

type EvidenceTableResult = Pick<ResultDto, "result_type" | "family" | "lane_id" | "mechanism_id" | "evidence" | "missing_prerequisites">;

export function resultEvidenceStateLabel(resultType: string) {
  const labels: Record<string, string> = {
    REVIEW_FINDING: "Review",
    INSUFFICIENT_EVIDENCE: "Insufficient evidence",
    QUALITY_DEGRADED: "Quality degraded",
    PREREQUISITE_MISSING: "Missing prerequisite",
    ANALYTIC_UNAVAILABLE: "Analytic unavailable",
    PLUGIN_STATUS: "Status",
  };
  return labels[resultType] ?? readable(resultType);
}

export function resultEvidenceStateTone(resultType: string) {
  const tones: Record<string, string> = {
    REVIEW_FINDING: "review",
    INSUFFICIENT_EVIDENCE: "insufficient",
    QUALITY_DEGRADED: "quality",
    PREREQUISITE_MISSING: "missing",
    ANALYTIC_UNAVAILABLE: "unavailable",
    PLUGIN_STATUS: "status",
  };
  return tones[resultType] ?? "status";
}

export function resultEvidenceSummary(result: EvidenceTableResult) {
  const evidence = result.evidence;
  const mechanism = `${result.mechanism_id ?? ""} ${result.lane_id}`.toLowerCase();
  const measurements = objectValue(evidence.measurements);

  if (mechanism.includes("dga")) {
    const score = evidence.dga_labelled_lexical_resemblance_score;
    if (typeof score === "number" && Number.isFinite(score)) return `Lexical resemblance score: ${formatNumber(score, 3)}`;
  }

  if (mechanism.includes("dns")) {
    const queryType = stringValue(evidence.qtype);
    const labels = finiteNumber(evidence.label_count);
    const facts = [queryType ? `${queryType.toUpperCase()} query` : null, labels === null ? null : `${labels} ${labels === 1 ? "label" : "labels"}`].filter((item): item is string => Boolean(item));
    if (facts.length) return facts.join(" · ");
    if (stringValue(evidence.qname_canonical) || stringValue(evidence.qname_rendered)) return "DNS name observed · structure measured";
  }

  if (mechanism.includes("c2")) {
    const observed = finiteNumber(evidence.observed_event_count) ?? finiteNumber(measurements?.event_count);
    const required = finiteNumber(evidence.required_event_count);
    if (result.result_type === "INSUFFICIENT_EVIDENCE" && observed !== null && required !== null) {
      return `${observed} / ${required} communication events observed`;
    }
    const history = finiteNumber(measurements?.history_span_seconds) ?? finiteNumber(evidence.history_span_seconds);
    if (observed !== null && history !== null) return `${observed} communication events observed · ${formatNumber(history, 1)} s history`;
    if (observed !== null && required !== null) return `${observed} / ${required} communication events observed`;
  }

  if (mechanism.includes("cat6") || mechanism.includes("unusual_transfer")) {
    const clientRate = finiteNumber(evidence.bytes_c2s_per_second);
    const serverRate = finiteNumber(evidence.bytes_s2c_per_second);
    if (clientRate !== null) return `Client→server rate: ${formatNumber(clientRate, 3)} B/s`;
    if (serverRate !== null) return `Server→client rate: ${formatNumber(serverRate, 3)} B/s`;
  }

  if (mechanism.includes("enc-a") || mechanism.includes("encrypted_session")) {
    const handshake = objectValue(evidence.parsed_handshake_metadata);
    const message = stringValue(handshake?.message_type);
    if (message) return `${stringValue(evidence.protocol)?.toUpperCase() ?? "TLS"} · ${message}`;
    if (stringValue(evidence.protocol)) return `${stringValue(evidence.protocol)!.toUpperCase()} handshake metadata observed`;
  }

  if (mechanism.includes("ddos")) {
    const sourceVisibility = objectValue(evidence.source_visibility);
    const reverseUnavailable = sourceVisibility?.REVERSE_FACTS === "UNAVAILABLE"
      || evidence.evidence_kind === "REVERSE_TCP_STATE_UNOBSERVABLE"
      || result.missing_prerequisites.some((item) => /reverse.*tcp.*state/i.test(item));
    const observedSyn = evidence.observed_syn === true || (finiteNumber(evidence.observed_initiating_syn_count) ?? 0) > 0;
    if (observedSyn && reverseUnavailable && result.result_type === "INSUFFICIENT_EVIDENCE") return "Forward initiation observed · reverse TCP evidence unavailable";
    if (observedSyn) return "Initiating SYN observed";
    const sources = finiteNumber(evidence.apparent_source_cardinality_lower_bound) ?? finiteNumber(evidence.unique_sources);
    if (sources !== null) return `${sources === 1 ? "One" : sources} apparent ${sources === 1 ? "source" : "sources"} observed`;
    const udp = finiteNumber(evidence.observed_udp_packet_count) ?? finiteNumber(evidence.udp_packets);
    if (udp !== null) return `${udp} UDP ${udp === 1 ? "packet" : "packets"} observed`;
    const packetsPerSecond = finiteNumber(evidence.packets_per_second);
    if (packetsPerSecond !== null) return `Observed demand: ${formatNumber(packetsPerSecond, 3)} packets/s`;
  }

  if (mechanism.includes("recon")) {
    const hosts = finiteNumber(measurements?.distinct_hosts) ?? finiteNumber(evidence.unique_targets);
    const ports = finiteNumber(measurements?.distinct_ports) ?? finiteNumber(evidence.unique_ports);
    if (hosts !== null && ports !== null) return `${hosts} ${hosts === 1 ? "host" : "hosts"} × ${ports} ${ports === 1 ? "port" : "ports"} observed`;
    if (hosts !== null) return `${hosts} ${hosts === 1 ? "host" : "hosts"} observed`;
    if (ports !== null) return `${ports} distinct ${ports === 1 ? "port" : "ports"} observed`;
    const attempts = finiteNumber(measurements?.attempt_count);
    if (attempts !== null) return `${attempts} scan ${attempts === 1 ? "attempt" : "attempts"} observed`;
  }

  return "Observed evidence available in detail";
}

export function resultCountLabel(count: number) {
  return `${count} ${count === 1 ? "Result" : "Results"}`;
}

function finiteNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function formatNumber(value: number, decimals: number) {
  return value.toFixed(decimals).replace(/(\.\d*?[1-9])0+$|\.0+$/, "$1");
}

type ResultContext = Pick<ResultDto, "family" | "lane_id" | "mechanism_id" | "entity_reference" | "evidence">;

/** Compact, threat-specific context built only from fields present in a Result. */
export function contextSummary(result: ResultContext): string {
  return summarizeAnalystContext(result.family, `${result.mechanism_id ?? ""} ${result.lane_id}`, result.entity_reference, result.evidence);
}

export function summarizeAnalystContext(family: string, mechanism: string, entityReference: string, evidence: Record<string, unknown>): string {
  const representation = objectValue(evidence.representation);
  const dgaDomain = stringValue(representation?.registrable_domain)
    ?? stringValue(representation?.qname_canonical)
    ?? stringValue(evidence.qname_canonical);
  const id = `${family} ${mechanism}`.toLowerCase();

  if (id.includes("dga")) return dgaDomain ?? "Domain unavailable";
  if (id.includes("dns")) return stringValue(evidence.qname_canonical)
    ?? stringValue(evidence.qname_rendered)
    ?? "Queried domain unavailable";
  if (id.includes("c2")) {
    const entity = objectValue(evidence.entity);
    const client = stringValue(entity?.client_ref);
    const peer = stringValue(entity?.peer_ref);
    const service = stringValue(entity?.service_ref);
    if (client && peer) return `${client} → ${peer}${service ? `:${service.replace(/^service\//i, "")}` : ""}`;
    const tuple = parsedArray(entityReference);
    if (tuple && typeof tuple[0] === "string" && typeof tuple[1] === "string") {
      const port = typeof tuple[2] === "string" || typeof tuple[2] === "number" ? `:${tuple[2]}` : "";
      return `${tuple[0]} → ${tuple[1]}${port}`;
    }
    return "Client → peer";
  }
  if (id.includes("ddos")) {
    const target = stringValue(evidence.target_ref);
    const service = serviceLabel(stringValue(evidence.service_ref));
    if (target) return `${target}${service ? ` · ${service}` : ""}`;
    const tuple = parsedArray(entityReference);
    if (tuple && typeof tuple[0] === "string") {
      const tupleService = typeof tuple[1] === "string" ? serviceLabel(tuple[1]) : null;
      return `${tuple[0]}${tupleService ? ` · ${tupleService}` : ""}`;
    }
    return "Target not available";
  }
  if (id.includes("recon")) {
    const scanner = stringValue(evidence.scanner_ref) ?? stringValue(evidence.source_ref)
      ?? stringValue(evidence.source);
    const target = stringValue(evidence.target_scope) ?? stringValue(evidence.target_ref);
    if (scanner && target) return `${scanner} → ${target}`;
    if (scanner) return `Scanner · ${scanner}`;
    if (target) return `Target scope · ${target}`;
    return "Observed scan scope";
  }
  if (id.includes("encrypted")) {
    const handshake = objectValue(evidence.parsed_handshake_metadata);
    const serverName = stringValue(handshake?.sni);
    return serverName ? `Session · ${serverName}` : "Encrypted session";
  }
  if (id.includes("transfer") || id.includes("unusual_transfer") || id.includes("cat6")) {
    const endpoints = evidence.endpoints_source_order;
    if (Array.isArray(endpoints) && typeof endpoints[0] === "string" && typeof endpoints[1] === "string") {
      return `${endpoints[0]} → ${endpoints[1]}`;
    }
    if (evidence.direction_scope === "CLIENT_TO_SERVER_ONLY") return "Client → server";
    if (evidence.direction_scope === "SERVER_TO_CLIENT_ONLY") return "Server → client";
    return "Transfer direction unavailable";
  }

  return /^(flow|dns):/i.test(entityReference) ? "Observed context" : summarizeReference(entityReference, mechanism);
}

function objectValue(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function parsedArray(value: string): unknown[] | null {
  try {
    const parsed: unknown = JSON.parse(value);
    return Array.isArray(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

function serviceLabel(value: string | null): string | null {
  if (!value) return null;
  return value.replace(/^service\//i, "").replaceAll("_", " ").toUpperCase();
}

export function pluralize(count: number, singular: string, plural = `${singular}s`) {
  const naturalPlural = plural === `${singular}s` && singular.endsWith("y")
    ? `${singular.slice(0, -1)}ies`
    : plural;
  return `${count} ${count === 1 ? singular : naturalPlural}`;
}

export type GroupedFamilyFinding = {
  title: string;
  findings: FamilyFindingDto[];
  sourceResultIds: string[];
};

/** Presentation grouping retains each underlying immutable Result reference. */
export function groupFamilyFindings(findings: FamilyFindingDto[]): GroupedFamilyFinding[] {
  const groups = new Map<string, GroupedFamilyFinding>();
  for (const finding of findings) {
    const title = finding.title.trim() || "Mechanism finding";
    const group = groups.get(title) ?? { title, findings: [], sourceResultIds: [] };
    group.findings.push(finding);
    group.sourceResultIds.push(finding.source_result_id);
    groups.set(title, group);
  }
  return [...groups.values()];
}

export type InvestigationNavigationGroup = {
  key: string;
  leftFamily: string;
  rightFamily: string;
  links: InvestigationLinkDto[];
  latestTime: string;
};

/** Group links for navigation while retaining the factual link records intact. */
export function groupInvestigationLinks(
  links: InvestigationLinkDto[],
  views: FamilyEvidenceViewDto[],
): InvestigationNavigationGroup[] {
  const byId = new Map(views.map((view) => [view.family_view_id, view]));
  const groups = new Map<string, InvestigationNavigationGroup>();
  for (const link of links) {
    const left = byId.get(link.left_family_view_id);
    const right = byId.get(link.right_family_view_id);
    if (!left || !right) continue;
    const orderedFamilies = [left.family, right.family].sort((a, b) => a.localeCompare(b));
    const leftFamily = orderedFamilies[0]!;
    const rightFamily = orderedFamilies[1]!;
    const key = `${leftFamily}\u0000${rightFamily}`;
    const group: InvestigationNavigationGroup = groups.get(key) ?? {
      key, leftFamily, rightFamily, links: [], latestTime: "",
    };
    group.links.push(link);
    const linkTime = [left.time_end, right.time_end].sort(compareTimeDesc)[0] ?? "";
    if (timestampMs(linkTime) > timestampMs(group.latestTime)) group.latestTime = linkTime;
    groups.set(key, group);
  }
  return [...groups.values()].sort((a, b) => compareTimeDesc(a.latestTime, b.latestTime));
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
