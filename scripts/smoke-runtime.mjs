import assert from "node:assert/strict";

const baseUrl = process.env.BASE_URL ?? "http://localhost:3000";
const ownerEmail = `smoke-${Date.now()}@example.test`;
const ownerHeaders = {
  "content-type": "application/json",
  "oai-authenticated-user-email": ownerEmail,
  "oai-authenticated-user-full-name": encodeURIComponent("Runtime Smoke Test"),
  "oai-authenticated-user-full-name-encoding": "percent-encoded-utf-8",
};

async function jsonRequest(path, init = {}) {
  const response = await fetch(`${baseUrl}${path}`, init);
  const text = await response.text();
  let body = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    throw new Error(`${init.method ?? "GET"} ${path} returned non-JSON (${response.status}): ${text.slice(0, 240)}`);
  }
  return { response, body };
}

const home = await fetch(`${baseUrl}/`);
assert.equal(home.status, 200);
assert.match(await home.text(), /立場交換研究室/);

const anonymous = await jsonRequest("/api/runs", {
  method: "POST",
  headers: { "content-type": "application/json", "x-forwarded-host": "example.test" },
  body: JSON.stringify({ ticker: "NVDA", analysisDate: "2024-12-31", mode: "demo" }),
});
assert.equal(anonymous.response.status, 401);
assert.equal(anonymous.body.error.code, "AUTH_REQUIRED");

const liveWithoutKey = await jsonRequest("/api/runs", {
  method: "POST",
  headers: ownerHeaders,
  body: JSON.stringify({ ticker: "NVDA", analysisDate: "2024-12-31", mode: "live" }),
});
assert.equal(liveWithoutKey.response.status, 503);
assert.equal(liveWithoutKey.body.error.code, "GEMINI_NOT_CONFIGURED");

const created = await jsonRequest("/api/runs", {
  method: "POST",
  headers: ownerHeaders,
  body: JSON.stringify({ ticker: "NVDA", analysisDate: "2024-12-31", mode: "demo" }),
});
assert.equal(created.response.status, 201, JSON.stringify(created.body));
const runId = created.body.run.id;
assert.match(runId, /^[0-9a-f-]{36}$/i);
assert.equal(created.body.run.totalSteps, 20);
assert.equal(created.body.evidence.length, 12);
assert.equal(created.body.run.syntheticData, true);
const listed = await jsonRequest("/api/runs", { headers: ownerHeaders });
assert.equal(listed.response.status, 200);
assert.ok(listed.body.runs.some((run) => run.id === runId));
const conflict = await jsonRequest("/api/runs", {
  method: "POST", headers: ownerHeaders,
  body: JSON.stringify({ ticker: "AAPL", analysisDate: "2024-12-31", mode: "demo" }),
});
assert.equal(conflict.response.status, 409);
assert.equal(conflict.body.error.details.runId, runId);

let view = created.body;
for (let index = 0; index < 20; index += 1) {
  const key = `smoke-step-${index.toString().padStart(2, "0")}`;
  const advanced = await jsonRequest(`/api/runs/${runId}/advance`, {
    method: "POST",
    headers: { ...ownerHeaders, "idempotency-key": key },
    body: "{}",
  });
  assert.ok([200, 202].includes(advanced.response.status), JSON.stringify(advanced.body));
  view = advanced.body;

  if (index === 0) {
    const duplicate = await jsonRequest(`/api/runs/${runId}/advance`, {
      method: "POST",
      headers: { ...ownerHeaders, "idempotency-key": key },
      body: "{}",
    });
    assert.equal(duplicate.response.status, 200, JSON.stringify(duplicate.body));
    assert.equal(duplicate.body.run.logicalCalls, 1);
    assert.equal(duplicate.body.run.providerAttempts, 1);
  }
}

assert.equal(view.run.status, "completed", JSON.stringify(view.run));
assert.equal(view.run.logicalCalls, 20);
assert.equal(view.run.providerAttempts, 20);
assert.equal(view.run.completedSteps, 20);
assert.equal(view.results.length, 4);
assert.equal(view.artifacts.length, 8);
assert.equal(view.run.exportsReady, true);
assert.ok(view.results.every((result) => result.backtest));

const artifact = await fetch(`${baseUrl}${view.artifacts[0].downloadUrl}`, {
  headers: { "oai-authenticated-user-email": ownerEmail },
});
assert.equal(artifact.status, 200);
assert.ok((await artifact.arrayBuffer()).byteLength > 0);
const repaired = await jsonRequest(`/api/runs/${runId}/exports`, { method: "POST", headers: ownerHeaders });
assert.equal(repaired.response.status, 200);
assert.equal(repaired.body.artifacts.length, 8);
assert.equal(repaired.body.run.providerAttempts, 20);
for (const file of repaired.body.artifacts) {
  const downloaded = await fetch(`${baseUrl}${file.downloadUrl}`, { headers: ownerHeaders });
  assert.equal(downloaded.status, 200, file.fileName);
  assert.ok((await downloaded.arrayBuffer()).byteLength > 0);
}

const otherOwner = await jsonRequest(`/api/runs/${runId}`, {
  headers: { "oai-authenticated-user-email": `other-${Date.now()}@example.test` },
});
assert.equal(otherOwner.response.status, 404);
assert.equal(otherOwner.body.error.code, "RUN_NOT_FOUND");
const otherList = await jsonRequest("/api/runs", { headers: { "oai-authenticated-user-email": `other-${Date.now()}@example.test` } });
assert.deepEqual(otherList.body.runs, []);
const otherExport = await jsonRequest(`/api/runs/${runId}/exports`, { method: "POST", headers: { "oai-authenticated-user-email": `other-${Date.now()}@example.test` } });
assert.equal(otherExport.response.status, 404);

const cancellable = await jsonRequest("/api/runs", {
  method: "POST", headers: ownerHeaders,
  body: JSON.stringify({ ticker: "AAPL", analysisDate: "2024-12-31", mode: "demo" }),
});
assert.equal(cancellable.response.status, 201);
const cancelled = await jsonRequest(`/api/runs/${cancellable.body.run.id}/cancel`, { method: "POST", headers: ownerHeaders });
assert.equal(cancelled.body.run.status, "cancelled");
const blocked = await jsonRequest(`/api/runs/${cancellable.body.run.id}/advance`, { method: "POST", headers: { ...ownerHeaders, "idempotency-key": "cancelled-advance" }, body: "{}" });
assert.equal(blocked.response.status, 409);

console.log(JSON.stringify({
  ok: true,
  runId,
  logicalCalls: view.run.logicalCalls,
  providerAttempts: view.run.providerAttempts,
  evidenceItems: view.evidence.length,
  results: view.results.length,
  artifacts: view.artifacts.length,
}));
