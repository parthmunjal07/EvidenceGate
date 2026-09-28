import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ResultsPage } from "./ResultsPage";

vi.mock("../state/EvidenceContext", () => ({
  useEvidence: () => ({
    state: { results: new Map(), orderedResults: [], streamState: "connected", nextCursor: null },
    loadOlder: vi.fn(),
    dispatch: vi.fn(),
  }),
}));

describe("ResultsPage", () => {
  it("shows every supported family and an empty state when no results are available", () => {
    render(<ResultsPage />);

    const family = screen.getByRole("combobox", { name: "Family" });
    expect(Array.from((family as HTMLSelectElement).options).map((option) => option.textContent)).toEqual([
      "All families", "DDoS", "C2 / Beaconing", "DGA", "DNS tunnelling", "Encrypted Sessions", "Reconnaissance", "Data Transfer",
    ]);
    expect(screen.getByText("No Results are available yet. Run a controlled replay to create demo activity.")).toBeInTheDocument();

    fireEvent.change(family, { target: { value: "DGA" } });
    expect(screen.getByText("No Results are available yet. Run a controlled replay to create demo activity.")).toBeInTheDocument();
  });
});
