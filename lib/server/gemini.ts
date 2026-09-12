import { STEP_OUTPUT_JSON_SCHEMA, validateStepOutput, type StepOutput } from "./workflow";
import { ProviderError } from "./provider-error";

export async function callGemini(input: {
  apiKey: string;
  model: string;
  prompt: string;
}): Promise<{ output: StepOutput; raw: unknown; latencyMs: number; httpStatus: number }> {
  if (!/^[A-Za-z0-9._-]+$/.test(input.model)) {
    throw new ProviderError("Gemini model name is invalid", null);
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 45_000);
  const started = Date.now();
  let response: Response;
  try {
    response = await fetch(
      `https://generativelanguage.googleapis.com/v1beta/models/${input.model}:generateContent`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-goog-api-key": input.apiKey,
        },
        body: JSON.stringify({
          contents: [{ role: "user", parts: [{ text: input.prompt }] }],
          generationConfig: {
            temperature: 0.2,
            topP: 0.9,
            maxOutputTokens: 1200,
            responseMimeType: "application/json",
            responseJsonSchema: STEP_OUTPUT_JSON_SCHEMA,
          },
        }),
        signal: controller.signal,
      },
    );
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ProviderError("Gemini request timed out after 45 seconds", 504);
    }
    throw new ProviderError(error instanceof Error ? error.message : "Gemini request failed", null);
  } finally {
    clearTimeout(timeout);
  }

  const latencyMs = Date.now() - started;
  const rawText = await response.text();
  let raw: unknown;
  try {
    raw = JSON.parse(rawText);
  } catch {
    raw = rawText;
  }

  if (!response.ok) {
    throw new ProviderError(
      `Gemini returned HTTP ${response.status}`,
      response.status,
      rawText.slice(0, 1000),
    );
  }

  const text = extractCandidateText(raw);
  let parsed: unknown;
  try {
    parsed = JSON.parse(stripCodeFence(text));
  } catch {
    throw new ProviderError("Gemini returned malformed structured JSON", response.status, text.slice(0, 1000));
  }

  return {
    output: validateStepOutput(parsed),
    raw,
    latencyMs,
    httpStatus: response.status,
  };
}

function extractCandidateText(raw: unknown): string {
  const candidate = raw as {
    candidates?: Array<{ content?: { parts?: Array<{ text?: string }> } }>;
  };
  const text = candidate?.candidates?.[0]?.content?.parts
    ?.map((part) => part.text ?? "")
    .join("")
    .trim();
  if (!text) throw new ProviderError("Gemini returned no candidate text", 502);
  return text;
}

function stripCodeFence(value: string): string {
  return value
    .replace(/^```(?:json)?\s*/i, "")
    .replace(/\s*```$/, "")
    .trim();
}
