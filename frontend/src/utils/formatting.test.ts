import { describe, expect, it } from "vitest";
import type { SihAlertProjection } from "../api/types";
import { claimSemantics, confidenceText, contextSummary, formatEvidenceValue, formatQuality, friendlyCategory, groupFamilyFindings, groupInvestigationLinks, humanEvidenceRows, observationLineageLabel, pluralize, primaryEntityLabel, summarizeEvidence, summarizeReference, summarizeTableEvidence, summarizeAnalystContext, threatClassLabel, familyLabel, mechanismLabel, shortId, whySurfaced } from "./formatting";
import { filterAlerts, filterResults } from "./filters";

const alert: SihAlertProjection = {
  alert_id: "a1",
  schema_version: "1",
  policy_version: "SIH_ALERT_POLICY_V1",
  timestamp: "2026-09-25T00:00:00Z",
  entity_or_flow_reference: "example.invalid",
  threat_class: "DGA",
  mechanism_id: "DGA-A1-M1",
  result_type: "REVIEW_FINDING",
  severity: "REVIEW",
  confidence_score: 0.82,
  confidence_basis: "MODEL_SCORE",
  confidence_statement: "DGA lexical score",
  supporting_evidence: {
    structured: {
      evidence_kind: "DGA_LEXICAL_MODEL_EVIDENCE",
      dga_labelled_lexical_resemblance_score: 0.82,
    },
    evidence_items: [],
    source_observation_ids: [],
  },
  source_result_ids: ["r1"],
  visibility: { available: ["DNS"], unavailable: [], degraded: [] },
  quality: {
    packet_loss: "CLEAR",
    sampling: "CLEAR",
    parser: "CLEAR",
    capture_gap: "CLEAR",
  },
  claim_ceiling: "DGA_LABELLED_LEXICAL_REVIEW_EVIDENCE_ONLY",
  model_refs: [],
  governing_ids: [],
  provenance_refs: [],
  quality_refs: [],
  parser_refs: [],
};

