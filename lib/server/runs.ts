import { ensureDatabaseSchema, getArtifactsBucket, getD1, getRuntimeBindings } from "@/db";
import { ApiError, parseJson } from "./http";
import { callGemini } from "./gemini";
import { callOllama, inspectOllama } from "./ollama";
import { ProviderError } from "./provider-error";
import {
  createDeterministicResearchSnapshots,
  flattenSnapshotEvidence,
} from "@/lib/domain/research";
import { runBacktest } from "@/lib/domain/backtest";
import { stableNumber } from "@/lib/domain/deterministic";
import {
  WORKFLOW_STEPS,
  buildStepPrompt,
  deterministicDemoOutput,
  type Decision,
  type EvidenceForPrompt,
  type GroupCode,
  type StepOutput,
  type WorkflowStep,
} from "./workflow";

type RunRow = {
  id: string;
  owner_hash: string;
  ticker: string;
  analysis_date: string;
  experiment_mode: string;
  model: string;
  status: "queued" | "running" | "completed" | "cancelled" | "failed";
  current_step: number;
  total_steps: number;
  logical_calls: number;
  provider_attempts: number;
  version: number;
  demo_mode: number;
  published: number;
  input_json: string;
  lease_token: string | null;
  lease_expires_at: number | null;
  decision_locked_at: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  cancelled_at: string | null;
};

type StepRow = {
  id: string;
  run_id: string;
  step_index: number;
  step_key: string;
  group_code: GroupCode;
  phase: WorkflowStep["phase"];
  round: number | null;
  agent_id: string | null;
  stance: WorkflowStep["stance"];
  status: "pending" | "running" | "completed";
  input_json: string;
  output_json: string | null;
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
};

type AdvanceRequestRow = {
  run_id: string;
  idempotency_key: string;
  owner_hash: string;
  step_index: number | null;
  status: "started" | "completed" | "failed";
  response_json: string | null;
};

type ResultRow = {
  id: string;
  run_id: string;
  group_code: GroupCode;
  raw_decision: Decision;
  final_decision: Decision;
  confidence: number;
  thesis: string;
  evidence_ids_json: string;
  gatekeeper_json: string;
  backtest_json: string | null;
  created_at: string;
};

type ArtifactRow = {
  id: string;
  run_id: string;
  kind: string;
  file_name: string;
  content_type: string;
  byte_size: number;
  checksum: string;
  status: string;
  created_at: string;
};

type EvidenceRow = {
  evidence_id: string;
  domain: string;
  source: string;
  source_url: string | null;
  published_at: string;
  available_at: string;
  analysis_date: string;
  claim: string;
  value: string | null;
  direction: string;
  uncertainty: string;
  checksum: string;
  is_valid: number;
};

type EventRow = {
  sequence: number;
  kind: string;
  message: string;
  payload_json: string;
  created_at: string;
};

export type ServiceResponse = { status: number; body: Record<string, unknown> };

export type ExecutionMode = "demo" | "local" | "live";

export async function createRun(input: {
  ownerHash: string;
  ticker: string;
  analysisDate: string;
  executionMode: ExecutionMode;
}): Promise<Record<string, unknown>> {
  await ensureDatabaseSchema();
  const db = getD1();
  const runtime = getRuntimeBindings();
  const id = crypto.randomUUID();
  const now = new Date().toISOString();
  const model =
    input.executionMode === "local"
      ? runtime.OLLAMA_MODEL?.trim() || "gemma3:4b"
      : input.executionMode === "live"
        ? runtime.GEMINI_MODEL?.trim() || "gemini-3.5-flash"
        : "deterministic-demo-v1";
  const demoMode = input.executionMode === "demo";
  if (input.executionMode === "live" && !runtime.GEMINI_API_KEY) {
    throw new ApiError(
      503,
      "GEMINI_NOT_CONFIGURED",
      "正式 Gemini 模式尚未設定金鑰；請先使用可重現示範。",
    );
  }
  if (input.executionMode === "local") {
    if (!isLocalRuntime(runtime)) {
      throw new ApiError(403, "LOCAL_MODE_DISABLED", "本機模型模式只允許從本機開發伺服器使用。" );
    }
    const readiness = await inspectOllama({
      baseUrl: runtime.OLLAMA_BASE_URL?.trim() || "http://127.0.0.1:11434",
      model,
    });
    if (!readiness.ready) {
      throw new ApiError(503, readiness.code, readiness.message, { model });
    }
  }
  const quotaWindow = taipeiDay(new Date());
  const snapshotEvidence = flattenSnapshotEvidence(
    createDeterministicResearchSnapshots(input.ticker, input.analysisDate),
  );

  const quotaStatements: D1PreparedStatement[] = isLocalRuntime(runtime) ? [] : [
    db
      .prepare(
        `INSERT INTO quotas (scope, quota_key, window_start, count, updated_at)
         VALUES ('user', ?, ?, 1, ?)
         ON CONFLICT(scope, quota_key, window_start)
         DO UPDATE SET count = count + 1, updated_at = excluded.updated_at`,
      )
      .bind(input.ownerHash, quotaWindow, now),
    db
      .prepare(
        `INSERT INTO quotas (scope, quota_key, window_start, count, updated_at)
         VALUES ('site', 'global', ?, 1, ?)
         ON CONFLICT(scope, quota_key, window_start)
         DO UPDATE SET count = count + 1, updated_at = excluded.updated_at`,
      )
      .bind(quotaWindow, now),
  ];
  const statements: D1PreparedStatement[] = [
    ...quotaStatements,
    db
      .prepare(
        `INSERT INTO runs (
           id, owner_hash, ticker, analysis_date, experiment_mode, model, status,
           current_step, total_steps, logical_calls, provider_attempts, version,
           demo_mode, published, input_json, created_at, updated_at
         ) VALUES (?, ?, ?, ?, 'full', ?, 'queued', 0, ?, 0, 0, 0, ?, 0, ?, ?, ?)`,
      )
      .bind(
        id,
        input.ownerHash,
        input.ticker,
        input.analysisDate,
        model,
        WORKFLOW_STEPS.length,
        demoMode ? 1 : 0,
        JSON.stringify({
          ticker: input.ticker,
          analysisDate: input.analysisDate,
          experimentMode: "full",
          executionMode: input.executionMode,
          datasetVersion: "deterministic-demo-v1",
        }),
        now,
        now,
      ),
    ...WORKFLOW_STEPS.map((workflowStep) =>
      db
        .prepare(
          `INSERT INTO run_steps (
             id, run_id, step_index, step_key, group_code, phase, round,
             agent_id, stance, status, input_json
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)`,
        )
        .bind(
          crypto.randomUUID(),
          id,
          workflowStep.index,
          workflowStep.key,
          workflowStep.groupCode,
          workflowStep.phase,
          workflowStep.round,
          workflowStep.agentId,
          workflowStep.stance,
          JSON.stringify(workflowStep),
        ),
    ),
    ...snapshotEvidence.map((item) =>
      db
        .prepare(
          `INSERT INTO evidence_items (
             id, run_id, evidence_id, domain, source, source_url, published_at,
             available_at, analysis_date, claim, value, direction, uncertainty,
             checksum, is_valid
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)`,
        )
        .bind(
          crypto.randomUUID(),
          id,
          item.evidenceId,
          item.domain,
          item.source,
          item.sourceUrl,
          item.publishedAt,
          item.availableAt,
          item.analysisDate,
          item.claim,
          String(item.value),
          item.direction,
          String(item.uncertainty),
          item.checksum,
        ),
    ),
    db
      .prepare(
        `INSERT INTO events (id, run_id, sequence, kind, message, payload_json, created_at)
         VALUES (?, ?, 0, 'run_created', ?, ?, ?)`,
      )
      .bind(
        crypto.randomUUID(),
        id,
        input.executionMode === "local"
          ? `已建立本機 ${model} 實驗。`
          : demoMode
            ? "已建立可重現示範實驗。"
            : "已建立 Gemini 實驗，等待逐步執行。",
        JSON.stringify({ executionMode: input.executionMode, totalSteps: WORKFLOW_STEPS.length }),
        now,
      ),
  ];

  try {
    await db.batch(statements);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    if (message.includes("quota_limit")) {
      throw new ApiError(429, "DAILY_QUOTA_REACHED", "今日實驗額度已用完，請於明日再試。", {
        perUser: 3,
        siteWide: 10,
        timeZone: "Asia/Taipei",
      });
    }
    if (message.includes("runs_one_active_owner_uq") || message.includes("runs.owner_hash")) {
      const active = await db.prepare("SELECT id FROM runs WHERE owner_hash = ? AND status IN ('queued','running') LIMIT 1")
        .bind(input.ownerHash).first<{ id: string }>();
      throw new ApiError(409, "ACTIVE_RUN_EXISTS", "你已有一個尚未完成的實驗，請先繼續或取消。", { runId: active?.id });
    }
    throw error;
  }

  return getRunView(input.ownerHash, id);
}

