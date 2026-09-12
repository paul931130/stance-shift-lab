import assert from "node:assert/strict";

const baseUrl = process.env.BASE_URL ?? "http://localhost:3000";
const ownerEmail = `ollama-smoke-${Date.now()}@example.test`;
const headers = {
  "content-type": "application/json",
  "oai-authenticated-user-email": ownerEmail,
};
const model = process.env.OLLAMA_MODEL || "gemma3:4b";
const stepLimit = Number(process.env.LOCAL_SMOKE_STEPS ?? 20);
assert.ok(Number.isInteger(stepLimit) && stepLimit >= 1 && stepLimit <= 20);

async function requestJson(path, init = {}) {
  const response = await fetch(`${baseUrl}${path}`, init);
  const text = await response.text();
  let body;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    throw new Error(`${path} 回傳非 JSON 內容 (${response.status})：${text.slice(0, 240)}`);
  }
  return { response, body };
}

const lab = await fetch(`${baseUrl}/lab`);
assert.equal(lab.status, 200);
const labHtml = await lab.text();
assert.match(labHtml, /本機基礎模型/);
assert.ok(labHtml.includes(model));

const created = await requestJson("/api/runs", {
  method: "POST",
  headers,
  body: JSON.stringify({ ticker: "NVDA", analysisDate: "2024-12-31", mode: "local" }),
});
assert.equal(created.response.status, 201, JSON.stringify(created.body));
const runId = created.body.run.id;
assert.equal(created.body.run.providerMode, "ollama-local");
assert.equal(created.body.run.model, model);
console.log(`開始地端驗證：${runId} · ${model} · ${stepLimit} 步`);

const startedAt = Date.now();
let view = created.body;
for (let step = 0; step < stepLimit; step += 1) {
  let completed = false;
  for (let retry = 0; retry < 3 && !completed; retry += 1) {
    const result = await requestJson(`/api/runs/${runId}/advance`, {
      method: "POST",
      headers: { ...headers, "idempotency-key": `ollama-${step}-${retry}-${Date.now()}` },
      body: "{}",
    });
    view = result.body;
    if (result.response.ok && view.run?.completedSteps > step) {
      completed = true;
      break;
    }
    if (result.response.status === 202) {
      await new Promise((resolve) => setTimeout(resolve, result.body.retryAfterMs ?? 1500));
      retry -= 1;
      continue;
    }
    const retriable = result.body?.error?.retriable;
    if (!retriable) throw new Error(JSON.stringify(result.body));
    console.warn(`步驟 ${step + 1} 第 ${retry + 1} 次失敗：${result.body.error.message}`);
  }
  assert.equal(completed, true, `步驟 ${step + 1} 重試後仍失敗`);
  console.log(`完成 ${step + 1}/20：${view.steps[step]?.output?.decision ?? "—"}`);
}

if (stepLimit < 20) {
  const cancelled = await requestJson(`/api/runs/${runId}/cancel`, { method: "POST", headers });
  assert.equal(cancelled.response.status, 200);
  console.log(JSON.stringify({ ok: true, partial: true, model, runId, completedSteps: view.run.completedSteps, elapsedSeconds: Math.round((Date.now() - startedAt) / 1000) }));
  process.exit(0);
}

assert.equal(view.run.status, "completed");
assert.equal(view.run.logicalCalls, 20);
assert.equal(view.run.completedSteps, 20);
assert.equal(view.results.length, 4);
assert.equal(view.artifacts.length, 8);
assert.ok(view.steps.every((step) => step.output?.thesis && step.output?.argument));
const downloaded = await fetch(`${baseUrl}${view.artifacts[0].downloadUrl}`, { headers });
assert.equal(downloaded.status, 200);
assert.ok((await downloaded.arrayBuffer()).byteLength > 0);

console.log(JSON.stringify({
  ok: true,
  runId,
  model: view.run.model,
  elapsedSeconds: Math.round((Date.now() - startedAt) / 1000),
  logicalCalls: view.run.logicalCalls,
  providerAttempts: view.run.providerAttempts,
  results: view.results.map((result) => ({
    group: result.groupCode,
    decision: result.finalDecision,
    confidence: result.confidence,
  })),
  artifacts: view.artifacts.length,
}));
