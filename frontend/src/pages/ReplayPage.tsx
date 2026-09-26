import { useEffect, useMemo, useRef, useState } from "react";
import { useEvidence } from "../state/EvidenceContext";
import { EmptyState, PageHeading } from "../components/common/Primitives";
import { api } from "../api/client";
import type { FamilyEvidenceViewDto, InvestigationLinkDto, ResultDto, RuntimeTraceEvent } from "../api/types";
import { compareTimeAsc, familyLabel, formatEvidenceDateTime, formatShortTime, formatTimeZoneLabel, friendlyCategory, groupFamilyFindings, mechanismLabel, pluralize, readable, summarizeReference } from "../utils/formatting";
import { useReplay } from "../hooks/useReplay";
import { useTimeZone } from "../state/TimeZoneContext";
import type { PageKey } from "../state/types";
import type { NavigationContext } from "../state/navigation";
import { drainRuntimeTraceCursor, latestReadinessByObservationLane, mergeRuntimeTraceEvents, observationLaneKey } from "../utils/runtimeTrace";
import { newPersistedReplayRows, sourceLinkedReplayResults } from "../utils/replayAttribution";
import { clearLatestReplayMarker, saveLatestReplayMarker } from "../utils/latestReplayScope";

type Presentation = "demo" | "runtime";
type Lifecycle = "IDLE" | "STARTING" | "PROCESSING" | "FINALIZING" | "READY" | "FAILED";