export async function listRuns(ownerHash: string) {
  await ensureDatabaseSchema();
  const rows = await getD1().prepare(
    `SELECT * FROM runs WHERE owner_hash = ?
     ORDER BY CASE WHEN status IN ('queued','running') THEN 0 ELSE 1 END, created_at DESC LIMIT 100`,
  ).bind(ownerHash).all<RunRow>();
  return rows.results.map((run) => ({
    id: run.id, ticker: run.ticker, analysisDate: run.analysis_date,
    status: run.status, model: run.model, executionMode: executionModeForRun(run),
    completedSteps: run.current_step, totalSteps: run.total_steps, createdAt: run.created_at,
  }));
}

export async function getRunView(ownerHash: string, runId: string): Promise<Record<string, unknown>> {
  await ensureDatabaseSchema();
  const db = getD1();
  const run = await ownedRun(db, ownerHash, runId);

  const [stepsResult, eventsResult, evidenceResult, resultsResult, artifactsResult] = await Promise.all([
    db.prepare("SELECT * FROM run_steps WHERE run_id = ? ORDER BY step_index").bind(runId).all<StepRow>(),
    db
      .prepare(
        "SELECT sequence, kind, message, payload_json, created_at FROM events WHERE run_id = ? ORDER BY sequence",
      )
      .bind(runId)
      .all<EventRow>(),
    db
      .prepare(
        `SELECT evidence_id, domain, source, source_url, published_at, available_at,
                analysis_date, claim, value, direction, uncertainty, checksum, is_valid
         FROM evidence_items WHERE run_id = ? ORDER BY evidence_id`,
      )
      .bind(runId)
      .all<EvidenceRow>(),
    db.prepare("SELECT * FROM results WHERE run_id = ? ORDER BY group_code").bind(runId).all<ResultRow>(),
    db
      .prepare(
        `SELECT id, run_id, kind, file_name, content_type, byte_size, checksum, status, created_at
         FROM artifacts WHERE run_id = ? AND owner_hash = ? ORDER BY created_at`,
      )
      .bind(runId, ownerHash)
      .all<ArtifactRow>(),
  ]);

  const completedSteps = stepsResult.results.filter((item) => item.status === "completed").length;
  const executionMode = executionModeForRun(run);
  return {
    run: {
      id: run.id,
      ticker: run.ticker,
      analysisDate: run.analysis_date,
      experimentMode: run.experiment_mode,
      status: run.status,
      model: run.model,
      executionMode,
      datasetVersion: "deterministic-demo-v1",
      syntheticData: true,
      exportsReady: artifactsResult.results.filter((item) => item.status === "ready").length === 8,
      providerMode: providerName(executionMode),
      currentStep: run.current_step,
      totalSteps: run.total_steps,
      completedSteps,
      progressPercent: Math.round((completedSteps / run.total_steps) * 100),
      logicalCalls: run.logical_calls,
      providerAttempts: run.provider_attempts,
      decisionLockedAt: run.decision_locked_at,
      errorMessage: run.error_message,
      createdAt: run.created_at,
      updatedAt: run.updated_at,
      completedAt: run.completed_at,
      cancelledAt: run.cancelled_at,
    },
    steps: stepsResult.results.map((item) => ({
      index: item.step_index,
      key: item.step_key,
      groupCode: item.group_code,
      phase: item.phase,
      round: item.round,
      agentId: item.agent_id,
      stance: item.stance,
      status: item.status,
      output: parseJson<StepOutput | null>(item.output_json, null),
      startedAt: item.started_at,
      completedAt: item.completed_at,
      errorMessage: item.error_message,
    })),
    events: eventsResult.results.map((item) => ({
      sequence: item.sequence,
      kind: item.kind,
      message: item.message,
      payload: parseJson(item.payload_json, {}),
      createdAt: item.created_at,
    })),
    evidence: evidenceResult.results.map((item) => ({
      evidenceId: item.evidence_id,
      domain: item.domain,
      source: item.source,
      sourceUrl: item.source_url,
      publishedAt: item.published_at,
      availableAt: item.available_at,
      analysisDate: item.analysis_date,
      claim: item.claim,
      value: item.value,
      direction: item.direction,
      uncertainty: item.uncertainty,
      checksum: item.checksum,
      isValid: Boolean(item.is_valid),
    })),
    results: resultsResult.results.map((item) => ({
      id: item.id,
      groupCode: item.group_code,
      rawDecision: item.raw_decision,
      finalDecision: item.final_decision,
      confidence: item.confidence / 1000,
      thesis: item.thesis,
      evidenceIds: parseJson<string[]>(item.evidence_ids_json, []),
      gatekeeper: parseJson(item.gatekeeper_json, {}),
      backtest: parseJson(item.backtest_json, null),
      createdAt: item.created_at,
    })),
    artifacts: artifactsResult.results.map((item) => ({
      id: item.id,
      kind: item.kind,
      fileName: item.file_name,
      contentType: item.content_type,
      byteSize: item.byte_size,
      checksum: item.checksum,
      status: item.status,
      createdAt: item.created_at,
      downloadUrl: `/api/runs/${runId}/artifacts/${item.id}`,
    })),
    nextAction:
      run.status === "queued" || run.status === "running"
        ? { method: "POST", href: `/api/runs/${runId}/advance`, requiresIdempotencyKey: true }
        : null,
  };
}

