export const alertReviewDisclaimer =
  "Alert means analyst review, not confirmation of malicious activity.";

export const resultsSourceNote =
  "Each row is one immutable mechanism Result behind family evidence and analyst review. Open it to review observed evidence, evidence limits and provenance.";

export const nonDgaProbabilityNote =
  "Numeric attack probability is not defined by this analytic.";

export function dgaScoreNote(score: number | null) {
  return `DGA-labelled lexical resemblance score: ${score == null ? "not present" : score.toFixed(6)}. Not calibrated attack probability. Observed evidence; no attack probability is implied.`;
}

export const dgaScoreInterpretation =
  "Lexical model score is DGA-labelled resemblance evidence. Observed evidence; no attack probability is implied. The score is not calibrated.";
