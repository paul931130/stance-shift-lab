import { requireApiOwner } from "@/lib/server/auth";
import { ApiError, json, readIdempotencyKey, readJsonObject, routeError } from "@/lib/server/http";
import { advanceRun } from "@/lib/server/runs";

export const dynamic = "force-dynamic";

type RouteContext = { params: Promise<{ id: string }> };

export async function POST(request: Request, context: RouteContext) {
  try {
    const owner = await requireApiOwner();
    const { id } = await context.params;
    if (!isUuid(id)) throw new ApiError(404, "RUN_NOT_FOUND", "找不到此實驗。" );

    let body: Record<string, unknown> = {};
    if ((request.headers.get("content-type") ?? "").toLowerCase().includes("application/json")) {
      body = await readJsonObject(request);
    }
    const idempotencyKey = readIdempotencyKey(request, body);
    const response = await advanceRun(owner.hash, id, idempotencyKey);
    if (response.status === 202 && typeof response.body.retryAfterMs === "number") {
      return json(response.body, {
        status: response.status,
        headers: { "Retry-After": String(Math.max(1, Math.ceil(response.body.retryAfterMs / 1000))) },
      });
    }
    return json(response.body, { status: response.status });
  } catch (error) {
    return routeError(error);
  }
}

function isUuid(value: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value);
}
