import assert from "node:assert/strict";
import test from "node:test";
import { DatabaseSync } from "node:sqlite";
import { loadTypeScript } from "./load-typescript.mjs";

test("partial export failure is repairable without rerunning models", async (t) => {
  const sqlite = new DatabaseSync(":memory:");
  t.after(() => sqlite.close());
  const db = {
    prepare(sql) {
      let values = [];
      return {
        bind(...args) { values = args; return this; },
        async run() { const result = sqlite.prepare(sql).run(...values); return { success: true, meta: { changes: Number(result.changes) } }; },
        async all() { return { results: sqlite.prepare(sql).all(...values), success: true }; },
        async first() { return sqlite.prepare(sql).get(...values) ?? null; },
      };
    },
    async batch(statements) {
      sqlite.exec("BEGIN");
      try {
        const results = [];
        for (const statement of statements) results.push(await statement.run());
        sqlite.exec("COMMIT");
        return results;
      } catch (error) { sqlite.exec("ROLLBACK"); throw error; }
    },
  };
  let writes = 0;
  let fail = true;
  const bucket = { async put() { writes++; if (fail && writes === 3) throw new Error("simulated disk failure"); } };
  const services = loadTypeScript("lib/server/runs.ts", {
    "cloudflare:workers": { env: { DB: db, ARTIFACTS: bucket, LOCAL_MODE: "true", APP_ENV: "development" } },
    "drizzle-orm/d1": { drizzle() {} },
    "./schema": {},
  });
  t.mock.method(console, "error", () => {});
  let view = await services.createRun({ ownerHash: "owner-a", ticker: "NVDA", analysisDate: "2024-12-31", executionMode: "demo" });
  const runId = view.run.id;
  for (let step = 0; step < 20; step++) {
    const result = await services.advanceRun("owner-a", runId, `test-step-${step}`);
    assert.equal(result.status, 200);
    view = result.body;
  }
  assert.equal(view.run.status, "completed");
  assert.equal(view.artifacts.length, 2);
  assert.equal(view.run.exportsReady, false);
  assert.equal(view.results.length, 4);
  fail = false;
  const repaired = await services.repairRunArtifacts("owner-a", runId);
  assert.equal(repaired.artifacts.length, 8);
  assert.equal(repaired.run.exportsReady, true);
  assert.equal(repaired.run.providerAttempts, 20);
  const writesBefore = writes;
  await services.repairRunArtifacts("owner-a", runId);
  assert.equal(writes, writesBefore);
  await assert.rejects(services.repairRunArtifacts("other-owner", runId), (error) => error.code === "RUN_NOT_FOUND");
});
