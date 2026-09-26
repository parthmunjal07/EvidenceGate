import type {
  AlertsResponse,
  FamilyEvidenceResponse,
  HealthResponse,
  ReplayRequest,
  ReplayStatusResponse,
  ResultDto,
  ResultsResponse,
  RuntimeStatusResponse,
  RuntimeTraceResponse,
  InvestigationsResponse,
} from "./types";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    readonly detail?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      headers: { Accept: "application/json", ...init.headers },
    });
  } catch (error) {
    throw new ApiError(
      0,
      error instanceof Error ? error.message : "Backend unavailable",
    );
  }
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail =
      typeof body === "object" && body !== null && "detail" in body
        ? body.detail
        : undefined;
    throw new ApiError(
      response.status,
      typeof detail === "string"
        ? detail
        : `Request failed (${response.status})`,
      detail,
    );
  }
  return body as T;
}

export const api = {
  health: (signal?: AbortSignal) =>
    request<HealthResponse>("/health", { signal: signal ?? null }),
  runtime: (signal?: AbortSignal) =>
    request<RuntimeStatusResponse>("/runtime", { signal: signal ?? null }),
  alerts: (signal?: AbortSignal) =>
    request<AlertsResponse>("/alerts", { signal: signal ?? null }),
  familyEvidence: (signal?: AbortSignal) =>
    request<FamilyEvidenceResponse>("/family-evidence", { signal: signal ?? null }),
  investigations: (signal?: AbortSignal) =>
    request<InvestigationsResponse>("/investigations", { signal: signal ?? null }),
  results: (
    query: { cursor?: string; limit?: number } = {},
    signal?: AbortSignal,
  ) => {
    const params = new URLSearchParams();
    if (query.cursor) params.set("cursor", query.cursor);
    if (query.limit) params.set("limit", String(query.limit));
    return request<ResultsResponse>(
      `/results${params.size ? `?${params}` : ""}`,
      { signal: signal ?? null },
    );
  },
  result: (id: string, signal?: AbortSignal) =>
    request<ResultDto>(`/results/${encodeURIComponent(id)}`, {
      signal: signal ?? null,
    }),
  replay: (value: ReplayRequest, signal?: AbortSignal) =>
    request<ReplayStatusResponse>("/replay", {
      method: "POST",
      signal: signal ?? null,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(value),
    }),
  replayStatus: (signal?: AbortSignal) =>
    request<ReplayStatusResponse>("/replay/status", { signal: signal ?? null }),
  runtimeTrace: (after = 0, signal?: AbortSignal) =>
    request<RuntimeTraceResponse>(`/runtime/trace?after=${after}&limit=100`, { signal: signal ?? null }),
};
