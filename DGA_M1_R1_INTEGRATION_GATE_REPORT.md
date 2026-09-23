# DGA M1-R1 integration gate report — M14A reconciliation

## Preserved M14 history and correction

M14 verified the Drive-owned R1 artifact (`5,720,970` bytes, SHA-256 `39da209d2cfd869dd284e10b8a07adc04826c95146712cc6854a69b9873890df`) and then blocked it because `classifier.classes_` was `['benign', 'dga']`, rather than historical M1's `[0, 1]`. That was a false comparison across label encodings, not a byte, feature, or model-family finding.

M14A read the authoritative R1 config (Drive `1LvmseXW42TagQD0akPAR47tokt8rzV5e`) and training/evaluation scripts. The config declares `label_column: label` and `positive_class: dga`; training passes that column directly to `fit`, and evaluation selects the `dga` probability column. The original prepared parity utility's `int(pred)` is an **R1 execution-kit parity script defect**, not artifact corruption.

The strict corrected contract is exactly two classes `{benign, dga}`, exactly one configured positive `dga`, and exactly one admitted negative `benign`. It rejects `clean/dga`, `benign/malware`, numeric labels, absent/duplicated positives, and multiclass models. Scores are selected by `classes.index('dga')`; no hard-coded `[0][1]` remains.

## Post-hoc immutable artifact validation

This is `POST_HOC_R1_ARTIFACT_VALIDATION`, not a reconstruction of original `09_run_outputs`. Train, validation, and test bytes were downloaded from their frozen Drive IDs and hash-checked before reading. Labels are object values: train `dga=160082`, `benign=159917`; validation `dga=19960`, `benign=20040`; test retains `dga=69957`, `benign=20043`, `ood=200000` across its declared roles.

| Dataset | AUROC | Historical reference | Delta |
|---|---:|---:|---:|
| Validation (40,000) | 0.9934089761 | 0.9934168537 | -0.0000078775 |
| Known test (40,000) | 0.9936135380 | 0.9936188955 | -0.0000053575 |

Accuracy, precision, recall, F1, PR-AUC, deterministic representative scores, and exact input identities are in `benchmark_results/dga_m1_r1_posthoc_validation.json`. The historical model was serialized under sklearn 1.8.0, unlike R1's required 1.6.1; its warning and incompatibility in the R1 environment were not suppressed. Historical fixture scoring instead ran in an isolated 1.8.0 environment. Diagnostic vocabulary comparison finds 150,000 terms in each model, 145,705 shared terms with equal shared IDF, small aligned coefficient/intercept differences, and no claim of binary equivalence.

Original R1 `09_run_outputs` remains empty. Gate-A candidate classification is **SCIENTIFICALLY_CONSISTENT_REBUILD WITH ORIGINAL-RUN TRACEABILITY LIMITATION**, not strong reproduction.

## Gate B measured representation audit

The audit applies the current offline `tldextract 5.1.3` bundled snapshot with no suffix-list URLs and private domains enabled to every frozen train, validation, and known-test input (399,999 rows). Exact eTLD+1 parity is `399,805 / 399,999` (`99.9514999%`). There are zero available changed-by-PSL strings and `194` unavailable strings (`0.0485001%`), all unknown/internal under the chosen private-suffix policy; Unicode count is zero. Enabling private suffixes changes exactly those 194 rows relative to public-only extraction. No last-two-label fallback, Unicode repair, or unknown-suffix scoring is used.

This supports the registrable-domain live policy while retaining explicit unavailable cases. Gate B is **PASS_WITH_EXPLICIT_UNAVAILABLE_CASES**, pending the final human promotion decision. Full categories/examples are in `benchmark_results/dga_m1_r1_representation_audit.json`.

## Non-default product integration and measurement

`dga.m1` now emits a `REVIEW_FINDING` for admitted input, carrying `dga_labelled_lexical_resemblance_score`, `positive_class: dga`, resolved class index, exact classifier classes, claim ceiling, configuration hash, and typed model refs. The score means **DGA-labelled lexical resemblance**, never attack, infection, malware, C2, tunnel, or exfiltration probability. Default `dga` remains the shell.

The controlled model microbenchmark recorded verified load `2.426s`, representation p50/p95/p99 `0.0023/0.0176/0.0262ms`, inference p50/p95/p99 `0.426/0.821/2.548ms`, `2,096` names/s, and `166,985,728` RSS bytes. It is not a whole-stack benchmark.

Frozen no-tuning challenge measurements cover unknown family, OOD, CrUX broad, and CrUX machine-looking; their quantiles and historical-0.5 comparison rates are in `benchmark_results/dga_m1_r1_challenge_measurement.json`. A 0.5 comparison rate is not a production threshold.

No retraining, threshold tuning, model modification, ThreatAlert, severity, or default activation occurred. Human Gate required: **yes** — Control Room must decide final DGA promotion.
