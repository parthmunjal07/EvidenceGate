export const EXPECTED_API_CONTRACT_VERSION = "1";
export const RELEASE_RECOVERY_KEY = "evidencegate.release-recovery-attempted";

export type ReleaseCheck =
  | { state: "compatible" }
  | { state: "reload"; url: string }
  | { state: "warning" }
  | { state: "incompatible" };

export function checkReleaseCompatibility(
  frontendRelease: string,
  backendRelease: string,
  backendApiContract: string | null | undefined,
  alreadyAttempted: boolean,
  currentUrl: string,
): ReleaseCheck {
  const developmentRelease = frontendRelease === "dev" || backendRelease === "dev";
  const releaseMismatch = !developmentRelease && Boolean(frontendRelease && backendRelease && frontendRelease !== backendRelease);
  if (releaseMismatch && !alreadyAttempted) {
    const url = new URL(currentUrl);
    url.searchParams.set("eg_release", backendRelease);
    return { state: "reload", url: url.toString() };
  }
  if (backendApiContract && backendApiContract !== EXPECTED_API_CONTRACT_VERSION) {
    return { state: "incompatible" };
  }
  return !developmentRelease && (releaseMismatch || !frontendRelease || !backendRelease)
    ? { state: "warning" }
    : { state: "compatible" };
}
