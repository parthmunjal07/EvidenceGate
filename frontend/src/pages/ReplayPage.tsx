import { useEffect, useMemo, useReducer, useRef, useState, type CSSProperties } from "react";
import { useEvidence } from "../state/EvidenceContext";
import { EmptyState, PageHeading } from "../components/common/Primitives";
import { api } from "../api/client";
import type { FamilyEvidenceViewDto, InvestigationLinkDto, ResultDto, RuntimeTraceEvent } from "../api/types";
import { compareTimeAsc, contextSummary, formatEvidenceDateTime, formatEvidenceDateTimeCompact, formatEvidenceClockTime, formatTimeZoneLabel, mechanismLabel, normalizeFamilyName, pluralize, readable, summarizeReference } from "../utils/formatting";
import { useReplay } from "../hooks/useReplay";
import { useTimeZone } from "../state/TimeZoneContext";
import type { PageKey } from "../state/types";
import type { NavigationContext } from "../state/navigation";
import { drainRuntimeTraceCursor, latestReadinessByObservationLane, mergeRuntimeTraceEvents, observationLaneKey } from "../utils/runtimeTrace";
import { newPersistedReplayRows, sourceLinkedReplayResults } from "../utils/replayAttribution";
import { clearLatestReplayMarker, saveLatestReplayMarker } from "../utils/latestReplayScope";
import { buildReplayPresentationSteps, groupFamilyEpisodes, groupRelationsByFamilyPair, playerReducer, presentationSchedule, type PresentationMode, type ReplayPresentationStage } from "../utils/replayPresentation";

type Lifecycle = "IDLE" | "STARTING" | "PROCESSING" | "FINALIZING" | "READY" | "FAILED";

