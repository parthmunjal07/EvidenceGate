import { describe, expect, it } from "vitest";
import type { ResultDto } from "../api/types";
import { projectResultExplanation } from "./resultExplanation";

const make=(mechanism:string, evidence:Record<string,unknown>={})=>({mechanism_id:mechanism,lane_id:mechanism,family:"Evidence",result_type:"REVIEW_FINDING",claim_ceiling:"OBSERVED_MEASUREMENT_ONLY; NO_ATTACK_CONFIRMATION",evidence,evidence_items:["3 packets observed"],missing_prerequisites:["REVERSE_FACTS"],source_observation_ids:["obs-1"],status_snapshot:{readiness:"READY"}} as unknown as ResultDto);
const cases=["ddos.syn_state","ddos.udp_demand","ddos.reflection_victim","ddos.source_diversity","ddos.connection_churn","recon.h","recon.v","recon.2d","recon.tcp","c2.r1","dga.m1","dns_tunnelling.t1","encrypted_session.enc_a","unusual_transfer.m1"];

describe("deterministic Result explanation projection",()=>{
  it.each(cases)("projects routed, observed, result, support, limits and lineage for %s",mechanism=>{
    const explanation=projectResultExplanation(make(mechanism,{dga_labelled_lexical_resemblance_score:0.87}));
    expect(explanation.eligibilityReasons.length).toBeGreaterThan(0);
    expect(explanation.observedFacts.length).toBeGreaterThan(0);
    expect(explanation.resultReason.length).toBeGreaterThan(10);
    expect(explanation.supports).toContain("observed measurement only");
    expect(explanation.limitations).toContain("no attack confirmation");
    expect(explanation.missingEvidence).toContain("reverse facts");
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
    expect(x.missingEvidence).toContain("reverse facts");
    expect(x.resultReason).toContain("TCP initiation/state evidence");
  });
  it("does not expose provider or fixture state keys as observed facts",()=>{
    const result=make("ddos.source_diversity",{apparent_source_cardinality_lower_bound:3});
    result.evidence_items=["state:provider.ddos.source_diversity:[\"192.0.2.10\"]"];
    const x=projectResultExplanation(result);
    expect(x.observedFacts.some(item=>item.includes("provider."))).toBe(false);
    expect(x.observedFacts).toContain("Minimum apparent source count: 3");
  });
});
