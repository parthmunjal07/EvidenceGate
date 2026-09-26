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
import { contextFromHash, type NavigationContext } from "./state/navigation";

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
  const [navigationContext, setNavigationContext] = useState<NavigationContext>(contextFromHash);
  const { selectSourceResult } = useEvidence();
  useEffect(() => {
    const update = () => { setPage(routeFromHash()); setNavigationContext(contextFromHash()); };
    window.addEventListener("hashchange", update);
    return () => window.removeEventListener("hashchange", update);
  }, []);
  const navigate = useCallback((next: PageKey, context: NavigationContext = {}) => {
    setPage(next);
    setNavigationContext(context);
    const params = new URLSearchParams();
    if (context.resultId) params.set("result_id", context.resultId);
    for (const id of context.sourceResultIds ?? []) params.append("source_result_id", id);
    if (context.familyViewId) params.set("family_view_id", context.familyViewId);
    if (context.linkId) params.set("link_id", context.linkId);
    if (context.family) params.set("family", context.family);
    const hash = `#/${next}${params.size ? `?${params.toString()}` : ""}`;
    if (location.hash !== hash) location.hash = hash;
    window.scrollTo({
      top: 0,
      behavior: "instant",
    });
  }, []);
  async function openResult(id: string) {
    try {
      await selectSourceResult(id);
      navigate("results", { resultId: id });
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
          key={navigationContext.familyViewId ?? "default-family"}
          initialAlert={null}
          clearInitial={() => undefined}
          openResult={(id) => void openResult(id)}
          navigate={navigate}
          {...(navigationContext.familyViewId ? { initialFamilyViewId: navigationContext.familyViewId } : {})}
        />
      )}
      {page === "investigations" && <InvestigationsPage key={navigationContext.linkId ?? navigationContext.family ?? "default-link"} navigate={navigate} {...(navigationContext.linkId ? { initialLinkId: navigationContext.linkId } : {})} {...(navigationContext.family ? { initialFamily: navigationContext.family } : {})} />}
      {page === "results" && <ResultsPage key={`${navigationContext.resultId ?? ""}:${(navigationContext.sourceResultIds ?? []).join("\u0000")}`} {...(navigationContext.resultId ? { initialResultId: navigationContext.resultId } : {})} sourceResultIds={navigationContext.sourceResultIds ?? []} />}
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
