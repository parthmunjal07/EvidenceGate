# DGA M1-R1 Default Activation Report

## Decision and artifact

Human-Gate decision `C3-DEC-DGA-M1-R1-PROMOTION-V1` is accepted for controlled
MVP promotion. The admitted Drive-owned binary is
`DGA_M1_R1_SERIALIZED_MODEL.joblib` (5,720,970 bytes), with private Drive
locator omitted and SHA-256
`39da209d2cfd869dd284e10b8a07adc04826c95146712cc6854a69b9873890df`.
The binary remains gitignored; the repository owns only its identity manifest.

Gate A remains **SCIENTIFICALLY_CONSISTENT_REBUILD WITH ORIGINAL-RUN
TRACEABILITY LIMITATION**. It is not a strong or bit-identical historical
reproduction. The separate recovered R1 execution attempt references a different
serialization hash and later failed in evaluation; it does not replace M14A
admission evidence. Gate B remains `PASS_WITH_EXPLICIT_UNAVAILABLE_CASES`:
399,805/399,999 exact historical representations, with 194 explicit unavailable
cases.

## Runtime activation

The default registry replaces `dga`/`DgaShellPlugin` with the stateless
`dga.m1`/`DgaM1Plugin`; the exact default count remains 16. There is no DGA
reorder policy or state allocation. A clear-DNS observation routes zero-to-many
to both `dga.m1` and independent `dns_tunnelling.t1`.

The service verifies and loads once per application lifecycle. Typed readiness
is one of `VERIFIED_READY`, `ARTIFACT_MISSING`, `ARTIFACT_HASH_MISMATCH`,
`DEPENDENCY_MISMATCH`, or `MODEL_CONTRACT_MISMATCH`. Missing or divergent
artifacts keep the lane present but emit `ANALYTIC_UNAVAILABLE` with an explicit
reason and full model/config provenance. There is no fallback model.

The result is always a `REVIEW_FINDING` for admitted input and carries a
**DGA-labelled lexical resemblance score**, representation evidence, semantic
positive class/index, classifier classes, source-shift warning, claim ceiling,
model refs, and promotion decision. No threshold, severity, ThreatAlert, or
attack verdict is activated.

## Product and evidence path

The allowlisted `dga_lexical` scenario follows the normal canonical DNS path,
performs real inference, persists separate DGA and DNS-T1 results to SQLite,
publishes result notifications, and is visible through REST/SSE/dashboard.
`GET /runtime` reports exact-artifact readiness and the DGA family as either
`ACTIVE M1 LEXICAL MODEL EVIDENCE` or `ACTIVE LANE — MODEL UNAVAILABLE`.

The frozen regression input `ajdkskqweoiuzx.com` scores
`0.9851716132182514` with absolute tolerance `1e-12` on the admitted artifact.
This number has no maliciousness meaning.

## Benchmark linkage

The final evidence is in `benchmark_results/final_mvp_model_inclusive_benchmark.json`
and `FINAL_MVP_MODEL_INCLUSIVE_BENCHMARK_REPORT.md`. The typed mixed run exercises
all seven implemented families including genuine DGA inference. The raw-PCAP run
truthfully records DGA as not exercised because DNS extraction is deferred.

## Verification

Targeted activation, artifact, routing, persistence, REST, SSE, dashboard, demo,
and benchmark tests pass (82 passed). The full suite passes (422 passed, 0
failed), `compileall` and `git diff --check` pass, and the joblib remains ignored
and untracked.
