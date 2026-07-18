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
  const [route, auth] = await Promise.all([
    readFile(new URL("../app/api/runs/route.ts", import.meta.url), "utf8"),
    readFile(new URL("../lib/server/auth.ts", import.meta.url), "utf8"),
  ]);
  assert.match(route, /await requireApiOwner\(\)/);
  assert.match(auth, /if \(!user\)/);
  assert.match(auth, /401, "AUTH_REQUIRED"/);
  assert.doesNotMatch(route, /ownerHash.*body|body.*ownerHash/);
});

test("ships Sites persistence bindings, migrations, and a bespoke social card", async () => {
  const [hosting, packageJson, migration] = await Promise.all([
    readFile(new URL("../.openai/hosting.json", import.meta.url), "utf8"),
    readFile(new URL("../package.json", import.meta.url), "utf8"),
    readFile(new URL("../drizzle/0000_shocking_anita_blake.sql", import.meta.url), "utf8"),
  ]);
  assert.deepEqual(JSON.parse(hosting), { d1: "DB", r2: "ARTIFACTS" });
  assert.doesNotMatch(packageJson, /react-loading-skeleton/);
  assert.match(migration, /CREATE TABLE `runs`/);
  assert.match(migration, /runs_one_active_owner_uq/);
  assert.match(migration, /quotas_limit_update/);
  await access(new URL("../public/og.png", import.meta.url));
  await assert.rejects(access(new URL("../app/_sites-preview", projectRoot)));
});
