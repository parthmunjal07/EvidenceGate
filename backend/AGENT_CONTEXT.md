# EVIDENCEGATE — BACKEND AGENT CONTEXT

## PROJECT

Project: SIH26145 — AI-Based Detection of Cyber Threats in Unidirectional IP Traffic

Product working name: EvidenceGate

Current objective: build a truthful, passive, streaming network-evidence backend
for the SIH internal round.

This repository is the implementation workspace.

---

# 1. CORE RULE

Do not build "a cyber-threat detector" all at once.

Build a thin, testable evidence pipeline:

```
SOURCE
  ↓
FACTUAL OBSERVATIONS
  ↓
BOUNDED STATE
  ↓
THREAT-SPECIFIC ANALYTIC
  ↓
REVISIONABLE EVIDENCE
  ↓
EPISODE / CASE
  ↓
API / UI
```

Every layer must preserve what was actually observed.

Missing information must never silently become benign information.

---

# 2. AUTHORITY ORDER

When making implementation decisions, use:

1. Official SIH26145 problem statement
2. SEVEN_THREAT_DECISION_BOARD
3. SEVEN_ANALYTIC_SPECIFICATIONS
4. Accepted Product/System/Data+ML contracts
5. Existing Network Replayer implementation
6. Accepted backend architecture/task contracts
7. Research documents
8. Agent assumptions

If sources conflict:

```
DO NOT silently resolve the conflict.
```

Report:

```
CONFLICT
SOURCES
IMPACT
DECISION REQUIRED
```

---

# 3. CURRENT BACKEND STRATEGY

The backend is being built incrementally.

Current vertical slice:

```
Network Replayer
    ↓
ReplaySource adapter
    ↓
Canonical factual observations
    ↓
bounded keyed state
    ↓
Recon breadth measurement
    ↓
revisionable evidence
```

Do not jump ahead to seven detectors.

Do not add ML until the corresponding data/analytic contract justifies it.

---

# 4. NETWORK REPLAYER

The existing Network Replayer is infrastructure.

It is NOT EvidenceGate's threat detector.

Reuse it.

Do NOT:

* rewrite the PCAP parser
* duplicate replay logic
* change established replay semantics
* embed threat detection into the replayer
* make the backend depend on internal implementation details unnecessarily

EvidenceGate should consume the Replayer through a narrow source abstraction.

Conceptual interface:

```
ReplaySource
    →
canonical factual observations
```

Future sources such as:

```
LivePacketSource
FlowSource
```

may eventually implement the same conceptual boundary.

Do NOT implement them now.

---

# 5. TIME SEMANTICS

Always distinguish:

```
event_time
ingest_time
emit_time
replay wall-clock time
```

Captured/event time is the scientific time.

Replay wall-clock timing is an execution property.

Changing replay speed must not change event-time analytics.

Never use:

```
datetime.now()
```

as a replacement for captured event_time.

Stateful analytics must operate on declared event-time horizons.

---

# 6. CANONICAL OBSERVATIONS

Canonical observations describe facts.

They must remain threat-neutral.

Examples:

```
TCP packet observed
source contacted destination
destination port observed
DNS query observed
QNAME observed
```

Not:

```
reconnaissance detected
malicious DNS
attack
suspicious traffic
threat score
confidence
```

Common factual information may include:

* event_id
* event_type
* event_time
* ingest_time
* source/destination
* ports
* protocol
* direction semantics
* packet/flow identity
* visible protocol facts
* observation contract
* capture/source identity
* quality metadata
* parser/config version
* provenance

Do not create a universal feature vector.

Different analytics require different observations.

---

# 7. OBSERVATION CONTRACT

Every analytic must explicitly state what it requires.

Do not assume every analytic can consume every observation.

An analytic may declare:

* accepted observation types
* required fields
* required visibility/direction
* event-time horizon
* runtime key
* bounded state
* warm-up/history
* quality prerequisites
* missing-evidence behavior
* result state
* evidence components
* provenance
* claim ceiling
* revision semantics

Do not invent generic requirements such as:

```
universal five-tuple
universal domain
universal flow ID
universal probability
universal confidence
```

