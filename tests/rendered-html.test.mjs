import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import test from "node:test";

const projectRoot = new URL("../", import.meta.url);

test("ships the finished Traditional Chinese research surface", async () => {
  const [page, layout, css] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/layout.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/globals.css", import.meta.url), "utf8"),
  ]);
  assert.match(layout, /lang="zh-Hant-TW"/);
  assert.match(layout, /images: \[\{ url: "\/og\.png"/);
  assert.match(page, /立場交換研究室/);
  assert.match(page, /讓模型先/);
  assert.match(page, /三輪辯論，第二輪必須站到對面/);
  assert.match(css, /--paper:/);
  assert.doesNotMatch(`${page}\n${layout}`, /codex-preview|Your site is taking shape|SkeletonPreview|react-loading-skeleton/i);
});

test("keeps auth-protected writes closed to anonymous callers", async () => {
  const [route, auth, localAuth] = await Promise.all([
    readFile(new URL("../app/api/runs/route.ts", import.meta.url), "utf8"),
    readFile(new URL("../lib/server/auth.ts", import.meta.url), "utf8"),
    readFile(new URL("../app/chatgpt-auth.ts", import.meta.url), "utf8"),
  ]);
  assert.match(route, /await requireApiOwner\(\)/);
  assert.match(auth, /if \(!user\)/);
  assert.match(auth, /401, "AUTH_REQUIRED"/);
  assert.doesNotMatch(route, /ownerHash.*body|body.*ownerHash/);
  assert.match(localAuth, /runtime\.APP_ENV === "development"/);
  assert.match(localAuth, /runtime\.LOCAL_MODE === "true"/);
  assert.match(localAuth, /isLoopbackRequest/);
});

test("ships a loopback-only Ollama provider and local-first launcher", async () => {
  const [provider, launcher, packageJson] = await Promise.all([
    readFile(new URL("../lib/server/ollama.ts", import.meta.url), "utf8"),
    readFile(new URL("../app/lab/RunLauncher.tsx", import.meta.url), "utf8"),
    readFile(new URL("../package.json", import.meta.url), "utf8"),
  ]);
  assert.match(provider, /\/api\/generate/);
  assert.match(provider, /format: STEP_OUTPUT_JSON_SCHEMA/);
  assert.match(provider, /allowedHosts = new Set\(\["localhost", "127\.0\.0\.1", "\[::1\]"\]\)/);
  assert.match(launcher, /本機基礎模型（推薦）/);
  assert.match(launcher, /mode === "local"/);
  assert.match(packageJson, /LOCAL_MODE=true/);
  assert.doesNotMatch(launcher, /127\.0\.0\.1:11434/);
});

test("ships Sites persistence bindings, migrations, and a bespoke social card", async () => {
  const [hosting, packageJson, migration] = await Promise.all([
    readFile(new URL("../.openai/hosting.json", import.meta.url), "utf8"),
    readFile(new URL("../package.json", import.meta.url), "utf8"),
    readFile(new URL("../drizzle/0000_shocking_anita_blake.sql", import.meta.url), "utf8"),
  ]);
  const hostingConfig = JSON.parse(hosting);
  assert.equal(hostingConfig.d1, "DB");
  assert.equal(hostingConfig.r2, "ARTIFACTS");
  assert.match(hostingConfig.project_id, /^appgprj_/);
  assert.doesNotMatch(packageJson, /react-loading-skeleton/);
  assert.match(migration, /CREATE TABLE `runs`/);
  assert.match(migration, /runs_one_active_owner_uq/);
  assert.match(migration, /quotas_limit_update/);
  await access(new URL("../public/og.png", import.meta.url));
  await assert.rejects(access(new URL("../app/_sites-preview", projectRoot)));
});
