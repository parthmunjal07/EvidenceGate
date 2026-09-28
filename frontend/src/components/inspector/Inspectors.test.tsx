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
    const row = screen
      .getByText(/lexical resemblance score was recorded for review/)
      .closest("tr");
    expect(row).toHaveAttribute("tabindex", "0");
    fireEvent.keyDown(row!, { key: "Enter" });
    expect(select).toHaveBeenCalledWith(alert);
  });
  it("renders the six-column Result table with split timestamps and keyboard row selection", () => {
    const select = vi.fn();
    render(
      <ResultTable results={[result]} selectedId={null} onSelect={select} />,
    );
    expect(
      screen.getByRole("columnheader", { name: /Result time/ }),
    ).toHaveTextContent(/UTC|Local|IST|GMT/);
    expect(screen.getAllByRole("columnheader")).toHaveLength(6);
    expect(screen.getByText("DNS tunnelling")).toBeInTheDocument();
    expect(screen.getByText("Review")).toBeInTheDocument();
    const time = screen.getByText("05:30:00").closest("time");
    expect(time).toHaveAttribute(
      "title",
      expect.stringContaining("Observed / Result time:"),
    );
    const row = screen.getByText("DNS name structure").closest("tr");
    expect(row).toHaveAttribute("tabindex", "0");
    fireEvent.keyDown(row!, { key: " " });
    expect(select).toHaveBeenCalledWith(result);
  });
  it("keeps DGA score wording factual in the alert inspector", () => {
    render(
      <AlertInspector alert={alert} onClose={vi.fn()} onResult={vi.fn()} />,
    );
    expect(
      screen.getByText(/Not calibrated attack probability/i),
    ).toBeInTheDocument();
    expect(screen.getByText("Supported by this evidence")).toBeInTheDocument();
    expect(screen.queryByText("Developer details")).not.toBeInTheDocument();
    expect(screen.queryByText("Mechanism ID")).not.toBeInTheDocument();
  });
  it("normalizes numeric protocol evidence to its transport name", () => {
    const ddosResult: ResultDto = {
      ...result,
      lane_id: "ddos.syn_state",
      family: "DDoS",
      mechanism_id: "DDOS-SYN-STATE",
      evidence: { protocol: 6 },
    };
    render(<ResultInspector result={ddosResult} onClose={vi.fn()} />);
    expect(screen.getByText("Transport").parentElement).toHaveTextContent(
      "TCP",
    );
    expect(screen.queryByText("Protocol 6")).not.toBeInTheDocument();
  });
  it("renders durable C2 client, peer, transport, event count and history span", () => {
    const c2Result: ResultDto = {
      ...result,
      lane_id: "c2.r1",
      family: "C2 / Beaconing",
      mechanism_id: "C2-M1",
      evidence: {
        entity: {
          client_ref: "client-a",
          peer_ref: "198.51.100.44",
          service_ref: "443",
          protocol: 6,
        },
        measurements: { event_count: 5, history_span_seconds: 249 },
      },
    };
    render(<ResultInspector result={c2Result} onClose={vi.fn()} />);
    expect(screen.getByText("client-a")).toBeInTheDocument();
    expect(screen.getByText("198.51.100.44:443")).toBeInTheDocument();
    expect(screen.getByText("Peer port").parentElement).toHaveTextContent(
      "443",
    );
    expect(screen.getByText("Transport").parentElement).toHaveTextContent(
      "TCP",
    );
    expect(
      screen.getByText("Communication events").parentElement,
    ).toHaveTextContent("5");
    expect(
      screen.getByText("Observed history span").parentElement,
    ).toHaveTextContent("249 s");
  });
  it("resets evidence modal scroll when the selected Result changes", () => {
    const { rerender } = render(
      <ResultInspector result={result} onClose={vi.fn()} />,
    );
    const firstModal = screen.getByRole("dialog", { name: "Evidence record" });
    firstModal.scrollTop = 420;
    const next = {
      ...result,
      result_id: "result-2",
      lane_id: "dns_tunnelling.t2",
    };

    rerender(<ResultInspector result={next} onClose={vi.fn()} />);

    const nextModal = screen.getByRole("dialog", { name: "Evidence record" });
    expect(nextModal).not.toBe(firstModal);
    expect(nextModal.scrollTop).toBe(0);
  });
  it("presents source lineage as an observation count and opens cached source context", () => {
    const openSource = vi.fn();
    const sourceObservation = {
      observation_id: "obs-1",
      observation_type: "PACKET",
      event_time: "2026-09-25T00:00:00Z",
      source_position: "1",
      wire_direction: "FORWARD",
      direction_basis: "CAPTURE_INTERFACE",
      finality: "CURRENT",
      availability_basis: "SOURCE_DECLARED",
      present_fields: [],
      identity: {
        observed_identifiers: [],
        identifier_basis: "DECLARED",
        role_assignments: [],
      },
      visibility,
      quality,
      facts: {
        source_address: "198.51.100.1",
        destination_address: "192.0.2.1",
        protocol_number: 6,
      },
    };
    render(
      <ResultInspector
        result={result}
        onClose={vi.fn()}
        availableSourceCount={1}
        sourceObservations={[sourceObservation]}
        onOpenSource={openSource}
      />,
    );
    expect(
      screen.getByText("1 network observation contributed"),
    ).toBeInTheDocument();
    expect(screen.queryByText("obs-1")).not.toBeInTheDocument();
    fireEvent.click(
      screen.getByText(/review 1 contributing source observation/i),
    );
    fireEvent.click(
      screen.getByRole("button", { name: /open observation 1/i }),
    );
    expect(openSource).toHaveBeenCalledWith(0);
  });
  it("keeps observed TCP flags and source-level visibility and quality in the Result context", () => {
    const sourceObservation = {
      observation_id: "obs-1",
      observation_type: "PACKET",
      event_time: "2026-09-25T00:00:00Z",
      source_position: "1",
      wire_direction: "FORWARD",
      direction_basis: "CAPTURE_INTERFACE",
      finality: "CURRENT",
      availability_basis: "SOURCE_DECLARED",
      present_fields: [],
      identity: {
        observed_identifiers: [],
        identifier_basis: "DECLARED",
        role_assignments: [],
      },
      visibility: {
        available: ["FORWARD_FACTS", "PACKET_HEADERS"],
        unavailable: ["REVERSE_TCP_STATE"],
        degraded: [],
      },
      quality,
      facts: {
        source_address: "198.51.100.1",
        source_port: 50122,
        destination_address: "192.0.2.1",
        destination_port: 8443,
        protocol_number: 6,
        flags: ["SYN"],
        tcp_state: "syn_sent",
      },
    };
    const tcpResult = {
      ...result,
      lane_id: "ddos.syn_state",
      mechanism_id: "DDOS-SYN-STATE",
      family: "DDoS",
      evidence: { initiating_syn_count: 1 },
      source_observation_ids: ["obs-1"],
    };
    render(
      <ResultInspector
        result={tcpResult}
        onClose={vi.fn()}
        availableSourceCount={1}
        sourceObservations={[sourceObservation]}
        onOpenSource={vi.fn()}
      />,
    );
    expect(
      screen.getAllByText("198.51.100.1:50122 → 192.0.2.1:8443"),
    ).toHaveLength(2);
    expect(screen.getByText(/Flags: SYN/)).toBeInTheDocument();
    fireEvent.click(screen.getByText("Sensor visibility and capture quality"));
    expect(screen.getByText("Forward facts available")).toBeInTheDocument();
    expect(screen.getByText("Packet headers available")).toBeInTheDocument();
    expect(
      screen.getByText("Reverse TCP state unavailable"),
    ).toBeInTheDocument();
    expect(screen.getByText("Sampling").parentElement).toHaveTextContent(
      "Clear",
    );
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
    expect(document.body.querySelector(".inspector-modal")).toBeInTheDocument();
    expect(
      document.body.querySelector("[aria-modal='true']"),
    ).toBeInTheDocument();
    expect(document.body.querySelector(".inspector-layer")).toBeInTheDocument();
    expect(document.body).toHaveClass("inspector-open");
    expect(container.querySelector(".technical-details")).toBeNull();
  });
  it("keeps DGA representation metadata and source IDs out of the analyst modal", () => {
    const dgaResult: ResultDto = {
      ...result,
      family: "DGA",
      lane_id: "dga.m1",
      mechanism_id: "DGA-A1-M1",
      entity_reference: "flow:internal-reference",
      evidence: {
        dga_labelled_lexical_resemblance_score: 0.985,
        representation: {
          registrable_domain: "ajdkskqweoiuzx.com",
          m1_representation_version: "DGA_M1_REPRESENTATION_v1",
        },
      },
      claim_ceiling:
        "DGA_LABELLED_LEXICAL_REVIEW_EVIDENCE_ONLY;NO_MALWARE_CONFIRMATION",
    };
    render(<ResultInspector result={dgaResult} onClose={vi.fn()} />);
    expect(screen.getByText("Queried domain").parentElement).toHaveTextContent(
      "ajdkskqweoiuzx.com",
    );
    expect(
      screen.getAllByText("DGA-labelled lexical resemblance score")[0]
        ?.parentElement,
    ).toHaveTextContent("0.985");
    expect(
      screen.queryByText("DGA_M1_REPRESENTATION_v1"),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("Audit details")).not.toBeInTheDocument();
    expect(screen.queryByText("result-1")).not.toBeInTheDocument();
    expect(
      screen.getByText("1 network observation contributed"),
    ).toBeInTheDocument();
  });
  it("shows threat-specific alternatives and navigable analyst next actions", () => {
    const openFamily = vi.fn();
    const openInvestigation = vi.fn();
    const resultWithAlternatives = {
      ...result,
      evidence: {
        ...result.evidence,
        hard_negative_alternatives: [
          "authorized vulnerability scanning",
          "asset inventory",
        ],
      },
    };
    render(
      <ResultInspector
        result={resultWithAlternatives}
        onClose={vi.fn()}
        onOpenFamily={openFamily}
        onOpenInvestigation={openInvestigation}
      />,
    );
    expect(screen.getByText("What else could explain it?")).toBeInTheDocument();
    expect(
      screen.getByText("Authorized vulnerability scanning"),
    ).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: /open dns family evidence/i }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: /open related investigations/i }),
    );
    expect(openFamily).toHaveBeenCalledOnce();
    expect(openInvestigation).toHaveBeenCalledOnce();
  });
  it("connects measured Recon breadth to exact target and service facts from source observations", () => {
    const reconResult: ResultDto = {
      ...result,
      family: "Recon",
      lane_id: "recon.2d",
      mechanism_id: "RECON-2D",
      taxonomy: ["Network", "Recon", "Host Port Geometry"],
      evidence: {
        measurements: {
          distinct_hosts: 2,
          distinct_ports: 2,
          distinct_host_port_pairs: 2,
          attempt_count: 3,
          horizon_seconds: 3600,
        },
        hard_negative_alternatives: ["authorized vulnerability scanning"],
      },
      source_observation_ids: ["obs-1", "obs-2"],
      evidence_interval: ["2026-09-25T00:00:00Z", "2026-09-25T00:00:10Z"],
    };
    const observation = (
      id: string,
      destination: string,
      port: number,
      service: string,
    ) => ({
      observation_id: id,
      observation_type: "PACKET",
      event_time: "2026-09-25T00:00:00Z",
      source_position: "1",
      wire_direction: "FORWARD",
      direction_basis: "CAPTURE_INTERFACE",
      finality: "CURRENT",
      availability_basis: "SOURCE_DECLARED",
      present_fields: [],
      identity: {
        observed_identifiers: [],
        identifier_basis: "DECLARED",
        role_assignments: [
          {
            identifier: "198.51.100.14",
            role: "initiator_id",
            basis: "SOURCE_DECLARED_ROLE",
          },
          {
            identifier: destination,
            role: "target_id",
            basis: "SOURCE_DECLARED_ROLE",
          },
          {
            identifier: `service/${service}`,
            role: "service_id",
            basis: "POLICY_DECLARED_ROLE",
          },
        ],
      },
      visibility,
      quality,
      facts: {
        source_address: "198.51.100.14",
        destination_address: destination,
        destination_port: port,
        protocol_number: 6,
      },
    });
    render(
      <ResultInspector
        result={reconResult}
        onClose={vi.fn()}
        sourceObservations={[
          observation("obs-1", "192.0.2.10", 443, "https"),
          observation("obs-2", "192.0.2.12", 8443, "tcp-8443"),
        ]}
        availableSourceCount={2}
        onOpenSource={vi.fn()}
      />,
    );
    expect(screen.getByText("198.51.100.14")).toBeInTheDocument();
    expect(
      screen.getByText("Destination hosts").parentElement,
    ).toHaveTextContent("2");
    expect(
      screen.getByText("Host × service pairs").parentElement,
    ).toHaveTextContent("2");
    expect(screen.getByText("192.0.2.10:443").parentElement).toHaveTextContent(
      "HTTPS",
    );
    expect(screen.getByText("192.0.2.12:8443").parentElement).toHaveTextContent(
      "Not identified",
    );
    expect(screen.getByText("192.0.2.10:443").parentElement).toHaveTextContent(
      "Configured service role",
    );
    expect(screen.queryByText("obs-1")).not.toBeInTheDocument();
  });
  it("closes an open inspector with Escape", () => {
    const close = vi.fn();
    render(<AlertInspector alert={alert} onClose={close} onResult={vi.fn()} />);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(close).toHaveBeenCalled();
  });
});