export async function advanceRun(
  ownerHash: string,
  runId: string,
  idempotencyKey: string,
): Promise<ServiceResponse> {
  await ensureDatabaseSchema();
  const db = getD1();
  let run = await ownedRun(db, ownerHash, runId);
  const existing = await db
    .prepare(
      `SELECT ar.run_id, ar.idempotency_key, ar.owner_hash, ar.step_index, ar.status, ar.response_json
       FROM advance_requests ar
       INNER JOIN runs r ON r.id = ar.run_id AND r.owner_hash = ar.owner_hash
       WHERE ar.run_id = ? AND ar.idempotency_key = ? AND ar.owner_hash = ?`,
    )
    .bind(runId, idempotencyKey, ownerHash)
    .first<AdvanceRequestRow>();

  if (existing && (existing.status === "completed" || existing.status === "failed")) {
    const replay = parseJson<ServiceResponse | null>(existing.response_json, null);
    if (replay) return { ...replay, body: { ...replay.body, idempotentReplay: true } };
  }

  if (run.status === "completed") {
    return { status: 200, body: { ...(await getRunView(ownerHash, runId)), idempotentReplay: true } };
  }
  if (run.status === "cancelled") {
    throw new ApiError(409, "RUN_CANCELLED", "此實驗已取消。" );
  }
  if (run.status === "failed") {
    throw new ApiError(409, "RUN_FAILED", run.error_message ?? "此實驗已失敗。" );
  }

  const nowMs = Date.now();
  if (existing?.status === "started" && run.lease_expires_at && run.lease_expires_at > nowMs) {
    return {
      status: 202,
      body: {
        busy: true,
        retryAfterMs: Math.min(5_000, run.lease_expires_at - nowMs),
        ...(await getRunView(ownerHash, runId)),
      },
    };
  }

  const leaseToken = crypto.randomUUID();
  const leaseExpiresAt = nowMs + (executionModeForRun(run) === "local" ? 210_000 : 75_000);
  const lease = await db
    .prepare(
      `UPDATE runs
       SET lease_token = ?, lease_expires_at = ?, status = 'running', updated_at = CURRENT_TIMESTAMP, version = version + 1
       WHERE id = ? AND owner_hash = ? AND status IN ('queued','running')
         AND (lease_expires_at IS NULL OR lease_expires_at < ?)`,
    )
    .bind(leaseToken, leaseExpiresAt, runId, ownerHash, nowMs)
    .run();
  if ((lease.meta.changes ?? 0) !== 1) {
    return {
      status: 202,
      body: { busy: true, retryAfterMs: 1500, ...(await getRunView(ownerHash, runId)) },
    };
  }

  run = await ownedRun(db, ownerHash, runId);
  if (run.provider_attempts >= 25) {
    await failExhaustedRun(db, run, ownerHash, leaseToken);
    throw new ApiError(409, "ATTEMPT_LIMIT_REACHED", "模型供應商嘗試次數已達 25 次。" );
  }

  let stepRow: StepRow | null = null;
  if (existing?.step_index !== null && existing?.step_index !== undefined) {
    stepRow = await db
      .prepare("SELECT * FROM run_steps WHERE run_id = ? AND step_index = ?")
      .bind(runId, existing.step_index)
      .first<StepRow>();
    if (stepRow?.status === "completed") {
      const response: ServiceResponse = {
        status: 200,
        body: { ...(await getRunView(ownerHash, runId)), idempotentReplay: true },
      };
      await completeAdvanceRequests(db, runId, ownerHash, stepRow.step_index, response);
      await releaseLease(db, runId, ownerHash, leaseToken);
      return response;
    }
  }
  if (!stepRow) {
    stepRow = await db
      .prepare("SELECT * FROM run_steps WHERE run_id = ? AND status != 'completed' ORDER BY step_index LIMIT 1")
      .bind(runId)
      .first<StepRow>();
  }

  if (!stepRow) {
    await releaseLease(db, runId, ownerHash, leaseToken);
    await finalizeRun(ownerHash, runId);
    return { status: 200, body: await getRunView(ownerHash, runId) };
  }

  const attemptNumber = run.provider_attempts + 1;
  const attemptId = crypto.randomUUID();
  const step = WORKFLOW_STEPS[stepRow.step_index];
  if (!step || step.key !== stepRow.step_key) {
    await releaseLease(db, runId, ownerHash, leaseToken);
    throw new ApiError(500, "WORKFLOW_MISMATCH", "工作流程版本與已儲存步驟不一致。" );
  }

  const [evidenceResult, historyResult] = await Promise.all([
    db
      .prepare(
        `SELECT evidence_id, domain, claim, direction, uncertainty, available_at, is_valid
         FROM evidence_items WHERE run_id = ? AND available_at <= ? ORDER BY evidence_id`,
      )
      .bind(runId, run.analysis_date)
      .all<{
        evidence_id: string;
        domain: string;
        claim: string;
        direction: string;
        uncertainty: string;
        available_at: string;
        is_valid: number;
      }>(),
    db
      .prepare(
        `SELECT step_key, group_code, output_json FROM run_steps
         WHERE run_id = ? AND status = 'completed' AND step_index < ? ORDER BY step_index`,
      )
      .bind(runId, step.index)
      .all<{ step_key: string; group_code: string; output_json: string }>(),
  ]);
  const evidence: EvidenceForPrompt[] = evidenceResult.results.map((item) => ({
    evidenceId: item.evidence_id,
    domain: item.domain,
    claim: item.claim,
    direction: item.direction,
    uncertainty: item.uncertainty,
    availableAt: item.available_at,
    isValid: Boolean(item.is_valid),
  }));
  const priorOutputs = historyResult.results.map((item) => ({
    stepKey: item.step_key,
    groupCode: item.group_code,
    output: parseJson<StepOutput>(item.output_json, {
      decision: "NO_TRADE",
      confidence: 0,
      thesis: "輸出損毀",
      argument: "",
      evidenceIds: [],
      counterpoint: "",
    }),
  }));
  const prompt = buildStepPrompt({
    ticker: run.ticker,
    analysisDate: run.analysis_date,
    step,
    evidence,
    priorOutputs,
  });
  const requestHash = await sha256(prompt);
  const claimResults = await db.batch([
    db
      .prepare(
        `INSERT INTO advance_requests (run_id, idempotency_key, owner_hash, step_index, status)
         VALUES (?, ?, ?, ?, 'started')
         ON CONFLICT(run_id, idempotency_key) DO UPDATE
         SET step_index = COALESCE(advance_requests.step_index, excluded.step_index)
         WHERE advance_requests.owner_hash = excluded.owner_hash`,
      )
      .bind(runId, idempotencyKey, ownerHash, step.index),
    db
      .prepare(
        `UPDATE run_steps SET status = 'running', started_at = COALESCE(started_at, CURRENT_TIMESTAMP),
                error_message = NULL
         WHERE id = ? AND run_id = ? AND status IN ('pending','running')
           AND EXISTS (
             SELECT 1 FROM runs WHERE id = ? AND owner_hash = ? AND lease_token = ? AND status = 'running'
           )`,
      )
      .bind(stepRow.id, runId, runId, ownerHash, leaseToken),
    db
      .prepare(
        `INSERT INTO llm_attempts (
           id, run_id, step_id, attempt_number, provider, model, request_hash, status
         ) VALUES (?, ?, ?, ?, ?, ?, ?, 'started')`,
      )
      .bind(
        attemptId,
        runId,
        stepRow.id,
        attemptNumber,
        providerName(executionModeForRun(run)),
        run.model,
        requestHash,
      ),
    db
      .prepare(
        `UPDATE runs SET provider_attempts = provider_attempts + 1, updated_at = CURRENT_TIMESTAMP
         WHERE id = ? AND owner_hash = ? AND lease_token = ? AND status = 'running'`,
      )
      .bind(runId, ownerHash, leaseToken),
  ]);
  if ((claimResults[3].meta.changes ?? 0) !== 1) {
    throw new ApiError(409, "LEASE_LOST", "執行租約已失效，請重新整理後繼續。" );
  }

  let output: StepOutput;
  let rawResponse: unknown;
  let latencyMs = 0;
  let httpStatus = 200;
  try {
    const executionMode = executionModeForRun(run);
    if (executionMode === "demo") {
      const started = Date.now();
      output = await deterministicDemoOutput({
        ticker: run.ticker,
        analysisDate: run.analysis_date,
        step,
        evidenceIds: evidence.map((item) => item.evidenceId),
      });
      rawResponse = output;
      latencyMs = Date.now() - started;
    } else if (executionMode === "local") {
      const runtime = getRuntimeBindings();
      if (!isLocalRuntime(runtime)) {
        throw new ProviderError("本機模型模式已停用。", null, null, "LOCAL_MODE_DISABLED");
      }
      const result = await callOllama({
        baseUrl: runtime.OLLAMA_BASE_URL?.trim() || "http://127.0.0.1:11434",
        model: run.model,
        prompt,
      });
      output = result.output;
      rawResponse = result.raw;
      latencyMs = result.latencyMs;
      httpStatus = result.httpStatus;
    } else {
      const apiKey = getRuntimeBindings().GEMINI_API_KEY;
      if (!apiKey) throw new ProviderError("GEMINI_API_KEY disappeared during the run", null);
      const result = await callGemini({ apiKey, model: run.model, prompt });
      output = result.output;
      rawResponse = result.raw;
      latencyMs = result.latencyMs;
      httpStatus = result.httpStatus;
    }
  } catch (error) {
    return recordAttemptFailure({
      db,
      run,
      ownerHash,
      leaseToken,
      stepRow,
      attemptId,
      attemptNumber,
      idempotencyKey,
      error,
    });
  }

  const now = new Date().toISOString();
  const responseJson = JSON.stringify(output);
  const completionResults = await db.batch([
    db
      .prepare(
        `UPDATE llm_attempts
         SET status = 'completed', http_status = ?, latency_ms = ?, response_json = ?, completed_at = ?
         WHERE id = ? AND run_id = ?`,
      )
      .bind(httpStatus, latencyMs, JSON.stringify(rawResponse), now, attemptId, runId),
    db
      .prepare(
        `UPDATE run_steps
         SET status = 'completed', output_json = ?, completed_at = ?, error_message = NULL
         WHERE id = ? AND run_id = ?
           AND EXISTS (
             SELECT 1 FROM runs WHERE id = ? AND owner_hash = ? AND lease_token = ? AND status = 'running'
           )`,
      )
      .bind(responseJson, now, stepRow.id, runId, runId, ownerHash, leaseToken),
    db
      .prepare(
        `UPDATE runs
         SET current_step = ?, logical_calls = logical_calls + 1, lease_token = NULL,
             lease_expires_at = NULL, updated_at = ?, version = version + 1
         WHERE id = ? AND owner_hash = ? AND lease_token = ? AND status = 'running'`,
      )
      .bind(step.index + 1, now, runId, ownerHash, leaseToken),
    db
      .prepare(
        `INSERT INTO events (id, run_id, sequence, kind, message, payload_json, created_at)
         SELECT ?, ?, ?, 'step_completed', ?, ?, ?
         WHERE EXISTS (
           SELECT 1 FROM run_steps WHERE id = ? AND run_id = ? AND status = 'completed'
         )`,
      )
      .bind(
        crypto.randomUUID(),
        runId,
        attemptNumber,
        `${step.label}已完成。`,
        JSON.stringify({ stepIndex: step.index, stepKey: step.key, decision: output.decision }),
        now,
        stepRow.id,
        runId,
      ),
  ]);
  if ((completionResults[2].meta.changes ?? 0) !== 1) {
    throw new ApiError(409, "RUN_CHANGED", "實驗狀態已變更，這次結果未寫入。" );
  }

  if (step.index === WORKFLOW_STEPS.length - 1) {
    await finalizeRun(ownerHash, runId);
  }

  const response: ServiceResponse = { status: 200, body: await getRunView(ownerHash, runId) };
  await completeAdvanceRequests(db, runId, ownerHash, step.index, response);
  return response;
}

