import { useEffect, useMemo, useState } from "react";
import type { ObservationPresentationDto, ResultDto, RuntimeTraceEvent } from "../../api/types";
import { formatEvidenceClockTime, mechanismLabel, pluralize, readable } from "../../utils/formatting";
import type { DisplayTimeZone } from "../../utils/formatting";
import type { NavigationContext } from "../../state/navigation";
import type { PageKey } from "../../state/types";
import { projectResultExplanation } from "../../utils/resultExplanation";

type Row = { observation: ObservationPresentationDto; source: RuntimeTraceEvent["source_record"] };

export function ObservationWorkbench({ observation, source, routes, results, eventTimeZone }: {
  observation: ObservationPresentationDto | null;
  source: RuntimeTraceEvent["source_record"];
  routes: RuntimeTraceEvent[];
  results: ResultDto[];
  eventTimeZone: DisplayTimeZone;
}) {
  if (!observation) return <div className="observation-empty">Canonical presentation is unavailable; runtime evidence continues independently.</div>;
  const roles = observation.identity.role_assignments;
  const visibilityRows = [
    ...observation.visibility.available.map((value) => ({ value, state: "Available" })),
    ...observation.visibility.unavailable.map((value) => ({ value, state: "Unavailable" })),
    ...observation.visibility.degraded.map((value) => ({ value, state: "Degraded" })),
  ];
  return <div className="observation-workbench">
    <div className="source-canonical-workbench">
      <section className="source-record-summary"><span className="eyebrow">Source record</span><h3>{source?.observation_type ? `${readable(source.observation_type)} ${source.record_number ? `#${source.record_number}` : ""}` : "Source summary unavailable"}</h3>{source?.event_time && <time>{formatEvidenceClockTime(source.event_time, eventTimeZone)}</time>}<FactList facts={source?.facts ?? {}} empty="No safe source facts were supplied." /></section>
      <span className="source-canonical-arrow" aria-hidden="true">→</span>
      <section className="canonical-observation-summary"><span className="eyebrow">Canonical observation</span><h3>{readable(observation.observation_type)}</h3><div className="canonical-time-line"><span>Event time</span><time>{formatEvidenceClockTime(observation.event_time, eventTimeZone)}</time></div><FactList facts={observation.facts} empty="No type-specific facts were reported." />
        {roles.length > 0 && <p className="observation-identity-line">Explicit roles: {roles.map(formatRole).join(" · ")}</p>}
        {visibilityRows.length > 0 && <div className="observation-visibility-block"><strong>Sensor visibility</strong><ul>{visibilityRows.map(({ value, state }) => <li key={value}><span className={`fact-mark ${state.toLowerCase()}`}>{state === "Available" ? "✓" : state === "Degraded" ? "△" : "○"}</span>{readable(value)}<small>{state}</small></li>)}</ul></div>}
        <div className="observation-quality-block"><strong>Quality</strong>{Object.entries(observation.quality).map(([key, value]) => <span key={key}>{readable(key)} · {qualityText(value)}</span>)}</div>
        <details><summary>View normalized fields</summary><p>Present: {observation.present_fields.map(readable).join(" · ") || "Not reported"}</p><p>Direction {readable(observation.wire_direction)} · {readable(observation.direction_basis)} · {readable(observation.finality)} · {readable(observation.availability_basis)}</p></details>
      </section>
    </div>
    <section className="observation-routes-summary"><strong>Eligible analytics</strong>{routes.length ? <ul>{routes.map((route) => <li key={route.sequence}>{mechanismLabel(route.mechanism || route.lane_id || "Analytic")}</li>)}</ul> : <p>No eligible analytics. The source observation was retained.</p>}
      {results.length > 0 && <div className="observation-result-scores">{results.filter((result) => result.mechanism_id === "DGA-A1-M1" && typeof result.evidence.dga_labelled_lexical_resemblance_score === "number").map((result) => <span key={result.result_id}>DGA-labelled lexical resemblance score: {String(result.evidence.dga_labelled_lexical_resemblance_score)} · score is not calibrated attack probability</span>)}</div>}
    </section>
  </div>;
}

export function NetworkObservationsSection({
  events, results, zone, navigate,
}: {
  events: RuntimeTraceEvent[];
  results: ResultDto[];
  zone: DisplayTimeZone;
  navigate: (page: PageKey, context?: NavigationContext) => void;
}) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const rows = useMemo(() => {
    const sources = events.filter((event) => event.kind === "SOURCE_RECORD_ACCEPTED" && event.source_record);
    return events.flatMap((trace): Row[] => {
      const observation = trace.kind === "OBSERVATION_CREATED" ? trace.canonical_observation : null;
      if (!observation) return [];
      const recordNumber = Number(observation.source_position);
      const source = sources.find((event) => event.source_record?.record_number === recordNumber)?.source_record ?? null;
      return [{ observation, source }];
    });
  }, [events]);
  const selected = rows.find((row) => row.observation.observation_id === selectedId) ?? null;
  const routeByObservation = useMemo(() => {
    const map = new Map<string, RuntimeTraceEvent[]>();
    for (const event of events) {
      if (event.kind !== "ROUTED" || !event.observation_id) continue;
      const group = map.get(event.observation_id) ?? [];
      group.push(event);
      map.set(event.observation_id, group);
    }
    return map;
  }, [events]);

  useEffect(() => {
    if (!selected) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setSelectedId(null);
      if (event.key === "Tab") {
        const focusable = [...document.querySelectorAll<HTMLElement>(".observation-modal button, .observation-modal summary")];
        const first = focusable[0], last = focusable.at(-1);
        if (event.shiftKey && document.activeElement === first && last) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last && first) { event.preventDefault(); first.focus(); }
      }
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [selected]);

  if (!rows.length) return null;
  return <>
    <section className="panel network-observations-panel" aria-labelledby="network-observations-title">
      <div className="player-panel-head"><div><span className="eyebrow">Current replay</span><strong id="network-observations-title">Network observations</strong></div><span className="stage-state-pill">{rows.length} {pluralize(rows.length, "observation")}</span></div>
      <p className="network-observation-scroll-note">Scroll horizontally to see all observation fields.</p>
      <div className="network-observation-table-wrap">
        <table className="network-observation-table">
          <thead><tr><th>Time</th><th>Type</th><th>Network context</th><th>Protocol / service</th><th>Observed fact</th><th>Direction</th><th>Routes</th><th>Details</th></tr></thead>
          <tbody>{rows.map(({ observation, source }) => {
            const routes = routeByObservation.get(observation.observation_id) ?? [];
            const fact = source?.facts ?? observation.facts;
            return <tr key={observation.observation_id} tabIndex={0} aria-label={`View ${readable(observation.observation_type)} observation`} onClick={() => setSelectedId(observation.observation_id)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); setSelectedId(observation.observation_id); } }}>
              <td>{formatEvidenceClockTime(observation.event_time, zone)}</td>
              <td>{readable(observation.observation_type)}</td>
              <td>{networkContext(fact)}</td>
              <td>{protocolAndService(observation, fact)}</td>
              <td>{observedFact(observation, fact)}</td>
              <td>{readable(observation.wire_direction)}</td>
              <td><button className="observation-route-count" onClick={() => setSelectedId(observation.observation_id)} aria-label={`${routes.length} analytic routes; view observation`}>{routes.length}</button></td>
              <td className="observation-detail-cell"><button className="text-button" onClick={() => setSelectedId(observation.observation_id)}>Details</button></td>
            </tr>;
          })}</tbody>
        </table>
      </div>
    </section>
    {selected && <ObservationDetail
      row={selected}
      routes={routeByObservation.get(selected.observation.observation_id) ?? []}
      results={results.filter((result) => result.source_observation_ids.includes(selected.observation.observation_id))}
      close={() => setSelectedId(null)}
      navigate={navigate}
    />}
  </>;
}

