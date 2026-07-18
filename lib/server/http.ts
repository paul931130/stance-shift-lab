export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly details?: Record<string, unknown>,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function json(data: unknown, init: ResponseInit = {}): Response {
  const headers = new Headers(init.headers);
  headers.set("Cache-Control", "no-store");
  return Response.json(data, { ...init, headers });
}

export function routeError(error: unknown): Response {
  if (error instanceof ApiError) {
    return json(
      {
        error: {
          code: error.code,
          message: error.message,
          ...(error.details ? { details: error.details } : {}),
        },
      },
      { status: error.status },
    );
  }

  const message = error instanceof Error ? error.message : "Unexpected error";
  console.error("Unhandled API error", error);
  return json(
    { error: { code: "INTERNAL_ERROR", message: "系統暫時無法處理要求。", requestError: message } },
    { status: 500 },
  );
}

export async function readJsonObject(request: Request): Promise<Record<string, unknown>> {
  const contentType = request.headers.get("content-type") ?? "";
  if (!contentType.toLowerCase().includes("application/json")) {
    throw new ApiError(415, "JSON_REQUIRED", "請使用 application/json。" );
  }
  try {
    const value = await request.json();
    if (!value || typeof value !== "object" || Array.isArray(value)) {
      throw new Error("not an object");
    }
    return value as Record<string, unknown>;
  } catch {
    throw new ApiError(400, "INVALID_JSON", "JSON 內容格式無效。" );
  }
}

export function readIdempotencyKey(request: Request, body?: Record<string, unknown>): string {
  const raw = request.headers.get("idempotency-key") ?? body?.idempotencyKey;
  if (typeof raw !== "string" || !/^[A-Za-z0-9._:-]{8,128}$/.test(raw)) {
    throw new ApiError(
      400,
      "IDEMPOTENCY_KEY_REQUIRED",
      "advance 要求必須提供 8–128 字元的 Idempotency-Key。",
    );
  }
  return raw;
}

export function parseJson<T>(value: string | null, fallback: T): T {
  if (!value) return fallback;
  try {
    return JSON.parse(value) as T;
  } catch {
    return fallback;
  }
}
