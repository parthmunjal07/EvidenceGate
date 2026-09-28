import { useCallback, useEffect, useState } from "react";
import { AppShell } from "./components/layout/AppShell";
import { ErrorBoundary } from "./components/common/ErrorBoundary";
import { EvidenceProvider } from "./state/EvidenceContext";
import type { PageKey } from "./state/types";
import { OverviewPage } from "./pages/OverviewPage";
import { AlertsPage } from "./pages/AlertsPage";
import { ResultsPage } from "./pages/ResultsPage";
import { ReplayPage } from "./pages/ReplayPage";
import { InvestigationsPage } from "./pages/InvestigationsPage";
import { contextFromHash, type NavigationContext } from "./state/navigation";
import { TimeZoneProvider } from "./state/TimeZoneContext";

const pageKeys: PageKey[] = [
  "overview",
  "alerts",
  "investigations",
  "results",
  "replay",
];
function routeFromHash(): PageKey {
  const value = location.hash.replace(/^#\/?/, "").split("?", 1)[0] as PageKey;
  return pageKeys.includes(value) ? value : "overview";
}
function ConsoleApp() {
  const [page, setPage] = useState<PageKey>(routeFromHash);
  const [navigationContext, setNavigationContext] =
    useState<NavigationContext>(contextFromHash);
  useEffect(() => {
    const update = () => {
      setPage(routeFromHash());
      setNavigationContext(contextFromHash());
    };
    window.addEventListener("hashchange", update);
    return () => window.removeEventListener("hashchange", update);
  }, []);
  const navigate = useCallback(
    (next: PageKey, context: NavigationContext = {}) => {
      setPage(next);
      setNavigationContext(context);
      const params = new URLSearchParams();
      if (context.resultId) params.set("result_id", context.resultId);
      if (context.returnResultId)
        params.set("return_result_id", context.returnResultId);
      for (const id of context.sourceResultIds ?? [])
        params.append("source_result_id", id);
      if (context.familyViewId)
        params.set("family_view_id", context.familyViewId);
      if (context.linkId) params.set("link_id", context.linkId);
      if (context.family) params.set("family", context.family);
      const hash = `#/${next}${params.size ? `?${params.toString()}` : ""}`;
      if (location.hash !== hash) location.hash = hash;
      window.scrollTo({
        top: 0,
        behavior: "instant",
      });
    },
    [],
  );
  return (
    <AppShell page={page} onNavigate={navigate}>
      {page === "overview" && <OverviewPage navigate={navigate} />}
      {page === "alerts" && (
        <AlertsPage
          key={
            navigationContext.familyViewId ??
            navigationContext.family ??
            "default-family"
          }
          initialAlert={null}
          clearInitial={() => undefined}
          navigate={navigate}
          {...(navigationContext.returnResultId
            ? { returnResultId: navigationContext.returnResultId }
            : {})}
          {...(navigationContext.familyViewId
            ? { initialFamilyViewId: navigationContext.familyViewId }
            : {})}
          {...(navigationContext.family
            ? { initialFamily: navigationContext.family }
            : {})}
        />
      )}
      {page === "investigations" && (
        <InvestigationsPage
          key={
            navigationContext.linkId ??
            navigationContext.family ??
            "default-link"
          }
          navigate={navigate}
          {...(navigationContext.linkId
            ? { initialLinkId: navigationContext.linkId }
            : {})}
          {...(navigationContext.family
            ? { initialFamily: navigationContext.family }
            : {})}
        />
      )}
      {page === "results" && (
        <ResultsPage
          key={`${navigationContext.resultId ?? ""}:${(navigationContext.sourceResultIds ?? []).join("\u0000")}`}
          {...(navigationContext.resultId
            ? { initialResultId: navigationContext.resultId }
            : {})}
          sourceResultIds={navigationContext.sourceResultIds ?? []}
          navigate={navigate}
        />
      )}
      {page === "replay" && <ReplayPage navigate={navigate} />}
    </AppShell>
  );
}
export default function App() {
  return (
    <ErrorBoundary>
      <TimeZoneProvider>
        <EvidenceProvider>
          <ConsoleApp />
        </EvidenceProvider>
      </TimeZoneProvider>
    </ErrorBoundary>
  );
}