function ObservationDetail({ row, routes, results, close, navigate }: {
  row: Row; routes: RuntimeTraceEvent[]; results: ResultDto[]; close: () => void;
  navigate: (page: PageKey, context?: NavigationContext) => void;
}) {
  const [expandedResultId, setExpandedResultId] = useState<string | null>(null);
  const { observation, source } = row;
  return <div className="observation-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) close(); }}>
    <section className="observation-modal" role="dialog" aria-modal="true" aria-labelledby="observation-detail-title">
      <header className="observation-modal-header"><div><span className="eyebrow">Traffic Lab</span><h2 id="observation-detail-title">Canonical network observation</h2></div><button className="secondary-button" onClick={close} autoFocus>Close</button></header>
      <div className="observation-modal-body">
        <section><h3>Observed traffic</h3><FactList facts={source?.facts ?? observation.facts} empty="Source summary is unavailable." /></section>
        <section><h3>Normalized observation</h3><p>{readable(observation.observation_type)} · {readable(observation.wire_direction)} · {new Date(observation.event_time).toLocaleString()}</p><FactList facts={observation.facts} empty="No additional type-specific facts were reported." />
          <p className="observation-identity-line">Identity basis: {readable(observation.identity.identifier_basis)}{observation.identity.role_assignments.length ? " · " + observation.identity.role_assignments.map((role) => formatRole(role)).join(" · ") : " · No explicit role assignments"}</p>
          <details><summary>View normalized fields</summary><p>Present fields: {observation.present_fields.map(readable).join(" · ") || "Not reported"}</p><p>Availability basis: {readable(observation.availability_basis)} · Finality: {readable(observation.finality)} · Source position: {observation.source_position}</p><p>Observed identifiers: {observation.identity.observed_identifiers.join(" · ") || "Not reported"}</p></details>
        </section>
        <section><h3>Visibility and quality</h3><p>Available: {formatStates(observation.visibility.available)} · Unavailable: {formatStates(observation.visibility.unavailable)} · Degraded: {formatStates(observation.visibility.degraded)}</p><FactList facts={observation.quality} empty="Quality not reported." /></section>
        <section><h3>Analytics routed</h3>{routes.length ? <ul>{routes.map((route) => <li key={route.sequence}>{mechanismLabel(route.mechanism || route.lane_id || "Analytic")}</li>)}</ul> : <p>No eligible analytics. This observation was retained, but no active analytic declared it eligible.</p>}</section>
        <section><h3>Evidence produced</h3>{results.length ? <ul>{results.map((result) => { const explanation = projectResultExplanation(result, routes, observation); const open = expandedResultId === result.result_id; return <li key={result.result_id} className="observation-produced-result"><span><strong>{mechanismLabel(result.mechanism_id || result.lane_id)}</strong> · {readable(result.result_type)} · {explanation.resultReason}</span><div><button className="text-button" aria-expanded={open} onClick={() => setExpandedResultId(open ? null : result.result_id)}>{open ? "Hide explanation" : "Why this result?"}</button> <button className="text-button" onClick={() => navigate("results", { resultId: result.result_id })}>Open Result</button></div>{open && <div className="inline-result-explanation"><strong>Why this analytic ran</strong><p>{explanation.eligibilityReasons.join(" ")}</p><strong>Observed</strong><ul>{(explanation.observedFacts.length ? explanation.observedFacts : ["No scalar evidence items were reported."]).map(fact => <li key={fact}>{fact}</li>)}</ul><strong>Why the Result was emitted</strong><p>{explanation.resultReason}</p><strong>Supports</strong><ul>{explanation.supports.map(fact=><li key={fact}>{fact}</li>)}</ul><strong>Does not establish</strong><ul>{explanation.limitations.map(fact=><li key={fact}>{fact}</li>)}</ul>{explanation.missingEvidence.length>0 && <><strong>Missing evidence</strong><ul>{explanation.missingEvidence.map(fact=><li key={fact}>{fact}</li>)}</ul></>}<strong>Source lineage</strong><span>{explanation.sourceObservationIds.length} source observation{explanation.sourceObservationIds.length === 1 ? "" : "s"}</span></div>}</li>; })}</ul> : <p>No source-linked Result is available for this observation.</p>}</section>
        <details className="observation-lineage"><summary>Source lineage / audit detail</summary><p>Source record {source?.record_number ?? observation.source_position} · Observation {observation.observation_id}</p></details>
      </div>
    </section>
  </div>;
}

