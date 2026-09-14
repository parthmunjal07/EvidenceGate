# SIH26145 — Gemini 3.1 Pro Implementation Prompts v1.1

Use the prompts in order. Attach the named project documents as context. `MVP_IMPLEMENTATION_CONTRACT_v1.1.md` is frozen Control Room authority: Gemini must implement it, not reinterpret it. Gemini is not allowed to research, redesign architecture, or invent threat analytics.

---

## Prompt 1 — Fresh-repository bootstrap and implementation setup

```text
You are Gemini 3.1 Pro bootstrapping a brand-new SIH26145 EvidenceGate repository for shared-runtime implementation.

AUTHORITATIVE INPUTS

1. MVP_SYSTEM_RESEARCH_HANDOFF_v1.2.md, including Amendment A1 / DEC-SYS-27.
2. MVP_IMPLEMENTATION_CONTRACT_v1.1.md, status `CONTROL ROOM APPROVED — READY FOR PARTH IMPLEMENTATION`.
3. No existing application code. Treat the repository as empty apart from normal git metadata.

TASK

Create the minimal repository foundation required by the contract. The contract is corrected and frozen; do not edit, restate, or reinterpret it.

OUTPUT

OUTPUT

Create the following foundation and return a short `IMPLEMENTATION_BOOTSTRAP_REPORT.md` covering:

1. A Python package skeleton matching the contract boundaries.
2. `pyproject.toml` with a minimal pinned dependency set.
3. `README.md` stating scope, setup, run, test, and explicit no-go boundaries.
4. Test/configuration directories and a runnable test command.
5. Contract conflicts or missing prerequisites that genuinely block coding.
6. The dependency-minimal build order for Prompt 2.

Do not implement analytics in this prompt. Do not request scientific choices. Treat ungoverned threat-specific state/analytic requirements as deferred, not as gaps to fill. Do not add placeholder threat scores or fake data.

HARD INVARIANTS TO CHECK

- Ingest admission is before state mutation but does not reject `WARMING_UP`, `INSUFFICIENT_HISTORY`, or `STATE_EVICTED`.
- Evaluation readiness occurs after state update.
- Canonicalization is pure and returns observations plus control events.
- Lane ingress is bounded before admission; the dispatcher computes state key then sends to a deterministic shard.
- Governance owns `allowed_result_types`; result permissions are never inferred from status names.
- A scaffold can use `NOT_YET_GOVERNED` state and cannot invent analytic state science.
- Result plus mandatory evidence/provenance/link rows are atomic and idempotent in SQLite.
```

---

## Prompt 2 — Parth shared-runtime implementation

```text
You are Gemini 3.1 Pro acting as Parth’s implementation engineer for SIH26145 EvidenceGate.

AUTHORITATIVE INPUTS

1. MVP_SYSTEM_RESEARCH_HANDOFF_v1.2.md with Amendment A1.
2. MVP_IMPLEMENTATION_CONTRACT_v1.1.md, status `CONTROL ROOM APPROVED — READY FOR PARTH IMPLEMENTATION`.
3. The fresh repository created by Prompt 1.

MISSION

Implement only the shared EvidenceGate runtime described by the contract. Do not implement or tune a scientific threat detector.

WORKING RULES

- Start from the scaffold created by Prompt 1 and create missing files/directories as required.
- If an implementation choice is not specified by the contract, choose the smallest local option and record it as an assumption.
- Use Python typed immutable dataclasses for hot-path domain objects.
- Use a static registry; no dynamic third-party plugin loading.
- Keep the application single-host and modular.
- Record every dependency/version introduced and its license.
- Do not use a central classifier, Kafka, Flink, Akka, Redis, Elasticsearch, Kubernetes, blockchain, payload decryption, or active network response.

IMPLEMENT IN THIS ORDER

1. Domain package:
   - frozen enums and immutable data classes;
   - separate NetworkObservation and RuntimeControlEvent unions;
   - canonical field-presence semantics;
   - source/provenance/quality/gap/governance/result types.

2. Canonicalization boundary:
   - InputSource protocol;
   - RawSourceRecord;
   - pure CanonicalizationResult with observations and control events;
   - no parser-side publishing or database writes.

3. Governance and registry:
   - versioned read-only LaneGovernance;
   - status, phase, blockers, claim ceiling, ingest permission, and allowed_result_types;
   - static manifest validation;
   - scaffold-compatible NOT_APPLICABLE / NOT_YET_GOVERNED state specs.

4. Runtime pipeline exactly as follows:

   relevance router
   -> bounded lane ingress queue
   -> ingest admission
   -> state key
   -> deterministic shard dispatcher
   -> state update
   -> evaluation readiness
   -> plugin analytic
   -> result validator
   -> atomic result writer.

   Ingest admission must not reject an observation for WARMING_UP, INSUFFICIENT_HISTORY, or STATE_EVICTED. Those are evaluation-readiness states after factual state can be updated.

5. Bounded state and gap lifecycle:
   - lane-local queues and health;
   - deterministic per-key ordering;
   - lossless replay backpressure;
   - explicit live quality gaps;
   - declared GapAction only when governed;
   - a non-governed scaffold must not invent state recovery science.

6. Results, SQLite, API, and metrics:
   - immutable result union;
   - AnalyticUnavailable as the single unavailable result type;
   - atomic/idempotent SQLite write of result plus mandatory children;
   - cursor-based REST queries and bounded WebSocket notifications;
   - Prometheus metrics with bounded labels only.

7. Scaffolds and tests:
   - include at most contract-safe scaffolds that validate lifecycle/routing/health;
   - no ThreatAlert/confidence/severity/threat score from scaffolds;
   - implement the contract acceptance tests IC-01 through IC-18 before any performance claim.

MANDATORY NO-GO LIST

Do not choose or hardcode:

- DDoS thresholds/windows/features;
- DGA lexical features/models;
- DNS tunnelling representations, state keys, windows, or scores;
- Recon rules/authorization truth;
- C2 scorer or periodicity rule;
- TLS/QUIC detection feature/model;
- unusual-transfer history definition;
- confidence/severity semantics;
- cross-lane correlation rule;
- fixed queue capacities/shard counts.

DELIVERABLES

1. Working code in the fresh repository.
2. A concise IMPLEMENTATION_REPORT.md containing:
   - commit/version;
   - changed files and purpose;
   - interfaces and data flow;
   - contract decision IDs and acceptance tests mapped to code;
   - dependencies/licenses;
   - assumptions, deviations, limitations, and technical debt.
3. Test command(s) and their output, including IC-01 through IC-18 mapping.
4. A list of any item blocked by missing repository context or scientific governance.

STOP CONDITION

Stop after the shared runtime and contract tests are complete. Do not proceed to threat-analytic implementation, benchmark claims, or UI polishing beyond the generic contract endpoints/views.
```

