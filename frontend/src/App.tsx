import { useCallback, useEffect, useState } from "react";
import { AppShell } from "./components/layout/AppShell";
import { ErrorBoundary } from "./components/common/ErrorBoundary";
import { EvidenceProvider, useEvidence } from "./state/EvidenceContext";
import type { PageKey } from "./state/types";
import { OverviewPage } from "./pages/OverviewPage";
import { AlertsPage } from "./pages/AlertsPage";
import { ResultsPage } from "./pages/ResultsPage";
import { ReplayPage } from "./pages/ReplayPage";
import { InvestigationsPage } from "./pages/InvestigationsPage";

const pageKeys: PageKey[] = [
  "overview",
  "alerts",
  "investigations",
  "results",
  "replay",
];
function routeFromHash(): PageKey {
  const value = location.hash.replace(/^#\/?/, "") as PageKey;
  return pageKeys.includes(value) ? value : "overview";
}
function ConsoleApp() {
  const [page, setPage] = useState<PageKey>(routeFromHash);
  const [sourceResultId, setSourceResultId] = useState<string | null>(null);
  const { selectSourceResult } = useEvidence();
  useEffect(() => {
    const update = () => setPage(routeFromHash());
    window.addEventListener("hashchange", update);
    return () => window.removeEventListener("hashchange", update);
  }, []);
  const navigate = useCallback((next: PageKey) => {
    setPage(next);
    if (location.hash !== `#/${next}`) location.hash = `/${next}`;
    window.scrollTo({
      top: 0,
      behavior: "instant",
    });
  }, []);
  async function openResult(id: string) {
    try {
      await selectSourceResult(id);
      setSourceResultId(id);
      navigate("results");
    } catch {
      /* Provider displays the request error. */
    }
  }
  return (
    <AppShell page={page} onNavigate={navigate}>
      {page === "overview" && (
        <OverviewPage navigate={navigate} />
      )}
      {page === "alerts" && (
        <AlertsPage
          initialAlert={null}
          clearInitial={() => undefined}
          openResult={(id) => void openResult(id)}
          navigate={navigate}
        />
      )}
      {page === "investigations" && <InvestigationsPage navigate={navigate} />}
      {page === "results" && <ResultsPage initialResultId={sourceResultId} />}
      {page === "replay" && <ReplayPage navigate={navigate} />}
    </AppShell>
  );
}
export default function App() {
  return (
    <ErrorBoundary>
      <EvidenceProvider>
        <ConsoleApp />
      </EvidenceProvider>
    </ErrorBoundary>
  );
}