function FactList({ facts, empty }: { facts: Record<string, unknown>; empty: string }) {
  const entries = Object.entries(facts).filter(([, value]) => value !== null && value !== undefined);
  if (!entries.length) return <p>{empty}</p>;
  return <dl className="observation-fact-list">{entries.map(([key, value]) => <div key={key}><dt>{fieldLabel(key)}</dt><dd>{typeof value === "object" ? Object.entries(value as Record<string, unknown>).map(([child, item]) => `${fieldLabel(child)}: ${item === "UNKNOWN" ? "Not reported" : String(item)}`).join(" · ") : value === "UNKNOWN" ? "Not reported" : key.endsWith("_time") ? formatEvidenceClockTime(String(value)) : readable(String(value))}</dd></div>)}</dl>;
}

function networkContext(facts: Record<string, unknown>) {
  if (facts.source_address || facts.destination_address) return `${endpoint(facts.source_address, facts.source_port)} → ${endpoint(facts.destination_address, facts.destination_port)}`;
  if (facts.endpoint_a || facts.endpoint_b) return `${String(facts.endpoint_a ?? "Endpoint A")} ↔ ${String(facts.endpoint_b ?? "Endpoint B")}`;
  return String(facts.qname_rendered ?? facts.qname_canonical ?? "Network context unavailable");
}

