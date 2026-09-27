import { useEffect, useMemo, useReducer, useRef, useState, type CSSProperties } from "react";
import { useEvidence } from "../state/EvidenceContext";
import { EmptyState, PageHeading } from "../components/common/Primitives";
import { api } from "../api/client";
import type { FamilyEvidenceViewDto, InvestigationLinkDto, ResultDto, RuntimeTraceEvent } from "../api/types";
import { contextSummary, formatEvidenceDateTime, formatEvidenceClockTime, formatTimeZoneLabel, mechanismLabel, normalizeFamilyName, pluralize, readable } from "../utils/formatting";
import { useReplay } from "../hooks/useReplay";
import { useTimeZone } from "../state/TimeZoneContext";
import type { PageKey } from "../state/types";
import type { NavigationContext } from "../state/navigation";
import { advanceRuntimeTraceCursor, captureRuntimeTraceBaseline, hasCompleteRuntimeTraceRange, hasRuntimeTraceGap, latestReadinessByObservationLane, mergeRuntimeTraceEvents, observationLaneKey } from "../utils/runtimeTrace";
import { sourceLinkedReplayResults } from "../utils/replayAttribution";
import { clearLatestReplayMarker, saveLatestReplayMarker } from "../utils/latestReplayScope";
import { buildReplayPresentationSteps, groupFamilyEpisodes, groupRelationsByFamilyPair, playerReducer, presentationSchedule, type ReplayPresentationStage } from "../utils/replayPresentation";
import { judgeDemoScenarios, validateJudgeDemo, validateScopedEvidence } from "../utils/judgeDemos";
import { NetworkObservationsSection, ObservationWorkbench } from "../components/replay/NetworkObservationsSection";
import { projectResultExplanation } from "../utils/resultExplanation";
import { checkReleaseCompatibility, RELEASE_RECOVERY_KEY } from "../utils/releaseCompatibility";
import { cacheReplayEvidence, clearReplayEvidenceCache } from "../utils/replayEvidenceCache";
import { replayFinalizationReady } from "../utils/replayFinalization";
import { ReplayRunGeneration } from "../utils/replayRunGeneration";

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

