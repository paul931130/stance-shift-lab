import { ProviderError } from "./provider-error";
import { STEP_OUTPUT_JSON_SCHEMA, validateStepOutput, type StepOutput } from "./workflow";

type OllamaTagsResponse = {
  models?: Array<{ name?: string; model?: string }>;
};

type OllamaGenerateResponse = {
  response?: string;
  error?: string;
  done?: boolean;
};

export type OllamaReadiness = {
  ready: boolean;
  code: "OLLAMA_READY" | "OLLAMA_UNREACHABLE" | "OLLAMA_MODEL_MISSING" | "OLLAMA_INVALID_URL";
  message: string;
  model: string;
};

export async function inspectOllama(input: {
  baseUrl: string;
  model: string;
}): Promise<OllamaReadiness> {
  let baseUrl: string;
  try {
    baseUrl = normalizeLoopbackBaseUrl(input.baseUrl);
  } catch (error) {
    return {
      ready: false,
      code: "OLLAMA_INVALID_URL",
      message: error instanceof Error ? error.message : "Ollama 位址無效。",
      model: input.model,
    };
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 5_000);
  try {
    const response = await fetch(`${baseUrl}/api/tags`, {
      headers: { Accept: "application/json" },
      signal: controller.signal,
    });
    const rawText = await response.text();
    if (!response.ok) {
      return {
        ready: false,
        code: "OLLAMA_UNREACHABLE",
        message: `Ollama 健康檢查回傳 HTTP ${response.status}。`,
        model: input.model,
      };
    }

    let payload: OllamaTagsResponse;
    try {
      payload = JSON.parse(rawText) as OllamaTagsResponse;
    } catch {
      return {
        ready: false,
        code: "OLLAMA_UNREACHABLE",
        message: "Ollama 健康檢查未回傳有效 JSON。",
        model: input.model,
      };
    }
    const installed = new Set(
      (payload.models ?? []).flatMap((item) => [item.name, item.model]).filter(Boolean),
    );
    if (!installed.has(input.model)) {
      return {
        ready: false,
        code: "OLLAMA_MODEL_MISSING",
        message: `Ollama 已啟動，但尚未安裝 ${input.model}。`,
        model: input.model,
      };
    }
    return {
      ready: true,
      code: "OLLAMA_READY",
      message: `Ollama 與 ${input.model} 已就緒。`,
      model: input.model,
    };
  } catch (error) {
    const timedOut = error instanceof Error && error.name === "AbortError";
    return {
      ready: false,
      code: "OLLAMA_UNREACHABLE",
      message: timedOut
        ? "Ollama 健康檢查逾時，請確認應用程式已啟動。"
        : "無法連上本機 Ollama，請先啟動 Ollama。",
      model: input.model,
    };
  } finally {
    clearTimeout(timeout);
  }
}

export async function callOllama(input: {
  baseUrl: string;
  model: string;
  prompt: string;
}): Promise<{ output: StepOutput; raw: unknown; latencyMs: number; httpStatus: number }> {
  if (!/^[A-Za-z0-9._:-]+$/.test(input.model)) {
    throw new ProviderError("Ollama 模型名稱無效。", null, null, "OLLAMA_MODEL_INVALID");
  }
  const baseUrl = normalizeLoopbackBaseUrl(input.baseUrl);
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 180_000);
  const started = Date.now();
  let response: Response;
  let rawText: string;
  try {
    response = await fetch(`${baseUrl}/api/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({
        model: input.model,
        prompt: input.prompt,
        stream: false,
        format: STEP_OUTPUT_JSON_SCHEMA,
        keep_alive: "30m",
        options: {
          temperature: 0.2,
          top_p: 0.9,
          num_predict: 650,
        },
      }),
      signal: controller.signal,
    });
    // Keep the timeout active until the entire non-streaming response arrives.
    rawText = await response.text();
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") {
      throw new ProviderError(
        "本機模型推論超過 180 秒。",
        504,
        null,
        "LOCAL_MODEL_TIMEOUT",
      );
    }
    throw new ProviderError(
      "無法連上本機 Ollama，請確認應用程式仍在執行。",
      null,
      null,
      "OLLAMA_UNREACHABLE",
    );
  } finally {
    clearTimeout(timeout);
  }

  const latencyMs = Date.now() - started;
  let raw: OllamaGenerateResponse | string;
  try {
    raw = JSON.parse(rawText) as OllamaGenerateResponse;
  } catch {
    raw = rawText;
  }
  if (!response.ok) {
    throw new ProviderError(
      `Ollama 回傳 HTTP ${response.status}。`,
      response.status,
      rawText.slice(0, 1000),
      response.status === 404 ? "OLLAMA_MODEL_MISSING" : "OLLAMA_REQUEST_FAILED",
    );
  }

  const generated = typeof raw === "string" ? "" : raw.response?.trim();
  if (!generated) {
    throw new ProviderError(
      "本機模型沒有回傳內容。",
      response.status,
      rawText.slice(0, 1000),
      "LOCAL_MODEL_EMPTY_RESPONSE",
    );
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(stripCodeFence(generated));
  } catch {
    throw new ProviderError(
      "本機模型輸出不是有效 JSON。",
      response.status,
      generated.slice(0, 1000),
      "LOCAL_MODEL_BAD_JSON",
    );
  }
  try {
    return {
      output: validateStepOutput(parsed),
      raw,
      latencyMs,
      httpStatus: response.status,
    };
  } catch (error) {
    throw new ProviderError(
      error instanceof Error ? error.message : "本機模型輸出格式不符。",
      response.status,
      generated.slice(0, 1000),
      "LOCAL_MODEL_BAD_JSON",
    );
  }
}

function normalizeLoopbackBaseUrl(value: string): string {
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    throw new ProviderError("OLLAMA_BASE_URL 格式無效。", null, null, "OLLAMA_INVALID_URL");
  }
  const allowedHosts = new Set(["localhost", "127.0.0.1", "[::1]"]);
  if (url.protocol !== "http:" || !allowedHosts.has(url.hostname.toLowerCase())) {
    throw new ProviderError(
      "基礎版只允許連線到本機 loopback Ollama。",
      null,
      null,
      "OLLAMA_INVALID_URL",
    );
  }
  if (url.username || url.password || url.search || url.hash) {
    throw new ProviderError("OLLAMA_BASE_URL 不可包含憑證或查詢參數。", null, null, "OLLAMA_INVALID_URL");
  }
  return `${url.origin}${url.pathname.replace(/\/+$/, "")}`;
}

function stripCodeFence(value: string): string {
  return value.replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "").trim();
}
