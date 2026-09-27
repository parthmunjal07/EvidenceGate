import { describe, expect, it } from "vitest";
import type { FamilyEvidenceViewDto, InvestigationLinkDto, ResultDto, RuntimeTraceEvent, ScenarioDto } from "../api/types";
import { demoContractFromScenario, judgeDemoScenarios, validateDemoVersions, validateJudgeDemo, validateScopedEvidence } from "./judgeDemos";

const scenarios = [
  {id:"mixed_ddos_recon",label:"mixed",family:"DDoS / Reconnaissance",source_type:"NDJSON",asset_version:"mixed_ddos_recon_v2",demo_title:"DDoS + Recon fan-out",demo_purpose:"",expected_records:12,expected_observations:12,expected_routes:60,expected_results:65,expected_family_views:17,expected_relations:8,expected_zero_route_observations:2,max_trace_events:500,source_label:"Controlled observations",episode_summary:[]},
  {id:"ddos_one_way",label:"one way",family:"DDoS",source_type:"NDJSON",asset_version:"ddos_one_way_v2",demo_title:"One-way SYN visibility",expected_records:8,expected_observations:8,expected_routes:37,expected_results:40,expected_family_views:11,expected_relations:5,expected_zero_route_observations:2,max_trace_events:500},
  {id:"c2_recurrence",label:"c2",family:"C2 / Beaconing",source_type:"NDJSON",asset_version:"c2_recurrence_v2",demo_title:"C2 recurrence",expected_records:7,expected_observations:7,expected_routes:14,expected_results:14,expected_family_views:10,expected_relations:7,expected_zero_route_observations:0,max_trace_events:500},
  {id:"dga_lexical",label:"dga",family:"DGA / DNS",source_type:"NDJSON",asset_version:"dga_dns_v2",demo_title:"DGA + DNS",expected_records:6,expected_observations:6,expected_routes:12,expected_results:12,expected_family_views:6,expected_relations:0,expected_zero_route_observations:0,max_trace_events:500,needs_dga:true},
  {id:"raw_pcap_ddos_recon",label:"pcap",family:"DDoS / Reconnaissance",source_type:"PCAP",asset_version:"raw_pcap_ddos_recon_v2",demo_title:"Recorded PCAP",expected_records:18,expected_observations:18,expected_routes:71,expected_results:58,expected_family_views:15,expected_relations:8,expected_zero_route_observations:5,max_trace_events:500},
] as ScenarioDto[];
const result = (id: string): ResultDto => ({ result_id:id, source_observation_ids:["obs-a"] } as ResultDto);
const view = (family:string,id=family):FamilyEvidenceViewDto=>({family,family_view_id:id,source_result_ids:[],source_observation_ids:["obs-a"]} as unknown as FamilyEvidenceViewDto);
const trace=[{sequence:1,kind:"OBSERVATION_CREATED",observation_id:"obs-a"},{sequence:2,kind:"ROUTED",observation_id:"obs-a"}] as RuntimeTraceEvent[];
const link=(left:string,right:string,id="l"):InvestigationLinkDto=>({link_id:id,left_family_view_id:left,right_family_view_id:right} as InvestigationLinkDto);

describe("backend-owned judge demo contracts",()=>{
  it("surfaces the five backend contracts and gates DGA on readiness",()=>{
    const available=judgeDemoScenarios([...scenarios,{id:"internal",label:"internal",family:"test",source_type:"NDJSON"}],false);
    expect(available.map(x=>x.id)).toEqual(scenarios.map(x=>x.id));
    expect(available[0]).toMatchObject({recommended:true,label:"DDoS + Recon fan-out"});
    expect(available.find(x=>x.id==="dga_lexical")?.unavailableReason).toBe("DGA model unavailable in this deployment");
  });
  it("blocks backend/frontend build or asset generation mismatch",()=>{
    const s=scenarios[0]!, contract=demoContractFromScenario(s)!;
    expect(validateDemoVersions("sha-a","sha-b",s,contract).buildMismatch).toBe(true);
    expect(validateDemoVersions("unknown","unknown",s,contract).buildMismatch).toBe(true);
    expect(validateDemoVersions("sha-a","sha-a",{...s,asset_version:"mixed_ddos_recon_v1"},contract).assetMismatch).toBe(true);
    expect(validateDemoVersions("sha-a","sha-a",s,contract)).toEqual({buildMismatch:false,assetMismatch:false});
  });
  it("rejects links outside current scoped family views",()=>{
    expect(validateScopedEvidence([], [link("a","b")])).toBe(false);
    expect(validateScopedEvidence([view("DDoS","a")],[link("a","b")])).toBe(false);
    expect(validateScopedEvidence([view("DDoS","a"),view("Recon","b")],[link("a","b")])).toBe(true);
  });
  it("fails closed against the known two-record mixed demo state",()=>{
    const contract=demoContractFromScenario(scenarios[0]!)!;
    const checked=validateJudgeDemo(contract,{records:2,observations:2,results:[result("r1")],familyViews:[view("DDoS")],links:[],trace,traceAvailable:true,runtimeCompleted:true});
    expect(checked.ok).toBe(false);
    expect(checked.reasons).toContain("Expected 65 source-linked Results; received 1");
    expect(checked.reasons).toContain("Expected family evidence for Reconnaissance");
    expect(checked.reasons).toContain("Expected 8 factual relationships; received 0");
  });
});
