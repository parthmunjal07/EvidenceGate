import { describe, expect, it } from "vitest";
import type { SihAlertProjection } from "../api/types";
import { confidenceText, formatQuality, summarizeEvidence } from "./formatting";
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
  it("labels DGA scores as lexical resemblance, never attack probability", () => {
    expect(confidenceText("MODEL_SCORE", 0.82, "ignored")).toContain(
      "Not calibrated attack probability.",
    );
  });
  it("keeps non-DGA numeric probability undefined", () => {
    expect(
      confidenceText("OBSERVED_EVIDENCE", null, "visible handshake evidence"),
    ).toContain("Numeric attack probability is not defined");
  });
  it("summarizes DGA lexical evidence without changing its claim", () => {
    expect(summarizeEvidence(alert.supporting_evidence.structured)).toContain(
      "0.820",
    );
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
      family: "DGA",
      lane_id: "dga.m1",
      mechanism_id: "DGA-A1-M1",
      entity_reference: "example.invalid",
      evidence: {},
      result_type: "REVIEW_FINDING",
    } as Parameters<typeof filterResults>[0][number];
    expect(
      filterResults([result], {
        search: "dga-a1",
        family: "DGA",
        resultType: "REVIEW_FINDING",
      }),
    ).toHaveLength(1);
  });
});
