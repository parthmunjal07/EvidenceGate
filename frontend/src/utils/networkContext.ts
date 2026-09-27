export type ServiceRole = { identifier: string; basis: string } | null | undefined;

export function transportLabel(value: unknown): string {
  if (value === 6 || value === "6") return "TCP";
  if (value === 17 || value === "17") return "UDP";
  if (value === 1 || value === "1") return "ICMP";
  if (typeof value === "string" && /^(tcp|udp|icmp|quic|tls)$/i.test(value)) return value.toUpperCase();
  return typeof value === "number" || (typeof value === "string" && /^\d+$/.test(value)) ? `IP protocol ${value}` : "Not reported";
}

export function formatEndpoint(address: unknown, port: unknown): string | null {
  if (address === null || address === undefined || String(address).trim() === "") return null;
  return `${String(address)}${port === null || port === undefined || port === "" ? "" : `:${String(port)}`}`;
}

export function formatEndpointPair(facts: Record<string, unknown>): string | null {
  const source = formatEndpoint(facts.source_address, facts.source_port);
  const destination = formatEndpoint(facts.destination_address, facts.destination_port);
  if (source && destination) return `${source} → ${destination}`;
  if (facts.endpoint_a || facts.endpoint_b) return `${String(facts.endpoint_a ?? "Endpoint A")} ↔ ${String(facts.endpoint_b ?? "Endpoint B")}`;
  return null;
}

export function formatTcpBehavior(facts: Record<string, unknown>): string | null {
  const state = typeof facts.tcp_state === "string" && facts.tcp_state.trim().length > 0
    ? facts.tcp_state.trim().toUpperCase()
    : null;
  const rawFlags = Array.isArray(facts.flags) ? facts.flags : facts.tcp_flags;
  const flags = Array.isArray(rawFlags)
    ? rawFlags.filter((flag): flag is string => typeof flag === "string" && flag.trim().length > 0).map((flag) => flag.trim().toUpperCase())
    : [];
  const parts = [state ? `State: ${state}` : null, flags.length ? `Flags: ${[...new Set(flags)].join(", ")}` : null].filter((part): part is string => Boolean(part));
  return parts.length ? parts.join(" · ") : null;
}

export function presentService(role?: ServiceRole, port?: unknown): { label: string; basis: string } {
  const label = role?.identifier.replace(/^service\//i, "").trim() ?? "";
  const basis = role?.basis ?? "";
  const genericPortToken = /^(tcp|udp|icmp)[-_]?\d+$/i.test(label);
  const recognizedBasis: Record<string, string> = {
    SOURCE_DECLARED_ROLE: "Source-declared service role",
    POLICY_DECLARED_ROLE: "Configured service role",
  };
  if (label && !genericPortToken && recognizedBasis[basis]) {
    return { label: label.toUpperCase(), basis: recognizedBasis[basis] };
  }
  return { label: "Not identified", basis: port === undefined || port === null ? "No explicit service metadata" : "Port observed; service was not identified" };
}