unless an authoritative contract requires them.

---

# 8. BOUNDED STATE

Any stateful analytic must declare:

* key
* state shape
* event-time window/history
* TTL
* warm-up
* expiry
* late-event handling
* restart behavior
* eviction behavior
* bounded-memory behavior

Never maintain unbounded global history.

State must be inspectable and testable.

Prefer immutable/inspectable state transitions where the existing architecture
supports them.

---

# 9. QUALITY

Quality is first-class.

Potential quality conditions include:

* capture loss
* processing drops
* queue overload
* malformed input
* unsupported observations
* ordering/lateness issues
* incomplete visibility
* state loss

Actual quality degradation must never be hidden.

Important distinction:

```
intentional observation projection
≠
accidental capture/processing loss
```

For example, an A→B visibility projection intentionally excluding reverse
traffic is not automatically DATA_QUALITY_DEGRADED.

But actual packet/capture loss may require:

```
DATA_QUALITY_DEGRADED
```

depending on the analytic prerequisite contract.

Never turn missing evidence into:

```
benign
zero
safe
no attack
```

unless the authoritative analytic explicitly supports that conclusion.

---

# 10. PROJECTION / VISIBILITY

The Replayer may support different observation contracts/projections.

Examples:

```
FULL
A→B
```

The backend must preserve what each projection actually exposes.

If reverse traffic is absent:

```
do not fabricate it.
```

If a TCP outcome requires reverse-direction evidence and that evidence is
not present:

```
the analytic may be unavailable / incompatible / non-assessable
```

according to its contract.

But do not manufacture DATA_QUALITY_DEGRADED merely because a deliberate
projection excludes information.

---

# 11. CURRENT MVP ANALYTIC

Primary MVP analytic:

```
Recon breadth evidence construction
```

Question:

```
How many distinct destinations did a source entity contact during the
declared event-time observation horizon?
```

This is an observation/evidence measurement.

It is NOT a claim that reconnaissance occurred.

Example:

```
A → B
A → B
A → C
A → D
```

produces:

```
source = A
distinct_destinations = 3
```

Repeated packets to the same destination count once.

The exact state/window/key semantics must follow the accepted analytic
contract.

---

# 12. RECON CLAIM CEILING

Allowed conceptual claim:

```
"Observed source-to-destination breadth within the declared event-time
 horizon."
```

Not allowed:

```
"Reconnaissance detected."

"Malicious reconnaissance."

"Attack detected."
```

Do not introduce thresholds, confidence, severity, or threat scores.

---

# 13. NON-ASSESSMENT

The system must distinguish inability to assess from benign evidence.

Relevant conceptual states include:

```
SUPPORTED
UNDER_REVIEW
ANALYTIC_UNAVAILABLE
ABSTAINED / OBSERVATION_INCOMPATIBLE
DATA_QUALITY_DEGRADED
INSUFFICIENT_HISTORY / WARMING_UP
```

Use the authoritative result contract for exact names.

If a required field is absent:

```
do NOT substitute zero.
```

---

# 14. EVIDENCE REVISION

Evidence is revisionable.

Conceptually:

```
revision 1
   ↓
revision 2
   ↓
revision 3
```

A later observation may:

```
strengthen
weaken
retract
degrade
remain unchanged
```

depending on the analytic contract.

Never overwrite historical evidence.

The current state may be materialized for fast access, but historical
revisions must remain inspectable.

---

# 15. PROVENANCE

Consequential evidence should preserve:

* observation contract
* event-time horizon
* evidence
* missing evidence
* quality
* analytic/config version
* provenance
* claim ceiling

Where available also preserve:

* source/capture identity
* input identity/hash
* projection identity/version
* parser/config version
* sequence/order information

Never invent provenance.

---

# 16. ARCHITECTURE DISCIPLINE

Current implementation preference:

```
Python
existing Network Replayer
bounded in-process processing
FastAPI when API is introduced
SQLite when persistence is introduced
```

Do not introduce:

```
Kafka
Flink
Redis
Kubernetes
Rust
distributed processing
```

unless an actual measured requirement justifies it.