export async function cancelRun(ownerHash: string, runId: string): Promise<Record<string, unknown>> {
  await ensureDatabaseSchema();
  const db = getD1();
  const run = await ownedRun(db, ownerHash, runId);
  if (run.status === "completed") {
    throw new ApiError(409, "RUN_ALREADY_COMPLETED", "已完成的實驗無法取消。" );
  }
  if (run.status === "cancelled") return getRunView(ownerHash, runId);

  const now = new Date().toISOString();
  await db.batch([
    db
      .prepare(
        `UPDATE runs SET status = 'cancelled', cancelled_at = ?, updated_at = ?,
                lease_token = NULL, lease_expires_at = NULL, version = version + 1
         WHERE id = ? AND owner_hash = ? AND status IN ('queued','running','failed')`,
      )
      .bind(now, now, runId, ownerHash),
    db
      .prepare(
        `INSERT OR IGNORE INTO events (id, run_id, sequence, kind, message, payload_json, created_at)
         VALUES (?, ?, 99, 'run_cancelled', '實驗已由使用者取消。', '{}', ?)`,
      )
      .bind(crypto.randomUUID(), runId, now),
  ]);
  return getRunView(ownerHash, runId);
}

export async function downloadArtifact(
  ownerHash: string,
  runId: string,
  artifactId: string,
): Promise<Response> {
  await ensureDatabaseSchema();
  const db = getD1();
  const artifact = await db
    .prepare(
      `SELECT a.id, a.r2_key, a.file_name, a.content_type, a.byte_size, a.checksum
       FROM artifacts a
       INNER JOIN runs r ON r.id = a.run_id
       WHERE a.id = ? AND a.run_id = ? AND a.owner_hash = ? AND r.owner_hash = ? AND a.status = 'ready'`,
    )
    .bind(artifactId, runId, ownerHash, ownerHash)
    .first<{
      id: string;
      r2_key: string;
      file_name: string;
      content_type: string;
      byte_size: number;
      checksum: string;
    }>();
  if (!artifact) throw new ApiError(404, "ARTIFACT_NOT_FOUND", "找不到此匯出檔案。" );

  const object = await getArtifactsBucket().get(artifact.r2_key);
  if (!object) throw new ApiError(410, "ARTIFACT_MISSING", "匯出檔案已不存在。" );
  const safeName = artifact.file_name.replace(/[^A-Za-z0-9._-]/g, "_");
  return new Response(object.body, {
    headers: {
      "Cache-Control": "private, no-store",
      "Content-Type": artifact.content_type,
      "Content-Length": String(artifact.byte_size),
      "Content-Disposition": `attachment; filename="${safeName}"`,
      "X-Content-Type-Options": "nosniff",
      ETag: object.httpEtag,
      "X-Checksum-SHA256": artifact.checksum,
    },
  });
}