const observationLabel = (value: string | null) => value ? readable(value) : "Packet observation";
const prefersReducedMotion = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;
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
  const [presentation, setPresentation] = useState<PresentationMode>(() => prefersReducedMotion() ? "instant" : "normal");
  const [receivedTrace, setReceivedTrace] = useState<RuntimeTraceEvent[]>([]);
  const [baseline, setBaseline] = useState<Set<string> | null>(null);
  const [runResults, setRunResults] = useState<ResultDto[]>([]);
  const [newRowsPersisted, setNewRowsPersisted] = useState(0);
  const [familyViews, setFamilyViews] = useState<FamilyEvidenceViewDto[]>([]);
  const [investigationLinks, setInvestigationLinks] = useState<InvestigationLinkDto[]>([]);
  const [derivedUnavailable, setDerivedUnavailable] = useState(false);
  const [traceUnavailable, setTraceUnavailable] = useState(false);
  const [resultSyncUnavailable, setResultSyncUnavailable] = useState(false);
  const [lifecycle, setLifecycle] = useState<Lifecycle>("IDLE");
  const [player, dispatchPlayer] = useReducer(playerReducer, { stepIndex: -1, paused: false, followLive: true, selectedObservationId: null });
  const [showPicker, setShowPicker] = useState(true);
  const traceCursor = useRef(0);
  const traceIssueRef = useRef(false);
  const receivedRef = useRef(receivedTrace);
  const runResultsRef = useRef(runResults);
  const baselineRef = useRef<Set<string> | null>(null);
  const activeReplayStartedAt = useRef<string | null>(null);
  const replayTraceStartSequence = useRef<number | null>(null);
  const finalizingStartedAt = useRef<string | null>(null);
  useEffect(() => {
    receivedRef.current = receivedTrace;
    runResultsRef.current = runResults;
    baselineRef.current = baseline;
  }, [receivedTrace, runResults, baseline]);

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
    receivedRef.current = [];
    setRunResults([]);
    runResultsRef.current = [];
    setNewRowsPersisted(0);
    setFamilyViews([]);
    setInvestigationLinks([]);
    setDerivedUnavailable(false);
    dispatchPlayer({ type: "RESET" });
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

      if (controller.signal.aborted) return;
      if (!controller.signal.aborted) setLifecycle("READY");
      if (!controller.signal.aborted && !traceIssueRef.current && replayTraceStartSequence.current !== null && replay.started_at && replay.finished_at && replay.scenario && replay.source_type) {
        saveLatestReplayMarker({ scenario: replay.scenario, sourceType: replay.source_type, startedAt: replay.started_at, finishedAt: replay.finished_at, startSequence: replayTraceStartSequence.current, endSequence: traceCursor.current });
      }
    })();
    return () => controller.abort();
  }, [replay?.state, replay?.started_at, replay?.finished_at, replay?.results_persisted, replay?.scenario, replay?.source_type, baseline, dispatch]);

  const presentationSteps = useMemo(() => buildReplayPresentationSteps(receivedTrace, runResults, familyViews, investigationLinks), [receivedTrace, runResults, familyViews, investigationLinks]);
  const observationEvents = useMemo(() => receivedTrace.filter((event) => event.kind === "OBSERVATION_CREATED" && event.observation_id), [receivedTrace]);
  const schedule = useMemo(() => presentationSchedule(presentationSteps, replay?.scenario ?? "", sourceType, observationEvents.length, presentation), [presentationSteps, replay?.scenario, sourceType, observationEvents.length, presentation]);
  const effectiveStepIndex = presentation === "instant" || prefersReducedMotion() ? presentationSteps.length - 1 : Math.min(player.stepIndex, presentationSteps.length - 1);
  const currentStep = presentationSteps[effectiveStepIndex] ?? null;

  useEffect(() => {
    if (lifecycle !== "READY" || !presentationSteps.length) return;
    if (presentation === "instant" || prefersReducedMotion()) return;
    if (player.paused || player.stepIndex >= presentationSteps.length - 1) return;
    const nextIndex = player.stepIndex + 1;
    const timer = setTimeout(() => dispatchPlayer({ type: "ADVANCE", stepCount: presentationSteps.length }), player.stepIndex < 0 ? 0 : schedule[nextIndex] ?? 300);
    return () => clearTimeout(timer);
  }, [lifecycle, presentation, player.paused, player.stepIndex, presentationSteps, schedule]);

  const revealedSteps = presentationSteps.slice(0, effectiveStepIndex + 1);
  const revealedSequences = new Set(revealedSteps.flatMap((step) => step.eventSequences));
  const revealedResultIds = new Set(revealedSteps.flatMap((step) => step.resultIds));
  const presentedTrace = receivedTrace.filter((event) => revealedSequences.has(event.sequence));
  const visibleRunResults = runResults.filter((result) => revealedResultIds.has(result.result_id));
  const familyStepIndex = presentationSteps.findIndex((step) => step.stage === "FAMILY");
  const relationStepIndex = presentationSteps.findIndex((step) => step.stage === "RELATION");
  const familiesPresented = effectiveStepIndex >= familyStepIndex && familyStepIndex >= 0;
  const linksPresented = investigationLinks.length
    ? effectiveStepIndex >= relationStepIndex && relationStepIndex >= 0
    : lifecycle === "READY" && familiesPresented && !derivedUnavailable;
  const runFamilyViews = familiesPresented ? familyViews : [];
  const runLinks = linksPresented ? investigationLinks : [];

  const observations = useMemo(() => {
    const map = new Map<string, RuntimeTraceEvent>();
    for (const event of presentedTrace) if (event.kind === "OBSERVATION_CREATED" && event.observation_id) map.set(event.observation_id, event);
    return [...map.values()];
  }, [presentedTrace]);
  const observationRoutes = useMemo(() => {
    const map = new Map<string, RuntimeTraceEvent[]>();
    for (const event of presentedTrace) if (event.kind === "ROUTED" && event.observation_id && event.lane_id) {
      const rows = map.get(event.observation_id) ?? [];
      if (!rows.some((row) => row.lane_id === event.lane_id)) rows.push(event);
      map.set(event.observation_id, rows);
    }
    return map;
  }, [presentedTrace]);
  const liveObservationId = currentStep?.observationId ?? observations.at(-1)?.observation_id ?? null;
  const selectedObservation = observations.find((event) => event.observation_id === (player.followLive ? liveObservationId : player.selectedObservationId)) ?? null;
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

  const presentedReviewCount = visibleRunResults.filter((item) => item.result_type === "REVIEW_FINDING").length;
  const presentedLimitationCount = visibleRunResults.length - presentedReviewCount;
  const familyGroups = groupFamilyEpisodes(runFamilyViews);
  const relationGroups = groupRelationsByFamilyPair(runLinks, runFamilyViews);
  const stageIndex: Record<ReplayPresentationStage, number> = { SOURCE: 0, OBSERVATION: 1, VISIBILITY: 1, ROUTING: 2, EVALUATION: 3, RESULT: 4, FAMILY: 5, RELATION: 6 };
  const activeStage = currentStep ? stageIndex[currentStep.stage] : lifecycle === "READY" && player.stepIndex >= presentationSteps.length - 1 ? 7 : 0;
  const stageAvailable = [receivedTrace.some((event) => event.kind === "SOURCE_RECORD_ACCEPTED"), observations.length > 0, receivedTrace.some((event) => event.kind === "ROUTED"), receivedTrace.some((event) => event.kind.startsWith("ANALYTIC_") || event.kind === "ADMISSION_REJECTED"), runResults.length > 0, familyViews.length > 0, investigationLinks.length > 0];
  const relateNotApplicable = lifecycle === "READY" && familiesPresented && !derivedUnavailable && investigationLinks.length === 0;
  const sourceRecords = sourceType.toLowerCase().includes("pcap") ? "Packets" : "Records";
  const sourceCount = receivedTrace.filter((event) => event.kind === "SOURCE_RECORD_ACCEPTED").length || replay?.records_read || 0;
  const totalObservationCount = replay?.observations_emitted || observationEvents.length;
  const presentedRouteCount = observationRoutes.get(selectedObservation?.observation_id ?? "")?.length ?? 0;
  const selectedResults = selectedObservation ? visibleRunResults.filter((item) => item.source_observation_ids.includes(selectedObservation.observation_id || "")) : [];
  const contextItems = selectedObservation ? [...new Set(runResults.filter((result) => result.source_observation_ids.includes(selectedObservation.observation_id || "")).map(contextSummary))].filter((item) => item && item !== "Observed network context").slice(0, 2) : [];
  const selectedVisibilityEvents = selectedObservation ? presentedTrace.filter((event) => event.observation_id === selectedObservation.observation_id && event.kind === "VISIBILITY_EVALUATED") : [];
  const currentStageLabel = currentStep ? presentationStageLabel(currentStep.stage) : lifecycle === "READY" ? "Demo ready" : "Waiting for replay";
  const observationIndex = selectedObservation ? observations.findIndex((event) => event.observation_id === selectedObservation.observation_id) : -1;
  const familyResultCounts = new Map<string, number>();
  for (const result of visibleRunResults) familyResultCounts.set(result.taxonomy[1], (familyResultCounts.get(result.taxonomy[1]) ?? 0) + 1);
  const resultTimeHeading = `Evidence time · ${formatTimeZoneLabel(zone)}`;
  const playbackDone = lifecycle === "READY" && effectiveStepIndex >= presentationSteps.length - 1;
  const diagnostic = lifecycle === "READY" && runResults.length === 0 && !resultSyncUnavailable ? traceUnavailable ? "Runtime trace unavailable; source-lineage Result attribution could not be established." : (replay?.results_persisted ?? 0) > 0 ? "The runtime reported persisted Results, but no durable Result could be linked to the current replay observations." : "Replay completed, but no mechanism Result was produced." : null;

  const hasRun = lifecycle !== "IDLE" && Boolean(replay?.scenario);
  const visibleObservationIds = new Set(presentedTrace.filter((event) => event.kind === "OBSERVATION_CREATED").map((event) => event.observation_id).filter((id): id is string => Boolean(id)));
  const selectableObservations = playbackDone ? observations : observations.filter((event) => Boolean(event.observation_id && visibleObservationIds.has(event.observation_id)));
  const stages = ["Input", "Observe", "Route", "Evaluate", "Evidence", "Compose", "Relate"];
  const stageTimeTitle = `Runtime trace · local wall clock · ${formatTimeZoneLabel("local")}`;
  const qualityLabels: Record<string, string> = { packet_loss: "Packet loss", sampling: "Sampling", parser: "Parser", capture_gap: "Capture gaps" };
  const selectedVisibility = selectedResults.flatMap((result) => [
    ...result.visibility_snapshot.available.map((item) => ({ label: visibilityLabel(item), status: "Available" })),
    ...result.visibility_snapshot.degraded.map((item) => ({ label: visibilityLabel(item), status: "Degraded" })),
    ...result.visibility_snapshot.unavailable.map((item) => ({ label: visibilityLabel(item), status: "Unavailable" })),
  ]).filter((item, index, items) => items.findIndex((value) => value.label === item.label && value.status === item.status) === index);
  const selectedQuality = selectedResults.length ? Object.entries(selectedResults[0]!.quality_snapshot).map(([key, value]) => ({ label: qualityLabels[key] ?? readable(key), status: value === "CLEAR" ? "Clear" : value === "DEGRADED" ? "Degraded" : "Not reported" })) : [];
  const recentResults = visibleRunResults.slice(-4).reverse();
  const runtimeCaption = replay?.state === "COMPLETED" ? `Runtime completed in ${replay.elapsed_wall_seconds.toFixed(2)} s` : running ? "Runtime processing is separate from presentation playback" : "Runtime processing time not available";
  const setPlaybackMode = (mode: PresentationMode) => { setPresentation(mode); if (mode === "instant") dispatchPlayer({ type: "SHOW_FINAL", stepCount: presentationSteps.length }); };

  return <section className="page active-page traffic-lab-page" aria-labelledby="replay-title">
    <PageHeading titleId="replay-title" title="Traffic Lab" deck="Watch passive observations route into separate evidence, family views and shared-context relationships." />
    {state.runtime?.dga_model_readiness && state.runtime.dga_model_readiness !== "VERIFIED_READY" && <div className="stream-notice" role="status">DGA lexical model is unavailable. DGA scores will not be produced.</div>}

    {(showPicker || !hasRun) && <section className="panel scenario-picker-panel demo-scenario-panel">
      <div className="panel-head compact"><div><span className="eyebrow">Controlled passive inputs</span><h2>Choose an evidence episode</h2><p>Replay uses recorded or controlled observations. It does not capture or generate network traffic.</p></div><label className="demo-mode-control">Demo playback<select aria-label="Demo playback" value={presentation} onChange={(event) => setPlaybackMode(event.target.value as PresentationMode)}><option value="normal">Normal</option><option value="fast">Fast</option><option value="instant">Show instantly</option></select></label></div>
      <div className="scenario-list">{scenarios.map((scenario) => <div className="scenario-row" key={scenario.id}><div><strong>{scenario.label}</strong><span>{sourceLabel(scenario.source_type)} · {normalizeFamilyName(scenario.family)}</span></div><button className="primary-button" disabled={running || busy} onClick={() => void runScenario(scenario.id)}>{lifecycle === "STARTING" && replay?.scenario === scenario.id ? "Starting…" : "Run"}</button></div>)}</div>
      {!scenarios.length && <EmptyState>No scenarios are available from the runtime.</EmptyState>}
      <p className="presentation-note">Normal and Fast pace only the on-screen explanation. Runtime processing, source event times, Result persistence and scientific output are unchanged.</p>
    </section>}

    {hasRun && replay && <>
      <section className="panel player-run-header">
        <div className="run-title-row"><div><span className="eyebrow">{sourceLabel(sourceType)}</span><h2>{scenarioName}</h2><p>{lifecycle === "STARTING" ? "Preparing replay…" : lifecycle === "PROCESSING" ? "Runtime processing in progress." : lifecycle === "FINALIZING" ? "Synchronizing observed trace and durable evidence…" : lifecycle === "READY" ? runtimeCaption : lifecycle === "FAILED" ? "Replay processing failed." : "Controlled replay"}{lifecycle === "READY" && <span className="presentation-honesty"> · Presentation playback is paced for demonstration only</span>}</p></div><div className="run-header-actions"><span className={`status-chip${running ? " running" : lifecycle === "FAILED" ? " warning" : " neutral"}`}>{lifecycle === "FINALIZING" ? "Preparing episode" : lifecycle === "READY" ? "Runtime complete" : running ? "Running" : lifecycle === "FAILED" ? "Failed" : replay.state}</span><button className="secondary-button" onClick={() => setShowPicker((value) => !value)}>{showPicker ? "Hide scenarios" : "Run another"}</button></div></div>
        <div className="run-hero-metrics"><div><span>Input</span><strong>{sourceCount} {sourceRecords.toLowerCase()}</strong></div><div><span>Observations</span><strong>{replay.observations_emitted || observations.length}</strong></div><div><span>Evidence</span><strong>{runResults.length} Results</strong></div><div><span>Families</span><strong>{familyGroups.length ? familyGroups.map((group) => normalizeFamilyName(group.family)).join(" + ") : derivedUnavailable ? "Unavailable" : familiesPresented ? "None composed" : "Waiting for evidence"}</strong></div><div><span>Related context</span><strong>{linksPresented ? derivedUnavailable ? "Unavailable" : `${runLinks.length} factual ${runLinks.length === 1 ? "link" : "links"}` : familyStepIndex >= 0 && effectiveStepIndex < familyStepIndex ? "Waiting for family evidence" : "Waiting for related context"}</strong></div></div>
        <div className="demo-player-controls"><div><strong>Demo playback</strong><span>{presentation === "normal" ? "Normal" : presentation === "fast" ? "Fast" : "Show instantly"}{prefersReducedMotion() ? " · reduced motion" : ""}</span></div><div className="player-actions"><button className="secondary-button" disabled={lifecycle !== "READY" || playbackDone || presentation === "instant"} onClick={() => dispatchPlayer({ type: player.paused ? "RESUME" : "PAUSE" })}>{player.paused ? "Resume" : "Pause"}</button><label className="demo-mode-control"><span className="sr-only">Demo playback speed</span><select aria-label="Demo playback speed" value={presentation} onChange={(event) => setPlaybackMode(event.target.value as PresentationMode)}><option value="normal">Normal</option><option value="fast">Fast</option><option value="instant">Show instantly</option></select></label><button className="text-button" disabled={!presentationSteps.length || playbackDone} onClick={() => setPlaybackMode("instant")}>Show final state</button></div></div>
        <ol className="episode-stage-rail" aria-label="Replay evidence stages">{stages.map((label, index) => { const notApplicable = index === 6 && relateNotApplicable; const complete = !notApplicable && stageAvailable[index] && (playbackDone || index < activeStage); const active = !notApplicable && !complete && index === activeStage; return <li key={label} className={`${complete ? "complete" : ""}${active ? " active" : ""}${notApplicable ? " not-applicable" : ""}`} title={notApplicable ? "No cross-family relation for this replay" : undefined} aria-current={active ? "step" : undefined}><span>{notApplicable ? "—" : complete ? "✓" : active ? "●" : "○"}</span>{label}</li>; })}</ol>
      </section>

      <section className="episode-player-grid" aria-label="Evidence episode player">
        <aside className="panel observation-sequence-panel"><div className="player-panel-head"><div><span className="eyebrow">Observation sequence</span><strong>{selectedObservation ? `${sourceType.toLowerCase().includes("pcap") ? "Packet" : "Observation"} ${observationIndex + 1} of ${totalObservationCount}` : playbackDone ? `${totalObservationCount} observations` : `${visibleObservationIds.size} of ${totalObservationCount} observed`}</strong></div>{!player.followLive && <button className="text-button" onClick={() => dispatchPlayer({ type: "FOLLOW_LIVE" })}>Resume live focus</button>}</div>
          <div className="observation-sequence-list">{selectableObservations.map((event) => { const index = observations.findIndex((item) => item.observation_id === event.observation_id); const current = selectedObservation?.observation_id === event.observation_id; return <button type="button" className={`observation-sequence-item${current ? " selected" : ""}`} key={event.observation_id} aria-label={`${sourceType.toLowerCase().includes("pcap") ? "Packet" : "Observation"} ${index + 1} of ${totalObservationCount}: ${observationLabel(event.observation_type)}`} aria-pressed={current} onClick={() => dispatchPlayer({ type: "SELECT_OBSERVATION", observationId: event.observation_id! })}><span>{index + 1}</span></button>; })}{!selectableObservations.length && <p className="player-waiting">{running ? "Waiting for the first observation…" : lifecycle === "READY" ? "No canonical observation was emitted." : "Waiting for runtime processing…"}</p>}</div><p className="sequence-caption">{selectedObservation ? observationLabel(selectedObservation.observation_type) : "Packets become selectable as observations are presented."}</p>
        </aside>

        <article className="panel current-observation-panel" aria-live="polite">
          <div className="player-panel-head"><div><span className="eyebrow">Current observation</span><strong>{selectedObservation ? `${sourceType.toLowerCase().includes("pcap") ? "Packet" : "Observation"} ${observationIndex + 1} of ${totalObservationCount}` : "Preparing observation"}</strong></div><span className="stage-state-pill">{currentStageLabel}</span></div>
          {selectedObservation ? <>
            <div className="observation-hero"><h2>{observationLabel(selectedObservation.observation_type)}</h2><p>{contextItems.length ? contextItems.join(" · ") : "Network context appears with its source-linked evidence Results."}</p>{selectedVisibility.some((item) => item.status === "Unavailable") && analytics.some((item) => item.status === "Insufficient evidence") && <p className="evidence-limitation-note">Evidence limitation preserved · unavailable facts remain unavailable</p>}<div className="observation-facts"><span>{selectedObservation.observation_type ? readable(selectedObservation.observation_type) : "Passive observation"}</span><span>Canonical observation</span></div></div>
            <div className="visibility-card"><div className="visibility-title"><strong>Visibility</strong><span>{selectedVisibility.length ? "Evidence scope" : selectedVisibilityEvents.length ? "Observed" : "Awaiting visibility"}</span></div>{selectedVisibility.length ? <ul>{selectedVisibility.slice(0, 4).map((item) => <li key={`${item.label}-${item.status}`}><span className={`fact-mark ${item.status.toLowerCase()}`}>{item.status === "Available" ? "✓" : item.status === "Degraded" ? "△" : "○"}</span>{item.label}<strong>{item.status}</strong></li>)}</ul> : selectedVisibilityEvents.length ? <p>{selectedVisibilityEvents[0]!.reason ? friendlyVisibilityReason(selectedVisibilityEvents[0]!.reason!) : "Visibility was evaluated from the observed packet facts."}</p> : <p>{currentStep?.stage === "OBSERVATION" ? "Waiting for visibility assessment…" : "No visibility event has been presented for this observation yet."}</p>}
              <div className="quality-inline"><strong>Quality</strong>{selectedQuality.length ? selectedQuality.slice(0, 3).map((item) => <span key={item.label}>{item.label} · {item.status}</span>) : <span>Packet-loss and sampling telemetry appear with evidence Results.</span>}</div>
            </div>
          </> : <div className="observation-empty">{lifecycle === "READY" ? diagnostic ?? "No observation is available for this replay." : "The episode player will focus the first observation when it is received."}</div>}
          {selectableObservations.length > 1 && <div className="observation-pager"><button className="text-button" disabled={!selectedObservation || observationIndex <= 0} onClick={() => { const previous = selectableObservations[observationIndex - 1]; if (previous?.observation_id) dispatchPlayer({ type: "SELECT_OBSERVATION", observationId: previous.observation_id }); }}>← Previous</button><span>{selectedObservation ? `${observationIndex + 1} / ${totalObservationCount}` : "—"}</span><button className="text-button" disabled={!selectedObservation || observationIndex >= selectableObservations.length - 1} onClick={() => { const next = selectableObservations[observationIndex + 1]; if (next?.observation_id) dispatchPlayer({ type: "SELECT_OBSERVATION", observationId: next.observation_id }); }}>Next →</button></div>}
        </article>

        <section className="panel fanout-panel"><div className="player-panel-head"><div><span className="eyebrow">Zero-to-many routing</span><strong>{selectedObservation ? `${presentedRouteCount} analytics` : "Analytics"}</strong></div><span className="stage-state-pill">{activeStage < 2 ? "Waiting" : currentStep?.stage === "ROUTING" ? "Routing" : "Independent"}</span></div>
          {selectedObservation && analytics.length ? <div className="fanout-list">{analytics.map((item, index) => <article className="fanout-analytic" key={`${item.observation_id}-${item.lane_id}`} style={{ "--route-delay": `${Math.min(index, 8) * 150}ms` } as CSSProperties}><span className="fanout-connector" aria-hidden="true" /><div><strong>{mechanismLabel(item.mechanism || item.lane_id || "Analytic")}</strong><small>{item.status === "Routed" && currentStep?.stage === "ROUTING" ? "Routed" : item.status}</small></div>{item.status === "Evidence produced" ? <span className="fanout-result-mark">✓</span> : null}</article>)}</div> : <div className="fanout-empty">{activeStage < 2 ? "Waiting for routing…" : lifecycle === "READY" && currentStep?.stage === "RELATION" ? "No analytic route was recorded for this observation." : "This observation has no route visible at this point in the presentation."}</div>}
        </section>
      </section>

      <section className="panel evidence-outcome-panel"><div className="outcome-heading"><div><span className="eyebrow">Evidence outcome</span><h2>{visibleRunResults.length} / {runResults.length} mechanism Results presented</h2></div><span>{presentedReviewCount} review · {presentedLimitationCount} evidence limitations presented</span></div>
        <div className="outcome-track"><div><strong>Mechanism evidence</strong><span>{visibleRunResults.length} source-linked Results</span>{familyResultCounts.size > 0 && <div className="result-family-counts">{[...familyResultCounts].map(([family, count]) => <div key={family}><span>{normalizeFamilyName(family)}</span><strong>{count}</strong></div>)}</div>}</div><span className="outcome-chevron">↓</span><div><strong>Family evidence</strong><span>{derivedUnavailable && familiesPresented ? "Family composition unavailable" : familiesPresented ? `${familyGroups.length} families composed` : runResults.length ? "Waiting for source Results…" : lifecycle === "READY" ? "No source-linked Results" : "Waiting for runtime evidence…"}</span>{familyGroups.length > 0 && <div className="family-outcome-groups">{familyGroups.map((group) => <details className="family-outcome-group" key={group.family}><summary><strong>{normalizeFamilyName(group.family)}</strong><span>{group.views.length} episode{group.views.length === 1 ? "" : "s"} · {group.views.reduce((sum, view) => sum + view.findings.length, 0)} independent findings · {group.views.filter((view) => view.limitations.length || view.missing_evidence.length).length} with limits</span></summary><div className="family-episode-list">{group.views.map((view) => { const sourceRows = view.source_result_ids.map((id) => runResults.find((result) => result.result_id === id)).filter((item): item is ResultDto => Boolean(item)); const context = [...new Set(sourceRows.map(contextSummary))].slice(0, 1)[0] ?? "Observed context unavailable"; const limits = new Set([...view.limitations, ...view.missing_evidence]).size; return <div key={view.family_view_id}><time title={formatEvidenceDateTime(view.time_start, zone)}>{formatEvidenceClockTime(view.time_start, zone)}</time><span>{context} · {pluralize(view.findings.length, "finding")} · {limits} limits</span><button className="text-button" onClick={() => navigate("alerts", { familyViewId: view.family_view_id })}>Review →</button></div>; })}</div></details>)}</div>}</div><span className="outcome-chevron">↓</span><div><strong>Related context</strong><span>{!linksPresented ? familyGroups.length ? "Waiting for family evidence…" : "Joint review only · relations follow family composition" : derivedUnavailable ? "Related context unavailable" : relationGroups.length ? "Shared source context; no causal inference" : "No cross-family relation for this replay"}</span>{relationGroups.map((group) => <article className="relation-outcome" key={`${group.leftFamily}:${group.rightFamily}`}><div><strong>{normalizeFamilyName(group.leftFamily)} ↔ {normalizeFamilyName(group.rightFamily)}</strong><span>{pluralize(group.links.length, "factual relationship")} · {new Set(group.sharedObservationIds).size} shared source observations</span></div><small>Joint review only · no causality or common attacker inferred</small><details><summary>View exact relationships</summary>{group.links.map((link) => <div className="exact-relation-row" key={link.link_id}><span>{link.shared_source_observation_ids.length} shared source observations</span><button className="text-button" onClick={() => navigate("investigations", { linkId: link.link_id })}>Open investigation →</button></div>)}</details><button className="text-button" onClick={() => navigate("investigations", { linkId: group.links[0]!.link_id })}>Open investigation →</button></article>)}</div></div>
      </section>

      <section className="panel recent-evidence-panel"><div className="player-panel-head"><div><span className="eyebrow">{resultTimeHeading}</span><strong>Recent evidence</strong></div><button className="text-button" onClick={() => navigate("results")}>View all {runResults.length} evidence Results →</button></div>{recentResults.length ? <div className="recent-result-list">{recentResults.map((result) => <article key={result.result_id}><time title={formatEvidenceDateTime(result.created_time, zone)}>{formatEvidenceClockTime(result.created_time, zone)}</time><div><strong>{mechanismLabel(result.mechanism_id || result.lane_id)}</strong><span>{contextSummary(result)}</span></div><button className="text-button" onClick={() => navigate("results", { resultId: result.result_id })}>Review →</button></article>)}</div> : <p className="player-waiting">{resultSyncUnavailable ? "Durable Results could not be synchronized." : lifecycle === "READY" && !runResults.length ? diagnostic : "Results appear after their observation is evaluated."}</p>}</section>

      {diagnostic && traceUnavailable && <p className="replay-diagnostic" role="status">{diagnostic}</p>}
      {error && <div className="stream-notice" role="status">{error}</div>}
      <details className="technical-details-panel"><summary>Run details</summary><div className="technical-details-grid"><div><span>Scenario</span><strong>{scenarioName}</strong></div><div><span>Input type</span><strong>{sourceType}</strong></div><div><span>Runtime elapsed</span><strong>{replay.elapsed_wall_seconds.toFixed(2)} s</strong></div><div><span>Source-linked immutable Results</span><strong>{runResults.length}</strong></div><div><span>New database rows</span><strong>{newRowsPersisted}</strong></div><div><span>Existing deterministic Results</span><strong>{Math.max(0, runResults.length - newRowsPersisted)}</strong></div><div><span>Trace events</span><strong>{receivedTrace.length}{traceUnavailable ? " · partial/unavailable" : ""}</strong></div><div><span>Presentation mode</span><strong>{presentation === "normal" ? "Normal" : presentation === "fast" ? "Fast" : "Show instantly"}</strong></div></div>{runResults.length > 0 && <p>{runResults.length} source-linked immutable Results · {newRowsPersisted} new database rows · {Math.max(0, runResults.length - newRowsPersisted)} Results were already present due to deterministic IDs.</p>}</details>
      <details className="technical-details-panel"><summary>View all {runResults.length} evidence Results</summary><p className="technical-time-heading">Result time · {formatTimeZoneLabel(zone)}</p>{runResults.map((result) => <div className="technical-result-row" key={result.result_id}><time title={formatEvidenceDateTime(result.created_time, zone)}>{formatEvidenceDateTimeCompact(result.created_time, zone)}</time><strong>{normalizeFamilyName(result.taxonomy[1])}</strong><span>{mechanismLabel(result.mechanism_id || result.lane_id)} · {summarizeReference(result.entity_reference, result.mechanism_id)}</span><code>{result.result_id}</code><button className="text-button" onClick={() => navigate("results", { resultId: result.result_id })}>Open →</button></div>)}</details>
      <details className="technical-details-panel raw-trace-details"><summary>View complete runtime trace ({receivedTrace.length} events)</summary><p className="technical-time-heading">{stageTimeTitle} · not observed network event time</p>{receivedTrace.map((event) => <div className="technical-result-row trace-detail-row" key={event.sequence}><time title={`Runtime trace · ${formatEvidenceDateTime(event.occurred_at, "local")}`}>{formatEvidenceClockTime(event.occurred_at, "local")}</time><strong>{readable(event.kind)}</strong><span>{event.mechanism || event.reason || event.readiness || "Runtime telemetry"}</span><code>#{event.sequence}</code></div>)}</details>
    </>}
  </section>;
}

function presentationStageLabel(stage: ReplayPresentationStage) {
  const names: Record<ReplayPresentationStage, string> = { SOURCE: "Passive input", OBSERVATION: "Observation", VISIBILITY: "Visibility", ROUTING: "Zero-to-many routing", EVALUATION: "Analytic evaluation", RESULT: "Mechanism evidence", FAMILY: "Family composition", RELATION: "Related context" };
  return names[stage];
}

function visibilityLabel(value: string) {
  const labels: Record<string, string> = { FORWARD_FACTS: "Forward packet facts", REVERSE_FACTS: "Reverse packet facts", PACKET_FACTS: "Packet facts", FLOW_FACTS: "Flow facts", CLEAR_DNS_FIELDS: "Clear DNS fields", TLS_HANDSHAKE_METADATA: "TLS handshake metadata" };
  return labels[value] ?? readable(value);
}

function friendlyVisibilityReason(value: string) {
  if (/forward.*reverse/i.test(value)) return "Forward and reverse packet facts are available.";
  if (/forward/i.test(value)) return "Forward packet facts are available.";
  if (/reverse/i.test(value)) return "Reverse packet evidence is unavailable.";
  if (/packet.?loss|sampling|quality/i.test(value)) return "Quality telemetry is partially reported.";
  return "Visibility was evaluated from observed telemetry.";
}
