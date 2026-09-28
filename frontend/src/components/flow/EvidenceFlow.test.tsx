import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import type { ResultDto } from "../../api/types";
import { EvidenceFlow } from "./EvidenceFlow";

describe("EvidenceFlow", () => {
  it("shows the active result and analyst review branch", () => {
    const result = {
      lane_id: "dga.m1",
      family: "DGA",
      mechanism_id: "DGA-A1-M1",
      result_type: "REVIEW_FINDING",
    } as ResultDto;
    render(<EvidenceFlow result={result} replaying={false} />);
    expect(
      screen.getByText("Latest persisted result: DGA · DGA-A1-M1"),
    ).toBeInTheDocument();
    expect(document.querySelector('[data-stage="results"]')).toHaveClass(
      "is-active",
    );
    expect(screen.getByText("Analyst review")).toHaveClass("is-active");
  });
  it("does not show an alert branch for unrelated records", () => {
    render(<EvidenceFlow result={null} replaying />);
    expect(screen.getByText("Replay running")).toBeInTheDocument();
  });
});
