import { describe, expect, it } from "vitest";
import { compareTimeAsc, compareTimeDesc, formatEvidenceDateTime, formatEvidenceDateTimeCompact, formatEvidenceRange, formatEvidenceTableClock, formatEvidenceTableDate, formatEvidenceTime, formatTimeZoneLabel, latestObservedTime, normalizeTimeZoneLabel } from "./formatting";

describe("evidence time presentation", () => {
  const earlier = "2026-01-01T00:30:00Z";
  const later = "2026-01-01T06:15:00+05:30";

  it("sorts mixed ISO offsets by their represented instant", () => {
    expect(Date.parse(later)).toBeGreaterThan(Date.parse(earlier));
    expect([later, earlier].sort(compareTimeAsc)).toEqual([earlier, later]);
    expect([earlier, later].sort(compareTimeDesc)).toEqual([later, earlier]);
    expect(latestObservedTime([earlier, later])).toBe(later);
  });

  it("renders the same instant in UTC and the browser's local zone", () => {
    expect(formatEvidenceDateTime(later, "utc")).toBe("01 Jan 2026 · 00:45:00 UTC");
    expect(formatEvidenceTime(later, "utc")).toBe("00:45:00 UTC");
    expect(formatEvidenceDateTime(later, "local")).toContain(formatTimeZoneLabel("local"));
    expect(formatEvidenceDateTime(later, "local")).not.toBe(formatEvidenceDateTime(earlier, "local"));
  });

  it("formats an observed range with one date when both times share a local date", () => {
    expect(formatEvidenceRange("2026-01-01T00:30:00Z", "2026-01-01T00:45:00Z", "utc"))
      .toBe("01 Jan 2026 · 00:30:00–00:45:00 UTC");
  });

  it("uses IST only for the recognized India IANA zones and keeps table times compact", () => {
    expect(normalizeTimeZoneLabel("Asia/Kolkata", "GMT+5:30")).toBe("IST");
    expect(normalizeTimeZoneLabel("Asia/Calcutta", "GMT+5:30")).toBe("IST");
    expect(normalizeTimeZoneLabel("Asia/Kathmandu", "GMT+5:45")).toBe("GMT+5:45");
    expect(formatEvidenceDateTimeCompact("2026-01-01T00:00:00Z", "utc")).toBe("01 Jan 2026 · 00:00:00");
    expect(formatEvidenceTableDate("2026-01-01T00:00:00Z", "utc")).toBe("01 Jan 2026");
    expect(formatEvidenceTableClock("2026-01-01T00:00:00Z", "utc")).toBe("00:00:00");
  });
});
