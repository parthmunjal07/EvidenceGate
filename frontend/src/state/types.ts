import type {
  AlertsResponse,
  ReplayStatusResponse,
  ResultDto,
  RuntimeStatusResponse,
} from "../api/types";

export type PageKey = "overview" | "alerts" | "results" | "system" | "replay";
export type EvidenceState = {
  runtime: RuntimeStatusResponse | null;
  results: Map<string, ResultDto>;
  orderedResults: string[];
  alerts: AlertsResponse["alerts"];
  statusItems: AlertsResponse["status_items"];
  replay: ReplayStatusResponse | null;
  nextCursor: string | null;
  syncCursor: string | null;
  pageError: string | null;
  streamState: "connecting" | "connected" | "reconnecting";
  latestResult: ResultDto | null;
  replayEvents: ResultDto[];
};
export type EvidenceAction =
  | { type: "runtime"; value: RuntimeStatusResponse }
  | {
      type: "results";
      value: ResultDto[];
      cursor?: string | null;
      syncCursor?: string | null;
      animate?: boolean;
    }
  | { type: "alerts"; value: AlertsResponse }
  | { type: "replay"; value: ReplayStatusResponse }
  | { type: "error"; value: string | null }
  | { type: "stream"; value: EvidenceState["streamState"] };
