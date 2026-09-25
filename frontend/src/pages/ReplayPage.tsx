import { useEffect, useMemo, useRef, useState } from "react";
import { useEvidence } from "../state/EvidenceContext";
import { PageHeading, EmptyState } from "../components/common/Primitives";
import { familyLabel, formatShortTime, friendlyCategory, readable, summarizeReference } from "../utils/formatting";
import { useReplay } from "../hooks/useReplay";
import type { PageKey } from "../state/types";
import { VisualTrace } from "../components/flow/VisualTrace";

export function ReplayPage({ navigate }: { navigate: (page: PageKey) => void }) {
  const { state } = useEvidence();
  const { scenarios, replay, error, start, busy } = useReplay();
  const [speed, setSpeed] = useState(0);
  const [traceOpen, setTraceOpen] = useState(false);
  const [runBaseline, setRunBaseline] = useState<{ results: Set<string>; alerts: Set<string>; statuses: Set<string> } | null>(null);
  const traceTrigger = useRef<HTMLButtonElement>(null);
  const traceClose = useRef<HTMLButtonElement>(null);
  const running = replay?.state === "RUNNING";
  const selectedScenario = scenarios.find((scenario) => scenario.id === replay?.scenario);
  const scenarioName = selectedScenario?.label || "Traffic replay";
  const sourceType = replay?.source_type || selectedScenario?.source_type || "Controlled observations";
  const sourceLabel = (value: string) => /pcap/i.test(value) ? "Recorded PCAP" : /ndjson|typed/i.test(value) ? "Controlled observation stream" : value;
  const groups = useMemo(() => scenarios.reduce<Record<string, typeof scenarios>>((acc, scenario) => {
    const pcap = /pcap/i.test(scenario.source_type);
    (acc[pcap ? "Packet capture" : "Controlled scenarios"] ??= []).push(scenario);
    return acc;
  }, {}), [scenarios]);
  useEffect(() => {
    if (traceOpen) traceClose.current?.focus();
    else traceTrigger.current?.focus();
  }, [traceOpen]);
  const runEvents = runBaseline ? [...state.results.values()].filter((item) => !runBaseline.results.has(item.result_id)) : [];
  const reviewCount = runBaseline ? state.alerts.filter((item) => !runBaseline.alerts.has(item.alert_id)).length : 0;
  const limitationCount = runBaseline ? state.statusItems.filter((item) => !runBaseline.statuses.has(item.status_id)).length : 0;
  const runScenario = (id: string) => {
    setRunBaseline({ results: new Set(state.results.keys()), alerts: new Set(state.alerts.map((item) => item.alert_id)), statuses: new Set(state.statusItems.map((item) => item.status_id)) });
    void start(id, speed);
  };

  return <section className="page active-page" aria-labelledby="replay-title">
    <PageHeading titleId="replay-title" title="Traffic lab" deck="Run controlled traffic through EvidenceGate." />
    <div className="replay-intro"><div className="replay-intro-mark" aria-hidden="true">▷</div><div><h2>Controlled observation replay and PCAP replay</h2><p>This lab replays supplied observations and recorded packet captures. It does not simulate a live network.</p></div></div>
    {state.runtime?.dga_model_readiness && state.runtime.dga_model_readiness !== "VERIFIED_READY" && <div className="stream-notice" role="status">DGA lexical model is unavailable. DGA scores will not be produced.</div>}
    <section className="panel replay-run-panel">
      <div className="panel-head compact"><div><h2>Choose a scenario</h2><p>Source type is reported by the runtime.</p></div><label className="speed-control">Replay rate<select value={speed} onChange={(event) => setSpeed(Number(event.target.value))}><option value={0}>Unpaced</option><option value={0.5}>0.5× event-time spacing</option><option value={1}>1× event-time spacing</option><option value={2}>2× event-time spacing</option></select></label></div>
      {Object.entries(groups).map(([group, items]) => <section className="scenario-group" key={group}><h3>{group}</h3><div className="scenario-grid">{items.map((scenario) => <article className="scenario-card" key={scenario.id}>
        <div className="scenario-title"><span className="scenario-icon" aria-hidden="true">▷</span><div><h4>{scenario.label}</h4><p>{sourceLabel(scenario.source_type)} · {familyLabel(scenario.family.toLowerCase())}</p></div></div>
        <p className="scenario-purpose">{scenario.family.toLowerCase() === "ddos" ? "Review traffic demand and related evidence." : `${friendlyCategory(scenario.family)} from the supplied source.`}</p>
        {scenario.family.toLowerCase() === "dga" && state.runtime?.dga_model_readiness !== "VERIFIED_READY" && <p className="scenario-limitation">DGA model unavailable; no lexical score will be returned.</p>}
        <button className="primary-button run-replay" disabled={running || busy} onClick={() => runScenario(scenario.id)}>{running ? "Replay running…" : busy ? "Starting…" : "Run scenario"}</button>
      </article>)}</div></section>)}
      {!scenarios.length && <EmptyState>No scenarios are available from the runtime.</EmptyState>}
    </section>
    <section className="panel replay-progress-panel"><div className="panel-head compact"><div><h2>{running ? `Running ${scenarioName}` : replay?.state === "FAILED" ? "Replay failed" : replay?.state === "COMPLETED" ? `${scenarioName} completed` : "No scenario is running"}</h2></div><span className={`status-chip${running ? " running" : replay?.state === "FAILED" ? " warning" : " neutral"}`}>{running ? "Running" : replay?.state === "COMPLETED" ? "Completed" : replay?.state === "FAILED" ? "Failed" : "Idle"}</span></div>
      <div className="progress-track"><div className={running ? "indeterminate" : ""} style={{ width: running ? "35%" : replay?.state === "COMPLETED" ? "100%" : "0%" }} /></div>
      {replay && <div className="replay-counters">{[["Source", sourceLabel(sourceType)], ["Records read", replay.records_read], ["Observations processed", replay.observations_emitted], ["Evidence results", replay.results_persisted], ["Elapsed", `${replay.elapsed_wall_seconds.toFixed(2)} s`]].map(([label, value]) => <div key={String(label)}><span className="field-label">{label}</span><strong>{value}</strong></div>)}</div>}
      <div className="replay-message" role="status">{error || replay?.error || (running ? "Processing supplied source observations. Results appear as they are persisted." : replay?.state === "COMPLETED" ? "Replay completed. Results are available in Evidence." : "Choose a scenario to begin." )}</div>
      {replay?.state === "COMPLETED" && <div className="run-summary"><strong>Completed</strong><span>{replay.observations_emitted} observations processed</span><span>{replay.results_persisted} evidence results</span><span>{reviewCount} items requiring review</span><span>{limitationCount} evidence or status limitations</span><button className="text-button" onClick={() => navigate("results")}>View results →</button><button ref={traceTrigger} className="text-button" onClick={() => setTraceOpen(true)}>View processing trace →</button></div>}
      {running && <button ref={traceTrigger} className="text-button trace-open-button" onClick={() => setTraceOpen(true)}>View processing trace →</button>}
    </section>
    <section className="panel replay-flow-panel"><div className="panel-head compact"><div><h2>Recent output</h2><p>Evidence received in this session.</p></div><button className="text-button" onClick={() => navigate("results")}>View evidence →</button></div><div className="replay-event-log">{state.replayEvents.length ? state.replayEvents.map((result) => <div className="event-log-item" key={result.result_id}><time>{formatShortTime(result.created_time)}</time><strong>{familyLabel(result.family.toLowerCase())}</strong><span>{readable(result.result_type)} · {summarizeReference(result.entity_reference, result.mechanism_id)}</span></div>) : <span className="log-empty">No evidence results received in this session.</span>}</div></section>
    {traceOpen && <div className="trace-modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setTraceOpen(false); }}><section className="trace-modal" role="dialog" aria-modal="true" aria-labelledby="trace-modal-title" onKeyDown={(event) => {
      if (event.key === "Escape") { event.stopPropagation(); setTraceOpen(false); }
      if (event.key === "Tab") {
        const nodes = event.currentTarget.querySelectorAll<HTMLElement>('button:not([disabled]), [href], select, input, [tabindex]:not([tabindex="-1"])');
        const first = nodes[0]; const last = nodes[nodes.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }
    }}><div className="trace-modal-head"><div><h2 id="trace-modal-title">Processing trace</h2><p>{scenarioName} · {sourceLabel(sourceType)}</p></div><button ref={traceClose} className="inspector-close" aria-label="Close processing trace" onClick={() => setTraceOpen(false)}>×</button></div><VisualTrace events={runEvents} pace="demo" /></section></div>}
  </section>;
}
