import { requireApiOwner } from "@/lib/server/auth";
import { ApiError, json, routeError } from "@/lib/server/http";
import { cancelRun } from "@/lib/server/runs";

export const dynamic = "force-dynamic";

type RouteContext = { params: Promise<{ id: string }> };

export async function POST(_request: Request, context: RouteContext) {
  try {
    const owner = await requireApiOwner();
    const { id } = await context.params;
    if (!isUuid(id)) throw new ApiError(404, "RUN_NOT_FOUND", "找不到此實驗。" );
    return json(await cancelRun(owner.hash, id));
  } catch (error) {
    return routeError(error);
  }
}

function isUuid(value: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value);
}
