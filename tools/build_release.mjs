import { execFileSync, execSync } from "node:child_process";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

const frontendManifest = resolve("public/release-manifest.json");
const staticRoot = resolve("../evidencegate/api/static");

execFileSync("node", ["../tools/generate_release_manifest.mjs", frontendManifest], {
  cwd: process.cwd(),
  env: process.env,
  stdio: "inherit",
});
execSync("npm run build:assets", { cwd: process.cwd(), env: process.env, stdio: "inherit" });

const manifest = JSON.parse(await readFile(frontendManifest, "utf8"));
const packagedManifest = JSON.parse(await readFile(resolve(staticRoot, "release-manifest.json"), "utf8"));
if (manifest.release_id !== packagedManifest.release_id || manifest.source_sha !== packagedManifest.source_sha) {
  throw new Error("Frontend and packaged backend release manifests do not match.");
}
const html = await readFile(resolve(staticRoot, "index.html"), "utf8");
const scriptPaths = [...html.matchAll(/src="([^"]+\.js)"/g)].map((match) => match[1]);
if (!scriptPaths.length) throw new Error("Built frontend does not reference a JavaScript bundle.");
const bundles = await Promise.all(scriptPaths.map((path) => readFile(resolve(staticRoot, path.replace(/^\//, "")), "utf8")));
if (!bundles.some((bundle) => bundle.includes(manifest.release_id))) {
  throw new Error("Built frontend bundle does not embed the packaged release ID.");
}
console.log(`Verified production release ${manifest.release_id} (${manifest.source_sha})`);