async function ownedRun(db: D1Database, ownerHash: string, runId: string): Promise<RunRow> {
  const run = await db
    .prepare("SELECT * FROM runs WHERE id = ? AND owner_hash = ?")
    .bind(runId, ownerHash)
    .first<RunRow>();
  if (!run) throw new ApiError(404, "RUN_NOT_FOUND", "找不到此實驗。" );
  return run;
}

async function releaseLease(
  db: D1Database,
  runId: string,
  ownerHash: string,
  leaseToken: string,
): Promise<void> {
  await db
    .prepare(
      `UPDATE runs SET lease_token = NULL, lease_expires_at = NULL, updated_at = CURRENT_TIMESTAMP
       WHERE id = ? AND owner_hash = ? AND lease_token = ?`,
    )
    .bind(runId, ownerHash, leaseToken)
    .run();
}

async function failExhaustedRun(
  db: D1Database,
  run: RunRow,
  ownerHash: string,
  leaseToken: string,
): Promise<void> {
  await db
    .prepare(
      `UPDATE runs SET status = 'failed', error_message = ?, lease_token = NULL,
              lease_expires_at = NULL, updated_at = CURRENT_TIMESTAMP
       WHERE id = ? AND owner_hash = ? AND lease_token = ?`,
    )
    .bind("模型供應商嘗試次數已達 25 次。", run.id, ownerHash, leaseToken)
    .run();
}

