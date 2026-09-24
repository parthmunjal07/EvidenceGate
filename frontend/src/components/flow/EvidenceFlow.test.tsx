import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import type { ResultDto } from "../../api/types";
import { EvidenceFlow } from "./EvidenceFlow";

describe("EvidenceFlow", () => {
  it("labels result authority and eligible projection stages independently", () => {
    const result = {
      lane_id: "dga.m1",
      result_type: "REVIEW_FINDING",
    } as ResultDto;
    render(<EvidenceFlow result={result} replaying={false} />);
    expect(
      screen.getByText("dga.m1 · SIH alert projection"),
    ).toBeInTheDocument();
    expect(document.querySelector('[data-stage="results"]')).toHaveClass(
      "is-active",
    );
    expect(document.querySelector('[data-stage="projection"]')).toHaveClass(
      "is-presentation",
    );
  });
  it("does not show an alert branch for unrelated records", () => {
    render(<EvidenceFlow result={null} replaying />);
    expect(screen.getByText(/Replay running/)).toBeInTheDocument();
  });
});
