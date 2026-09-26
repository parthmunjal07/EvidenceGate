import { useEffect, useMemo, useRef, useState } from "react";
import { useEvidence } from "../state/EvidenceContext";
import { EmptyState, PageHeading } from "../components/common/Primitives";
import { api } from "../api/client";
import type { FamilyEvidenceViewDto, InvestigationLinkDto, RuntimeTraceEvent } from "../api/types";
import { familyLabel, formatShortTime, friendlyCategory, mechanismLabel, observationLineageLabel, readable, summarizeReference } from "../utils/formatting";
import { useReplay } from "../hooks/useReplay";
import type { PageKey } from "../state/types";
import { fetchFinalRuntimeTrace, latestReadinessByObservationLane, mergeRuntimeTraceEvents, observationLaneKey } from "../utils/runtimeTrace";

const observationLabel = (value: string | null) => value ? readable(value).toUpperCase() : "OBSERVATION";
const readinessLabel = (event: RuntimeTraceEvent | undefined, hasResult: boolean) => {
  if (hasResult) return "Evidence produced";
  if (!event) return "Waiting for relevant traffic";
  if (event.readiness === "READY") return "Ready";
  if (event.readiness === "WARMING_UP" || event.readiness === "INSUFFICIENT_HISTORY") return "Building context";
  if (event.readiness === "INSUFFICIENT_VISIBILITY" || event.readiness === "PREREQUISITE_MISSING") return "Missing required evidence";
  if (event.readiness === "STATE_EVICTED") return "Insufficient evidence";
  if (event.kind === "ADMISSION_REJECTED") return "Missing required evidence";
  if (event.kind === "ANALYTIC_EVALUATING") return "Evaluating";
  return event.readiness ? readable(event.readiness) : "Evaluating";
};