## Prompt 3 — Contract test completion

```text
You are Gemini 3.1 Pro acting as the verification engineer for SIH26145 EvidenceGate.

Read MVP_SYSTEM_RESEARCH_HANDOFF_v1.2.md, MVP_IMPLEMENTATION_CONTRACT_v1.1.md, the repository, and IMPLEMENTATION_REPORT.md.

Implement TEST_PLAN_v1.md and all missing tests. Verify IC-01 through IC-18, including:

- zero-to-many routing;
- admission versus evaluation readiness and warm-up;
- causal availability/finality;
- deterministic state-key sharding and concurrent lanes;
- queue saturation and quality gaps;
- scaffold result restrictions;
- read-only governance and allowed_result_types;
- atomic SQLite rollback and duplicate result_id behavior;
- pure canonicalization;
- bounded metric labels and slow WebSocket recovery.

Use deterministic fixtures. Do not use threat labels, invented thresholds, fake confidence, or production-performance claims.

Deliver:
1. TEST_PLAN_v1.md
2. test code and fixtures
3. test report showing each IC criterion as PASS, FAIL, or BLOCKED with evidence
4. updated IMPLEMENTATION_REPORT.md
```

## Prompt 4 — Benchmark execution plan and measurement

```text
You are Gemini 3.1 Pro acting as the performance engineer for SIH26145 EvidenceGate.

Read the research handoff, implementation contract, TEST_PLAN_v1.md, and current runtime. Do not change scientific behavior.

Create BENCHMARK_PLAN_v1.md defining reproducible measurements for:

- input, routed, admitted, processed, and dropped rates;
- queue depth, oldest age, and saturation;
- plugin and persistence p50/p95/p99 latency;
- end-to-end latency with event-time and causal-availability definitions;
- state count, memory/RSS, CPU, event-loop lag;
- concurrent lanes, shard concurrency, replay pacing, and slow clients.

Use synthetic infrastructure fixtures only to measure runtime behavior. Do not claim detector accuracy or real-world generalization. Record machine, Python, SQLite, dependency, dataset/fixture, configuration, run ID, and commit/version.

Run only after IC-01 through IC-18 pass. Deliver benchmark scripts, raw outputs, a reproducible report, and explicit limitations. Never hardcode queue capacities or shard counts into the contract.
```

## Prompt 5 — Documentation and operator handoff

```text
You are Gemini 3.1 Pro acting as the documentation engineer for SIH26145 EvidenceGate.

Read the research handoff, implementation contract, implementation report, test report, and benchmark report.

Create DOCUMENTATION_PLAN_v1.md and implement the documentation needed to operate and defend the MVP:

- README setup/run/test instructions;
- architecture and data-flow explanation;
- configuration and governance reference;
- plugin author contract;
- API and WebSocket examples;
- quality-gap, abstention, and unavailable-result behavior;
- SQLite persistence and replay notes;
- troubleshooting/runbook;
- dependency and license inventory;
- explicit scientific no-go boundaries.

Documentation must distinguish observation, evidence, analytic status, operational health, and threat claims. Do not describe scaffolds as detectors and do not invent performance or accuracy numbers.
```

## Prompt 6 — Final implementation audit and traceability

```text
You are Gemini 3.1 Pro performing the final independent implementation audit for SIH26145 EvidenceGate.

Read all authoritative handoffs, the implementation contract, source code, tests, benchmark outputs, and documentation.

Produce:

1. CODE_TRACEABILITY_HANDOFF.md mapping contract decision IDs DEC-SYS-01 through DEC-SYS-34 and IC-01 through IC-18 to files, classes, functions, and tests.
2. CODE_EXPLAINER.md explaining input source -> canonical observation/control event -> quality -> router -> lane ingress -> ingest admission -> state/shard -> evaluation readiness -> analytic/scaffold -> validator -> atomic persistence -> API/UI.

Audit for:

- history/readiness deadlock;
- accidental state mutation before admission;
- canonicalizer side effects;
- unbounded queues or metric labels;
- result permission bypass;
- partial SQLite commits;
- fake threat claims/confidence/severity;
- undocumented dependencies and licenses;
- contract deviations, assumptions, limitations, and technical debt.

Do not modify scientific contracts or silently fix material deviations. Report each as PASS, CORRECTED, OPEN, or BLOCKED with evidence.
```
