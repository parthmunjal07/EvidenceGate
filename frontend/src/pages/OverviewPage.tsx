import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { FamilyEvidenceViewDto, InvestigationLinkDto, RuntimeTarget } from "../api/types";
import type { PageKey } from "../state/types";
import { PageHeading } from "../components/common/Primitives";
import { useEvidence } from "../state/EvidenceContext";
import { readable } from "../utils/formatting";

const familyCards = [
  { id: "ddos", title: "DDoS", prefixes: ["ddos"], statusMatch: ["ddos"], paths: ["TCP initiating activity", "UDP demand", "Reflection-shaped traffic", "Source diversity", "ICMP and fragment demand", "Connection / attempt activity"] },
  { id: "c2", title: "C2 / Beaconing", prefixes: ["c2"], statusMatch: ["c2"], paths: ["Recurring communication", "History and continuity state"] },
  { id: "dns", title: "DGA + DNS", prefixes: ["dga", "dns_tunnelling"], statusMatch: ["dga", "dns tunnelling"], paths: ["DGA lexical evidence", "DNS structural evidence"], note: "Both analytics can independently receive the same DNS observation." },
  { id: "encrypted", title: "Encrypted Sessions", prefixes: ["encrypted_session"], statusMatch: ["encrypted sessions"], paths: ["Handshake evidence", "Session metadata"] },
  { id: "recon", title: "Reconnaissance", prefixes: ["recon"], statusMatch: ["reconnaissance"], paths: ["Host breadth", "Service breadth", "Host by service activity", "TCP attempt activity"] },
  { id: "transfer", title: "Data Transfer", prefixes: ["unusual_transfer"], statusMatch: ["data exfiltration"], paths: ["Directional transfer magnitude"], note: "Transfer magnitude does not establish exfiltration." },
];