async function recordAttemptFailure(input: {
  db: D1Database;
  run: RunRow;
  ownerHash: string;
  leaseToken: string;
  stepRow: StepRow;
  attemptId: string;
  attemptNumber: number;
  idempotencyKey: string;
  error: unknown;
}): Promise<ServiceResponse> {
  const { db, run, ownerHash, leaseToken, stepRow, attemptId, attemptNumber, error } = input;
  const providerError = error instanceof ProviderError ? error : null;
  const message = error instanceof Error ? error.message : "Provider request failed";
  const publicMessage = providerFailureMessage(providerError?.code);
  const terminal = attemptNumber >= 25;
  const now = new Date().toISOString();
  await db.batch([
    db
      .prepare(
        `UPDATE llm_attempts SET status = 'failed', http_status = ?, error_message = ?,
                response_json = ?, completed_at = ? WHERE id = ? AND run_id = ?`,
      )
      .bind(providerError?.httpStatus ?? null, message, providerError?.responseExcerpt ?? null, now, attemptId, run.id),
    db
      .prepare(
        `UPDATE run_steps SET status = 'pending', error_message = ?
         WHERE id = ? AND run_id = ?
           AND EXISTS (SELECT 1 FROM runs WHERE id = ? AND owner_hash = ? AND lease_token = ?)`,
      )
      .bind(message.slice(0, 1000), stepRow.id, run.id, run.id, ownerHash, leaseToken),
    db
      .prepare(
        `UPDATE runs SET status = ?, error_message = ?, lease_token = NULL, lease_expires_at = NULL,
                updated_at = ?, version = version + 1
         WHERE id = ? AND owner_hash = ? AND lease_token = ?`,
      )
      .bind(terminal ? "failed" : "queued", terminal ? message.slice(0, 1000) : null, now, run.id, ownerHash, leaseToken),
    db
      .prepare(
        `INSERT OR IGNORE INTO events (id, run_id, sequence, kind, message, payload_json, created_at)
         VALUES (?, ?, ?, 'step_failed', ?, ?, ?)`,
      )
      .bind(
        crypto.randomUUID(),
        run.id,
        attemptNumber,
        `${WORKFLOW_STEPS[stepRow.step_index]?.label ?? "步驟"}暫時失敗。`,
        JSON.stringify({ stepIndex: stepRow.step_index, retriable: !terminal, providerCode: providerError?.code }),
        now,
      ),
  ]);

  const response: ServiceResponse = {
    status: terminal ? 409 : 502,
    body: {
      error: {
        code: terminal ? "ATTEMPT_LIMIT_REACHED" : "PROVIDER_STEP_FAILED",
        message: terminal ? "模型嘗試次數已達上限。" : publicMessage,
        retriable: !terminal,
        attemptNumber,
        providerCode: providerError?.code ?? "PROVIDER_ERROR",
      },
      ...(await getRunView(ownerHash, run.id)),
    },
  };
  await db
    .prepare(
      `UPDATE advance_requests SET status = 'failed', response_json = ?, completed_at = CURRENT_TIMESTAMP
       WHERE run_id = ? AND idempotency_key = ? AND owner_hash = ?`,
    )
    .bind(JSON.stringify(response), run.id, input.idempotencyKey, ownerHash)
    .run();
  return response;
}

function executionModeForRun(run: RunRow): ExecutionMode {
  if (run.demo_mode) return "demo";
  const stored = parseJson<{ executionMode?: string }>(run.input_json, {});
  return stored.executionMode === "local" ? "local" : "live";
}

function providerName(mode: ExecutionMode): "deterministic-demo" | "ollama-local" | "gemini" {
  return mode === "demo" ? "deterministic-demo" : mode === "local" ? "ollama-local" : "gemini";
}

function isLocalRuntime(runtime: ReturnType<typeof getRuntimeBindings>): boolean {
  return runtime.LOCAL_MODE === "true" && runtime.APP_ENV === "development";
}

function providerFailureMessage(code?: string): string {
  switch (code) {
    case "OLLAMA_UNREACHABLE":
      return "無法連上本機 Ollama；請啟動 Ollama 後按下重試。";
    case "OLLAMA_MODEL_MISSING":
      return "找不到指定的本機模型；請確認模型仍已安裝。";
    case "LOCAL_MODEL_TIMEOUT":
      return "本機模型推論逾時；進度已保存，可重新連線並重試。";
    case "LOCAL_MODEL_BAD_JSON":
    case "LOCAL_MODEL_EMPTY_RESPONSE":
      return "本機模型輸出格式不符；進度已保存，可再次重試。";
    case "LOCAL_MODE_DISABLED":
      return "本機模式已停用，請改由本機開發伺服器開啟。";
    default:
      return "此步驟執行失敗，進度已保存，可使用新的要求重試。";
  }
}

async function completeAdvanceRequests(
  db: D1Database,
  runId: string,
  ownerHash: string,
  stepIndex: number,
  response: ServiceResponse,
): Promise<void> {
  await db
    .prepare(
      `UPDATE advance_requests SET status = 'completed', response_json = ?, completed_at = CURRENT_TIMESTAMP
       WHERE run_id = ? AND owner_hash = ? AND step_index = ? AND status = 'started'`,
    )
    .bind(JSON.stringify(response), runId, ownerHash, stepIndex)
    .run();
}

