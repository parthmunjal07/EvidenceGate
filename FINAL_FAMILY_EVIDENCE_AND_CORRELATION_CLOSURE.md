# Family Evidence and Correlation Closure

## Architecture closure

Implementation is layered after persisted immutable Results:

`source → canonical observation → visibility / quality → zero-to-many routing → independent Results → family evidence → factual relation index → investigation links → analyst workbench`

Family evidence and investigation links are pure read-only projections. SQLite `/results` remains authoritative; no second scientific store or Result mutation was introduced.

## Composer contract

`evidencegate/family/composer.py` centralizes the official family mapping and composes same-family connected components using direct or transitive overlap of exact `source_observation_ids`. Results without source lineage remain individual views. No time threshold is used.

Each immutable `FamilyEvidenceView` carries a stable view ID, family, event-time bounds, entity references, source Result and observation IDs, independent child findings, governed limitations, missing evidence, and visibility / quality summaries. It contains no family score, attack probability, fused severity, or stronger composite claim. Child claim ceilings and source Results are unchanged.

### Six official family mappings

| Official family | Mechanism lanes |
| --- | --- |
| DDoS | `ddos.syn_state`, `ddos.udp_demand`, `ddos.reflection_victim`, `ddos.source_diversity`, `ddos.icmp_demand`, `ddos.fragment_demand`, `ddos.connection_churn` |
| C2 / Beaconing | `c2.r1` |
| DGA + DNS | `dga.m1`, `dns_tunnelling.t1` |
| Encrypted Sessions | `encrypted_session.enc_a` |
| Reconnaissance | `recon.h`, `recon.v`, `recon.2d`, `recon.tcp` |
| Data Transfer | `unusual_transfer.m1` |

DGA and DNS results remain independent findings inside the shared DGA + DNS view.

## Factual relation index

The index is an inverted map from exact source observation ID to family views. Its only active relation is `SHARED_SOURCE_OBSERVATION` between different official families. Each `InvestigationLink` includes both family-view IDs, shared observation IDs, source Result IDs, and claim guards: `FOR_JOINT_INVESTIGATION_ONLY`, `NO_CAUSALITY`, `NO_COMMON_ATTACKER`, `NO_ATTACK_CHAIN_CONFIRMATION`, and `NO_MALICIOUSNESS_PROBABILITY`.

Same-entity overlap is not active. DNS resolved-peer to later TLS, Recon to later DDoS, and C2 to later transfer remain deferred because their temporal windows are not frozen. ML relevance ranking, GNN correlation, attacker probability, causality scoring, and attack-chain reconstruction remain deferred / not promoted.

The implementation forms candidates inside each factual observation bucket; it does not scan all family-view pairs globally. Engineering characterization: 2,400 synthetic views, 2,400 source-observation index entries, 1,200 factual candidates; composition took 0.0537 s, indexing 0.0057 s, total 0.0594 s on this workstation.

## API and analyst experience

- `GET /family-evidence` derives the family views from recent SQLite Results; it accepts a bounded `limit` and optional repeated `source_result_id` filter.
- `GET /investigations` returns the derived views and deterministic factual links.
- `/alerts` and `SIH_ALERT_POLICY_V1` remain available and unchanged as one-Result standardized projections.
- Analyst Queue now lists family evidence items and opens a human-first family card with independent findings, limitations, missing evidence, and related evidence. The normal card contains no mechanism IDs, raw claim-ceiling strings, raw JSON, or technical-details accordion.
- Evidence remains mechanism-level with friendly finding text; the user-facing inspector no longer exposes implementation IDs or raw technical details. Exact audit identifiers remain available through backend APIs.
- Traffic Lab shows family composition and shared-observation investigation stages after replay.
- The permanent topbar capability issue badge is removed. DGA unavailability appears with the relevant Traffic Lab scenario. Runtime status displays Online, Offline, or Replaying.

## DGA model resolution

Resolution precedence is explicit `model_path`, `EVIDENCEGATE_DGA_MODEL`, existing repository-local `artifacts/dga/local/DGA_M1_R1_SERIALIZED_MODEL.joblib`, then unavailable. Resolution changes only the path; the verifier remains fail-closed for the exact filename, 5,720,970 bytes, SHA-256 `39da209d2cfd869dd284e10b8a07adc04826c95146712cc6854a69b9873890df`, model identity, representation, dependency versions, and class semantics.

Readiness during QA: `VERIFIED_READY` (no failure reason). The verified local artifact was auto-discovered.

## QA results

### Live replay QA

- `mixed_ddos_recon`: 8 Results persisted; DDoS and Reconnaissance family views appeared with one shared-observation investigation link.
- `dga_lexical`: 2 independent Results appeared in one DGA + DNS family view.
- `c2_recurrence`: 6 Results persisted; C2 family lineage retained multiple source observations and linked to Data Transfer through three exact shared-observation candidates.
- `ddos_one_way`: 4 Results persisted; missing reverse evidence survived family composition.

### Automated checks

- Backend: `pytest -q` — 450 tests passed.
- Frontend: `npm run typecheck` — pass; `npm run lint` — pass; `npm test -- --run` — 46 tests passed; `npm run build` — pass; `npm audit` — 0 vulnerabilities.
- `python -m compileall -q evidencegate scripts` — pass.
- `git diff --check` — pass.
- A clean `npm ci` succeeded in an isolated verification directory. Running it in the active frontend directory first hit `EPERM` because the already-running Vite process held the Windows Rolldown native binding open; dependencies were restored with `npm install`. The environment Node version is 22.20.0 while the package declares `>=24.21.0` (npm emitted the engine warning).

## Scientific freeze

Mechanism algorithms, thresholds, readiness, state windows, routing, models, Result semantics, claim ceilings, confidence semantics, alert policy science, visibility semantics, and quality semantics were not changed. Family composition uses source lineage only and performs no scientific fusion.
