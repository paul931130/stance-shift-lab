import { requireApiOwner } from "@/lib/server/auth";
import { ApiError, routeError } from "@/lib/server/http";
import { downloadArtifact } from "@/lib/server/runs";

export const dynamic = "force-dynamic";

type RouteContext = { params: Promise<{ id: string; artifactId: string }> };

export async function GET(_request: Request, context: RouteContext) {
  try {
    const owner = await requireApiOwner();
    const { id, artifactId } = await context.params;
    if (!isUuid(id) || !isUuid(artifactId)) {
      throw new ApiError(404, "ARTIFACT_NOT_FOUND", "找不到此匯出檔案。" );
    }
    return await downloadArtifact(owner.hash, id, artifactId);
  } catch (error) {
    return routeError(error);
  }
}

function isUuid(value: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value);
}
