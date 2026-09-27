import { randomUUID } from "node:crypto";
import { execFileSync } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";

const output = resolve(process.argv[2] ?? "frontend/public/release-manifest.json");
let detectedSourceSha = "unknown";
try { detectedSourceSha = execFileSync("git", ["rev-parse", "HEAD"], { encoding: "utf8" }).trim(); } catch { /* build context may not include git metadata */ }
const sourceSha = process.env.EVIDENCEGATE_BUILD_SHA || process.env.RAILWAY_GIT_COMMIT_SHA || detectedSourceSha;
const releaseId = process.env.EVIDENCEGATE_RELEASE_ID || `rel-${randomUUID()}`;
const manifest = {
  release_id: releaseId,
  source_sha: sourceSha,
  built_at: new Date().toISOString(),
};

await mkdir(dirname(output), { recursive: true });
await writeFile(output, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
await writeFile(resolve(dirname(output), "..", ".env.production.local"),
  `VITE_EVIDENCEGATE_RELEASE_ID=${releaseId}\nVITE_EVIDENCEGATE_SOURCE_SHA=${sourceSha}\n`, "utf8");
console.log(`Created release manifest ${releaseId} from source ${sourceSha}`);