async function finalizeRun(ownerHash: string, runId: string): Promise<void> {
  const db = getD1();
  const run = await ownedRun(db, ownerHash, runId);
  if (run.status === "completed") return;
  if (run.status === "cancelled" || run.status === "failed") return;
  const stepResult = await db
    .prepare("SELECT * FROM run_steps WHERE run_id = ? AND status = 'completed' ORDER BY step_index")
    .bind(runId)
    .all<StepRow>();
  if (stepResult.results.length !== WORKFLOW_STEPS.length) return;

  const evidenceResult = await db
    .prepare("SELECT * FROM evidence_items WHERE run_id = ? ORDER BY evidence_id")
    .bind(runId)
    .all<EvidenceRow>();
  const decisions = deriveGroupDecisions(stepResult.results);
  const now = new Date().toISOString();
  const resultStatements = (Object.entries(decisions) as Array<[GroupCode, StepOutput]>).map(
    ([groupCode, output]) => {
      const gated = applyGatekeeper(output, evidenceResult.results);
      const backtest = createSyntheticBacktest(
        run.ticker,
        run.analysis_date,
        gated.finalDecision,
        output.confidence,
        now,
      );
      return db
        .prepare(
          `INSERT INTO results (
             id, run_id, group_code, raw_decision, final_decision, confidence,
             thesis, evidence_ids_json, gatekeeper_json, backtest_json, created_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(run_id, group_code) DO UPDATE SET
             raw_decision = excluded.raw_decision,
             final_decision = excluded.final_decision,
             confidence = excluded.confidence,
             thesis = excluded.thesis,
             evidence_ids_json = excluded.evidence_ids_json,
             gatekeeper_json = excluded.gatekeeper_json`,
        )
        .bind(
          crypto.randomUUID(),
          runId,
          groupCode,
          output.decision,
          gated.finalDecision,
          Math.round(output.confidence * 1000),
          output.thesis,
          JSON.stringify(output.evidenceIds),
          JSON.stringify(gated),
          JSON.stringify(backtest),
          now,
        );
    },
  );
  await db.batch([
    ...resultStatements,
    db
      .prepare(
        `UPDATE runs SET status = 'completed', decision_locked_at = ?, completed_at = ?,
                updated_at = ?, lease_token = NULL, lease_expires_at = NULL, version = version + 1
         WHERE id = ? AND owner_hash = ? AND status = 'running'`,
      )
      .bind(now, now, now, runId, ownerHash),
    db
      .prepare(
        `INSERT OR IGNORE INTO events (id, run_id, sequence, kind, message, payload_json, created_at)
         VALUES (?, ?, 100, 'run_completed', '四組決策已鎖定，實驗完成。', ?, ?)`,
      )
      .bind(crypto.randomUUID(), runId, JSON.stringify({ logicalCalls: 20 }), now),
  ]);

  // Decisions remain durable even if blob storage is temporarily unavailable.
  // The separate export action can repair partial exports without model calls.
  try {
    await repairRunArtifacts(ownerHash, runId);
  } catch (error) {
    console.error("Run decisions completed; exports need retry", runId, error);
  }
}

export async function repairRunArtifacts(ownerHash: string, runId: string): Promise<Record<string, unknown>> {
  await ensureDatabaseSchema();
  const db = getD1();
  const run = await ownedRun(db, ownerHash, runId);
  if (run.status !== "completed") {
    throw new ApiError(409, "RUN_NOT_COMPLETED", "請先完成四組決策，再產生匯出檔。");
  }
  const token = crypto.randomUUID();
  const now = Date.now();
  const lease = await db.prepare(
    `UPDATE runs SET lease_token = ?, lease_expires_at = ?
     WHERE id = ? AND owner_hash = ? AND status = 'completed'
       AND (lease_expires_at IS NULL OR lease_expires_at < ?)`,
  ).bind(token, now + 120_000, runId, ownerHash, now).run();
  if (lease.meta.changes !== 1) throw new ApiError(409, "EXPORT_BUSY", "匯出檔正在產生，請稍後重新整理。");
  try {
    await createRunArtifact(ownerHash, runId);
    return await getRunView(ownerHash, runId);
  } finally {
    await releaseLease(db, runId, ownerHash, token);
  }
}

function createSyntheticBacktest(
  ticker: string,
  analysisDate: string,
  decision: Decision,
  confidence: number,
  lockedAt: string,
) {
  const entry = stableNumber(`${ticker}|${analysisDate}|entry`, 40, 240);
  const futurePrices = [1, 30, 60, 90, 91].map((days) => ({
    date: addUtcDays(analysisDate, days),
    close: stableNumber(`${ticker}|${analysisDate}|future|${days}`, entry * 0.72, entry * 1.32),
  }));
  const action = decision === "BUY" ? "Buy" : decision === "SELL" ? "Sell" : decision === "NO_TRADE" ? "NoTrade" : "Hold";
  return runBacktest({
    analysisDate,
    decision: {
      action,
      confidence,
      rationale: "Synthetic demo outcome; not real market performance.",
      locked: true,
      lockedAt,
    },
    futurePrices,
    transactionCostBps: 10,
  });
}

