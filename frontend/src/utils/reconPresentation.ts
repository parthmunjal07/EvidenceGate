import type { ObservationPresentationDto, ResultDto } from "../api/types";
import { presentService, transportLabel } from "./networkContext";

export type ReconTarget = {
  target: string;
  port: string;
  transport: string;
  service: string;
  basis: string;
};
export type ReconPresentation = {
  source: string | null;
  measurements: Array<[string, string]>;
  targets: ReconTarget[];
  detailsUnavailable: boolean;
};

export function reconPresentation(
  result: ResultDto,
  observations: ObservationPresentationDto[],
): ReconPresentation | null {
  if (!result.lane_id.startsWith("recon.")) return null;
  const measurements = record(result.evidence.measurements);
  const values: Array<[string, string]> = [];
  const number = (key: string, label: string, suffix = "") => {
    const value = measurements?.[key];
    if (typeof value === "number" && Number.isFinite(value))
      values.push([label, `${value}${suffix}`]);
  };
  number("distinct_hosts", "Destination hosts");
  number("distinct_ports", "Destination ports/services");
  number("distinct_host_port_pairs", "Host × service pairs");
  number("attempt_count", "Initiating attempts");
  number("horizon_seconds", "Measurement horizon", " s");
  const sources = new Set<string>();
  const targetMap = new Map<string, ReconTarget>();
  for (const observation of observations) {
    const facts = observation.facts;
    const roles = observation.identity.role_assignments;
    const role = (...names: string[]) =>
      roles.find((item) => names.includes(item.role));
    const source =
      role("initiator_id", "source_id")?.identifier ??
      stringFact(facts.source_address);
    if (source) sources.add(source);
    const targetRole = role("target_id");
    const target =
      targetRole?.identifier ?? stringFact(facts.destination_address);
    if (!target) continue;
    const port = facts.target_port ?? facts.destination_port;
    const serviceRole = role("service_id");
    const service = presentService(serviceRole, port);
    const transport = transportLabel(
      facts.protocol_number ?? facts.protocol ?? facts.transport,
    );
    const portText =
      port === undefined || port === null ? "Port not reported" : String(port);
    const row: ReconTarget = {
      target,
      port: portText,
      transport,
      service: service.label,
      basis: service.basis,
    };
    targetMap.set(
      `${target}\u0000${portText}\u0000${transport}\u0000${service.label}`,
      row,
    );
  }
  return {
    source:
      sources.size === 1
        ? ([...sources][0] ?? null)
        : sources.size > 1
          ? `${sources.size} observed sources`
          : null,
    measurements: values,
    targets: [...targetMap.values()].sort(
      (a, b) =>
        a.target.localeCompare(b.target) || a.port.localeCompare(b.port),
    ),
    detailsUnavailable:
      observations.length === 0 && result.source_observation_ids.length > 0,
  };
}

function record(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}
function stringFact(value: unknown): string | null {
  return typeof value === "string" && value ? value : null;
}
