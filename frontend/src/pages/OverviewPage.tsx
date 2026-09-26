import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { FamilyEvidenceViewDto, InvestigationLinkDto, RuntimeTarget } from "../api/types";
import type { PageKey } from "../state/types";
import { PageHeading } from "../components/common/Primitives";
import { useEvidence } from "../state/EvidenceContext";
import { readable } from "../utils/formatting";

const familyCards = [
  { id: "ddos", title: "DDoS", prefixes: ["ddos"], statusMatch: ["ddos"], paths: ["TCP initiating activity", "UDP demand", "Reflection-shaped traffic", "Source diversity", "ICMP demand", "Fragment demand", "Connection / attempt activity"] },
  { id: "c2", title: "C2 / Beaconing", prefixes: ["c2"], statusMatch: ["c2"], paths: ["Recurring communication", "History / continuity state"] },
  { id: "dns", title: "DGA + DNS", prefixes: ["dga", "dns_tunnelling"], statusMatch: ["dga", "dns tunnelling"], paths: ["DGA lexical evidence", "DNS structural evidence"], note: "Both analytics can independently receive the same DNS observation." },
  { id: "encrypted", title: "Encrypted Sessions", prefixes: ["encrypted_session"], statusMatch: ["encrypted sessions"], paths: ["Handshake evidence", "Outer / session metadata"] },
  { id: "recon", title: "Reconnaissance", prefixes: ["recon"], statusMatch: ["reconnaissance"], paths: ["Host breadth", "Service breadth", "Host Ã— service activity", "TCP attempt activity"] },
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
    }).catch(() => { /* Overview remains useful while derived views are unavailable. */ });
    return () => controller.abort();
  }, [state.orderedResults.length, state.replay?.finished_at]);

  const runtime = state.runtime;
  const replay = state.replay ?? runtime?.replay;
  const mechanisms = runtime?.targets ?? [];
  const results = runtime?.durable_result_count ?? state.results.size;
  const activeObservations = replay?.observations_emitted ?? 0;
  const inputRate = replay && replay.elapsed_wall_seconds > 0
    ? (replay.records_read / replay.elapsed_wall_seconds).toFixed(1)
    : null;
  const prefixes = (target: RuntimeTarget) => target.lane_id.split(".")[0] ?? "";
  const pathTargets = new Map(familyCards.map((card) => [card.id, mechanisms.filter((target) => card.prefixes.includes(prefixes(target)))]));
  const visibility = state.pageError ? "Service unavailable" : runtime ? "Quality details per Result" : "Connecting";

  return <section className="page active-page" aria-labelledby="overview-title">
    <PageHeading titleId="overview-title" title="Overview" deck="Runtime activity, six family decompositions, and derived investigation context." meta={<span className="live-label"><i />{runtime?.state === "REPLAYING" ? "Replay in progress" : "Runtime connected"}</span>} />

    <section className="panel overview-runtime-panel">
      <div className="panel-head compact"><div><span className="eyebrow">{runtime?.state === "REPLAYING" ? "LIVE REPLAY" : "CURRENT RUNTIME Â· LATEST REPLAY COUNTERS"}</span><h2>Streaming and evidence state</h2><p>Replay counters describe the current run or the most recently completed run. Other values reflect current service state.</p></div><span className={`status-chip ${runtime?.state === "REPLAYING" ? "running" : ""}`}>{runtime?.state ?? "CONNECTING"}</span></div>
      <div className="runtime-strip">
        <RuntimeMetric label={replay?.state === "RUNNING" ? "Live input" : "Latest replay input"} value={replay?.records_read ? `${replay.records_read} records` : "No replay"} detail={`${replay?.observations_emitted ?? 0} observations Â· ${inputRate ? `${inputRate} records/s` : "rate unavailable"}`} />
        <RuntimeMetric label="Visibility" value={visibility} detail="Quality and visibility are reported with each Result" />
        <RuntimeMetric label="Analytics" value={`${runtime?.targets.length ?? 0} registered`} detail={`${runtime?.family_status.length ?? 0} runtime family statuses`} />
        <RuntimeMetric label="Results" value={results.toLocaleString()} detail="Durable mechanism Results" />
        <RuntimeMetric label="Family evidence" value={String(views.length)} detail="Current composed family views" />
        <RuntimeMetric label="Investigations" value={String(links.length)} detail="Exact shared-observation links" />
      </div>
      <div className="runtime-step-links" aria-label="Runtime progression">
        {[["Observations", "replay"], ["Analytics", "replay"], ["Results", "results"], ["Family evidence", "alerts"], ["Investigations", "investigations"]].map(([label, page], index) => <span className="runtime-step-wrap" key={label}><button className="runtime-step" onClick={() => navigate(page as PageKey)}><strong>{label}</strong><small>{index === 0 ? `${activeObservations} emitted` : index === 1 ? `${mechanisms.length} registered` : index === 2 ? `${results.toLocaleString()} durable` : index === 3 ? `${views.length} views` : `${links.length} links`}</small></button>{index < 4 && <i aria-hidden="true">â†’</i>}</span>)}
      </div>
    </section>

    <section className="overview-family-section">
        <div className="section-title-row"><div><h2>Threat-family coverage</h2><p>Mechanisms remain independent; a family card describes the current decomposition.</p></div><button className="text-button" onClick={() => navigate("replay")}>Runtime capability details â†’</button></div>
      <div className="family-card-grid">{familyCards.map((card) => {
        const targets = pathTargets.get(card.id) ?? [];
        const runtimeState = runtime?.family_status.find((item) => card.statusMatch.some((name) => item.family.toLowerCase().includes(name)));
        return <article className="overview-family-card" key={card.id}>
          <header><h3>{card.title}</h3><span className={`family-state-chip${targets.length ? " active" : " inactive"}`}>{targets.length ? `${targets.length} registered` : "No registered mechanism"}</span></header>
          <ul>{card.paths.map((path) => <li key={path}><span className={targets.length ? "path-dot active" : "path-dot"} />{path}</li>)}</ul>
          {card.note && <p className="family-card-note">{card.note}</p>}
          {runtimeState && <small className="runtime-family-status">Runtime status: {readable(runtimeState.status)}</small>}
        </article>;
      })}</div>
    </section>

    <section className="panel performance-panel">
      <div className="panel-head compact"><div><span className="eyebrow">{replay?.state === "RUNNING" ? "LIVE REPLAY" : "CURRENT SERVICE Â· LATEST REPLAY"}</span><h2>Runtime performance and bounded state</h2><p>Replay throughput is shown separately from latency and state measures the live service does not expose.</p></div></div>
      <div className="performance-grid">
        <div><span>{replay?.state === "RUNNING" ? "Live input" : "Latest replay input"}</span><strong>{replay ? `${replay.records_read} / ${replay.observations_emitted}` : "Not measured"}</strong><small>Records read / observations emitted</small></div>
        <div><span>Replay wall time</span><strong>{replay ? `${replay.elapsed_wall_seconds.toFixed(2)} s` : "Not measured"}</strong><small>Current run or most recently completed replay</small></div>
        <div><span>Processing p50 / p95</span><strong>Not exposed</strong><small>Live service has no processing latency samples</small></div>
        <div><span>End-to-end evidence latency</span><strong>Not exposed</strong><small>Persistence timing is not in the live API</small></div>
        <div><span>State footprint</span><strong>Not exposed</strong><small>Current active state entries are not reported</small></div>
        <div><span>Queue / pressure</span><strong>Not exposed</strong><small>No live queue-depth metric is reported</small></div>
      </div>
      <div className="benchmark-card">
        <div className="benchmark-heading"><div><span className="eyebrow">MEASURED BENCHMARK</span><h3>Governed development operating point</h3><p>50 offered observations/s Â· 30 s Â· mixed workload Â· 3 measured runs</p></div><span className="benchmark-tag">Historical</span></div>
        <div className="benchmark-stats"><BenchmarkStat label="Input/runtime drops" value="0 in each run" /><BenchmarkStat label="Processing latency median across runs" value="p50 198 ms Â· p95 873 ms Â· p99 1,025 ms" /><BenchmarkStat label="End-to-end evidence latency median" value="p50 316 ms Â· p95 1,002 ms Â· p99 1,266 ms" /><BenchmarkStat label="Peak RSS across runs" value="233.1 MB" /></div>
        <p className="benchmark-caveat">Controlled development benchmark, not production capacity or an SLA. Latency values are medians of the three 50 observations/s runs; peak RSS is the highest measured run. SSE notification loss is outside the runtime drop count. Source artifact: <code>benchmark_results/sustained_final_mvp_benchmark.json</code>, captured 2026-09-23.</p>
      </div>
    </section>
    <div className="overview-actions"><button className="primary-button" onClick={() => navigate("replay")}>Open Traffic Lab</button><button className="secondary-button" onClick={() => navigate("alerts")}>Review family evidence</button><button className="secondary-button" onClick={() => navigate("investigations")}>Open investigations</button><button className="text-button" onClick={() => navigate("results")}>Browse mechanism Evidence â†’</button></div>
  </section>;
}

function RuntimeMetric({ label, value, detail }: { label: string; value: string; detail: string }) {
  return <div className="runtime-metric"><span>{label}</span><strong>{value}</strong><small>{detail}</small></div>;
}
function BenchmarkStat({ label, value }: { label: string; value: string }) {
  return <div><span>{label}</span><strong>{value}</strong></div>;
}