export function ReplayPage({ navigate }: { navigate: (page: PageKey, context?: NavigationContext) => void }) {
  const { state, dispatch } = useEvidence();
  const { zone } = useTimeZone();
  const { scenarios, replay, error, start, busy } = useReplay();
  const presentation = prefersReducedMotion() ? "instant" as const : "normal" as const;
  const [receivedTrace, setReceivedTrace] = useState<RuntimeTraceEvent[]>([]);
  const [baseline, setBaseline] = useState<Set<string> | null>(null);
  const [runResults, setRunResults] = useState<ResultDto[]>([]);
  const [familyViews, setFamilyViews] = useState<FamilyEvidenceViewDto[]>([]);
  const [investigationLinks, setInvestigationLinks] = useState<InvestigationLinkDto[]>([]);
  const [derivedUnavailable, setDerivedUnavailable] = useState(false);
  const [traceUnavailable, setTraceUnavailable] = useState(false);
  const [resultSyncUnavailable, setResultSyncUnavailable] = useState(false);
  const [demoFailure, setDemoFailure] = useState<string[]>([]);
  const [playbackFailure, setPlaybackFailure] = useState(false);
  const [startingScenarioId, setStartingScenarioId] = useState<string | null>(null);
  const [expandedFanoutResultId, setExpandedFanoutResultId] = useState<string | null>(null);
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
  const runGeneration = useRef(new ReplayRunGeneration());
  const runController = useRef<AbortController | null>(null);
  useEffect(() => () => {
    runController.current?.abort();
    runGeneration.current.begin();
  }, []);
  useEffect(() => {
    receivedRef.current = receivedTrace;
    runResultsRef.current = runResults;
    baselineRef.current = baseline;
  }, [receivedTrace, runResults, baseline]);

  const selectedScenario = scenarios.find((scenario) => scenario.id === replay?.scenario);
  const dgaReady = state.runtime?.dga_model_readiness === "VERIFIED_READY";
  const availableScenarios = useMemo(() => judgeDemoScenarios(scenarios, dgaReady, import.meta.env.VITE_EVIDENCEGATE_DEV_SCENARIOS === "true"), [scenarios, dgaReady]);
  const scenarioInfo = availableScenarios.find((scenario) => scenario.id === replay?.scenario);
  const demoContract = scenarioInfo?.demo;
  const scenarioName = scenarioInfo?.demo?.title || selectedScenario?.label || "Traffic replay";
  const sourceType = replay?.source_type || selectedScenario?.source_type || "Controlled observations";
  const releaseCheck = state.runtime ? checkReleaseCompatibility(
    __EVIDENCEGATE_RELEASE_ID__, state.runtime.release_id, state.runtime.api_contract_version,
    window.sessionStorage.getItem(RELEASE_RECOVERY_KEY) === "true", window.location.href,
  ) : null;
  const apiIncompatible = releaseCheck?.state === "incompatible";
  const developerUi = import.meta.env.VITE_EVIDENCEGATE_DEV_UI === "true";
  const demoAssetMismatch = Boolean(scenarioInfo?.demo && scenarioInfo.asset_version !== scenarioInfo.demo.assetVersion);
  const sourceLabel = (value: string) => /pcap/i.test(value) ? "Recorded PCAP replay" : /ndjson|typed/i.test(value) ? "Controlled NDJSON replay" : value;
  const running = lifecycle === "STARTING" || lifecycle === "PROCESSING" || lifecycle === "FINALIZING";
  // Once runtime completion is observed, the finalizer becomes the only trace reader.
  const tracePolling = lifecycle === "PROCESSING" && replay?.state !== "COMPLETED";

  useEffect(() => {
    if (!tracePolling) return;
    const controller = new AbortController();
    const generation = runGeneration.current.current();
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const update = await api.runtimeTrace(traceCursor.current, controller.signal);
        if (controller.signal.aborted || !runGeneration.current.isCurrent(generation)) return;
        if (update.events.length) {
          if (hasRuntimeTraceGap(traceCursor.current, update.events)) {
            traceIssueRef.current = true;
            setTraceUnavailable(true);
          }
          const merged = mergeRuntimeTraceEvents(receivedRef.current, update.events);
          receivedRef.current = merged;
          setReceivedTrace(merged);
          traceCursor.current = advanceRuntimeTraceCursor(traceCursor.current, update.events);
        }
      } catch { if (!controller.signal.aborted && runGeneration.current.isCurrent(generation)) { traceIssueRef.current = true; setTraceUnavailable(true); } }
      if (!controller.signal.aborted && runGeneration.current.isCurrent(generation)) timer = setTimeout(poll, 300);
    };
    void poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [tracePolling]);

  const runScenario = async (id: string) => {
    runController.current?.abort();
    const controller = new AbortController();
    runController.current = controller;
    const generation = runGeneration.current.begin();
    const isCurrent = () => runGeneration.current.isCurrent(generation) && !controller.signal.aborted;
    clearReplayEvidenceCache();
    setStartingScenarioId(id);
    setLifecycle("STARTING");
    clearLatestReplayMarker();
    replayTraceStartSequence.current = null;
    activeReplayStartedAt.current = null;
    finalizingStartedAt.current = null;
    setTraceUnavailable(false);
    traceIssueRef.current = false;
    setResultSyncUnavailable(false);
    setDemoFailure([]);
    setPlaybackFailure(false);
    try {
      traceCursor.current = await captureRuntimeTraceBaseline((after, limit) => api.runtimeTrace(after, controller.signal, limit));
      if (!isCurrent()) return;
      replayTraceStartSequence.current = traceCursor.current;
    } catch {
      if (!isCurrent()) return;
      traceCursor.current = 0;
      traceIssueRef.current = true;
      setTraceUnavailable(true);
    }
    setReceivedTrace([]);
    receivedRef.current = [];
    setRunResults([]);
    runResultsRef.current = [];
    setFamilyViews([]);
    setInvestigationLinks([]);
    setDerivedUnavailable(false);
    dispatchPlayer({ type: "RESET" });
    setShowPicker(false);
    try {
      const before = await api.allResults(controller.signal);
      if (!isCurrent()) return;
      const ids = new Set(before.map((result) => result.result_id));
      baselineRef.current = ids;
      setBaseline(ids);
      const started = await start(id, 0, controller.signal);
      if (!isCurrent()) return;
      if (!started) throw new Error("Replay could not be started");
      activeReplayStartedAt.current = started.started_at;
      setStartingScenarioId(null);
      setLifecycle("PROCESSING");
    } catch (cause) {
      if (!isCurrent()) return;
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
    const generation = runGeneration.current.current();
    const isCurrent = () => runGeneration.current.isCurrent(generation) && !controller.signal.aborted;
    setLifecycle("FINALIZING");
    void (async () => {
      // Runtime completion closes the event stream. Read pages until the first empty page at the head.
      let drainedTraceHead = traceCursor.current;
      let drainedTrace: RuntimeTraceEvent[] = [];
      let traceDrained = false;
      while (isCurrent()) {
        try {
          const update = await api.runtimeTrace(traceCursor.current, controller.signal);
          if (!isCurrent()) return;
          drainedTraceHead = update.latest_sequence;
          if (update.events.length) {
            if (hasRuntimeTraceGap(traceCursor.current, update.events)) {
              traceIssueRef.current = true;
              setTraceUnavailable(true);
            }
            drainedTrace = mergeRuntimeTraceEvents(drainedTrace, update.events);
            const merged = mergeRuntimeTraceEvents(receivedRef.current, update.events);
            receivedRef.current = merged;
            setReceivedTrace(merged);
            traceCursor.current = advanceRuntimeTraceCursor(traceCursor.current, update.events);
            continue;
          }
          traceDrained = traceCursor.current === update.latest_sequence;
          if (!traceDrained) {
            traceIssueRef.current = true;
            setTraceUnavailable(true);
          }
          break;
        } catch {
          if (isCurrent()) {
            traceIssueRef.current = true;
            setTraceUnavailable(true);
          }
          break;
        }
      }
      if (!isCurrent()) return;

      let durableSnapshot: ResultDto[] | null = null;
      const known = baselineRef.current ?? baseline;
      try { durableSnapshot = await api.allResults(controller.signal); }
      catch { if (isCurrent()) setResultSyncUnavailable(true); }
      if (!isCurrent()) return;
      const durable = durableSnapshot ?? [];
      const finalTrace = mergeRuntimeTraceEvents(receivedRef.current, drainedTrace);
      const startSequence = replayTraceStartSequence.current;
      const rangeComplete = traceDrained && startSequence !== null && traceCursor.current === drainedTraceHead && hasCompleteRuntimeTraceRange(finalTrace, startSequence, drainedTraceHead);
      if (rangeComplete) { traceIssueRef.current = false; setTraceUnavailable(false); }
      else { traceIssueRef.current = true; setTraceUnavailable(true); }
      const sourceLinkedResults = traceIssueRef.current ? [] : sourceLinkedReplayResults(durable, finalTrace);
      const runResultsSorted = sourceLinkedResults;
      const newlyPersistedCount = durable.filter((result) => !known.has(result.result_id)).length;
      const resultSyncComplete = durableSnapshot !== null && newlyPersistedCount >= replay.results_persisted;
      if (!resultSyncComplete) setResultSyncUnavailable(true);
      if (!isCurrent()) return;
      cacheReplayEvidence(finalTrace, runResultsSorted);
      runResultsRef.current = runResultsSorted;
      setRunResults(runResultsSorted);
      dispatch({ type: "results", value: runResultsSorted, animate: true });

      let familyRequestComplete = false;
      let investigationRequestComplete = false;
      let evidenceConsistent = false;
      let contractValidated = !scenarioInfo?.demo;
      let validationReasons: string[] = [];
      try {
        const runIds = [...new Set(runResultsSorted.map((result) => result.result_id))];
        const derived = await api.investigations(controller.signal, runIds);
        if (!isCurrent()) return;
        const views = derived.family_views;
        const links = derived.links;
        familyRequestComplete = true;
        investigationRequestComplete = true;
        evidenceConsistent = validateScopedEvidence(views, links);
        if (!evidenceConsistent) setDerivedUnavailable(true);
        const acceptanceContract = scenarioInfo?.demo;
        if (acceptanceContract) {
          const validation = validateJudgeDemo(acceptanceContract, {
            records: replay.records_read,
            observations: replay.observations_emitted,
            results: runResultsSorted,
            familyViews: views,
            links,
            trace: finalTrace,
            traceAvailable: !traceIssueRef.current,
            runtimeCompleted: replay.state === "COMPLETED",
          });
          contractValidated = validation.ok;
          validationReasons = validation.reasons;
        }
        setFamilyViews(views);
        setInvestigationLinks(links);
      } catch {
        if (isCurrent()) setDerivedUnavailable(true);
      }

      if (!isCurrent()) return;
      const traceComplete = rangeComplete && !traceIssueRef.current;
      const barrierReady = replayFinalizationReady({
        runtimeCompleted: replay.state === "COMPLETED",
        traceDrained: traceComplete,
        resultAttributionComplete: resultSyncComplete && traceComplete,
        familyRequestComplete,
        investigationRequestComplete,
        demoContractValidated: contractValidated,
        scopedEvidenceConsistent: evidenceConsistent,
      });
      if (!barrierReady) {
        setDemoFailure(validationReasons.length ? validationReasons : [
          !traceComplete ? "Presentation trace could not be drained without gaps" : "Replay evidence synchronization did not complete",
        ]);
        setLifecycle("FAILED");
        return;
      }
      setLifecycle("READY");
      if (!traceIssueRef.current && replayTraceStartSequence.current !== null && replay.started_at && replay.finished_at && replay.scenario && replay.source_type) {
        saveLatestReplayMarker({ scenario: replay.scenario, sourceType: replay.source_type, startedAt: replay.started_at, finishedAt: replay.finished_at, startSequence: replayTraceStartSequence.current, endSequence: traceCursor.current });
      }
    })();
    return () => controller.abort();
  }, [replay?.state, replay?.started_at, replay?.finished_at, replay?.results_persisted, replay?.scenario, replay?.source_type, replay?.records_read, replay?.observations_emitted, baseline, dispatch, scenarioInfo?.demo]);

  const presentationSteps = useMemo(() => buildReplayPresentationSteps(receivedTrace, runResults, familyViews, investigationLinks), [receivedTrace, runResults, familyViews, investigationLinks]);
  const observationEvents = useMemo(() => receivedTrace.filter((event) => event.kind === "OBSERVATION_CREATED" && event.observation_id), [receivedTrace]);
  const schedule = useMemo(() => presentationSchedule(presentationSteps, replay?.scenario ?? "", sourceType, observationEvents.length, presentation), [presentationSteps, replay?.scenario, sourceType, observationEvents.length, presentation]);
  const effectiveStepIndex = presentation === "instant" || prefersReducedMotion() ? presentationSteps.length - 1 : Math.min(player.stepIndex, presentationSteps.length - 1);
  const currentStep = presentationSteps[effectiveStepIndex] ?? null;

  useEffect(() => {
    if (lifecycle !== "READY" || !presentationSteps.length || demoFailure.length || playbackFailure) return;
    if (presentation === "instant" || prefersReducedMotion()) return;
    if (player.paused || player.stepIndex >= presentationSteps.length - 1) return;
    const nextIndex = player.stepIndex + 1;
    const timer = setTimeout(() => dispatchPlayer({ type: "ADVANCE", stepCount: presentationSteps.length }), player.stepIndex < 0 ? 0 : schedule[nextIndex] ?? 300);
    return () => clearTimeout(timer);
  }, [lifecycle, presentation, player.paused, player.stepIndex, presentationSteps, schedule, demoFailure.length, playbackFailure]);

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
  const multiSourceResult = currentStep?.stage === "RESULT" && currentStep.sourceObservationIds.length > 1;
  const liveObservationId = currentStep?.focusObservationId ?? (currentStep?.stage === "RESULT" ? null : observations.at(-1)?.observation_id ?? null);
  const selectedObservation = multiSourceResult ? null : observations.find((event) => event.observation_id === (player.followLive ? liveObservationId : player.selectedObservationId)) ?? null;
  const selectedCanonical = selectedObservation?.canonical_observation;
  const selectedSourceRecord = selectedCanonical
    ? presentedTrace.find((event) => event.kind === "SOURCE_RECORD_ACCEPTED" && event.source_record?.record_number === Number(selectedCanonical.source_position))?.source_record ?? null
    : null;
  const analytics = useMemo(() => {
    const selectedId = selectedObservation?.observation_id;
    if (!selectedId) return [];
    const latest = latestReadinessByObservationLane(presentedTrace);
    const routes = observationRoutes.get(selectedId) ?? [];
    return routes.map((route) => {
      const results = visibleRunResults.filter((item) => item.lane_id === route.lane_id && item.source_observation_ids.includes(selectedId));
      const latestEvent = latest.get(observationLaneKey(selectedId, route.lane_id || ""));
      const laterResult = results.find((item) => item.source_observation_ids.length > 1);
      const status = laterResult ? `Contributes to later Result · ${laterResult.source_observation_ids.length} source observations`
        : results.some((item) => item.result_type === "ANALYTIC_UNAVAILABLE") ? "Unavailable"
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
  const routingCompletedObservationIds = new Set([
    ...presentedTrace.filter((event) => event.kind === "ROUTED" && event.observation_id).map((event) => event.observation_id!),
    ...revealedSteps.filter((step) => step.stage === "ROUTING" && step.observationId).map((step) => step.observationId!),
  ]);
  const explainedObservationIds = new Set(revealedSteps
    .filter((step) => step.stage === "ROUTING" || step.stage === "EVALUATION" || step.stage === "RESULT")
    .flatMap((step) => step.sourceObservationIds.length ? step.sourceObservationIds : step.observationId ? [step.observationId] : []));
  const relateNotApplicable = lifecycle === "READY" && familiesPresented && !derivedUnavailable && investigationLinks.length === 0;
  const sourceRecords = sourceType.toLowerCase().includes("pcap") ? "Packets" : "Records";
  const sourceCount = receivedTrace.filter((event) => event.kind === "SOURCE_RECORD_ACCEPTED").length || replay?.records_read || 0;
  const totalObservationCount = replay?.observations_emitted || observationEvents.length;
  const presentedRouteCount = observationRoutes.get(selectedObservation?.observation_id ?? "")?.length ?? 0;
  const observationIndex = selectedObservation ? observations.findIndex((event) => event.observation_id === selectedObservation.observation_id) : -1;
  const familyResultCounts = new Map<string, number>();
  for (const result of visibleRunResults) familyResultCounts.set(result.taxonomy[1], (familyResultCounts.get(result.taxonomy[1]) ?? 0) + 1);
  const resultTimeHeading = `Evidence time · ${formatTimeZoneLabel(zone)}`;
  const playbackDone = lifecycle === "READY" && presentationSteps.length > 0 && !demoFailure.length && !playbackFailure && effectiveStepIndex >= presentationSteps.length - 1;
  const currentStageLabel = playbackDone ? "COMPLETE" : playbackFailure ? "Playback unavailable" : demoFailure.length ? "Replay incomplete" : currentStep ? presentationStageLabel(currentStep.stage) : lifecycle === "READY" ? "Preparing playback" : "Runtime processing";
  const failureTitle = replay?.state !== "COMPLETED" ? "Runtime replay failed"
    : demoFailure.some((reason) => reason.toLowerCase().includes("inconsistent")) ? "Derived evidence inconsistency"
      : demoFailure.some((reason) => reason.startsWith("Expected") || reason.startsWith("Trace has") || reason.startsWith("A source-linked")) ? "Demo contract mismatch"
      : traceUnavailable ? "Presentation trace gap"
        : resultSyncUnavailable ? "Result synchronization incomplete"
          : derivedUnavailable ? "Derived evidence unavailable"
            : "Replay finalization incomplete";
  const diagnostic = lifecycle === "READY" && runResults.length === 0 && !resultSyncUnavailable ? traceUnavailable ? "Runtime trace unavailable; source-lineage Result attribution could not be established." : (replay?.results_persisted ?? 0) > 0 ? "The runtime reported persisted Results, but no durable Result could be linked to the current replay observations." : "Replay completed, but no mechanism Result was produced." : null;

  useEffect(() => {
    if (lifecycle !== "READY" || demoFailure.length || playbackFailure || playbackDone || player.paused) return;
    if (!presentationSteps.length) {
      const timer = setTimeout(() => setPlaybackFailure(true), 0);
      return () => clearTimeout(timer);
    }
    const longestStep = Math.max(0, ...schedule);
    const noProgressDeadline = Math.max(12000, longestStep * 3 + 5000);
    const timer = setTimeout(() => setPlaybackFailure(true), noProgressDeadline);
    return () => clearTimeout(timer);
  }, [lifecycle, demoFailure.length, playbackFailure, playbackDone, player.paused, player.stepIndex, presentationSteps.length, schedule]);

  const hasRun = lifecycle !== "IDLE" && lifecycle !== "STARTING" && Boolean(replay?.scenario);
  const visibleObservationIds = new Set(presentedTrace.filter((event) => event.kind === "OBSERVATION_CREATED").map((event) => event.observation_id).filter((id): id is string => Boolean(id)));
  const selectableObservations = playbackDone ? observations : observations.filter((event) => Boolean(event.observation_id && visibleObservationIds.has(event.observation_id)));
  const stages = ["Input", "Observe", "Route", "Evaluate", "Evidence", "Compose", "Relate"];
  const stageTimeTitle = `Runtime trace · local wall clock · ${formatTimeZoneLabel("local")}`;
  const recentResults = visibleRunResults.slice(-4);
  const runtimeCaption = replay?.state === "COMPLETED" ? `Runtime completed in ${replay.elapsed_wall_seconds.toFixed(2)} s` : running ? "Runtime processing is separate from presentation playback" : "Runtime processing time not available";
  const resetPlayback = () => { setPlaybackFailure(false); dispatchPlayer({ type: "RESET" }); };

  if (apiIncompatible) return <section className="page active-page traffic-lab-page" aria-labelledby="replay-title"><PageHeading titleId="replay-title" title="Traffic Lab" deck="Watch recorded or controlled passive observations become independent evidence." /><div className="stream-notice" role="alert">This Traffic Lab interface requires a newer runtime.</div></section>;
  if (demoAssetMismatch) return <section className="page active-page traffic-lab-page"><PageHeading title="Demo version mismatch" deck="The runtime completed, but the loaded demo asset does not match this interface version. Refresh or restart the application." /></section>;
  return <section className="page active-page traffic-lab-page" aria-labelledby="replay-title">
    <PageHeading titleId="replay-title" title="Traffic Lab" deck="Watch recorded or controlled passive observations become independent evidence." />
    {state.runtime?.dga_model_readiness && !dgaReady && <div className="stream-notice" role="status">DGA model unavailable in this deployment. The DGA + DNS demo is disabled.</div>}

    {(lifecycle === "IDLE" && (showPicker || !hasRun)) && <section className="panel scenario-picker-panel demo-scenario-panel">
      <div className="panel-head compact"><div><span className="eyebrow">Passive traffic demonstrations</span><h2>Choose a demo scenario</h2><p>Each demo highlights one EvidenceGate capability using recorded or controlled passive input.</p></div></div>
      <div className="scenario-list">{availableScenarios.map((scenario) => <div className={"scenario-row" + (scenario.recommended ? " recommended" : "")} key={scenario.id}>
        <div><strong>{scenario.demo?.title || scenario.label}{scenario.recommended && <span className="recommended-tag">Recommended demo</span>}</strong><span>{scenario.demo?.purpose || normalizeFamilyName(scenario.family) + " evidence"}</span><small>{scenario.demo?.sourceLabel || sourceLabel(scenario.source_type)}{scenario.unavailableReason ? " · " + scenario.unavailableReason : ""}</small>{scenario.demo?.episodeSummary && <small className="scenario-episode-summary">{scenario.demo.episodeSummary.join(" · ")}</small>}</div>
        <button className="primary-button" disabled={running || busy || Boolean(scenario.unavailableReason)} onClick={() => void runScenario(scenario.id)}>{scenario.unavailableReason ? "Unavailable" : "Run demo"}</button>
      </div>)}</div>
      {!availableScenarios.length && <EmptyState>No judge demo scenarios are available from the runtime.</EmptyState>}
    </section>}
    {lifecycle === "STARTING" && <div className="panel replay-diagnostic" role="status">Starting {availableScenarios.find((scenario) => scenario.id === startingScenarioId)?.demo?.title || "demo scenario"}…</div>}

    {hasRun && replay && <>
      <section className="panel player-run-header">
        <div className="run-title-row"><div><span className="eyebrow">{scenarioInfo?.demo?.sourceLabel || sourceLabel(sourceType)}</span><h2>{scenarioName}</h2><p>{lifecycle === "PROCESSING" ? "Runtime processing in progress." : lifecycle === "FINALIZING" ? "Synchronizing runtime outcome and evidence…" : lifecycle === "READY" ? runtimeCaption + ". Playback below is paced for explanation." : lifecycle === "FAILED" ? "Replay failed." : "Controlled replay"}</p></div><div className="run-header-actions"><span className={"status-chip" + (running ? " running" : lifecycle === "FAILED" || demoFailure.length ? " warning" : " neutral")}>{playbackDone ? "COMPLETE" : demoFailure.length ? "Demo unavailable" : playbackFailure ? "Playback could not complete" : lifecycle === "FINALIZING" ? "Finalizing" : lifecycle === "READY" ? "Runtime complete" : running ? "Running" : lifecycle === "FAILED" ? "Replay failed" : replay.state}</span>{(playbackDone || lifecycle === "FAILED" || demoFailure.length > 0 || playbackFailure) && <button className="secondary-button" onClick={() => { setShowPicker(true); setLifecycle("IDLE"); }}>← Choose another scenario</button>}</div></div>
        <div className="run-hero-metrics">
          <div><span>Input</span><strong>{lifecycle === "READY" ? sourceCount + " " + sourceRecords.toLowerCase() : running ? "Processing" : sourceCount + " " + sourceRecords.toLowerCase()}</strong></div>
          <div><span>Observations</span><strong>{lifecycle === "READY" ? replay.observations_emitted : running ? "Processing" : replay.observations_emitted}</strong></div>
          <div><span>Evidence</span><strong>{lifecycle === "READY" ? traceUnavailable ? replay.results_persisted + " Results · playback unavailable" : runResults.length + " Results" : running ? "Processing" : replay.results_persisted + " Results"}</strong></div>
          <div><span>Families</span><strong>{lifecycle !== "READY" ? "Processing" : derivedUnavailable ? "Unavailable" : familyGroups.length ? familyGroups.map((group) => normalizeFamilyName(group.family)).join(" + ") : "No family evidence"}</strong></div>
          <div><span>Related context</span><strong>{lifecycle !== "READY" ? "Processing" : derivedUnavailable ? "Unavailable" : investigationLinks.length ? investigationLinks.length + " factual " + (investigationLinks.length === 1 ? "relationship" : "relationships") : "No cross-family relationship in this scenario"}</strong></div>
        </div>
        {lifecycle === "READY" && <div className="playback-progress" aria-label="Playback progress"><strong>PLAYBACK PROGRESS</strong><span>Evidence shown {visibleRunResults.length} / {runResults.length}</span><span>Family stage {familiesPresented ? familyGroups.length + " composed" : "Not shown yet"}</span><span>Related context {linksPresented ? investigationLinks.length ? investigationLinks.length + " shown" : "No cross-family relationship in this scenario" : "Shown after family composition"}</span></div>}
        <div className="demo-player-controls"><span>{player.paused ? "Playback paused" : playbackDone ? "Playback complete" : "Playback is paced for explanation"}{prefersReducedMotion() ? " · reduced motion" : ""}</span><div className="player-actions">
          {!playbackDone && <button className="secondary-button" disabled={lifecycle !== "READY" || Boolean(demoFailure.length) || playbackFailure} onClick={() => dispatchPlayer({ type: player.paused ? "RESUME" : "PAUSE" })}>{player.paused ? "Resume" : "Pause"}</button>}
          {(playbackDone || playbackFailure) && <button className="secondary-button" onClick={resetPlayback}>Replay animation</button>}
          {demoFailure.length > 0 && <button className="secondary-button" onClick={() => void runScenario(replay.scenario!)}>Try again</button>}
        </div></div>
        <ol className="episode-stage-rail" aria-label="Replay evidence stages">{stages.map((label, index) => { const notApplicable = index === 6 && relateNotApplicable; const complete = !notApplicable && (playbackDone || stageAvailable[index] && index < activeStage); const active = !notApplicable && !complete && index === activeStage && lifecycle === "READY" && !demoFailure.length && !playbackFailure; return <li key={label} className={(complete ? "complete" : "") + (active ? " active" : "") + (notApplicable ? " not-applicable" : "")} title={notApplicable ? "No cross-family relation is expected for this scenario" : undefined} aria-current={active ? "step" : undefined}><span>{notApplicable ? "—" : complete ? "✓" : active ? "●" : "○"}</span>{label}</li>; })}</ol>
      </section>

      {demoFailure.length > 0 && <div className="replay-diagnostic demo-unavailable" role="alert"><strong>{failureTitle}</strong><p>{replay?.state === "COMPLETED" ? "The runtime completed, but the replay evidence did not pass finalization." : "The runtime did not complete this replay."}</p><details><summary>Technical details</summary><ul>{demoFailure.map((reason) => <li key={reason}>{reason}</li>)}</ul></details></div>}
      {playbackFailure && <div className="replay-diagnostic" role="alert"><strong>Playback could not complete</strong><p>Runtime evidence remains available below.</p><button className="text-button" onClick={() => navigate("results")}>Open Evidence →</button></div>}
      {lifecycle === "FAILED" && <div className="replay-diagnostic" role="alert"><strong>Replay failed</strong><p>{error || replay.error || "Runtime replay could not be completed."}</p><button className="secondary-button" onClick={() => void runScenario(replay.scenario!)}>Try again</button></div>}
      {traceUnavailable && replay.results_persisted > 0 && <div className="replay-diagnostic" role="status"><strong>Detailed playback unavailable</strong><p>The runtime reports {replay.results_persisted} persisted Results. The presentation trace could not be verified, so this timeline was not animated.</p><button className="text-button" onClick={() => navigate("results")}>Open Evidence →</button></div>}

      <section className="episode-player-grid" aria-label="Evidence episode player">
        <aside className="panel observation-sequence-panel"><div className="player-panel-head"><div><span className="eyebrow">Observation sequence</span><strong>{multiSourceResult ? currentStep!.sourceObservationIds.length + " observations contributed" : selectedObservation ? (sourceType.toLowerCase().includes("pcap") ? "Packet " : "Observation ") + (observationIndex + 1) + " of " + totalObservationCount : totalObservationCount + " observations"}</strong></div>{!player.followLive && <button className="text-button" onClick={() => dispatchPlayer({ type: "FOLLOW_LIVE" })}>Resume live focus</button>}</div>
          <div className="observation-sequence-list">{selectableObservations.map((event) => { const index = observations.findIndex((item) => item.observation_id === event.observation_id); const current = selectedObservation?.observation_id === event.observation_id; const routeCount = observationRoutes.get(event.observation_id || "")?.length ?? 0; const explained = explainedObservationIds.has(event.observation_id || "") && !current; const noRoute = routeCount === 0 && routingCompletedObservationIds.has(event.observation_id || ""); return <button type="button" className={"observation-sequence-item" + (current ? " selected" : "") + (noRoute ? " no-route" : "") + (explained ? " explained" : "")} key={event.observation_id} title={noRoute ? "No eligible analytics" : undefined} aria-label={(sourceType.toLowerCase().includes("pcap") ? "Packet " : "Observation ") + (index + 1) + " of " + totalObservationCount + (noRoute ? ": no eligible analytics" : "")} aria-pressed={current} onClick={() => dispatchPlayer({ type: "SELECT_OBSERVATION", observationId: event.observation_id! })}><span>{explained ? "✓" : current ? "●" : noRoute ? "·" : "○"}</span></button>; })}{!selectableObservations.length && <p className="player-waiting">{lifecycle === "READY" ? "No canonical observation was emitted." : "Preparing the first observation…"}</p>}</div><p className="sequence-caption">{multiSourceResult ? "Evidence from " + currentStep!.sourceObservationIds.length + " observations" : selectedObservation ? observationLabel(selectedObservation.observation_type) : playbackDone ? "All observations presented" : "Observations become selectable as the timeline advances."}</p>
        </aside>
        <article className="panel current-observation-panel" aria-live="polite">
          <div className="player-panel-head"><div><span className="eyebrow">{multiSourceResult ? "Evidence source context" : "Current observation"}</span><strong>{multiSourceResult ? currentStep!.sourceObservationIds.length + " observations contributed" : selectedObservation ? (sourceType.toLowerCase().includes("pcap") ? "Packet " : "Observation ") + (observationIndex + 1) + " of " + totalObservationCount : playbackDone ? "Complete" : "Preparing observation"}</strong></div><span className="stage-state-pill">{currentStageLabel}</span></div>
          {multiSourceResult ? <div className="observation-hero"><h2>Evidence from {currentStep!.sourceObservationIds.length} observations</h2><p>This Result retains its full contributing observation set. No single packet is presented as its owner.</p><div className="observation-facts">{currentStep!.sourceObservationIds.map((id) => <span key={id}>{observations.findIndex((event) => event.observation_id === id) + 1}. {sourceType.toLowerCase().includes("pcap") ? "Packet" : "Observation"}</span>)}</div></div> : selectedObservation ? <ObservationWorkbench observation={selectedObservation.canonical_observation ?? null} source={selectedSourceRecord} routes={observationRoutes.get(selectedObservation.observation_id || "") ?? []} results={visibleRunResults.filter((result) => result.source_observation_ids.includes(selectedObservation.observation_id || ""))} eventTimeZone={zone} /> : <div className="observation-empty">{traceUnavailable && runResults.length ? "Detailed playback unavailable; durable evidence remains available." : diagnostic || (playbackDone ? "Complete" : "Playback will focus the relevant source observation.")}</div>}
          {selectableObservations.length > 1 && !multiSourceResult && <div className="observation-pager"><button className="text-button" disabled={!selectedObservation || observationIndex <= 0} onClick={() => { const previous = selectableObservations[observationIndex - 1]; if (previous?.observation_id) dispatchPlayer({ type: "SELECT_OBSERVATION", observationId: previous.observation_id }); }}>← Previous</button><span>{selectedObservation ? observationIndex + 1 + " / " + totalObservationCount : "—"}</span><button className="text-button" disabled={!selectedObservation || observationIndex >= selectableObservations.length - 1} onClick={() => { const next = selectableObservations[observationIndex + 1]; if (next?.observation_id) dispatchPlayer({ type: "SELECT_OBSERVATION", observationId: next.observation_id }); }}>Next →</button></div>}
        </article>
        <section className="panel fanout-panel"><div className="player-panel-head"><div><span className="eyebrow">Zero-to-many routing</span><strong>{selectedObservation ? routingCompletedObservationIds.has(selectedObservation.observation_id || "") && !presentedRouteCount ? "No eligible analytics" : presentedRouteCount + " analytics" : multiSourceResult ? "Source-linked evidence" : "Analytics"}</strong></div><span className="stage-state-pill">{selectedObservation && routingCompletedObservationIds.has(selectedObservation.observation_id || "") ? "Routing complete" : lifecycle === "READY" ? "In playback" : "Processing"}</span></div>
          {selectedObservation && analytics.length ? <div className="fanout-list">{analytics.map((item, index) => { const result = runResults.find(value => value.lane_id === item.lane_id && value.source_observation_ids.includes(selectedObservation.observation_id || "")); const expanded = result?.result_id === expandedFanoutResultId; const explanation = result ? projectResultExplanation(result, receivedTrace, selectedObservation.canonical_observation) : null; return <article className="fanout-analytic" key={(item.observation_id || "") + (item.lane_id || "")} style={{ "--route-delay": Math.min(index, 8) * 150 + "ms" } as CSSProperties}><span className="fanout-connector" aria-hidden="true" /><div><strong>{mechanismLabel(item.mechanism || item.lane_id || "Analytic")}</strong><small>{item.status}</small>{result && explanation && <><button className="text-button fanout-why-button" aria-expanded={expanded} onClick={() => setExpandedFanoutResultId(expanded ? null : result.result_id)}>{expanded ? "Hide explanation" : "Why this result?"}</button>{expanded && <div className="inline-result-explanation"><strong>Why this analytic ran</strong><p>{explanation.eligibilityReasons.join(" ")}</p><strong>Observed</strong><ul>{explanation.observedFacts.map(fact=><li key={fact}>{fact}</li>)}</ul><strong>Why the Result was emitted</strong><p>{explanation.resultReason}</p><strong>Supports</strong><ul>{explanation.supports.map(fact=><li key={fact}>{fact}</li>)}</ul><strong>Does not establish</strong><ul>{explanation.limitations.map(fact=><li key={fact}>{fact}</li>)}</ul>{explanation.missingEvidence.length>0&&<><strong>Missing evidence</strong><ul>{explanation.missingEvidence.map(fact=><li key={fact}>{fact}</li>)}</ul></>}<span>Source lineage · {explanation.sourceObservationIds.length} observation</span></div>}</>}</div>{item.status === "Evidence produced" ? <span className="fanout-result-mark">✓</span> : null}</article>; })}</div> : selectedObservation && routingCompletedObservationIds.has(selectedObservation.observation_id || "") && !presentedRouteCount ? <div className="fanout-empty"><strong>No eligible analytics</strong><p>This observation was retained, but no active analytic declared it eligible.</p></div> : <div className="fanout-empty">{playbackDone ? "No eligible analytics for the selected observation." : "Routing stage not shown yet."}</div>}
        </section>
      </section>

      <NetworkObservationsSection events={receivedTrace} results={runResults} zone={zone} navigate={navigate} />
      <section className="panel evidence-outcome-panel"><div className="outcome-heading"><div><span className="eyebrow">Playback evidence</span><h2>{visibleRunResults.length} / {runResults.length} Results shown</h2></div><span>{presentedReviewCount} review · {presentedLimitationCount} evidence limitations shown</span></div>
        <div className="outcome-track"><div><strong>Mechanism evidence</strong><span>{visibleRunResults.length} of {runResults.length} source-linked Results shown</span>{familyResultCounts.size > 0 && <div className="result-family-counts">{[...familyResultCounts].map(([family, count]) => <div key={family}><span>{normalizeFamilyName(family)}</span><strong>{count}</strong></div>)}</div>}</div><span className="outcome-chevron">↓</span><div><strong>Family evidence</strong><span>{derivedUnavailable ? "Family composition unavailable" : familiesPresented ? familyGroups.length + " families composed" : lifecycle === "READY" ? "Family stage not shown yet" : "Runtime processing"}</span>{derivedUnavailable && <p>Derived evidence unavailable</p>}{familyGroups.length > 0 && <div className="family-outcome-groups">{familyGroups.map((group) => <details className="family-outcome-group" key={group.family}><summary><strong>{normalizeFamilyName(group.family)}</strong><span>{group.views.length} episode{group.views.length === 1 ? "" : "s"} · {group.views.reduce((sum, view) => sum + view.findings.length, 0)} independent findings · {group.views.filter((view) => view.limitations.length || view.missing_evidence.length).length} with limits</span></summary><p className="family-composition-note">Composed from {group.views.reduce((sum, view) => sum + view.findings.length, 0)} independent mechanism Results through shared source-observation lineage. This preserves child claim ceilings and applies no score fusion.</p><div className="family-episode-list">{group.views.map((view) => <div key={view.family_view_id}><time title={formatEvidenceDateTime(view.time_start, zone)}>{formatEvidenceClockTime(view.time_start, zone)}</time><span>{pluralize(view.findings.length, "finding")} · {view.limitations.length + view.missing_evidence.length} limits</span><button className="text-button" onClick={() => navigate("alerts", { familyViewId: view.family_view_id })}>Review →</button></div>)}</div></details>)}</div>}</div><span className="outcome-chevron">↓</span><div><strong>Related context</strong><span>{derivedUnavailable ? "Related context unavailable" : investigationLinks.length === 0 ? "No cross-family relationship in this scenario" : linksPresented ? "Shared source context; no causal inference" : "Relation stage not shown yet"}</span>{relationGroups.map((group) => <article className="relation-outcome" key={group.leftFamily + ":" + group.rightFamily}><div><strong>{normalizeFamilyName(group.leftFamily)} ↔ {normalizeFamilyName(group.rightFamily)}</strong><span>{pluralize(group.links.length, "factual relationship")} · {new Set(group.sharedObservationIds).size} shared source observations</span></div><small>These family views share {new Set(group.sharedObservationIds).size} exact passive source observations. This supports joint analyst review; it does not establish causality, a common attacker, or attack progression.</small></article>)}</div></div>
      </section>
      <section className="panel recent-evidence-panel"><div className="player-panel-head"><div><span className="eyebrow">{resultTimeHeading}</span><strong>Recent evidence</strong></div><button className="text-button" onClick={() => navigate("results")}>View all evidence ({runResults.length}) →</button></div>{recentResults.length ? <div className="recent-result-list">{recentResults.map((result) => <article key={result.result_id}><time title={formatEvidenceDateTime(result.created_time, zone)}>{formatEvidenceClockTime(result.created_time, zone)}</time><div><strong>{mechanismLabel(result.mechanism_id || result.lane_id)}</strong><small>{readable(result.result_type)} · {pluralize(result.source_observation_ids.length, "source observation")}</small><span>{contextSummary(result)}</span></div><button className="text-button" onClick={() => navigate("results", { resultId: result.result_id })}>Review →</button></article>)}</div> : <p className="player-waiting">{resultSyncUnavailable ? "Durable Results could not be synchronized." : lifecycle === "READY" && !runResults.length ? diagnostic || "No mechanism Result was produced." : "Results will appear after runtime finalization."}</p>}</section>
      {error && <div className="stream-notice" role="status">{error}</div>}
      {developerUi && <>
        {developerUi && <><details className="technical-details-panel"><summary>Run details</summary><div className="technical-details-grid"><div><span>Scenario</span><strong>{scenarioName}</strong></div><div><span>Input type</span><strong>{sourceType}</strong></div><div><span>Release</span><strong>{state.runtime?.release_id ?? "Unavailable"}</strong></div><div><span>Source SHA</span><strong>{state.runtime?.source_sha ?? "Unavailable"}</strong></div><div><span>Demo asset</span><strong>{scenarioInfo?.asset_version ?? "Not reported"}</strong></div><div><span>Demo contract</span><strong>{demoContract ? demoFailure.length ? "Failed · judge-demo-v2" : playbackDone ? "Passed · judge-demo-v2" : "Pending · judge-demo-v2" : "Internal scenario"}</strong></div><div><span>Runtime elapsed</span><strong>{replay.elapsed_wall_seconds.toFixed(2)} s</strong></div><div><span>Durable source-linked Results</span><strong>{runResults.length}</strong></div><div><span>Results shown</span><strong>{visibleRunResults.length}</strong></div><div><span>Trace events presented</span><strong>{presentedTrace.length}{traceUnavailable ? " · partial/unavailable" : ""}</strong></div></div></details>
        <details className="technical-details-panel"><summary>View evidence Results ({visibleRunResults.length} shown / {runResults.length} total)</summary>{visibleRunResults.map((result) => <div className="technical-result-row" key={result.result_id}><strong>{normalizeFamilyName(result.taxonomy[1])}</strong><span>{mechanismLabel(result.mechanism_id || result.lane_id)}</span><code>{result.result_id}</code><button className="text-button" onClick={() => navigate("results", { resultId: result.result_id })}>Open →</button></div>)}</details>
        <details className="technical-details-panel raw-trace-details"><summary>View presented runtime trace ({presentedTrace.length} events)</summary><p className="technical-time-heading">{stageTimeTitle} · not observed network event time</p>{presentedTrace.map((event) => <div className="technical-result-row trace-detail-row" key={event.sequence}><time title={"Runtime trace · " + formatEvidenceDateTime(event.occurred_at, "local")}>{formatEvidenceClockTime(event.occurred_at, "local")}</time><strong>{readable(event.kind)}</strong><span>{event.mechanism || event.reason || event.readiness || "Runtime telemetry"}</span><code>#{event.sequence}</code></div>)}</details></>}
      </>}
    </>}
  </section>;}

function presentationStageLabel(stage: ReplayPresentationStage) {
  const names: Record<ReplayPresentationStage, string> = { SOURCE: "Passive input", OBSERVATION: "Observation", VISIBILITY: "Visibility", ROUTING: "Zero-to-many routing", EVALUATION: "Analytic evaluation", RESULT: "Mechanism evidence", FAMILY: "Family composition", RELATION: "Related context" };
  return names[stage];
}
