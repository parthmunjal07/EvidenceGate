import { describe, expect, it } from "vitest";
import {
  checkReleaseCompatibility,
  EXPECTED_API_CONTRACT_VERSION,
} from "./releaseCompatibility";

describe("release compatibility", () => {
  it("accepts a package when release IDs match even if source revisions differ", () => {
    expect(
      checkReleaseCompatibility(
        "REL-A",
        "REL-A",
        EXPECTED_API_CONTRACT_VERSION,
        false,
        "https://demo.test/",
      ),
    ).toEqual({ state: "compatible" });
  });
  it("attempts one cache-busted reload then reports a non-blocking warning", () => {
    expect(
      checkReleaseCompatibility(
        "REL-A",
        "REL-B",
        EXPECTED_API_CONTRACT_VERSION,
        false,
        "https://demo.test/lab?tab=traffic",
      ),
    ).toEqual({
      state: "reload",
      url: "https://demo.test/lab?tab=traffic&eg_release=REL-B",
    });
    expect(
      checkReleaseCompatibility(
        "REL-A",
        "REL-B",
        EXPECTED_API_CONTRACT_VERSION,
        true,
        "https://demo.test/lab",
      ),
    ).toEqual({ state: "warning" });
  });
  it("treats explicit development release IDs as compatible", () => {
    expect(
      checkReleaseCompatibility(
        "",
        "dev",
        EXPECTED_API_CONTRACT_VERSION,
        false,
        "https://demo.test/",
      ),
    ).toEqual({ state: "compatible" });
  });
  it("does not hard block Vite development mode against a packaged backend", () => {
    expect(
      checkReleaseCompatibility(
        "dev",
        "REL-A",
        EXPECTED_API_CONTRACT_VERSION,
        false,
        "http://127.0.0.1:5173/",
      ),
    ).toEqual({ state: "compatible" });
  });
  it("marks only Traffic Lab incompatible when the API contract differs", () => {
    expect(
      checkReleaseCompatibility(
        "REL-A",
        "REL-A",
        "2",
        false,
        "https://demo.test/",
      ),
    ).toEqual({ state: "incompatible" });
  });
});
