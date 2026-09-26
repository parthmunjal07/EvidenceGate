import type { ResultDto, SihAlertProjection } from "../api/types";
import {
  alertSearchText,
  formatQuality,
  summarizeEvidence,
} from "./formatting";

export type AlertFilters = {
  search: string;
  threatClass: string;
  basis: string;
  quality: string;
  visibility: string;
};
export type ResultFilters = {
  search: string;
  family: string;
  resultType: string;
};
export function filterAlerts(
  alerts: SihAlertProjection[],
  filters: AlertFilters,
) {
  const term = filters.search.trim().toLowerCase();
  return alerts.filter(
    (alert) =>
      (!term || alertSearchText(alert).includes(term)) &&
      (!filters.threatClass || alert.threat_class === filters.threatClass) &&
      (!filters.basis || alert.confidence_basis === filters.basis) &&
      (!filters.quality || formatQuality(alert.quality) === filters.quality) &&
      (!filters.visibility ||
        alert.visibility[filters.visibility as keyof typeof alert.visibility]
          .length > 0),
  );
}
export function filterResults(results: ResultDto[], filters: ResultFilters) {
  const term = filters.search.trim().toLowerCase();
  return results.filter(
    (result) =>
      (!term ||
        [
          result.entity_reference,
          result.family,
          summarizeEvidence(result.evidence),
        ]
          .join(" ")
          .toLowerCase()
          .includes(term)) &&
      (!filters.family || result.family === filters.family) &&
      (!filters.resultType || result.result_type === filters.resultType),
  );
}