export function ReplayPage({ navigate }: { navigate: (page: PageKey) => void }) {
  const { state } = useEvidence();
  const { scenarios, replay, error, start, busy } = useReplay();
  const [speed, setSpeed] = useState(0);
  const [trace, setTrace] = useState<RuntimeTraceEvent[]>([]);
  const [cursor, setCursor] = useState(0);
  const [baseline, setBaseline] = useState<Set<string> | null>(null);
  const [familyViews, setFamilyViews] = useState<FamilyEvidenceViewDto[]>([]);
  const [investigationLinks, setInvestigationLinks] = useState<InvestigationLinkDto[]>([]);
  const [showPicker, setShowPicker] = useState(true);
  const previousReplayState = useRef(replay?.state);
  const running = replay?.state === "RUNNING";
  const selectedScenario = scenarios.find((scenario) => scenario.id === replay?.scenario);
  const scenarioName = selectedScenario?.label || "Traffic replay";
  const sourceType = replay?.source_type || selectedScenario?.source_type || "Controlled observations";
  const sourceLabel = (value: string) => /pcap/i.test(value) ? "PCAP replay" : /ndjson|typed/i.test(value) ? "NDJSON" : value;

  useEffect(() => {
    if (!running) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const update = await api.runtimeTrace(cursor, controller.signal);
        if (update.events.length) setTrace((current) => mergeRuntimeTraceEvents(current, update.events));
        setCursor((current) => Math.max(current, update.latest_sequence));
      } catch { /* Trace delivery is optional; replay processing continues. */ }
      if (!controller.signal.aborted) timer = setTimeout(poll, 350);
    };
    void poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [running, cursor]);

  useEffect(() => {
    const previous = previousReplayState.current;
    previousReplayState.current = replay?.state;
    if (replay?.state !== "COMPLETED") return;
    const controller = new AbortController();
    void fetchFinalRuntimeTrace(previous, replay.state, cursor, (after) => api.runtimeTrace(after, controller.signal)).then((update) => {
      if (!update) return;
      if (controller.signal.aborted) return;
      setTrace((current) => mergeRuntimeTraceEvents(current, update.events));
      setCursor((current) => Math.max(current, update.latest_sequence));
    }).catch(() => { /* Final presentation telemetry is optional; persisted Results remain authoritative. */ });
    return () => controller.abort();
  }, [replay?.state, cursor]);

  useEffect(() => {
    if (replay?.state !== "COMPLETED" || baseline === null) return;
    const controller = new AbortController();
    void api.investigations(controller.signal).then((value) => {
      if (controller.signal.aborted) return;
      setFamilyViews(value.family_views);
      setInvestigationLinks(value.links);
    }).catch(() => { /* Family views are derived presentation; persisted Results remain available. */ });
    return () => controller.abort();
  }, [replay?.state, replay?.finished_at, baseline]);

  const runScenario = async (id: string) => {
    let latestSequence = 0;
    try {
      const latest = await api.runtimeTrace(0);
      latestSequence = latest.latest_sequence;
    } catch { /* Optional trace startup must not gate source processing. */ }
    setCursor(latestSequence);
    setTrace([]);
    setBaseline(new Set(state.results.keys()));
    setFamilyViews([]);
    setInvestigationLinks([]);
    setShowPicker(false);
    await start(id, speed);
  };

  const runResults = useMemo(() => baseline
    ? [...state.results.values()]
      .filter((item) => !baseline.has(item.result_id))
      .sort((a, b) => a.created_time.localeCompare(b.created_time))
    : [], [state.results, baseline]);
  const observations = useMemo(() => {
    const unique = new Map<string, RuntimeTraceEvent>();
    for (const event of trace) if (event.kind === "OBSERVATION_CREATED" && event.observation_id) unique.set(event.observation_id, event);
    return [...unique.values()].slice(-8).reverse();
  }, [trace]);
  const analytics = useMemo(() => {
    const routed = new Map<string, RuntimeTraceEvent>();
    const recent = trace.filter((event) => event.observation_id === observations[0]?.observation_id);
    for (const event of recent) if (event.kind === "ROUTED" && event.lane_id) routed.set(event.lane_id, event);
    const latest = latestReadinessByObservationLane(trace);
    return [...routed.values()].map((route) => {
      const results = runResults.filter((item) => item.lane_id === route.lane_id && item.source_observation_ids.includes(route.observation_id || ""));
      const status = results.some((item) => item.result_type === "ANALYTIC_UNAVAILABLE") ? "Unavailable"
        : results.some((item) => item.result_type === "INSUFFICIENT_EVIDENCE" || item.missing_prerequisites.length > 0) ? "Insufficient evidence"
          : readinessLabel(latest.get(observationLaneKey(route.observation_id || "", route.lane_id!)), results.length > 0);
      return { ...route, status };
    });
  }, [trace, observations, runResults]);
  const sourceRecords = sourceType.toLowerCase().includes("pcap") ? "Packets read" : "Records read";
  const reviewCount = runResults.filter((item) => item.result_type === "REVIEW_FINDING").length;
  const limitationCount = runResults.length - reviewCount;
  const runResultIds = new Set(runResults.map((item) => item.result_id));
  const runFamilyViews = familyViews.filter((view) => view.source_result_ids.some((id) => runResultIds.has(id)));
  const runFamilyIds = new Set(runFamilyViews.map((view) => view.family_view_id));
  const runLinks = investigationLinks.filter((link) => runFamilyIds.has(link.left_family_view_id) && runFamilyIds.has(link.right_family_view_id));
  const viewsById = new Map(runFamilyViews.map((view) => [view.family_view_id, view]));

  return <section className="page active-page" aria-labelledby="replay-title">
    <PageHeading titleId="replay-title" title="Traffic lab" deck="Watch prepared passive input move through the runtime and into independent evidence." />
    {state.runtime?.dga_model_readiness && state.runtime.dga_model_readiness !== "VERIFIED_READY" && <div className="stream-notice" role="status">DGA lexical model is unavailable. DGA scores will not be produced.</div>}

    {(!replay || showPicker) && <section className="panel scenario-picker-panel">
      <div className="panel-head compact"><div><h2>Choose a scenario</h2><p>Prepared NDJSON observations and recorded PCAP sources.</p></div><label className="speed-control">Replay rate<select value={speed} onChange={(event) => setSpeed(Number(event.target.value))}><option value={0}>Unpaced</option><option value={0.5}>0.5× event-time spacing</option><option value={1}>1× event-time spacing</option><option value={2}>2× event-time spacing</option></select></label></div>
      <div className="scenario-list">{scenarios.map((scenario) => <div className="scenario-row" key={scenario.id}><div><strong>{scenario.label}</strong><span>{sourceLabel(scenario.source_type)} · {familyLabel(scenario.family.toLowerCase())}</span></div><button className="primary-button" disabled={running || busy} onClick={() => void runScenario(scenario.id)}>{busy && replay?.scenario === scenario.id ? "Starting…" : "Run"}</button></div>)}</div>
      {!scenarios.length && <EmptyState>No scenarios are available from the runtime.</EmptyState>}
    </section>}

    {replay && <>
      <section className="panel runtime-workbench">
        <div className="panel-head compact"><div><span className="eyebrow">LIVE SOURCE · {sourceLabel(sourceType)}</span><h2>{scenarioName}</h2><p>{running ? "Runtime events update from processing telemetry." : replay.state === "COMPLETED" ? "Source processing completed." : replay.state === "FAILED" ? "Source processing failed." : "Latest replay."}</p></div><span className={`status-chip${running ? " running" : replay.state === "FAILED" ? " warning" : " neutral"}`}>{replay.state}</span></div>
        <div className="replay-counters runtime-counters">{[[sourceRecords, replay.records_read], ["Observations", replay.observations_emitted], ["Results persisted", replay.results_persisted], ["Review items", reviewCount], ["Limitations", limitationCount], ["Elapsed", `${replay.elapsed_wall_seconds.toFixed(2)} s`]].map(([label, value]) => <div key={String(label)}><span className="field-label">{label}</span><strong>{value}</strong></div>)}</div>
        <div className="runtime-path" aria-label="Runtime path"><span className={trace.some((event) => event.kind === "SOURCE_RECORD_ACCEPTED") ? "is-active" : ""}>Source</span><i>→</i><span className={trace.some((event) => event.kind === "OBSERVATION_CREATED") ? "is-active" : ""}>Canonical observation</span><i>→</i><span className={trace.some((event) => event.kind === "VISIBILITY_EVALUATED") ? "is-active" : ""}>Visibility / quality</span><i>→</i><span className={trace.some((event) => event.kind === "ROUTED") ? "is-active" : ""}>Zero-to-many routing</span><i>→</i><span className={trace.some((event) => event.readiness) ? "is-active" : ""}>Mechanism readiness</span><i>→</i><span className={replay.results_persisted ? "is-active" : ""}>Immutable Results</span><i>→</i><span className={runFamilyViews.length ? "is-active" : ""}>Family composition</span><i>→</i><span className={runLinks.length ? "is-active" : ""}>Investigation link</span></div>
      </section>

      <div className="runtime-workbench-grid">
        <section className="panel runtime-observations"><div className="panel-head compact"><div><h2>Live observations</h2><p>Latest canonical observation events</p></div><span className="count-badge">{observations.length}</span></div>
          {observations.length ? <div className="runtime-event-list">{observations.map((event) => { const visibility = trace.find((item) => item.observation_id === event.observation_id && item.kind === "VISIBILITY_EVALUATED"); return <div className="runtime-event-row" key={event.sequence}><time>{new Date(event.occurred_at).toLocaleTimeString([], { hour12: false, minute: "2-digit", second: "2-digit" })}</time><strong>{observationLabel(event.observation_type)}</strong><span>{visibility?.reason || "Visibility facts unavailable"}</span></div>; })}</div> : <p className="runtime-empty">Waiting for source observations.</p>}
        </section>
        <section className="panel runtime-analytics"><div className="panel-head compact"><div><h2>Zero-to-many analytic routing</h2><p>{observations[0] ? `${observationLabel(observations[0].observation_type)} branches independently to eligible mechanisms` : "Actual router branches for the latest observation"}</p></div><span className="count-badge">{analytics.length} routes</span></div>
          {analytics.length ? <div className="runtime-analytic-list">{analytics.map((item) => <div className="runtime-analytic-row" key={`${item.observation_id}-${item.lane_id}`}><div><strong>{mechanismLabel(item.mechanism || item.lane_id || "Analytic")}</strong><span>{item.observation_type ? observationLabel(item.observation_type) : "Observation route"}</span></div><em>{item.status}</em></div>)}</div> : <p className="runtime-empty">No analytics have been routed yet.</p>}
        </section>
      </div>

      <section className="panel replay-flow-panel"><div className="panel-head compact"><div><h2>New evidence</h2><p>Immutable results persisted during this replay.</p></div><button className="text-button" onClick={() => navigate("results")}>Open Evidence →</button></div>
        {runResults.length ? <div className="replay-event-log">{runResults.slice(-10).reverse().map((result) => <div className="event-log-item" key={result.result_id}><time>{formatShortTime(result.created_time)}</time><strong>{friendlyCategory(result.taxonomy[1])}</strong><span>{mechanismLabel(result.mechanism_id || result.lane_id)} · {summarizeReference(result.entity_reference, result.mechanism_id)}{observationLineageLabel(result.source_observation_ids) ? ` · ${observationLineageLabel(result.source_observation_ids)}` : ""}</span><em>{result.result_type === "REVIEW_FINDING" ? "Review" : "Limitation"}</em></div>)}</div> : <p className="runtime-empty">Results will appear here after persistence.</p>}
      </section>
      <section className="panel replay-flow-panel"><div className="panel-head compact"><div><h2>Family evidence</h2><p>Independent Results composed by family and shared source lineage.</p></div><button className="text-button" onClick={() => navigate("alerts")}>Open analyst queue →</button></div>
        {runFamilyViews.length ? <div className="family-stage-list">{runFamilyViews.map((view) => <article key={view.family_view_id}><strong>{view.family}</strong><span>{view.source_result_ids.length} mechanism Results → {view.findings.length} independent findings</span><small>{view.entity_references.map((entity) => summarizeReference(entity)).join(", ")}</small></article>)}</div> : <p className="runtime-empty">Family evidence will appear after the read-only view is refreshed.</p>}
      </section>
      <section className="panel replay-flow-panel"><div className="panel-head compact"><div><h2>Related for investigation</h2><p>Exact shared source observations link different official families.</p></div></div>
        {runLinks.length ? <div className="family-stage-list">{runLinks.map((link) => { const left = viewsById.get(link.left_family_view_id); const right = viewsById.get(link.right_family_view_id); return left && right ? <article key={link.link_id}><strong>{left.family} evidence ↕ {right.family} evidence</strong><span>Shared passive observation</span><small>For joint investigation only; this does not establish causality, a common attacker, or an attack chain.</small></article> : null; })}</div> : <p className="runtime-empty">No cross-family shared observation is present in this replay.</p>}
      </section>
      <div className="run-summary"><span>{replay.observations_emitted} observations processed</span><span>{replay.results_persisted} results persisted</span><span>{reviewCount} review items · {limitationCount} limitations</span>{!running && <button className="text-button" onClick={() => setShowPicker((value) => !value)}>{showPicker ? "Hide scenarios" : "Run another scenario"}</button>}</div>
      {error && <div className="stream-notice" role="status">{error}</div>}
    </>}
  </section>;
}
