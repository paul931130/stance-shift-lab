export const ALLOWED_TICKERS = [
  "AAPL",
  "NVDA",
  "GOOGL",
  "MSFT",
  "AMZN",
  "JPM",
  "MCD",
  "LLY",
  "ASTS",
  "GE",
] as const;

export type AllowedTicker = (typeof ALLOWED_TICKERS)[number];
export type Decision = "BUY" | "HOLD" | "SELL" | "NO_TRADE";
export type GroupCode = "A" | "B" | "C" | "D";
export type Stance = "BULL" | "BEAR" | "NEUTRAL";

export type WorkflowStep = {
  index: number;
  key: string;
  groupCode: GroupCode;
  phase: "sample" | "debate" | "adjudication";
  round: number | null;
  agentId: string | null;
  stance: Stance;
  label: string;
};

export type EvidenceForPrompt = {
  evidenceId: string;
  domain: string;
  claim: string;
  direction: string;
  uncertainty: string;
  availableAt: string;
  isValid: boolean;
};

export type StepOutput = {
  decision: Decision;
  confidence: number;
  thesis: string;
  argument: string;
  evidenceIds: string[];
  counterpoint: string;
};

function step(
  index: number,
  key: string,
  groupCode: GroupCode,
  phase: WorkflowStep["phase"],
  round: number | null,
  agentId: string | null,
  stance: Stance,
  label: string,
): WorkflowStep {
  return { index, key, groupCode, phase, round, agentId, stance, label };
}

/**
 * The workflow contains exactly twenty logical model calls:
 * A=1, B=5, C=6 debate turns + adjudicator, D=6 turns + adjudicator.
 */
export const WORKFLOW_STEPS: readonly WorkflowStep[] = [
  step(0, "a-single", "A", "sample", null, "single", "NEUTRAL", "A 組：單次決策"),
  ...Array.from({ length: 5 }, (_, offset) =>
    step(
      offset + 1,
      `b-sample-${offset + 1}`,
      "B",
      "sample",
      null,
      `sample-${offset + 1}`,
      "NEUTRAL",
      `B 組：獨立抽樣 ${offset + 1}/5`,
    ),
  ),
  step(6, "c-r1-bull", "C", "debate", 1, "bull", "BULL", "C 組第一輪：Bull"),
  step(7, "c-r1-bear", "C", "debate", 1, "bear", "BEAR", "C 組第一輪：Bear"),
  step(8, "c-r2-bull", "C", "debate", 2, "bull", "BULL", "C 組第二輪：Bull"),
  step(9, "c-r2-bear", "C", "debate", 2, "bear", "BEAR", "C 組第二輪：Bear"),
  step(10, "c-r3-bull", "C", "debate", 3, "bull", "BULL", "C 組第三輪：Bull"),
  step(11, "c-r3-bear", "C", "debate", 3, "bear", "BEAR", "C 組第三輪：Bear"),
  step(12, "c-adjudicator", "C", "adjudication", null, "adjudicator", "NEUTRAL", "C 組裁決"),
  step(13, "d-r1-alpha-bull", "D", "debate", 1, "alpha", "BULL", "D 組第一輪：Alpha 看多"),
  step(14, "d-r1-beta-bear", "D", "debate", 1, "beta", "BEAR", "D 組第一輪：Beta 看空"),
  step(15, "d-r2-alpha-bear", "D", "debate", 2, "alpha", "BEAR", "D 組第二輪：Alpha 交換為看空"),
  step(16, "d-r2-beta-bull", "D", "debate", 2, "beta", "BULL", "D 組第二輪：Beta 交換為看多"),
  step(17, "d-r3-alpha-bull", "D", "debate", 3, "alpha", "BULL", "D 組第三輪：Alpha 回歸並整合反方"),
  step(18, "d-r3-beta-bear", "D", "debate", 3, "beta", "BEAR", "D 組第三輪：Beta 回歸並整合反方"),
  step(19, "d-adjudicator", "D", "adjudication", null, "adjudicator", "NEUTRAL", "D 組裁決"),
];

export const STEP_OUTPUT_JSON_SCHEMA = {
  type: "object",
  additionalProperties: false,
  properties: {
    decision: { type: "string", enum: ["BUY", "HOLD", "SELL", "NO_TRADE"] },
    confidence: { type: "number", minimum: 0, maximum: 1 },
    thesis: { type: "string", minLength: 1, maxLength: 500 },
    argument: { type: "string", minLength: 1, maxLength: 1200 },
    evidenceIds: {
      type: "array",
      items: { type: "string" },
      maxItems: 12,
    },
    counterpoint: { type: "string", maxLength: 500 },
  },
  required: [
    "decision",
    "confidence",
    "thesis",
    "argument",
    "evidenceIds",
    "counterpoint",
  ],
} as const;

export function parseTicker(value: unknown): AllowedTicker | null {
  if (typeof value !== "string") return null;
  const ticker = value.trim().toUpperCase();
  return (ALLOWED_TICKERS as readonly string[]).includes(ticker)
    ? (ticker as AllowedTicker)
    : null;
}

