import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ResultDto, SihAlertProjection } from "../../api/types";
import {
  AlertInspector,
  AlertTable,
  ResultInspector,
  ResultTable,
} from "./Inspectors";

afterEach(cleanup);

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
  it("renders analyst-first alert columns and keyboard selection without mechanism IDs", () => {
    const select = vi.fn();
    render(<AlertTable alerts={[alert]} selectedId={null} onSelect={select} />);
    expect(screen.getByText("Summary")).toBeInTheDocument();
    expect(screen.queryByText("Mechanism")).not.toBeInTheDocument();
    const row = screen.getByText(/lexical resemblance score was recorded for review/).closest("tr");
    expect(row).toHaveAttribute("tabindex", "0");
    fireEvent.keyDown(row!, { key: "Enter" });
    expect(select).toHaveBeenCalledWith(alert);
  });
  it("keeps DGA score wording factual in the alert inspector", () => {
    render(
      <AlertInspector alert={alert} onClose={vi.fn()} onResult={vi.fn()} />,
    );
    expect(
      screen.getByText(/Not calibrated attack probability/i),
    ).toBeInTheDocument();
    expect(screen.getByText("Supported by this evidence")).toBeInTheDocument();
    expect(screen.getByText(alert.claim_ceiling).closest("details")).not.toHaveAttribute("open");
    expect(screen.getByText("SIH_ALERT_POLICY_V1").closest("details")).not.toHaveAttribute("open");
    fireEvent.click(screen.getByText("Technical details"));
    expect(screen.getByText(alert.claim_ceiling)).toBeInTheDocument();
    expect(screen.getByText("Mechanism ID")).toBeInTheDocument();
  });
  it("resets evidence modal scroll when the selected Result changes", () => {
    const { rerender } = render(<ResultInspector result={result} onClose={vi.fn()} />);
    const firstModal = screen.getByRole("dialog", { name: "Evidence record" });
    firstModal.scrollTop = 420;
    const next = { ...result, result_id: "result-2", lane_id: "dns_tunnelling.t2" };

    rerender(<ResultInspector result={next} onClose={vi.fn()} />);

    const nextModal = screen.getByRole("dialog", { name: "Evidence record" });
    expect(nextModal).not.toBe(firstModal);
    expect(nextModal.scrollTop).toBe(0);
  });
  it("renders results as scientific records and keeps non-DGA probability undefined", () => {
    const { container } = render(
      <>
        <ResultTable results={[result]} selectedId={null} onSelect={vi.fn()} />
        <ResultInspector result={result} onClose={vi.fn()} />
      </>,
    );
    expect(screen.getAllByText("DNS evidence").length).toBeGreaterThan(0);
    expect(screen.getAllByText("DNS name structure")).toHaveLength(2);
    expect(screen.queryByText(/attack probability/i)).not.toBeInTheDocument();
    expect(container.querySelector(".inspector-modal")).toBeInTheDocument();
    expect(container.querySelector("[aria-modal='true']")).toBeInTheDocument();
    expect(container.querySelector(".technical-details")).not.toHaveAttribute("open");
  });
  it("keeps DGA representation metadata collapsed and out of primary facts", () => {
    const dgaResult: ResultDto = {
      ...result,
      family: "DGA",
      lane_id: "dga.m1",
      mechanism_id: "DGA-A1-M1",
      entity_reference: "flow:internal-reference",
      evidence: {
        dga_labelled_lexical_resemblance_score: 0.985,
        representation: { registrable_domain: "ajdkskqweoiuzx.com", m1_representation_version: "DGA_M1_REPRESENTATION_v1" },
      },
      claim_ceiling: "DGA_LABELLED_LEXICAL_REVIEW_EVIDENCE_ONLY;NO_MALWARE_CONFIRMATION",
    };
    render(<ResultInspector result={dgaResult} onClose={vi.fn()} />);
    expect(screen.getByText("Domain").parentElement).toHaveTextContent("ajdkskqweoiuzx.com");
    expect(screen.getAllByText("DGA-labelled lexical resemblance score")[0]?.parentElement).toHaveTextContent("0.985");
    const technical = screen.getByText("Technical metadata").closest("details");
    expect(technical).not.toHaveAttribute("open");
    expect(screen.getByText("DGA_M1_REPRESENTATION_v1").closest("details")).toBe(technical);
    fireEvent.click(screen.getByText("Technical metadata"));
    expect(screen.getByText("DGA_M1_REPRESENTATION_v1")).toBeInTheDocument();
  });
  it("closes an open inspector with Escape", () => {
    const close = vi.fn();
    render(<AlertInspector alert={alert} onClose={close} onResult={vi.fn()} />);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(close).toHaveBeenCalled();
  });
});