function endpoint(address: unknown, port: unknown) { return `${String(address ?? "Unknown")}${port === null || port === undefined ? "" : `:${String(port)}`}`; }
function protocolAndService(observation: ObservationPresentationDto, facts: Record<string, unknown>) {
  const protocol = facts.protocol_number === 6 ? "TCP" : facts.protocol_number === 17 ? "UDP" : facts.protocol_number === 1 ? "ICMP" : facts.protocol_number ? `IP ${String(facts.protocol_number)}` : facts.transport ?? "Not reported";
  const role = observation.identity.role_assignments.find((item) => item.role === "service_id");
  return `${String(protocol)}${role ? ` · ${role.identifier.replace("service/", "").toUpperCase()}` : facts.qtype ? ` · ${String(facts.qtype)}` : ""}`;
}
function observedFact(observation: ObservationPresentationDto, facts: Record<string, unknown>) {
  if (Array.isArray(facts.flags)) return `${facts.flags.join(" / ") || "Flags not reported"}${facts.ip_length ? ` · ${String(facts.ip_length)} B` : ""}`;
  if (facts.directional_counters) return Object.entries(facts.directional_counters as Record<string, unknown>).map(([key, value]) => `${String(value)} ${key.startsWith("bytes_") ? "B" : "packets"} ${key.endsWith("c2s") ? "client → server" : "server → client"}`).join(" · ");
  if (facts.message_length) return `${String(facts.message_length)} B query`;
  return readable(observation.finality);
}
function formatStates(values: string[]) { return values.length ? values.map(readable).join(", ") : "None reported"; }
function qualityText(value: string) { return value === "UNKNOWN" ? "Not reported" : readable(value); }
function formatRole(role: ObservationPresentationDto["identity"]["role_assignments"][number]) {
  const labels: Record<string, string> = { initiator_id: "Initiator", target_id: "Target", service_id: "Service", client_id: "Client", peer_id: "Peer", peer_port: "Peer port" };
  const identifier = role.role === "service_id" ? role.identifier.replace("service/", "").toUpperCase() : role.identifier;
  return `${labels[role.role] ?? readable(role.role)} ${identifier}`;
}
function fieldLabel(value: string) { return ({ source_address: "Source", source_port: "Source port", destination_address: "Destination", destination_port: "Destination port", protocol_number: "IP protocol", ip_length: "IP length", packet_length: "Packet length", qname_rendered: "Rendered query name", qname_canonical: "Canonical query name", message_length: "Message length", directional_counters: "Directional counters", flow_reference: "Flow reference", start_time: "Flow start", end_time: "Flow end", export_time: "Export time", documented_end_state: "Documented end state", reassembly_state: "Reassembly state", parser_version: "Parser version", fragmentation: "Fragmentation" } as Record<string, string>)[value] ?? readable(value); }
