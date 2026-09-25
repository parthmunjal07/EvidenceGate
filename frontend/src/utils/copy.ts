export const alertReviewDisclaimer =
  "Alert means analyst review, not confirmation of malicious activity.";

export const resultsSourceNote =
  "Evidence results are the source records behind analyst alerts.";

export const nonDgaProbabilityNote =
  "Numeric attack probability is not defined by this analytic.";

export function dgaScoreNote(score: number | null) {
  return `DGA-labelled lexical resemblance score: ${score == null ? "not present" : score.toFixed(6)}. Not calibrated attack probability.`;
}
