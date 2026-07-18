import { requireApiOwner } from "@/lib/server/auth";
import { ApiError, json, readJsonObject, routeError } from "@/lib/server/http";
import { createRun } from "@/lib/server/runs";
import { parseAnalysisDate, parseTicker } from "@/lib/server/workflow";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  try {
    const owner = await requireApiOwner();
    const body = await readJsonObject(request);
    const ticker = parseTicker(body.ticker);
    const analysisDate = parseAnalysisDate(body.analysisDate);
    if (!ticker) {
      throw new ApiError(400, "INVALID_TICKER", "ticker 不在本實驗核准的十檔股票中。" );
    }
    if (!analysisDate) {
      throw new ApiError(400, "INVALID_ANALYSIS_DATE", "analysisDate 必須是 2021–2025 的有效 ISO 日期。" );
    }
    if (body.mode !== "demo" && body.mode !== "live") {
      throw new ApiError(400, "INVALID_MODE", "mode 必須是 demo 或 live。" );
    }

    return json(
      await createRun({
        ownerHash: owner.hash,
        ticker,
        analysisDate,
        executionMode: body.mode,
      }),
      { status: 201 },
    );
  } catch (error) {
    return routeError(error);
  }
}
