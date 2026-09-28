# Scientific boundaries

EvidenceGate is designed to preserve uncertainty in passive, potentially one-way observations. These limits apply to every Result and every interface that presents one.

## Missing is not zero

Missing reverse traffic does not mean no response, no attack, zero activity, or benign behavior. A field can be absent because the sensor was one-way, sampling or packet loss removed it, capture began midstream, or the protocol encrypted it. Providers should describe the resulting observation as missing, degraded, or unavailable rather than silently supply a negative fact.

## Evidence is not a verdict

A Result records evidence from a mechanism and its observation contract. Evidence may support review. It does not by itself establish maliciousness, intent, identity, authorization, impact, or causality. Multiple results do not become a confirmed attack merely because they appear together.

## Score semantics

The DGA model score means resemblance to DGA-labelled lexical examples under the model's representation. It is not a malware probability, infection probability, or universal threat probability. An unavailable model is not a zero score or a negative result.

## Family-specific limits

- Periodic communication is not proof of C2.
- DNS name structure or transaction behavior is not proof of tunnelling.
- Encrypted-session metadata does not reveal payload meaning or malware.
- Reconnaissance breadth does not establish malicious intent or lack of authorization.
- Observed demand/state does not establish victim exhaustion or impact.
- Transfer magnitude does not establish unusualness, unauthorized access, sensitivity, or theft.
- Apparent source diversity does not establish source spoofing.
- A factual relation between Results does not establish a common attacker, campaign, or attack progression.

## One-way degradation

With only one direction, a sensor can still record arrivals, visible TCP flags, bytes and packets observed at that point, and whatever application metadata is present. It may not see replies, connection completion, server outcomes, request/response semantics, or the counterfactual victim impact. Loss, sampling, truncation, and midstream start further weaken state reconstruction. Sidecar-supplied role or direction metadata is an input assertion, not an independently inferred fact.

## Bounded research and generalization

Every experiment is limited by its dataset, sample unit, labels, profile, split, capture visibility, and hard negatives. Known-family separation does not guarantee unseen-family performance. A synthetic mechanics fixture is not a population estimate. A diagnostic false-positive result is not a deployed operating point. Detailed decisions and limitations are recorded in [EXPERIMENTS.md](EXPERIMENTS.md).

## Controlled MVP is not production sizing

The prototype supports recorded replay through a single-process application and bounded provider state. The checked-in performance results are controlled development measurements for their recorded workload and environment. They do not establish a production SLA, enterprise scale, live real-time detection, or a general zero-drop rate.

## Semantic ladder for data transfer

```text
transfer observed ≠ unusual transfer ≠ unauthorized transfer
                 ≠ sensitive data ≠ theft / exfiltration
```

The current mechanism reports directional magnitude evidence. The research did not identify an admissible corpus with the required authorization and sensitivity truth for semantic exfiltration claims.