const observationLabel = (value: string | null) => value ? readable(value) : "Packet observation";
const traceBatchDelay = (first: RuntimeTraceEvent) => first.kind === "SOURCE_RECORD_ACCEPTED" ? 90 : 100;
const readinessLabel = (event: RuntimeTraceEvent | undefined) => {
  if (!event) return "Routed";
  if (event.kind === "ANALYTIC_EVALUATING") return "Evaluating";
  if (event.readiness === "READY" || event.readiness === "TERMINAL_EVIDENCE_PENDING") return "Evaluated";
  if (event.readiness === "WARMING_UP" || event.readiness === "INSUFFICIENT_HISTORY") return "Building context";
  if (event.readiness === "INSUFFICIENT_VISIBILITY" || event.readiness === "PREREQUISITE_MISSING" || event.kind === "ADMISSION_REJECTED") return "Insufficient evidence";
  if (event.readiness === "STATE_EVICTED") return "Insufficient evidence";
  return event.readiness ? readable(event.readiness) : "Evaluating";
};
const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export function ReplayPage({ navigate }: { navigate: (page: PageKey, context?: NavigationContext) => void }) {
  const { state, dispatch } = useEvidence();
  const { zone } = useTimeZone();
  const { scenarios, replay, error, start, busy } = useReplay();
  const [presentation, setPresentation] = useState<Presentation>("demo");
  const [receivedTrace, setReceivedTrace] = useState<RuntimeTraceEvent[]>([]);
  const [pacedTrace, setPacedTrace] = useState<RuntimeTraceEvent[]>([]);
  const [baseline, setBaseline] = useState<Set<string> | null>(null);
  const [runResults, setRunResults] = useState<ResultDto[]>([]);
  const [newRowsPersisted, setNewRowsPersisted] = useState(0);
  const [pacedResults, setPacedResults] = useState(0);
  const [familyViews, setFamilyViews] = useState<FamilyEvidenceViewDto[]>([]);
  const [investigationLinks, setInvestigationLinks] = useState<InvestigationLinkDto[]>([]);
  const [familiesPresented, setFamiliesPresented] = useState(false);
  const [linksPresented, setLinksPresented] = useState(false);
  const [derivedUnavailable, setDerivedUnavailable] = useState(false);
  const [traceUnavailable, setTraceUnavailable] = useState(false);
  const [resultSyncUnavailable, setResultSyncUnavailable] = useState(false);
  const [lifecycle, setLifecycle] = useState<Lifecycle>("IDLE");
  const [selectedObservationId, setSelectedObservationId] = useState<string | null>(null);
  const [showPicker, setShowPicker] = useState(true);
  const presentationRef = useRef(presentation);
  const presentedTrace = presentation === "runtime" ? receivedTrace : pacedTrace;
  const presentedResults = presentation === "runtime" ? runResults.length : pacedResults;
  const traceCursor = useRef(0);
  const traceIssueRef = useRef(false);
  const receivedRef = useRef(receivedTrace);
  const presentedRef = useRef(presentedTrace);
  const presentedResultsRef = useRef(presentedResults);
  const runResultsRef = useRef(runResults);
  const baselineRef = useRef<Set<string> | null>(null);
  const activeReplayStartedAt = useRef<string | null>(null);
  const replayTraceStartSequence = useRef<number | null>(null);
  const finalizingStartedAt = useRef<string | null>(null);
  useEffect(() => {
    receivedRef.current = receivedTrace;
    presentedRef.current = presentedTrace;
    presentedResultsRef.current = presentedResults;
    runResultsRef.current = runResults;
    baselineRef.current = baseline;
    presentationRef.current = presentation;
  }, [receivedTrace, presentedTrace, presentedResults, runResults, baseline, presentation]);

  const selectedScenario = scenarios.find((scenario) => scenario.id === replay?.scenario);
  const scenarioName = selectedScenario?.label || "Traffic replay";
  const sourceType = replay?.source_type || selectedScenario?.source_type || "Controlled observations";
  const sourceLabel = (value: string) => /pcap/i.test(value) ? "Recorded PCAP replay" : /ndjson|typed/i.test(value) ? "Controlled NDJSON replay" : value;
  const running = lifecycle === "STARTING" || lifecycle === "PROCESSING" || lifecycle === "FINALIZING";
  const tracePolling = lifecycle === "PROCESSING" || lifecycle === "FINALIZING";

  useEffect(() => {
    if (!tracePolling) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const update = await api.runtimeTrace(traceCursor.current, controller.signal);
        if (update.events.length) {
          if (update.events[0]!.sequence > traceCursor.current + 1) {
            traceIssueRef.current = true;
            setTraceUnavailable(true);
          }
          const merged = mergeRuntimeTraceEvents(receivedRef.current, update.events);
          receivedRef.current = merged;
          setReceivedTrace(merged);
          traceCursor.current = Math.max(traceCursor.current, update.events.at(-1)?.sequence ?? traceCursor.current);
        }
      } catch { traceIssueRef.current = true; setTraceUnavailable(true); }
      if (!controller.signal.aborted) timer = setTimeout(poll, 300);
    };
    void poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [tracePolling]);

  useEffect(() => {
    if (presentation === "runtime") return;
    if (presentedTrace.length >= receivedTrace.length) return;
    const start = presentedTrace.length;
    const event = receivedTrace[start];
    if (!event) return;
    let end = start + 1;
    if (event.kind === "SOURCE_RECORD_ACCEPTED") {
      while (end < receivedTrace.length && receivedTrace[end]?.kind !== "SOURCE_RECORD_ACCEPTED") end += 1;
    } else if (event.observation_id) {
      while (end < receivedTrace.length && receivedTrace[end]?.observation_id === event.observation_id) end += 1;
    }
    const timer = setTimeout(() => setPacedTrace((current) => {
      const value = receivedTrace.slice(current.length, end);
      if (!value.length) return current;
      const next = [...current, ...value];
      presentedRef.current = next;
      return next;
    }), traceBatchDelay(event));
    return () => clearTimeout(timer);
  }, [presentation, receivedTrace, presentedTrace.length]);

  useEffect(() => {
    if (presentation === "runtime") return;
    if (presentedResults >= runResults.length) return;
    const timer = setTimeout(() => setPacedResults((current) => {
      const next = Math.min(current + 1, runResultsRef.current.length);
      presentedResultsRef.current = next;
      return next;
    }), 260);
    return () => clearTimeout(timer);
  }, [presentation, runResults.length, presentedResults]);

  const runScenario = async (id: string) => {
    setLifecycle("STARTING");
    clearLatestReplayMarker();
    replayTraceStartSequence.current = null;
    setTraceUnavailable(false);
    traceIssueRef.current = false;
    setResultSyncUnavailable(false);
    try {
      traceCursor.current = await drainRuntimeTraceCursor((after) => api.runtimeTrace(after));
      replayTraceStartSequence.current = traceCursor.current;
    } catch {
      traceCursor.current = 0;
      traceIssueRef.current = true;
      setTraceUnavailable(true);
    }
    setReceivedTrace([]);
    setPacedTrace([]);
    receivedRef.current = [];
    presentedRef.current = [];
    setRunResults([]);
    runResultsRef.current = [];
    setNewRowsPersisted(0);
    setPacedResults(0);
    setFamilyViews([]);
    setInvestigationLinks([]);
    setFamiliesPresented(false);
    setLinksPresented(false);
    setDerivedUnavailable(false);
    setSelectedObservationId(null);
    setShowPicker(false);
    try {
      const before = await api.allResults();
      const ids = new Set(before.map((result) => result.result_id));
      baselineRef.current = ids;
      setBaseline(ids);
      const started = await start(id, 0);
      if (!started) throw new Error("Replay could not be started");
      activeReplayStartedAt.current = started.started_at;
      if (replayTraceStartSequence.current === null) throw new Error("Runtime trace baseline is unavailable");
      setLifecycle("PROCESSING");
    } catch (cause) {
      setLifecycle("FAILED");
      baselineRef.current = null;
      setBaseline(null);
      if (cause instanceof Error) dispatch({ type: "error", value: cause.message });
    }
  };

  useEffect(() => {
    if (replay?.state !== "COMPLETED" || !baseline || !replay.started_at || replay.started_at !== activeReplayStartedAt.current) return;
    if (finalizingStartedAt.current === replay.started_at) return;
    finalizingStartedAt.current = replay.started_at;
    const controller = new AbortController();
    setLifecycle("FINALIZING");
    void (async () => {
      // Trace is explanatory only. Drain until the sequence is stable; durable Results remain authoritative.
      let stable = 0;
      let lastSequence = traceCursor.current;
      let drainedTrace: RuntimeTraceEvent[] = [];
      while (stable < 2) {
        try {
          const update = await api.runtimeTrace(traceCursor.current, controller.signal);
          if (update.events.length) {
            if (update.events[0]!.sequence > traceCursor.current + 1) {
              traceIssueRef.current = true;
              setTraceUnavailable(true);
            }
            drainedTrace = mergeRuntimeTraceEvents(drainedTrace, update.events);
            const merged = mergeRuntimeTraceEvents(receivedRef.current, update.events);
            receivedRef.current = merged;
            setReceivedTrace(merged);
            traceCursor.current = Math.max(traceCursor.current, update.events.at(-1)?.sequence ?? traceCursor.current);
          }
          stable = update.latest_sequence === lastSequence && update.events.length === 0 ? stable + 1 : 0;
          lastSequence = update.latest_sequence;
        } catch { traceIssueRef.current = true; setTraceUnavailable(true); stable = 2; }
        if (stable < 2) await sleep(120);
      }

      let durableSnapshot: ResultDto[] | null = null;
      const known = baselineRef.current ?? baseline;
      for (let attempt = 0; attempt < 8; attempt += 1) {
        try {
          durableSnapshot = await api.allResults(controller.signal);
          const newlyPersistedCount = durableSnapshot.filter((result) => !known.has(result.result_id)).length;
          if (newlyPersistedCount >= replay.results_persisted || attempt >= 2) break;
        } catch { if (attempt >= 2) { setResultSyncUnavailable(true); break; } }
        await sleep(120);
      }
      const durable = durableSnapshot ?? [];
      if (durableSnapshot === null) setResultSyncUnavailable(true);
      const sourceLinkedResults = traceIssueRef.current ? [] : sourceLinkedReplayResults(durable, mergeRuntimeTraceEvents(receivedRef.current, drainedTrace));
      const runResultsSorted = sourceLinkedResults.sort((a, b) => compareTimeAsc(a.created_time, b.created_time) || a.result_id.localeCompare(b.result_id));
      const newRows = newPersistedReplayRows(sourceLinkedResults, known);
      if (controller.signal.aborted) return;
      setNewRowsPersisted(newRows);
      runResultsRef.current = runResultsSorted;
      setRunResults(runResultsSorted);
      dispatch({ type: "results", value: runResultsSorted, animate: true });

      try {
        const derived = await api.investigations(controller.signal);
        const runIds = new Set(runResultsSorted.map((result) => result.result_id));
        const views = derived.family_views.filter((view) => view.source_result_ids.some((resultId) => runIds.has(resultId)));
        const viewIds = new Set(views.map((view) => view.family_view_id));
        const links = derived.links.filter((link) => viewIds.has(link.left_family_view_id) && viewIds.has(link.right_family_view_id));
        if (!controller.signal.aborted) { setFamilyViews(views); setInvestigationLinks(links); }
      } catch { if (!controller.signal.aborted) setDerivedUnavailable(true); }

      while (!controller.signal.aborted && presentationRef.current === "demo" && presentedRef.current.length < receivedRef.current.length) await sleep(80);
      while (!controller.signal.aborted && presentationRef.current === "demo" && presentedResultsRef.current < runResultsRef.current.length) await sleep(80);
      if (controller.signal.aborted) return;
      setFamiliesPresented(true);
      if (runResultsSorted.length && presentationRef.current === "demo") await sleep(280);
      if (controller.signal.aborted) return;
      setLinksPresented(true);
      if (runResultsSorted.length && presentationRef.current === "demo") await sleep(280);
      if (!controller.signal.aborted) setLifecycle("READY");
      if (!controller.signal.aborted && !traceIssueRef.current && replayTraceStartSequence.current !== null && replay.started_at && replay.finished_at && replay.scenario && replay.source_type) {
        saveLatestReplayMarker({ scenario: replay.scenario, sourceType: replay.source_type, startedAt: replay.started_at, finishedAt: replay.finished_at, startSequence: replayTraceStartSequence.current, endSequence: traceCursor.current });
      }
    })();
    return () => controller.abort();
  }, [replay?.state, replay?.started_at, replay?.finished_at, replay?.results_persisted, replay?.scenario, replay?.source_type, baseline, dispatch]);

  const observations = useMemo(() => {
    const map = new Map<string, RuntimeTraceEvent>();
    for (const event of presentedTrace) if (event.kind === "OBSERVATION_CREATED" && event.observation_id) map.set(event.observation_id, event);
    return [...map.values()];
  }, [presentedTrace]);
  const streamEvents = presentedTrace.filter((event) => event.kind === "SOURCE_RECORD_ACCEPTED" || event.kind === "OBSERVATION_CREATED");
  const observationRoutes = useMemo(() => {
    const map = new Map<string, RuntimeTraceEvent[]>();
    for (const event of presentedTrace) if (event.kind === "ROUTED" && event.observation_id && event.lane_id) {
      const rows = map.get(event.observation_id) ?? [];
      if (!rows.some((row) => row.lane_id === event.lane_id)) rows.push(event);
      map.set(event.observation_id, rows);
    }
    return map;
  }, [presentedTrace]);
  const selectedObservation = observations.find((event) => event.observation_id === selectedObservationId)
    ?? [...observations].reverse().find((event) => (observationRoutes.get(event.observation_id || "")?.length ?? 0) > 0)
    ?? observations.at(-1) ?? null;
  const visibleRunResults = runResults.slice(0, presentedResults);
  const analytics = useMemo(() => {
    const selectedId = selectedObservation?.observation_id;
    if (!selectedId) return [];
    const latest = latestReadinessByObservationLane(presentedTrace);
    const routes = observationRoutes.get(selectedId) ?? [];
    return routes.map((route) => {
      const results = visibleRunResults.filter((item) => item.lane_id === route.lane_id && item.source_observation_ids.includes(selectedId));
      const latestEvent = latest.get(observationLaneKey(selectedId, route.lane_id || ""));
      const status = results.some((item) => item.result_type === "ANALYTIC_UNAVAILABLE") ? "Unavailable"
        : results.some((item) => item.result_type === "INSUFFICIENT_EVIDENCE" || item.missing_prerequisites.length) ? "Insufficient evidence"
          : results.length ? "Evidence produced" : readinessLabel(latestEvent);
      return { ...route, status };
    });
  }, [presentedTrace, observationRoutes, visibleRunResults, selectedObservation?.observation_id]);

  const reviewCount = runResults.filter((item) => item.result_type === "REVIEW_FINDING").length;
  const limitationCount = runResults.length - reviewCount;
  const runResultIds = new Set(runResults.map((item) => item.result_id));
  const runFamilyViews = familiesPresented ? familyViews : [];
  const runFamilyIds = new Set(runFamilyViews.map((view) => view.family_view_id));
  const runLinks = linksPresented ? investigationLinks.filter((link) => runFamilyIds.has(link.left_family_view_id) && runFamilyIds.has(link.right_family_view_id)) : [];
  const viewsById = new Map(runFamilyViews.map((view) => [view.family_view_id, view]));
  const stageFacts = [
    presentedTrace.some((event) => event.kind === "SOURCE_RECORD_ACCEPTED"),
    presentedTrace.some((event) => event.kind === "OBSERVATION_CREATED"),
    presentedTrace.some((event) => event.kind === "ROUTED"),
    presentedTrace.some((event) => event.kind.startsWith("ANALYTIC_") || event.kind === "ADMISSION_REJECTED"),
    presentedResults > 0,
    runFamilyViews.length > 0,
    runLinks.length > 0,
  ];
  const activeStage = Math.max(1, stageFacts.lastIndexOf(true) + 2);
  const relateNotApplicable = lifecycle === "READY" && familiesPresented && runFamilyViews.length > 0 && runLinks.length === 0;
  const sourceRecords = sourceType.toLowerCase().includes("pcap") ? "Packets" : "Records";
  const diagnostic = lifecycle === "READY" && runResults.length === 0 && !resultSyncUnavailable ? traceUnavailable ? "Runtime trace unavailable; source-lineage Result attribution could not be established." : (replay?.results_persisted ?? 0) > 0 ? "The runtime reported persisted Results, but no durable Result could be linked to the current replay observations." : "Replay completed, but no mechanism Result was produced." : null;

  return <section className="page active-page" aria-labelledby="replay-title">
    <PageHeading titleId="replay-title" title="Traffic Lab" deck="Follow controlled passive replay from source records to independent evidence." />
    {state.runtime?.dga_model_readiness && state.runtime.dga_model_readiness !== "VERIFIED_READY" && <div className="stream-notice" role="status">DGA lexical model is unavailable. DGA scores will not be produced.</div>}

    {(!replay || showPicker) && <section className="panel scenario-picker-panel">
      <div className="panel-head compact"><div><h2>Prepared scenarios</h2><p>Controlled NDJSON replay and recorded PCAP replay. The input does not capture or generate network traffic.</p></div><label className="speed-control">Presentation pace<select value={presentation} onChange={(event) => setPresentation(event.target.value as Presentation)}><option value="demo">Demo pace</option><option value="runtime">As delivered by runtime</option></select></label></div>
      <div className="scenario-list">{scenarios.map((scenario) => <div className="scenario-row" key={scenario.id}><div><strong>{scenario.label}</strong><span>{sourceLabel(scenario.source_type)} · {familyLabel(scenario.family.toLowerCase())}</span></div><button className="primary-button" disabled={running || busy} onClick={() => void runScenario(scenario.id)}>{lifecycle === "STARTING" && replay?.scenario === scenario.id ? "Starting…" : "Run"}</button></div>)}</div>
      {!scenarios.length && <EmptyState>No scenarios are available from the runtime.</EmptyState>}
      <p className="presentation-note">Demo pace changes only how received telemetry and persisted evidence are revealed on this page. Runtime processing, source event time, and Result persistence are unchanged.</p>
    </section>}

    {replay && <>
      <section className="panel runtime-workbench">
        <div className="panel-head compact"><div><span className="eyebrow">{sourceLabel(sourceType)}</span><h2>{scenarioName}</h2><p>{lifecycle === "STARTING" ? "Preparing replay…" : lifecycle === "PROCESSING" ? "Receiving runtime telemetry." : lifecycle === "FINALIZING" ? "Finalizing evidence: draining trace and syncing persisted Results." : lifecycle === "READY" ? "Evidence and derived views are synchronized." : replay.state === "FAILED" ? "Replay processing failed." : "Latest controlled replay."}</p></div><span className={`status-chip${running ? " running" : lifecycle === "FAILED" ? " warning" : " neutral"}`}>{lifecycle === "FINALIZING" ? "Finalizing evidence" : lifecycle === "READY" ? "Complete" : running ? "Running" : lifecycle === "FAILED" ? "Failed" : replay.state}</span></div>
        <div className="replay-counters runtime-counters">{[[sourceRecords, replay.records_read], ["Observations", replay.observations_emitted], ["Source-linked Results", runResults.length], ["New rows persisted", newRowsPersisted], ["Family views", runFamilyViews.length], ["Investigation links", runLinks.length], ["Elapsed", `${replay.elapsed_wall_seconds.toFixed(2)} s`]].map(([label, value]) => <div key={String(label)}><span className="field-label">{label}</span><strong>{value}</strong></div>)}</div>
        <ol className="episode-stage-rail" aria-label="Replay evidence stages">{["Input", "Observe", "Route", "Evaluate", "Evidence", "Compose", "Relate"].map((label, index) => { const notApplicable = index === 6 && relateNotApplicable; const complete = !notApplicable && stageFacts[index] && (lifecycle === "READY" || index + 1 < activeStage); const active = !notApplicable && !complete && index + 1 === activeStage; return <li key={label} className={`${complete ? "complete" : ""}${active ? " active" : ""}${notApplicable ? " not-applicable" : ""}`} title={notApplicable ? "No cross-family relation for this replay" : undefined}><span>{notApplicable ? "—" : complete ? "✓" : `0${index + 1}`}</span>{label}</li>; })}</ol>
      </section>

      <div className="runtime-workbench-grid episode-grid">
        <section className="panel runtime-observations"><div className="panel-head compact"><div><h2>Replay milestones</h2><p>Runtime trace · local wall clock ({formatTimeZoneLabel("local")}); these times are not observed network event times.</p></div><span className="count-badge">{observations.length} observations</span></div>
          {streamEvents.length ? <div className="runtime-event-list">{streamEvents.map((event) => {
            const time = formatShortTime(event.occurred_at, "local");
            if (event.kind === "SOURCE_RECORD_ACCEPTED") {
              if (streamEvents.find((item) => item.kind === "SOURCE_RECORD_ACCEPTED")?.sequence !== event.sequence) return null;
              const count = presentedTrace.filter((item) => item.kind === "SOURCE_RECORD_ACCEPTED").length;
              return <div className="runtime-event-row source-select" key="source-accepted"><time>{time}</time><strong>Source records accepted</strong><span>{count} passive input record{count === 1 ? "" : "s"}</span><em>Input</em></div>;
            }
            if (event.kind === "OBSERVATION_CREATED") {
              const index = observations.findIndex((item) => item.observation_id === event.observation_id);
              const routed = observationRoutes.get(event.observation_id || "")?.length ?? 0;
              const visibility = presentedTrace.find((item) => item.observation_id === event.observation_id && item.kind === "VISIBILITY_EVALUATED");
              const linkedResultCount = runResults.filter((result) => result.source_observation_ids.includes(event.observation_id || "")).length;
              const parts = [visibility?.reason ? readable(visibility.reason) : "Observation created", routed ? `${routed} analytics routed` : "No analytic route", linkedResultCount ? `${linkedResultCount} source-linked Results` : ""].filter(Boolean);
              return <button type="button" className={`runtime-event-row observation-select${selectedObservation?.observation_id === event.observation_id ? " selected" : ""}`} key={event.sequence} onClick={() => setSelectedObservationId(event.observation_id)}><time>{time}</time><strong>{sourceType.toLowerCase().includes("pcap") ? `Packet ${index + 1}` : observationLabel(event.observation_type)}</strong><span>{parts.join(" · ")}</span><em>{routed ? `${routed} routes` : "Observed"}</em></button>;
            }
            return null;
          })}</div> : <p className="runtime-empty">{running ? "Waiting for the next source record…" : "No runtime trace was received for this replay."}</p>}
          <details className="raw-trace-details"><summary>Show complete runtime trace ({receivedTrace.length} events)</summary><div className="runtime-event-list">{receivedTrace.map((event) => <div className="runtime-event-row source-select" key={event.sequence}><time title={`Runtime trace · local wall clock: ${formatEvidenceDateTime(event.occurred_at, "local")}`}>{formatShortTime(event.occurred_at, "local")}</time><strong>{readable(event.kind)}</strong><span>{event.mechanism || event.reason || event.readiness || event.observation_id || "Runtime telemetry"}</span><em>#{event.sequence}</em></div>)}</div></details>
        </section>
        <section className="panel runtime-analytics"><div className="panel-head compact"><div><h2>Observation routes</h2><p>{selectedObservation ? `${observationLabel(selectedObservation.observation_type)} fans out independently` : "Select an observation to inspect its routes"}</p></div><span className="count-badge">{analytics.length}</span></div>
          {selectedObservation && <div className="selected-observation-summary"><span className="evidence-node">Packet observation</span><span>{observationLabel(selectedObservation.observation_type)}</span></div>}
          {analytics.length ? <div className="runtime-analytic-list">{analytics.map((item) => <div className="runtime-analytic-row" key={`${item.observation_id}-${item.lane_id}`}><span className="route-branch" aria-hidden="true">↳</span><div><strong>{mechanismLabel(item.mechanism || item.lane_id || "Analytic")}</strong><span>{readable(item.observation_type || "Observation route")}</span></div><em>{item.status}</em></div>)}</div> : <div className="runtime-empty">{running ? "Waiting for a routed observation…" : "No analytic route was recorded for this selected observation."}</div>}
        </section>
      </div>

      <section className="panel replay-flow-panel"><div className="panel-head compact"><div><h2>Persisted Results</h2><p>Durable evidence fetched from REST after source replay completion.</p></div><button className="text-button" onClick={() => navigate("results")}>Open Evidence →</button></div>
          {presentedResults ? <div className="replay-event-log"><p className="analyst-time-note">Result time · observed evidence context · {formatTimeZoneLabel(zone)}.</p>{runResults.slice(0, presentedResults).slice(-10).reverse().map((result) => <div className="event-log-item" key={result.result_id}><time>{formatEvidenceDateTime(result.created_time, zone)}</time><strong>{friendlyCategory(result.taxonomy[1])}</strong><span>{mechanismLabel(result.mechanism_id || result.lane_id)} · {summarizeReference(result.entity_reference, result.mechanism_id)}</span><em>{result.result_type === "REVIEW_FINDING" ? "Review" : "Evidence limitation"}</em><button className="inline-link" onClick={() => navigate("results", { resultId: result.result_id })}>View evidence</button></div>)}</div> : <p className="runtime-empty">{resultSyncUnavailable ? "Durable Results could not be synchronized; no conclusion about Result production is available." : lifecycle === "READY" ? diagnostic : "Results appear here after durable synchronization."}</p>}
        {runResults.length > 0 && replay.results_persisted < runResults.length && lifecycle === "READY" && <p className="replay-diagnostic">{newRowsPersisted} new rows written during this run; {runResults.length - newRowsPersisted} immutable source-linked Result{runResults.length - newRowsPersisted === 1 ? " was" : "s were"} already present in the durable store.</p>}
      {diagnostic && <p className="replay-diagnostic">{traceUnavailable ? "Trace telemetry was unavailable; source-lineage Result attribution could not be established." : `${presentedTrace.filter((event) => event.kind === "ROUTED").length} analytic routes were recorded in runtime trace, with no source-linked durable Result.`}</p>}
      </section>
      {familiesPresented && runResults.length > 0 && <section className="panel replay-flow-panel"><div className="panel-head compact"><div><h2>Family evidence</h2><p>Grouped views retain their source mechanism Results.</p></div><button className="text-button" onClick={() => navigate("alerts")}>Open Analyst Queue →</button></div>
        {derivedUnavailable ? <p className="runtime-empty">Family evidence could not be loaded; source-linked Results remain available.</p> : runFamilyViews.length ? <div className="family-stage-list">{runFamilyViews.map((view) => <article key={view.family_view_id}><strong>{view.family} evidence</strong><span>{pluralize(view.findings.length, "independent finding")} · {pluralize(new Set(view.limitations.concat(view.missing_evidence)).size, "evidence limitation")}</span><div className="mechanism-chips">{groupFamilyFindings(view.findings).slice(0, 4).map((group) => <span key={group.title}>{group.title}{group.findings.length > 1 ? ` ×${group.findings.length}` : ""}</span>)}</div><button className="text-button" onClick={() => navigate("alerts", { familyViewId: view.family_view_id })}>Open family evidence →</button></article>)}</div> : <p className="runtime-empty">No family view includes Results from this replay.</p>}
      </section>}
      {linksPresented && runFamilyViews.length > 0 && <section className="panel replay-flow-panel"><div className="panel-head compact"><div><h2>Related for investigation</h2><p>Exact shared source observations connect distinct family views.</p></div></div>
        {derivedUnavailable ? <p className="runtime-empty">Investigation links could not be loaded; their availability is unknown.</p> : runLinks.length ? <div className="family-stage-list">{runLinks.map((link) => { const left = viewsById.get(link.left_family_view_id); const right = viewsById.get(link.right_family_view_id); return left && right ? <article key={link.link_id}><strong>{left.family} ↔ {right.family}</strong><span>Shared passive observation · {link.shared_source_observation_ids.length}</span><small>Joint investigation context only. This does not establish a common attacker or causality.</small><button className="text-button" onClick={() => navigate("investigations", { linkId: link.link_id })}>Review relationship →</button></article> : null; })}</div> : <p className="runtime-empty">No cross-family shared-observation link includes this replay.</p>}
      </section>}
      {lifecycle === "READY" && !resultSyncUnavailable && !runResultIds.size && replay.results_persisted > 0 && <p className="replay-diagnostic" role="status">Backend reported {replay.results_persisted} persisted Results, but the durable resynchronization found none linked to this replay.</p>}
      <div className="run-summary"><span>{replay.records_read} {sourceRecords.toLowerCase()} · {replay.observations_emitted} observations</span><span>{runResults.length} durable Results</span><span>{reviewCount} review · {limitationCount} limitation</span>{!running && <button className="text-button" onClick={() => setShowPicker((value) => !value)}>{showPicker ? "Hide scenarios" : "Run another scenario"}</button>}</div>
      {error && <div className="stream-notice" role="status">{error}</div>}
    </>}
  </section>;
}
