import type { ObservationPresentationDto, ResultDto, RuntimeTraceEvent } from "../api/types";
import { humanEvidenceRows, whySurfaced } from "./formatting";

export type ResultExplanation = {
  title: string; family: string; mechanism: string; resultState: string;
  eligibilityReasons: string[]; observedFacts: string[]; readinessReason: string;
  resultReason: string; supports: string[]; limitations: string[];
  missingEvidence: string[]; sourceObservationIds: string[];
};

const words = (s: string) => s.replaceAll("_", " ").replaceAll(";", ", ").toLowerCase();
const mechanismCopy: Record<string, { eligible: string; emitted: string }> = {
  "ddos.syn_state": { eligible:"TCP initiating packet facts and available target/service identity made this analytic eligible.", emitted:"TCP initiation/state evidence was available for the scoped observation." },
  "ddos.udp_demand": { eligible:"A UDP packet observation with target/service context made this analytic eligible.", emitted:"UDP demand measurement became available from the observed packet facts." },
  "ddos.source_diversity": { eligible:"Source and target identity facts made apparent-source distribution measurable.", emitted:"Apparent source distribution was measured from the scoped observations." },
  "recon.host_discovery": { eligible:"Source and target identity facts made host-probing geometry measurable.", emitted:"Observed host breadth became measurable from accumulated probing facts." },
  "recon.h": { eligible:"Source and target identity facts made host-probing geometry measurable.", emitted:"Observed host breadth became measurable from accumulated probing facts." },
  "recon.service_discovery": { eligible:"Source, target and service/port facts made service-probing geometry measurable.", emitted:"Observed service breadth became measurable from accumulated probing facts." },
  "recon.v": { eligible:"Source and target identity facts made host-probing geometry measurable.", emitted:"Observed host breadth became measurable from accumulated probing facts." },
  "recon.2d": { eligible:"Source, target and service/port facts made probing geometry measurable.", emitted:"Observed host and service breadth became measurable from accumulated probing facts." },
  "recon.tcp": { eligible:"TCP source, target and service/port facts made probing geometry measurable.", emitted:"Observed TCP probing breadth became measurable from accumulated probing facts." },
  "c2.r1": { eligible:"A flow-start observation with client, peer and service identity entered bounded history evaluation.", emitted:"The Result records the recurrence state and evidence present in this flow history." },
  "dga.m1": { eligible:"A clear DNS query name and the required domain representation were available to the verified lexical model.", emitted:"The verified lexical model produced a DGA-labelled lexical resemblance score for the registrable domain." },
  "dns_tunnelling.t1": { eligible:"Clear DNS query-name fields were available for structural measurement.", emitted:"Query-name structure was measurable from the clear DNS observation." },
  "encrypted_session.enc_a": { eligible:"Visible TLS handshake metadata was available to the handshake analytic.", emitted:"Visible handshake metadata was recorded as contextual evidence." },
  "unusual_transfer.m1": { eligible:"Directional flow counters and duration facts were available for transfer measurement.", emitted:"Transfer magnitude was measured from the available flow counters." },
};

export function projectResultExplanation(result: ResultDto, trace: RuntimeTraceEvent[] = [], observation?: ObservationPresentationDto | null): ResultExplanation {
  const mechanism = result.lane_id;
  const contract = mechanismCopy[mechanism];
  const laneEvents = trace.filter(e => result.source_observation_ids.includes(e.observation_id ?? "") && (e.lane_id === result.lane_id || e.mechanism === result.lane_id || e.mechanism === result.mechanism_id));
  const observedFacts = observedFromResult(result);
  const readiness = laneEvents.find(e => e.readiness && e.readiness !== "READY");
  const ceilingParts = result.claim_ceiling.split(/[;|]/).map(x=>x.trim()).filter(Boolean);
  const supportTokens = ceilingParts.filter(x=>!/^NO_|^NOT_|^PROHIBITS|_PROHIBITED/i.test(x));
  const limitTokens = ceilingParts.filter(x=>/^NO_|^NOT_|^PROHIBITS|_PROHIBITED/i.test(x));
  if ((result.mechanism_id === "DGA-A1-M1" || result.lane_id === "dga.m1") && typeof result.evidence.dga_labelled_lexical_resemblance_score === "number") observedFacts.unshift(`DGA-labelled lexical resemblance score: ${result.evidence.dga_labelled_lexical_resemblance_score}`);
  return {
    title: mechanism, family: result.family, mechanism, resultState: result.status_snapshot.readiness,
    eligibilityReasons: eligibilityFromFacts(result, contract, laneEvents, observation),
    observedFacts, readinessReason: readiness ? `Readiness recorded by runtime: ${words(readiness.readiness ?? "unknown")}.` : `Readiness recorded on Result: ${words(result.status_snapshot.readiness)}.`,
    resultReason: contract?.emitted ?? `The immutable Result records ${words(result.result_type)} with its attached evidence and claim ceiling.`,
    supports: supportTokens.length ? supportTokens.map(words) : [words(result.claim_ceiling)],
    limitations: limitTokens.map(words), missingEvidence: result.missing_prerequisites.map(words), sourceObservationIds: result.source_observation_ids,
  };
}

