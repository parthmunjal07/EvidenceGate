import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "./client";

afterEach(() => vi.unstubAllGlobals());

describe("allResults pagination", () => {
  it("follows next_cursor even when a page is shorter than the requested limit", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({
        results: [{ result_id: "first" }],
        next_cursor: "page-two",
        sync_cursor: "sync-one",
      }), { status: 200, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        results: [{ result_id: "second" }],
        next_cursor: null,
        sync_cursor: "sync-two",
      }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);

    const results = await api.allResults();

    expect(results.map((result) => result.result_id)).toEqual(["first", "second"]);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(String(fetchMock.mock.calls[1]?.[0])).toContain("cursor=page-two");
  });
});
