import { describe, expect, it } from "vitest";
import type { ObservationPresentationDto, ResultDto } from "../api/types";
import { reconPresentation } from "./reconPresentation";

const result = {
  lane_id: "recon.2d",
  source_observation_ids: ["obs-1", "obs-2"],
  evidence: { measurements: { distinct_hosts: 2, distinct_ports: 2, distinct_host_port_pairs: 2, attempt_count: 3, horizon_seconds: 60 } },
} as unknown as ResultDto;
function observation(id: string, address: string, port: number, service: string, serviceBasis: string): ObservationPresentationDto {
  return {
    observation_id: id, observation_type: "PACKET", event_time: "2026-09-27T05:30:00Z", source_position: "1",
    wire_direction: "FORWARD", direction_basis: "CAPTURE_INTERFACE", finality: "CURRENT", availability_basis: "SOURCE_DECLARED",
    present_fields: [], visibility: { available: ["PACKET_FACTS"], unavailable: [], degraded: [] },
    quality: { packet_loss: "CLEAR", sampling: "CLEAR", parser: "CLEAR", capture_gap: "CLEAR" },
    identity: { observed_identifiers: [], identifier_basis: "DECLARED", role_assignments: [
      { identifier: "198.51.100.14", role: "initiator_id", basis: "SOURCE_DECLARED_ROLE" },
      { identifier: address, role: "target_id", basis: "SOURCE_DECLARED_ROLE" },
      { identifier: `service/${service}`, role: "service_id", basis: serviceBasis },
    ] },
    facts: { source_address: "198.51.100.14", destination_address: address, destination_port: port, protocol_number: 6 },
  };
}

describe("source-linked Recon presentation", () => {
  it("shows durable measurements and only target/port facts in contributing observations", () => {
    const view = reconPresentation(result, [
      observation("obs-1", "192.0.2.10", 443, "https", "POLICY_DECLARED_ROLE"),
      observation("obs-2", "192.0.2.12", 8443, "tcp-8443", "POLICY_DECLARED_ROLE"),
    ])!;
    expect(view.source).toBe("198.51.100.14");
    expect(view.measurements).toEqual(expect.arrayContaining([["Destination hosts", "2"], ["Destination ports/services", "2"], ["Host × service pairs", "2"], ["Initiating attempts", "3"]]));
    expect(view.targets).toEqual(expect.arrayContaining([
      expect.objectContaining({ target: "192.0.2.10", port: "443", transport: "TCP", service: "HTTPS", basis: "Configured service role" }),
      expect.objectContaining({ target: "192.0.2.12", port: "8443", transport: "TCP", service: "Not identified" }),
    ]));
    expect(view.detailsUnavailable).toBe(false);
  });
  it("does not fabricate a target list when active source observations are absent", () => {
    const view = reconPresentation(result, [])!;
    expect(view.targets).toEqual([]);
    expect(view.detailsUnavailable).toBe(true);
  });
  it("does not add Recon presentation to non-Recon Results", () => {
    expect(reconPresentation({ ...result, lane_id: "ddos.syn_state" }, [])).toBeNull();
  });
});
