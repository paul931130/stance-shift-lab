import { requireApiOwner } from "@/lib/server/auth";
import { json, routeError } from "@/lib/server/http";
import { repairRunArtifacts } from "@/lib/server/runs";

export const dynamic = "force-dynamic";

export async function POST(_request: Request, context: { params: Promise<{ id: string }> }) {
  try {
    const owner = await requireApiOwner();
    const { id } = await context.params;
    return json(await repairRunArtifacts(owner.hash, id));
  } catch (error) {
    return routeError(error);
  }
}