export function OverviewPage({ navigate }: { navigate: (page: PageKey) => void }) {
  const { state } = useEvidence();
  const [views, setViews] = useState<FamilyEvidenceViewDto[]>([]);
  const [links, setLinks] = useState<InvestigationLinkDto[]>([]);
  useEffect(() => {
    const controller = new AbortController();
    void api.investigations(controller.signal).then((value) => {
      if (!controller.signal.aborted) { setViews(value.family_views); setLinks(value.links); }
    }).catch(() => undefined);
    return () => controller.abort();
  }, [state.orderedResults.length, state.replay?.finished_at]);

  const runtime = state.runtime;
  const replay = state.replay ?? runtime?.replay;
  const mechanisms = runtime?.targets ?? [];
  const results = runtime?.durable_result_count ?? state.results.size;
  const activeObservations = replay?.observations_emitted ?? 0;
  const inputRate = replay && replay.elapsed_wall_seconds > 0 ? (replay.records_read / replay.elapsed_wall_seconds).toFixed(1) : null;
  const prefixes = (target: RuntimeTarget) => target.lane_id.split(".")[0] ?? "";
  const pathTargets = new Map(familyCards.map((card) => [card.id, mechanisms.filter((target) => card.prefixes.includes(prefixes(target)))]));

  return <section className="page active-page" aria-labelledby="overview-title">
    <PageHeading titleId="overview-title" title="Overview" deck="Current runtime, six family decompositions, and factual investigation context." meta={<span className="live-label"><i />{runtime?.state === "REPLAYING" ? "Replay in progress" : "Runtime connected"}</span>} />
    <section className="panel overview-runtime-panel">
      <div className="panel-head compact"><div><span className="eyebrow">CURRENT RUNTIME</span><h2>Streaming and evidence state</h2><p>Latest replay counters and durable mechanism evidence.</p></div><span className={`status-chip ${runtime?.state === "REPLAYING" ? "running" : ""}`}>{runtime?.state ?? "CONNECTING"}</span></div>
      <div className="runtime-strip">
        <RuntimeMetric label="Latest replay input" value={replay?.records_read ? `${replay.records_read} records` : "No replay"} detail={`${activeObservations} observations · ${inputRate ? `${inputRate} records/s` : "rate unavailable"}`} />
        <RuntimeMetric label="Analytics" value={`${mechanisms.length} registered`} detail={`${runtime?.family_status.length ?? 0} family statuses`} />
        <RuntimeMetric label="Results" value={results.toLocaleString()} detail="Durable mechanism Results" />
        <RuntimeMetric label="Derived evidence" value={`${views.length} families · ${links.length} links`} detail="Independent composition and shared-observation context" />
      </div>
      <div className="runtime-step-links" aria-label="Runtime progression">{[["Observations", "replay"], ["Analytics", "replay"], ["Results", "results"], ["Family evidence", "alerts"], ["Investigations", "investigations"]].map(([label, page], index) => <span className="runtime-step-wrap" key={label}><button className="runtime-step" onClick={() => navigate(page as PageKey)}><strong>{label}</strong><small>{index === 0 ? `${activeObservations} emitted` : index === 1 ? `${mechanisms.length} registered` : index === 2 ? `${results.toLocaleString()} durable` : index === 3 ? `${views.length} views` : `${links.length} links`}</small></button>{index < 4 && <i aria-hidden="true">→</i>}</span>)}</div>
    </section>

    <section className="overview-family-section">
      <div className="section-title-row"><div><h2>Threat-family coverage</h2><p>Mechanisms remain independent. Family views summarize related Results.</p></div><button className="text-button" onClick={() => navigate("replay")}>Open Traffic Lab →</button></div>
      <div className="family-card-grid">{familyCards.map((card) => {
        const targets = pathTargets.get(card.id) ?? [];
        const runtimeState = runtime?.family_status.find((item) => card.statusMatch.some((name) => item.family.toLowerCase().includes(name)));
        return <article className="overview-family-card" key={card.id}><header><h3>{card.title}</h3><span className={`family-state-chip${targets.length ? " active" : " inactive"}`}>{targets.length ? `${targets.length} registered` : "No registered mechanism"}</span></header><ul>{card.paths.map((path) => <li key={path}><span className={targets.length ? "path-dot active" : "path-dot"} />{path}</li>)}</ul>{card.note && <p className="family-card-note">{card.note}</p>}{runtimeState && <small className="runtime-family-status">Runtime status: {readable(runtimeState.status)}</small>}</article>;
      })}</div>
    </section>

    <section className="panel performance-panel">
      <div className="panel-head compact"><div><span className="eyebrow">MEASURED PERFORMANCE</span><h2>Runtime health and benchmark</h2><p>Live replay instrumentation and offline benchmark data are kept distinct.</p></div></div>
      <div className="performance-note-grid"><div><strong>Live instrumentation</strong><span>Replay wall time · records · observations</span></div><div><strong>Offline benchmark</strong><span>Processing and end-to-end latency · RSS</span></div><div><strong>Not instrumented live</strong><span>State footprint · queue depth</span></div></div>
      <div className="benchmark-card">
        <div className="benchmark-heading"><div><span className="eyebrow">APPROVED DEMO CLAIM</span><h3>Controlled MVP operating point</h3><p>50 offered observations/s · 30 seconds · mixed workload · zero input/runtime drops</p></div><span className="benchmark-tag">Human-Gate approved</span></div>
        <div className="benchmark-additional"><strong>Additional post-activation artifact measurements</strong><span>Processing p50 / p95 / p99: 186.3378 / 883.2264 / 1,017.04 ms</span><span>End-to-end evidence p50 / p95 / p99: 312.552 / 983.132 / 1,165.4749 ms</span><span>Peak RSS: 244,203,520 bytes</span></div>
        <p className="benchmark-caveat">Controlled development benchmark, not production capacity or an SLA. Additional values come from <code>benchmark_results/final_mvp_acceptance.json</code> (2026-09-24); the approved operating claim comes from <code>FINAL_MVP_IMPLEMENTATION_CLOSURE.md</code> (2026-09-23). SSE notification loss is outside the runtime drop count.</p>
      </div>
    </section>
    <div className="overview-actions"><button className="primary-button" onClick={() => navigate("replay")}>Open Traffic Lab</button><button className="secondary-button" onClick={() => navigate("alerts")}>Review family evidence</button><button className="secondary-button" onClick={() => navigate("investigations")}>Open investigations</button><button className="text-button" onClick={() => navigate("results")}>Browse mechanism Evidence →</button></div>
  </section>;
}

function RuntimeMetric({ label, value, detail }: { label: string; value: string; detail: string }) {
  return <div className="runtime-metric"><span>{label}</span><strong>{value}</strong><small>{detail}</small></div>;
}