export function parseAnalysisDate(value: unknown): string | null {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const parsed = new Date(`${value}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== value) return null;
  return value >= "2021-01-01" && value <= "2025-12-31" ? value : null;
}

export function validateStepOutput(value: unknown): StepOutput {
  if (!value || typeof value !== "object") throw new Error("模型未回傳 JSON 物件");
  const candidate = value as Record<string, unknown>;
  const decisions: Decision[] = ["BUY", "HOLD", "SELL", "NO_TRADE"];
  if (!decisions.includes(candidate.decision as Decision)) throw new Error("decision 無效");
  if (
    typeof candidate.confidence !== "number" ||
    !Number.isFinite(candidate.confidence) ||
    candidate.confidence < 0 ||
    candidate.confidence > 1
  ) {
    throw new Error("confidence 必須介於 0 與 1");
  }
  if (typeof candidate.thesis !== "string" || !candidate.thesis.trim()) {
    throw new Error("thesis 不可為空");
  }
  if (typeof candidate.argument !== "string" || !candidate.argument.trim()) {
    throw new Error("argument 不可為空");
  }
  if (!Array.isArray(candidate.evidenceIds) || !candidate.evidenceIds.every((id) => typeof id === "string")) {
    throw new Error("evidenceIds 格式無效");
  }
  if (typeof candidate.counterpoint !== "string") throw new Error("counterpoint 格式無效");

  return {
    decision: candidate.decision as Decision,
    confidence: Math.round(candidate.confidence * 1000) / 1000,
    thesis: candidate.thesis.trim().slice(0, 500),
    argument: candidate.argument.trim().slice(0, 1200),
    evidenceIds: [...new Set(candidate.evidenceIds as string[])].slice(0, 12),
    counterpoint: candidate.counterpoint.trim().slice(0, 500),
  };
}

export function buildStepPrompt(input: {
  ticker: string;
  analysisDate: string;
  step: WorkflowStep;
  evidence: EvidenceForPrompt[];
  priorOutputs: Array<{ stepKey: string; groupCode: string; output: StepOutput }>;
}): string {
  const { ticker, analysisDate, step: current, evidence, priorOutputs } = input;
  // B is a true self-consistency baseline: all five samples are independent
  // and therefore must not see earlier B outputs.
  const sameGroupHistory =
    current.groupCode === "B"
      ? []
      : priorOutputs.filter((item) => item.groupCode === current.groupCode);
  const stanceInstruction =
    current.stance === "BULL"
      ? "你必須提出目前證據能支持的最強看多論證，但不得捏造證據。"
      : current.stance === "BEAR"
        ? "你必須提出目前證據能支持的最強看空論證，但不得捏造證據。"
        : "你必須保持中立，依證據做出判斷。";
  const switchInstruction =
    current.groupCode === "D" && current.round === 2
      ? "這是強制立場交換輪。請從目前指定立場重新審視，不能沿用第一輪結論。"
      : current.groupCode === "D" && current.round === 3
        ? "回到原始立場，但必須納入第二輪親自提出的最強反方證據。"
        : "";
  const adjudicationInstruction =
    current.phase === "adjudication"
      ? "你是獨立裁決者。比較雙方證據品質後裁決，不得以發言長度或語氣作為依據。"
      : "";

  return [
    "你是多代理人歷史投資研究實驗中的一個受約束步驟。",
    `標的：${ticker}；分析截點：${analysisDate}；步驟：${current.label}。`,
    stanceInstruction,
    switchInstruction,
    adjudicationInstruction,
    "只能引用下方證據的 evidenceId。若證據不足或互相矛盾，選 NO_TRADE。",
    "HOLD 表示證據充分但方向中立；NO_TRADE 表示證據不足或不可靠。",
    `證據帳本：${JSON.stringify(evidence)}`,
    `本組先前輸出：${JSON.stringify(sameGroupHistory)}`,
    "請以繁體中文作答，並嚴格輸出指定 JSON。",
  ]
    .filter(Boolean)
    .join("\n");
}

export async function deterministicDemoOutput(input: {
  ticker: string;
  analysisDate: string;
  step: WorkflowStep;
  evidenceIds: string[];
}): Promise<StepOutput> {
  const seed = `${input.ticker}|${input.analysisDate}|${input.step.key}`;
  const bytes = new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(seed)));
  const score = bytes[0] / 255;
  let decision: Decision = score > 0.68 ? "BUY" : score < 0.32 ? "SELL" : "HOLD";
  if (input.evidenceIds.length === 0) decision = "NO_TRADE";
  if (input.step.stance === "BULL" && decision === "SELL") decision = "HOLD";
  if (input.step.stance === "BEAR" && decision === "BUY") decision = "HOLD";
  const confidence = Math.round((0.48 + (bytes[1] / 255) * 0.34) * 1000) / 1000;
  const stanceLabel =
    input.step.stance === "BULL" ? "看多" : input.step.stance === "BEAR" ? "看空" : "中立";
  return {
    decision,
    confidence,
    thesis: `${input.step.label}的可重現示範結論為 ${decision}。`,
    argument: `此為 deterministic demo，依固定種子模擬${stanceLabel}代理人的結構化輸出，不代表真實市場事實或投資建議。`,
    evidenceIds: input.evidenceIds.slice(0, 4),
    counterpoint: "正式研究必須以分析日當時可取得、且通過時間檢查的證據重新執行。",
  };
}
