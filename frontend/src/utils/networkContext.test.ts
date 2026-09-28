import { describe, expect, it } from "vitest";
import {
  formatEndpoint,
  formatEndpointPair,
  formatTcpBehavior,
  presentService,
  transportLabel,
} from "./networkContext";

describe("network context presentation", () => {
  it.each([
    [6, "TCP"],
    [17, "UDP"],
    [1, "ICMP"],
  ])("formats protocol %s as %s", (number, label) => {
    expect(transportLabel(number)).toBe(label);
  });
  it("keeps endpoint ports visible", () => {
    expect(formatEndpoint("192.0.2.10", 8443)).toBe("192.0.2.10:8443");
    expect(
      formatEndpointPair({
        source_address: "198.51.100.14",
        source_port: 50122,
        destination_address: "192.0.2.10",
        destination_port: 8443,
      }),
    ).toBe("198.51.100.14:50122 → 192.0.2.10:8443");
  });
  it("shows observed TCP state and flags when source facts retain them", () => {
    expect(
      formatTcpBehavior({
        tcp_state: "syn_sent",
        flags: ["SYN", "ACK", "SYN"],
      }),
    ).toBe("State: SYN_SENT · Flags: SYN, ACK");
    expect(formatTcpBehavior({})).toBeNull();
  });
  it("shows a service only with a known role basis", () => {
    expect(
      presentService(
        { identifier: "service/https", basis: "SOURCE_DECLARED_ROLE" },
        443,
      ),
    ).toEqual({ label: "HTTPS", basis: "Source-declared service role" });
    expect(
      presentService({ identifier: "service/smtp", basis: "UNKNOWN" }, 2525),
    ).toEqual({
      label: "Not identified",
      basis: "Port observed; service was not identified",
    });
    expect(
      presentService(
        { identifier: "service/tcp-8443", basis: "SOURCE_DECLARED_ROLE" },
        8443,
      ).label,
    ).toBe("Not identified");
  });
});