Do not optimize architecture based on imagined production scale.

Measure first.

---

# 17. PERFORMANCE

Keep these separate:

1. Structural time-to-signal
2. Processing latency
3. End-to-end alert latency
4. Sustained throughput
5. State/memory cost

Do not call replay execution time "live alert latency."

Useful future measurements:

* packets/sec
* flows/sec
* Mbps
* p50/p95/p99 processing latency
* queue depth
* dropped items
* CPU
* RSS
* active state keys
* state memory
* overload recovery

Never claim production performance without measurements.

---

# 18. TESTBED

The project uses a controlled, truth-aligned testbed.

Keep separate:

```
GENERATOR TRUTH
VICTIM/SERVICE TRUTH
PASSIVE NETWORK TRUTH
CAPTURE-QUALITY TRUTH
```

Truth data must not accidentally become detector input.

Controlled traffic is useful for:

* mechanism validation
* parser validation
* state validation
* timing validation
* projection validation
* quality degradation
* hard negatives
* load testing

Controlled traffic alone does NOT establish broad real-world detection
generalization or production FPR.

---

# 19. DATA / ML RULE

Do not select a model first.

Use:

```
mechanism
  ↓
passive observable
  ↓
required truth
  ↓
sample/unit
  ↓
modality
  ↓
candidate data
  ↓
provenance
  ↓
leakage audit
  ↓
hard negatives
  ↓
split freeze
  ↓
transparent baseline
  ↓
error analysis
  ↓
justified ML
```

Major leakage risks:

* IP
* port
* capture
* tool
* topology
* scenario
* time
* family
* seed
* duplicates
* environment
* dataset source
* future information

Ask:

```
WHAT NEW INFORMATION WOULD ML ACTUALLY LEARN?
```

Complexity cannot recover information that passive observation does not
contain.

---

# 20. THREAT SCOPE

The broader solution has seven threat families.

The MVP is intentionally narrower.

Current primary implementation focus:

```
Recon breadth evidence
```

Other threat families must not be implemented merely to make the backend
look complete.

Some may remain:

```
strategy
observation-only
prerequisite-only
analytic-unavailable
future work
```

The backend must represent these states honestly.

---

# 21. CODING RULES FOR THE AGENT

Before modifying code:

1. Inspect the repository.
2. Inspect existing contracts.
3. Inspect existing tests.
4. Reuse existing infrastructure.
5. Identify the smallest change.
6. Implement only the requested task.
7. Run relevant tests.
8. Report actual results.

Do not claim tests passed unless they were actually run.

Do not refactor unrelated code.

Do not silently rename public APIs.

Do not create duplicate implementations.

---

# 22. STOP CONDITIONS

STOP and report BLOCKED if:

* authoritative contracts conflict;
* required semantics are undefined;
* implementation would require inventing scientific meaning;
* missing evidence would have to become benign;
* event-time semantics are unclear;
* projection semantics are unclear;
* an existing component would need semantic changes;
* a task requires selecting a threat threshold/model without authorization.

Report:

```
BLOCKED

REASON:
...

EVIDENCE:
...

DECISION REQUIRED:
...
```

Do not work around a scientific/contractual block by making assumptions.

---

# 23. CURRENT TASK BOUNDARY

The immediate backend sequence is:

```
STEP 1
Backend repository/setup

STEP 2
Network Replayer plugin/source integration

STEP 3
Bounded state + Recon breadth evidence

STEP 4
Episode + persistence

STEP 5
Minimal API / streaming surface

STEP 6
Performance instrumentation + end-to-end demo
```

Do not skip ahead unless explicitly instructed.

---

# 24. DEFINITION OF DONE

A backend component is not "done" because it runs.

It is done when:

* its contract is explicit;
* its inputs are known;
* its outputs are known;
* event-time semantics are preserved;
* missing evidence is explicit;
* quality is preserved;
* provenance is preserved;
* state is bounded;
* historical evidence is revisionable where required;
* tests cover failure cases;
* claims do not exceed available evidence.

The goal is not maximum feature count.

The goal is a small backend whose behavior we can defend in front of SIH
judges.
