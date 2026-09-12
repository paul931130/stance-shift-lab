import assert from "node:assert/strict";
import test from "node:test";
import { loadTypeScript } from "./load-typescript.mjs";

const { callOllama, inspectOllama } = loadTypeScript("lib/server/ollama.ts");
const { WORKFLOW_STEPS, buildStepPrompt } = loadTypeScript("lib/server/workflow.ts");
const input = { baseUrl: "http://127.0.0.1:11434", model: "gemma3:4b", prompt: "test" };
const output = { decision: "HOLD", confidence: .7, thesis: "test", argument: "test argument", counterpoint: "test counterpoint", evidenceIds: ["ev-1"] };

test("local provider sends structured output and validates its response", async (t) => {
  t.mock.method(globalThis, "fetch", async (_url, init) => {
    const request = JSON.parse(init.body);
    assert.equal(request.stream, false);
    assert.equal(request.model, input.model);
    assert.equal(request.format.type, "object");
    return Response.json({ response: JSON.stringify(output), done: true });
  });
  const result = await callOllama(input);
  assert.deepEqual(result.output, output);
});

test("local provider timeout includes slow response-body consumption", async (t) => {
  const realTimeout = globalThis.setTimeout;
  t.mock.method(globalThis, "setTimeout", (callback, ms) => realTimeout(callback, ms === 180000 ? 20 : ms));
  t.mock.method(globalThis, "fetch", async (_url, init) => new Response(new ReadableStream({
    start(controller) {
      init.signal.addEventListener("abort", () => controller.error(new DOMException("Aborted", "AbortError")), { once: true });
    },
  })));
  await assert.rejects(callOllama(input), (error) => error.code === "LOCAL_MODEL_TIMEOUT");
});

test("local provider rejects malformed JSON and non-loopback targets", async (t) => {
  t.mock.method(globalThis, "fetch", async () => Response.json({ response: "not json" }));
  await assert.rejects(callOllama(input), (error) => error.code === "LOCAL_MODEL_BAD_JSON");
  for (const baseUrl of ["https://example.com", "http://192.168.1.2:11434", "http://user:pass@localhost:11434"]) {
    await assert.rejects(callOllama({ ...input, baseUrl }), (error) => error.code === "OLLAMA_INVALID_URL");
  }
});

test("readiness distinguishes missing model and unreachable provider", async (t) => {
  const mocked = t.mock.method(globalThis, "fetch", async () => Response.json({ models: [] }));
  assert.equal((await inspectOllama(input)).code, "OLLAMA_MODEL_MISSING");
  mocked.mock.mockImplementation(async () => { throw new Error("offline"); });
  assert.equal((await inspectOllama(input)).code, "OLLAMA_UNREACHABLE");
});

test("server workflow preserves B independence and D second-round swap", () => {
  assert.deepEqual(Object.fromEntries(["A", "B", "C", "D"].map((g) => [g, WORKFLOW_STEPS.filter((s) => s.groupCode === g).length])), { A: 1, B: 5, C: 7, D: 7 });
  assert.deepEqual(WORKFLOW_STEPS.filter((s) => s.groupCode === "D" && s.phase === "debate").map((s) => s.stance), ["BULL", "BEAR", "BEAR", "BULL", "BULL", "BEAR"]);
  const prompt = buildStepPrompt({ ticker: "NVDA", analysisDate: "2024-12-31", step: WORKFLOW_STEPS[2], evidence: [], priorOutputs: [{ stepKey: "b-first", groupCode: "B", output: { ...output, thesis: "previous_sample_secret" } }] });
  assert.ok(!prompt.includes("previous_sample_secret"));
});
