import { describe, expect, it } from "vitest";
import type { ResultDto } from "../api/types";
import { projectResultExplanation } from "./resultExplanation";

const make=(mechanism:string, evidence:Record<string,unknown>={})=>({mechanism_id:mechanism,lane_id:mechanism,family:"Evidence",result_type:"REVIEW_FINDING",claim_ceiling:"OBSERVED_TCP_INITIATING_ATTEMPT_MEASUREMENT_ONLY;NO_DDOS_CONFIRMED",evidence,evidence_items:["3 packets observed"],missing_prerequisites:["REVERSE_TCP_STATE"],source_observation_ids:["obs-1"],status_snapshot:{readiness:"READY"}} as unknown as ResultDto);
const cases=["ddos.syn_state","ddos.udp_demand","ddos.reflection_victim","ddos.source_diversity","ddos.connection_churn","recon.h","recon.v","recon.2d","recon.tcp","c2.r1","dga.m1","dns_tunnelling.t1","encrypted_session.enc_a","unusual_transfer.m1"];

describe("deterministic Result explanation projection",()=>{
  it.each(cases)("projects routed, observed, result, support, limits and lineage for %s",mechanism=>{
    const explanation=projectResultExplanation(make(mechanism,{dga_labelled_lexical_resemblance_score:0.87}));
    expect(explanation.eligibilityReasons.length).toBeGreaterThan(0);
    expect(explanation.observedFacts.length).toBeGreaterThan(0);
    expect(explanation.resultReason.length).toBeGreaterThan(10);
    if (mechanism !== "encrypted_session.enc_a") expect(explanation.supports).toContain("TCP initiating attempts were measured.");
    expect(explanation.limitations).toContain("A DDoS attack is not confirmed.");
    expect(explanation.missingEvidence).toContain("Reverse TCP state");
    expect(explanation.sourceObservationIds).toEqual(["obs-1"]);
  });
  it("labels DGA output as lexical resemblance, never attack probability",()=>{
    const x=projectResultExplanation(make("dga.m1",{dga_labelled_lexical_resemblance_score:0.87}));
    expect(x.observedFacts).toContain("DGA-labelled lexical resemblance score: 0.87");
    expect(x.resultReason).toContain("DGA-labelled lexical resemblance score");
    expect(x.resultReason.toLowerCase()).not.toContain("attack probability");
  });
  it("explains one-way TCP evidence while preserving unavailable reverse state",()=>{
    const result=make("ddos.syn_state",{statement:"Initiating SYN was observed; reverse completion state is not observable from this source contract.",raw_syn_observations:1,target_ref:"192.0.2.10",service_ref:"service/https"});
    result.result_type="INSUFFICIENT_EVIDENCE";
    const x=projectResultExplanation(result);
    expect(x.observedFacts).toContain("Initiating SYN was observed; reverse completion state is not observable from this source contract.");
    expect(x.missingEvidence).toContain("Reverse TCP state");
    expect(x.resultReason).toContain("TCP initiation/state evidence");
  });
  it("uses analyst-facing readiness copy and never exposes missing trace uncertainty",()=>{
    const explanation=projectResultExplanation(make("recon.2d"));
    expect(explanation.eligibilityReasons.some((reason) => reason.includes("routing trace does not confirm"))).toBe(false);
    expect(explanation.eligibilityReasons).toContain("The canonical observation satisfied the analytic's declared input requirements.");
    expect(explanation.readinessReason).toContain("Bounded host-by-port measurement state");
  });
  it("explains Recon service discovery as port breadth, not host breadth",()=>{
    const explanation=projectResultExplanation(make("recon.v"));
    expect(explanation.eligibilityReasons).toContain("The canonical observation satisfied the analytic's declared input requirements.");
    expect(explanation.resultReason).toContain("Destination-port breadth became measurable");
    expect(explanation.resultReason).not.toContain("host breadth");
  });
  it("does not expose provider or fixture state keys as observed facts",()=>{
    const result=make("ddos.source_diversity",{apparent_source_cardinality_lower_bound:3});
    result.evidence_items=["state:provider.ddos.source_diversity:[\"192.0.2.10\"]"];
    const x=projectResultExplanation(result);
    expect(x.observedFacts.some(item=>item.includes("provider."))).toBe(false);
    expect(x.observedFacts).toContain("Minimum apparent source count: 3");
  });
  it("explains the visible TLS handshake without implying payload access or malware",()=>{
    const result=make("encrypted_session.enc_a",{protocol:"TLS",parsed_handshake_metadata:{message_type:"ClientHello",sni:"example.test"}});
    result.claim_ceiling="VISIBLE_CLIENTHELLO_FINGERPRINT_CONTEXT_ONLY; PROHIBITS MALWARE_CONFIRMED, COMPROMISE, C2, EXFILTRATION, DECRYPTED_CONTENT";
    const x=projectResultExplanation(result);
    expect(x.observedFacts).toEqual(["Protocol: TLS","Handshake message: ClientHello","Server Name Indication (SNI): example.test"]);
    expect(x.supports).toEqual(["Visible TLS ClientHello handshake metadata is available as outer-session context."]);
    expect(x.missingEvidence).toContain("Application payload content is unavailable because it remained encrypted and was not decrypted.");
    expect(x.limitations).toContain("The evidence does not establish malware, compromise, command-and-control, data exfiltration, or decrypted content.");
    expect(x.observedFacts.join(" ")).not.toContain("fixture");
  });
});