describe("scientific display helpers", () => {
  it("uses readable analyst labels for threat classes", () => {
    expect(threatClassLabel("DNS_TUNNELING")).toBe("DNS tunnelling");
    expect(threatClassLabel("DOS")).toBe("DDoS evidence");
    expect(threatClassLabel("RECONNAISSANCE")).toBe("Reconnaissance evidence");
  });
  it("labels DGA scores as lexical resemblance, never attack probability", () => {
    expect(confidenceText("MODEL_SCORE", 0.82)).toContain(
      "Not calibrated attack probability.",
    );
  });
  it("keeps non-DGA numeric probability undefined", () => {
    expect(
      confidenceText("OBSERVED_EVIDENCE", null),
    ).toContain("Numeric attack probability is not defined");
  });
  it("summarizes DGA lexical evidence without changing its claim", () => {
    expect(summarizeEvidence(alert.supporting_evidence.structured)).toContain(
      "0.82",
    );
  });
  it("shows structured entity references without JSON punctuation", () => {
    expect(summarizeReference('["192.0.2.10","service/https","FORWARD"]')).toBe(
      "192.0.2.10 · service/https · FORWARD",
    );
  });
  it("keeps the Analyst Queue primary entity compact", () => {
    expect(primaryEntityLabel('["10.0.1.10","service/dns-udp","FORWARD","2026-01-01T00:00:00+00:00",17]')).toBe("10.0.1.10");
  });
  it("formats capability families, mechanisms, and abbreviated result IDs", () => {
    expect(familyLabel("unusual_transfer")).toBe("Data transfer");
    expect(familyLabel("Data Exfiltration")).toBe("Data transfer");
    expect(friendlyCategory("BOTNET C2 BEACONING")).toBe("C2 / beaconing evidence");
    expect(friendlyCategory("MALWARE_IN_ENCRYPTED_SESSION")).toBe("Encrypted-session evidence");
    expect(mechanismLabel("DDOS-A-B0")).toBe("SYN state pressure");
    expect(shortId("2f6ba7c1-bbbb-4c4d-9a11-32a6326e326e")).toBe("2f6ba7…e326e");
  });
  it("falls back safely for nested or unknown entity structures", () => {
    expect(summarizeReference('{"flow":{"unexpected":true}}')).toBe("Structured reference · 1 fields");
    expect(summarizeReference('[{"unknown":true}]')).toBe("Structured value · 1 items");
    expect(summarizeReference("plain-entity")).toBe("plain-entity");
    expect(summarizeReference("flow:fixture-flow-transfer:1")).toBe("Flow fixture-flow-transfer:1");
    expect(observationLineageLabel(["obs-a", "obs-b", "obs-c"])).toBe("Evidence from 3 observations");
    expect(observationLineageLabel([])).toBeNull();
  });
  it("formats the verified DDOS-A state-key tuple as a TCP flow summary", () => {
    expect(summarizeReference('["192.0.2.10","service/https",6,[["192.0.2.10",443],["198.51.100.10",50000]]]', "DDOS-A-B0"))
      .toBe("Target 192.0.2.10 · service/https · TCP · 192.0.2.10:443 ↔ 198.51.100.10:50000");
    expect(summarizeReference('["192.0.2.10","service/https",6,[["192.0.2.10","bad"],["198.51.100.10",50000]]]', "DDOS-A-B0"))
      .toBe("Structured value · 4 items");
  });
  it("keeps primary evidence and why-surfaced copy concise and factual", () => {
    expect(summarizeReference('["192.0.2.10","service/https","FORWARD","2026-01-01T00:00:00Z"]'))
      .toBe("Target 192.0.2.10 · HTTPS");
    expect(whySurfaced("DDOS-D-B0", { apparent_source_cardinality_lower_bound: 1, attempt_capacity_reached: false }))
      .toBe("At least 1 apparent source was observed in the measurement window.");
    expect(whySurfaced("DDOS-E3-B0", { byte_count: 40, analytic_path: "DDOS-E3-B0" }))
      .toBe("TCP initiating attempts were measured for this peer.");
    expect(humanEvidenceRows({ byte_count: 40, analytic_path: "DDOS-E3-B0", capture_quality: { parser: "CLEAR" } }))
      .toEqual([["Bytes observed", "40"]]);
  });
  it("keeps claim ceiling text in inspectors instead of table summaries", () => {
    expect(summarizeTableEvidence({ claim_ceiling: "NO_MALICIOUSNESS", observed_count: 4 })).toBe("Observed count: 4");
  });
  it("formats evidence values with human labels and maps every frozen claim token", () => {
    expect(formatEvidenceValue("bytes_c2s_per_second", 409.6)).toBe("Client-to-server rate: 409.6 B/s");
    const claimValues = [
      "OBSERVED_TCP_SYN_AND_CAPTURED_STATE_EVIDENCE_ONLY;NO_DDOS_CONFIRMED;NO_VICTIM_EXHAUSTION;NO_BACKLOG_EXHAUSTION;NO_MALICIOUSNESS;NO_ATTACKER_IDENTITY",
      "OBSERVED_UDP_DEMAND_ONLY;NO_DDOS_CONFIRMED;NO_SERVICE_IMPACT;NO_COMPLETION_SEMANTICS;NO_MALICIOUSNESS",
      "RESPONSE_SHAPED_TRAFFIC_ONLY;NO_AMPLIFICATION_RATIO;NO_SPOOFING_CONFIRMED;NO_DDOS_CONFIRMED;NO_ATTACKER_IDENTITY",
      "APPARENT_SOURCE_DISTRIBUTION_ONLY;NO_SPOOFING_CONFIRMED;NO_BOTNET_CONFIRMED;NO_DDOS_CONFIRMED;NO_ATTRIBUTION",
      "OBSERVED_ICMP_DEMAND_ONLY;NO_DDOS_CONFIRMED;NO_SERVICE_IMPACT;NO_MALICIOUSNESS",
      "OBSERVED_FRAGMENTED_PACKET_DEMAND_ONLY;NO_DDOS_CONFIRMED;NO_SERVICE_IMPACT;NO_MALICIOUSNESS",
      "OBSERVED_TCP_INITIATING_ATTEMPT_MEASUREMENT_ONLY;NO_DDOS_CONFIRMED;NO_RESOURCE_EXHAUSTION;NO_SCAN_CLASSIFICATION;NO_MALICIOUSNESS",
      "RECURRENT_COMMUNICATION_MEASUREMENT_ONLY; NOT_C2; NOT_MALWARE; NOT_COMPROMISE; NOT_BENIGN",
      "DGA_LABELLED_LEXICAL_REVIEW_EVIDENCE_ONLY;NO_MALWARE_CONFIRMATION;NO_INFECTION_INFERENCE;NO_C2_INFERENCE;NO_DNS_TUNNEL_INFERENCE;NO_EXFILTRATION_INFERENCE;NO_DOMAIN_OWNERSHIP_OR_INTENT",
      "RAW_OBSERVATION_ONLY; NO_DNS_TUNNEL_VERDICT; NO_EXFILTRATION; NO_C2; NO_MALWARE",
      "VISIBLE_CLIENTHELLO_FINGERPRINT_CONTEXT_ONLY; PROHIBITS MALWARE_CONFIRMED, COMPROMISE, C2, EXFILTRATION, DECRYPTED_CONTENT",
      "OBSERVED_SCAN_ACTIVITY_EVIDENCE_ONLY;NO_MALICIOUSNESS;NO_AUTHORIZATION_INFERENCE;NO_ATTACKER_IDENTITY;NO_COMPROMISE",
      "TRANSFER_MAGNITUDE_ONLY; NO_UNUSUALNESS; NO_AUTHORIZATION_INFERENCE; NO_DATA_SENSITIVITY; NO_EXFILTRATION_CONFIRMED; NO_THEFT",
      "NO_SCIENTIFIC_CLAIMS",
    ];
    claimValues.forEach((value) => expect(claimSemantics(value).hasUnknown, value).toBe(false));
    expect(claimSemantics("UNKNOWN_TOKEN").hasUnknown).toBe(true);
  });
  it("surfaces factual TLS handshake fields and keeps representation metadata out of primary facts", () => {
    expect(humanEvidenceRows({
      protocol: "TLS",
      parsed_handshake_metadata: {
        message_type: "ClientHello",
        sni: "example.test",
        alpn: ["h2"],
      },
    })).toEqual([
      ["Protocol", "tls"],
      ["Handshake message", "ClientHello"],
      ["Server name", "example.test"],
      ["Application protocols", "h2"],
    ]);
    expect(humanEvidenceRows({
      dga_labelled_lexical_resemblance_score: 0.985,
      representation: { registrable_domain: "ajdkskqweoiuzx.com", m1_representation_version: "DGA_M1_REPRESENTATION_v1" },
    })).toEqual([["Domain", "ajdkskqweoiuzx.com"], ["DGA-labelled lexical resemblance score", "0.985"]]);
    expect(formatEvidenceValue("representation", { m1_representation_version: "DGA_M1_REPRESENTATION_v1" })).not.toContain("DGA_M1_REPRESENTATION_v1");
  });
  it("uses threat-specific context labels from observed fields only", () => {
    expect(summarizeAnalystContext("DGA", "dga.m1", "flow:opaque", { representation: { registrable_domain: "sample.test" } })).toBe("sample.test");
    expect(summarizeAnalystContext("DNS Tunnelling", "dns_tunnelling.t1", "dns:opaque", { qname_canonical: "query.test" })).toBe("query.test");
    expect(summarizeAnalystContext("C2", "c2.r1", "opaque", { entity: { client_ref: "10.0.0.1", peer_ref: "198.51.100.2", service_ref: "service/https" } })).toBe("10.0.0.1 → 198.51.100.2:https");
    expect(summarizeAnalystContext("DDoS", "ddos.syn_state", "[\"203.0.113.4\",\"service/https\"]", {})).toBe("203.0.113.4 · HTTPS");
    expect(summarizeAnalystContext("Encrypted sessions", "encrypted_session.enc_a", "flow:opaque", {})).toBe("Encrypted session");
    expect(summarizeAnalystContext("Data transfer", "unusual_transfer.m1", "flow:opaque", { direction_scope: "CLIENT_TO_SERVER_ONLY" })).toBe("Client → server");
    expect(contextSummary({ family: "Reconnaissance", mechanism_id: "recon.h", lane_id: "recon.h", entity_reference: "flow:opaque", evidence: { target_scope: "10.1.0.0/24" } })).toBe("Target scope · 10.1.0.0/24");
  });
  it("groups duplicate family findings for display while preserving every source Result ID", () => {
    const grouped = groupFamilyFindings([
      { source_result_id: "r1", title: "Recurring communication pattern", statements: [], result_type: "REVIEW_FINDING" },
      { source_result_id: "r2", title: "Recurring communication pattern", statements: [], result_type: "REVIEW_FINDING" },
      { source_result_id: "r3", title: "DNS name structure", statements: [], result_type: "REVIEW_FINDING" },
    ]);
    expect(grouped.map((group) => [group.title, group.findings.length, group.sourceResultIds])).toEqual([
      ["Recurring communication pattern", 2, ["r1", "r2"]], ["DNS name structure", 1, ["r3"]],
    ]);
  });
  it("groups investigation navigation by family pair without discarding link records", () => {
    const views = [
      { family_view_id: "a1", family: "C2", time_start: "2026-01-01", time_end: "2026-01-01" },
      { family_view_id: "b1", family: "Data transfer", time_start: "2026-01-01", time_end: "2026-01-01" },
      { family_view_id: "a2", family: "C2", time_start: "2026-01-02", time_end: "2026-01-02" },
      { family_view_id: "b2", family: "Data transfer", time_start: "2026-01-02", time_end: "2026-01-02" },
    ] as Parameters<typeof groupInvestigationLinks>[1];
    const links = [
      { link_id: "l1", left_family_view_id: "a1", right_family_view_id: "b1", relation_types: [], shared_source_observation_ids: ["o1"], source_result_ids: ["r1"], claim_guard: [] },
      { link_id: "l2", left_family_view_id: "a2", right_family_view_id: "b2", relation_types: [], shared_source_observation_ids: ["o2"], source_result_ids: ["r2"], claim_guard: [] },
    ];
    const grouped = groupInvestigationLinks(links, views);
    expect(grouped).toHaveLength(1);
    expect(grouped[0]?.links.map((link) => link.link_id)).toEqual(["l1", "l2"]);
  });
  it("uses singular and plural labels correctly", () => {
    expect(pluralize(1, "entity")).toBe("1 entity");
    expect(pluralize(2, "entity")).toBe("2 entities");
    expect(pluralize(2, "entity", "entities")).toBe("2 entities");
  });
  it("keeps quality independent and searchable by filters", () => {
    expect(formatQuality(alert.quality)).toBe("Clear");
    expect(
      filterAlerts([alert], {
        search: "example",
        threatClass: "",
        basis: "",
        quality: "Clear",
        visibility: "available",
      }),
    ).toHaveLength(1);
    expect(
      filterAlerts([alert], {
        search: "",
        threatClass: "",
        basis: "",
        quality: "Degraded",
        visibility: "",
      }),
    ).toHaveLength(0);
    const mixedQuality = {
      ...alert,
      quality: {
        packet_loss: "CLEAR",
        sampling: "DEGRADED",
        parser: "CLEAR",
        capture_gap: "CLEAR",
      },
    };
    expect(
      filterAlerts([mixedQuality], {
        search: "",
        threatClass: "",
        basis: "",
        quality: "Clear",
        visibility: "",
      }),
    ).toHaveLength(0);
    expect(
      filterAlerts([mixedQuality], {
        search: "",
        threatClass: "",
        basis: "",
        quality: "Degraded",
        visibility: "",
      }),
    ).toHaveLength(1);
  });
  it("filters result list by source fields", () => {
    const result = {
      result_id: "r1",
      family: "DGA + DNS",
      lane_id: "dga.m1",
      mechanism_id: "DGA-A1-M1",
      entity_reference: "example.invalid",
      evidence: {},
      result_type: "REVIEW_FINDING",
    } as Parameters<typeof filterResults>[0][number];
    expect(
      filterResults([result], {
        search: "example.invalid",
        family: "DGA + DNS",
        resultType: "REVIEW_FINDING",
      }),
    ).toHaveLength(1);
  });
});
