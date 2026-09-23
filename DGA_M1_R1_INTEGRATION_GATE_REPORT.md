# DGA M1-R1 integration gate report

## Artifact intake and Gate A

The local, Drive-owned artifact was retrieved from Drive ID `16YbGrjsC_aCluWGa8-bC0mN5DVPO_T-Y` and was checked before deserialization. Its filename is `DGA_M1_R1_SERIALIZED_MODEL.joblib`, its byte count is `5,720,970`, and its SHA-256 is `39da209d2cfd869dd284e10b8a07adc04826c95146712cc6854a69b9873890df`: both match the supplied identity.

Static pickle inspection stopped at the joblib array boundary (as expected for a joblib stream); only after identity acceptance was the object loaded. It is a dictionary containing `model_id`, `representation_version`, `normalization`, `vectorizer`, `classifier`, `config`, and `environment`.

| Contract | Observed | Status |
|---|---|---|
| model ID | `DGA-A1-M1-R1` | pass |
| representation | `DGA_M1_REPRESENTATION_v1` | pass |
| normalization | `str(value).strip().lower().rstrip('.')` | pass |
| vectorizer | char TF-IDF, 2–5 grams, min_df 2, max_features 150000, sublinear float32, IDF/smooth/l2/lowercase | pass |
| classifier | LogisticRegression, C 2.0, liblinear, balanced, max_iter 200, random_state 26145 | pass |
| class order | `['benign', 'dga']` | **fail**: frozen contract requires `[0, 1]` |
| artifact environment | sklearn 1.6.1, joblib 1.6.0; numpy 2.1.3, scipy 1.16.3, Python 3.13.15 | recorded |

The local integration environment uses the exact required sklearn `1.6.1` and joblib `1.6.0`. The verifier rejects the artifact at its class-order contract after hash validation and before any inference. There is no fallback model or label coercion.

The authorized `M1_R1_EXECUTION/09_run_outputs` folder (Drive ID `1EeQvOSCYMkAv36vOZkv6DXYrWET2qXSF`) is empty. Required R1 records such as the run manifest, leakage report, parity results, and metrics were therefore not found. This is a traceability gap. Historical references and the recovered source map support only comparison; they do not prove this R1 run.

Gate-A candidate classification: **REPRODUCTION_DIVERGENCE**. Evidence: the artifact hash is accepted and most embedded model configuration agrees, but the required class contract diverges and R1 run outputs are absent. This is not a promotion decision.

## Gate B and live integration

`DgaM1RepresentationAdapter` is separate from DNS-T1 and maps factual canonical DNS input through `tldextract==5.1.3` with its bundled PSL snapshot, empty suffix-list URLs, and private suffixes enabled. It has no network fetch path. It maps a valid public-suffix name to PSL-provided registrable domain, then applies the frozen M1 normalization. It does not use last-two-label logic.

| Case | Outcome |
|---|---|
| `Example.COM.` | `example.com` model input |
| `a.b.example.co.uk` | `example.co.uk` model input |
| `localhost`, unknown suffix | `ANALYTIC_UNAVAILABLE` |
| Unicode | `ANALYTIC_UNAVAILABLE`; exact Unicode policy is not authorized |
| malformed/root/empty/whitespace | left to factual DNS-T1 rejection, then unavailable in M1 |
| `xn--` label under an unknown suffix | unavailable, no fallback |

Gate B: **PASS_WITH_EXPLICIT_UNAVAILABLE_CASES** for the representation layer. IDNA policy is ASCII / pre-existing `xn--` text only; Unicode and invalid IDNA are unavailable. Private suffix behavior is supplied by the pinned local PSL snapshot. Unknown and internal suffixes are unavailable.

The non-default, stateless `dga.m1` plugin (`DGA-A1-M1`) is implemented. It carries deterministic representation configuration hash `394a7638455e2bf1d5b2fc1d87294203549e78818645cd8183a7ceabf482f5cd` and typed model refs for the model ID, SHA-256, and Drive ID. Runtime finalization now accepts plugin-owned model refs, preserving them through normal SQLite/API/SSE/dashboard pathways. With this artifact it emits `ANALYTIC_UNAVAILABLE`, not a review score.

The claim ceiling is exactly `DGA_LABELLED_LEXICAL_REVIEW_EVIDENCE_ONLY;NO_MALWARE_CONFIRMATION;NO_INFECTION_INFERENCE;NO_C2_INFERENCE;NO_DNS_TUNNEL_INFERENCE;NO_EXFILTRATION_INFERENCE;NO_DOMAIN_OWNERSHIP_OR_INTENT`. No alert projection, severity, confidence, threshold, or retraining was added. The default `dga` lane remains the shell; `dga.m1` is not registered by default.

## Tests and benchmark

`tests/test_dga_m1_r1.py` covers artifact identity, missing/wrong paths, the detected class-contract divergence, explicit Gate-B mapping, absence of a score on unavailability, config hash, claim ceiling, and model refs. The DGA card text is model-specific and calls any future numeric value a model score.

`benchmark_results/dga_m1_r1_inference_benchmark.json` intentionally records no inference timings. Measuring or emitting scores from an artifact rejected by its contract would not be a valid M1 benchmark.

## Human gate

Human Gate required: **yes**. Do not activate `dga.m1` or alter the default DGA shell. Control Room must resolve the class-order divergence and missing R1 run-output traceability before a promotion decision.