function addUtcDays(isoDate: string, days: number): string {
  const date = new Date(`${isoDate}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

function deriveGroupDecisions(steps: StepRow[]): Record<GroupCode, StepOutput> {
  const outputAt = (index: number): StepOutput => {
    const value = parseJson<StepOutput | null>(steps.find((item) => item.step_index === index)?.output_json ?? null, null);
    if (!value) throw new Error(`Missing output for workflow step ${index}`);
    return value;
  };
  const bSamples = [1, 2, 3, 4, 5].map(outputAt);
  const counts = new Map<Decision, number>();
  for (const item of bSamples) counts.set(item.decision, (counts.get(item.decision) ?? 0) + 1);
  const maxCount = Math.max(...counts.values());
  const leaders = new Set(
    [...counts.entries()].filter(([, count]) => count === maxCount).map(([decision]) => decision),
  );
  const bWinner = [...bSamples]
    .filter((item) => leaders.has(item.decision))
    .sort((left, right) => right.confidence - left.confidence)[0];

  return { A: outputAt(0), B: bWinner, C: outputAt(12), D: outputAt(19) };
}

function applyGatekeeper(output: StepOutput, evidence: EvidenceRow[]) {
  const valid = evidence.filter(
    (item) => Boolean(item.is_valid) && item.available_at <= item.analysis_date,
  );
  const evidencePassRate = evidence.length ? valid.length / evidence.length : 0;
  const distinctDomains = new Set(valid.map((item) => item.domain)).size;
  const allowedIds = new Set(valid.map((item) => item.evidence_id));
  const invalidCitations = output.evidenceIds.filter((id) => !allowedIds.has(id));
  const reasons: string[] = [];
  let finalDecision = output.decision;
  if (evidencePassRate < 0.8) reasons.push("證據通過率低於 80%");
  if (distinctDomains < 3) reasons.push("有效證據少於三個研究領域");
  if (invalidCitations.length > 0) reasons.push("輸出引用了無效 evidenceId");
  if (reasons.length > 0) finalDecision = "NO_TRADE";
  else if ((finalDecision === "BUY" || finalDecision === "SELL") && output.confidence < 0.53) {
    finalDecision = "HOLD";
    reasons.push("方向性決策信心低於 0.53");
  }
  return {
    passed: reasons.length === 0,
    finalDecision,
    evidencePassRate: Math.round(evidencePassRate * 1000) / 1000,
    distinctDomains,
    invalidCitations,
    reasons,
    volatilityGate: "not_available",
    historyGate: "not_enough_approved_cases",
  };
}

async function createRunArtifact(ownerHash: string, runId: string): Promise<void> {
  const db = getD1();
  const view = await getRunView(ownerHash, runId);
  const run = view.run as Record<string, unknown>;
  const resultsView = (view.results ?? []) as Array<Record<string, unknown>>;
  const evidenceView = (view.evidence ?? []) as Array<Record<string, unknown>>;
  const stepsView = (view.steps ?? []) as Array<Record<string, unknown>>;
  const eventsView = (view.events ?? []) as Array<Record<string, unknown>>;
  const ticker = String(run.ticker ?? "UNKNOWN");
  const analysisDate = String(run.analysisDate ?? "UNKNOWN");
  const resultLines = resultsView.map((item) =>
    `- Group ${item.groupCode}: ${item.finalDecision} (${Math.round(Number(item.confidence ?? 0) * 100)}%) — ${item.thesis}`,
  );
  const artifactsToWrite = [
    {
      kind: "run-json",
      fileName: "run.json",
      contentType: "application/json; charset=utf-8",
      body: JSON.stringify(view, null, 2),
    },
    {
      kind: "evidence-registry",
      fileName: "evidence_registry.json",
      contentType: "application/json; charset=utf-8",
      body: JSON.stringify(evidenceView, null, 2),
    },
    {
      kind: "transcript",
      fileName: "transcript.json",
      contentType: "application/json; charset=utf-8",
      body: JSON.stringify(stepsView, null, 2),
    },
    {
      kind: "state-trace",
      fileName: "state_trace.json",
      contentType: "application/json; charset=utf-8",
      body: JSON.stringify({ run, events: eventsView, steps: stepsView }, null, 2),
    },
    {
      kind: "cases-csv",
      fileName: "cases.csv",
      contentType: "text/csv; charset=utf-8",
      body: [
        "ticker,analysis_date,group,raw_decision,final_decision,confidence,thesis",
        ...resultsView.map((item) =>
          [ticker, analysisDate, item.groupCode, item.rawDecision, item.finalDecision, item.confidence, item.thesis]
            .map(csvCell)
            .join(","),
        ),
      ].join("\n"),
    },
    {
      kind: "summary-csv",
      fileName: "summary.csv",
      contentType: "text/csv; charset=utf-8",
      body: [
        "run_id,ticker,analysis_date,status,logical_calls,provider_mode,evidence_count",
        [run.id, ticker, analysisDate, run.status, run.logicalCalls, run.providerMode, evidenceView.length]
          .map(csvCell)
          .join(","),
      ].join("\n"),
    },
    {
      kind: "neutral-report",
      fileName: "neutral_report.md",
      contentType: "text/markdown; charset=utf-8",
      body: `# ${ticker} 中立研究報告\n\n- 分析日期：${analysisDate}\n- 資料版本：deterministic-demo-v1（合成證據與價格，非真實市場資料）\n- 模型：${run.model}\n- 證據數量：${evidenceView.length}\n- 邏輯模型呼叫：${run.logicalCalls}\n\n## 四組決策\n\n${resultLines.join("\n")}\n\n> 本報告為 AI 研究實驗，不構成投資建議。\n`,
    },
    {
      kind: "run-summary",
      fileName: "run_summary.md",
      contentType: "text/markdown; charset=utf-8",
      body: `# 立場交換研究室執行摘要\n\n資料為合成示範快照與價格，不能用來證明真實市場績效。\n\n實驗 ${run.id} 已完成固定 A/B/C/D = 1/5/7/7，共 20 個邏輯呼叫。\n\n${resultLines.join("\n")}\n`,
    },
  ] as const;

  for (const artifact of artifactsToWrite) {
    const existing = await db
      .prepare("SELECT id FROM artifacts WHERE run_id = ? AND owner_hash = ? AND kind = ?")
      .bind(runId, ownerHash, artifact.kind)
      .first<{ id: string }>();
    if (existing) continue;
    const bytes = new TextEncoder().encode(artifact.body);
    const checksum = await sha256(bytes);
    const artifactId = crypto.randomUUID();
    const r2Key = `runs/${ownerHash}/${runId}/${artifact.fileName}`;
    await getArtifactsBucket().put(r2Key, bytes, {
      httpMetadata: { contentType: artifact.contentType },
      customMetadata: { runId, artifactId, checksum },
    });
    await db
      .prepare(
        `INSERT INTO artifacts (
           id, run_id, owner_hash, kind, r2_key, file_name, content_type,
           byte_size, checksum, status
         ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'ready')`,
      )
      .bind(
        artifactId,
        runId,
        ownerHash,
        artifact.kind,
        r2Key,
        artifact.fileName,
        artifact.contentType,
        bytes.byteLength,
        checksum,
      )
      .run();
  }
}

function csvCell(value: unknown): string {
  const text = value == null ? "" : String(value);
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

async function sha256(value: string | Uint8Array): Promise<string> {
  const bytes = typeof value === "string" ? new TextEncoder().encode(value) : value;
  const digest = await crypto.subtle.digest("SHA-256", Uint8Array.from(bytes).buffer);
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

function taipeiDay(date: Date): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Taipei",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(date);
  const get = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((part) => part.type === type)?.value ?? "";
  return `${get("year")}-${get("month")}-${get("day")}`;
}