function eligibilityFromFacts(result:ResultDto, contract:{eligible:string;emitted:string}|undefined, events:RuntimeTraceEvent[], observation?:ObservationPresentationDto|null) {
  const routed=events.some(event=>event.kind==="ROUTED");
  if(!routed)return ["The runtime routing trace does not confirm eligibility for this source observation."];
  if(!observation)return contract?[contract.eligible]:["The runtime routing trace records this analytic as eligible for the source observation."];
  const facts=observation.facts;
  const roles=observation.identity.role_assignments;
  const role=(name:string)=>roles.some(item=>item.role===name);
  const proto=facts.protocol_number===6?"TCP":facts.protocol_number===17?"UDP":String(facts.transport??observation.observation_type);
  if(result.lane_id==="ddos.syn_state")return [`${proto} packet · ${Array.isArray(facts.flags)&&facts.flags.includes("SYN")?"initiating SYN observed · ":"packet facts available · "}${role("target_id")?"target":"target"}${role("service_id")?" and service":""} identity available.`];
  if(result.lane_id==="ddos.udp_demand")return [`UDP packet · ${role("target_id")?"target":"destination"}${role("service_id")?" and service":""} facts available.`];
  if(result.lane_id.startsWith("recon."))return [`${role("initiator_id")||role("source_id")?"Source":"Endpoint"} · ${role("target_id")?"target":"peer"}${role("service_id")||typeof facts.destination_port==="number"?" · port/service":""} · ${proto} probing facts available.`];
  if(result.lane_id==="dga.m1")return [typeof facts.qname_rendered==="string"||typeof facts.qname_canonical==="string"?"Clear DNS QNAME · canonical query-name facts available to the routed lexical lane.":contract?.eligible??"Clear DNS query-name facts were not present in this canonical observation."];
  if(result.lane_id==="dns_tunnelling.t1")return [typeof facts.qname_rendered==="string"||typeof facts.qname_canonical==="string"?"Clear DNS query-name fields available for structural measurement.":contract?.eligible??"DNS query-name availability is not present in this observation."];
  if(result.lane_id==="c2.r1")return [`Flow-start observation · ${role("client_id")?"client":"endpoint"} · ${role("peer_id")?"peer":"peer context"} · bounded history evaluation.`];
  return contract?[contract.eligible]:["The runtime routing trace records this analytic as eligible for the source observation."];
}

function observedFromResult(result: ResultDto): string[] {
  const e=result.evidence;
  const rows=humanEvidenceRows(e).filter(([label])=>label!=="Additional evidence").map(([label,value])=>`${label}: ${value}`);
  const measurements=typeof e.measurements === "object" && e.measurements !== null && !Array.isArray(e.measurements)
    ? Object.entries(e.measurements as Record<string,unknown>).map(([key,value])=>`${measurementLabel(key)}: ${String(value)}${key.endsWith("_seconds")?" s":""}`) : [];
  const statement=typeof e.statement === "string" ? [e.statement] : [];
  const nested=typeof e.observed_facts === "object" && e.observed_facts !== null && !Array.isArray(e.observed_facts)
    ? Object.entries(e.observed_facts as Record<string,unknown>).filter(([,v])=>v!==null&&v!==undefined).map(([k,v])=>`${words(k)}: ${String(v)}`) : [];
  const resultFacts=[...statement,...rows,...measurements,...nested];
  if(typeof e.model_readiness==="string")resultFacts.push(`Lexical model readiness: ${words(e.model_readiness)}`);
  for(const key of ["qtype","transport","label_count","max_label_length","full_qname_length"]){const value=e[key];if(typeof value==="string"||typeof value==="number")resultFacts.push(`${measurementLabel(key)}: ${String(value)}`);}
  const scopedEntity=typeof e.entity === "object"&&e.entity!==null&&!Array.isArray(e.entity)?e.entity as Record<string,unknown>:{};
  const target=publicEntity(e.target_ref)??publicEntity(scopedEntity.peer_ref)??publicEntity(result.entity_reference);
  if(target)resultFacts.push(`Target / peer: ${target}`);
  const service=publicService(e.service_ref)??publicService(scopedEntity.service_ref);
  if(service)resultFacts.push(`Service: ${service}`);
  if (resultFacts.length) return [...new Set(resultFacts)];
  const safeItems=result.evidence_items.filter(item=>!/^state:provider\.|^packet:[^ ]+:\d+$/i.test(item));
  if(safeItems.length)return safeItems;
  return [whySurfaced(result.lane_id,e)];
}

function measurementLabel(key:string) {
  const labels:Record<string,string>={attempt_count:"Attempts",distinct_hosts:"Distinct targets",distinct_ports:"Distinct ports",distinct_host_port_pairs:"Distinct target and port pairs",horizon_seconds:"Measurement horizon",initiating_syn_count:"Initiating SYN count",captured_syn_ack_response_count:"Captured SYN-ACK responses",captured_rst_response_count:"Captured RST responses",captured_ack_progression_count:"Captured ACK progression",recurrence_count:"Recurrence count",recurrence_observations:"Contributing observations",event_count:"Communication events",history_span_seconds:"History span",iat_median_seconds:"Median interval",iat_mad_seconds:"Interval median absolute deviation",interval_count:"Observed intervals",qtype:"DNS query type",transport:"DNS transport",label_count:"DNS label count",max_label_length:"Longest DNS label",full_qname_length:"Full query-name length"};
  return labels[key] ?? words(key);
}

function publicEntity(value:unknown){if(typeof value!=="string")return null;const text=value.trim();return /^[A-Za-z0-9.-]+$/.test(text)&&text.includes(".")?text:null;}
function publicService(value:unknown){if(typeof value!=="string")return null;const text=value.replace(/^service\//i,"").trim();return /^[A-Za-z0-9-]{1,32}$/.test(text)?text.toUpperCase():null;}
