import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ResultDto, SihAlertProjection } from "../../api/types";
import {
  AlertInspector,
  AlertTable,
  ResultInspector,
  ResultTable,
} from "./Inspectors";

const quality = {
  packet_loss: "CLEAR",
  sampling: "CLEAR",
  parser: "CLEAR",
  capture_gap: "CLEAR",
} as const;
const visibility = { available: ["DNS"], unavailable: [], degraded: [] };
const alert: SihAlertProjection = {
  alert_id: "alert-1",
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
  confidence_statement: "Lexical model score",
  supporting_evidence: {
    structured: { dga_labelled_lexical_resemblance_score: 0.82 },
    evidence_items: [],
    source_observation_ids: ["obs-1"],
  },
  source_result_ids: ["result-1"],
  visibility,
  quality,
  claim_ceiling: "DGA_LABELLED_LEXICAL_REVIEW_EVIDENCE_ONLY",
  model_refs: [
    "model:DGA-A1-M1-R1",
    "sha256:39da209d2cfd869dd284e10b8a07adc04826c95146712cc6854a69b9873890df",
  ],
  governing_ids: [],
  provenance_refs: [],
  quality_refs: [],
  parser_refs: [],
};
const result: ResultDto = {
  result_id: "result-1",
  schema_version: "3",
  result_type: "REVIEW_FINDING",
  created_time: "2026-09-25T00:00:00Z",
  lane_id: "dns_tunnelling.t1",
  family: "DNS Tunnelling",
  plugin_id: "dns",
  plugin_version: "1",
  analytic_version: "1",
  governance_version: "1",
  entity_reference: "example.invalid",
  taxonomy: ["a", "b", "c"],
  mechanism_id: "DNS-T1",
  status_snapshot: {
    scientific_status: "EVIDENCE_CONSTRUCTION",
    integration_status: "BASELINE_IMPLEMENTED",
    governance_version: "1",
    readiness: "READY",
    quality_degraded: false,
  },
  claim_ceiling: "DNS_T1_STRUCTURAL_EVIDENCE_ONLY",
  evidence: { query_count: 4 },
  evidence_items: [],
  missing_prerequisites: [],
  source_observation_ids: ["obs-1"],
  source_ids: [],
  quality_snapshot: quality,
  visibility_snapshot: visibility,
  state_version: null,
  config_hash: null,
  parser_refs: [],
  model_refs: [],
  governing_ids: [],
  quality_refs: [],
  provenance_refs: [],
  evidence_interval: null,
  reason_code: null,
};

describe("evidence table and inspector components", () => {
  it("renders alert table rows and keyboard selection", () => {
    const select = vi.fn();
    render(<AlertTable alerts={[alert]} selectedId={null} onSelect={select} />);
    const row = screen.getByText("DGA-A1-M1").closest("tr");
    expect(row).toHaveAttribute("tabindex", "0");
    fireEvent.keyDown(row!, { key: "Enter" });
    expect(select).toHaveBeenCalledWith(alert);
  });
  it("keeps DGA score wording factual in the alert inspector", () => {
    render(
      <AlertInspector alert={alert} onClose={vi.fn()} onResult={vi.fn()} />,
    );
    expect(
      screen.getByText(/Not calibrated attack probability/),
    ).toBeInTheDocument();
    expect(screen.getByText(alert.claim_ceiling)).toBeInTheDocument();
  });
  it("renders results as scientific records and keeps non-DGA probability undefined", () => {
    render(
      <>
        <ResultTable results={[result]} selectedId={null} onSelect={vi.fn()} />
        <ResultInspector result={result} onClose={vi.fn()} />
      </>,
    );
    expect(screen.getByText("DNS Tunnelling")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Numeric attack probability is not defined by this analytic.",
      ),
    ).toBeInTheDocument();
  });
  it("closes an open inspector with Escape", () => {
    const close = vi.fn();
    render(<AlertInspector alert={alert} onClose={close} onResult={vi.fn()} />);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(close).toHaveBeenCalled();
  });
});
