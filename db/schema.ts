import { sql } from "drizzle-orm";
import {
  index,
  integer,
  primaryKey,
  sqliteTable,
  text,
  uniqueIndex,
} from "drizzle-orm/sqlite-core";

export const runs = sqliteTable(
  "runs",
  {
    id: text("id").primaryKey(),
    ownerHash: text("owner_hash").notNull(),
    ticker: text("ticker").notNull(),
    analysisDate: text("analysis_date").notNull(),
    experimentMode: text("experiment_mode").notNull().default("full"),
    model: text("model").notNull(),
    status: text("status").notNull().default("queued"),
    currentStep: integer("current_step").notNull().default(0),
    totalSteps: integer("total_steps").notNull().default(20),
    logicalCalls: integer("logical_calls").notNull().default(0),
    providerAttempts: integer("provider_attempts").notNull().default(0),
    version: integer("version").notNull().default(0),
    demoMode: integer("demo_mode", { mode: "boolean" }).notNull().default(false),
    published: integer("published", { mode: "boolean" }).notNull().default(false),
    inputJson: text("input_json").notNull().default("{}"),
    leaseToken: text("lease_token"),
    leaseExpiresAt: integer("lease_expires_at"),
    decisionLockedAt: text("decision_locked_at"),
    errorMessage: text("error_message"),
    createdAt: text("created_at").notNull().default(sql`CURRENT_TIMESTAMP`),
    updatedAt: text("updated_at").notNull().default(sql`CURRENT_TIMESTAMP`),
    completedAt: text("completed_at"),
    cancelledAt: text("cancelled_at"),
  },
  (table) => [
    index("runs_owner_created_idx").on(table.ownerHash, table.createdAt),
    index("runs_owner_status_idx").on(table.ownerHash, table.status),
    index("runs_public_idx").on(table.published, table.completedAt),
  ],
);

export const runSteps = sqliteTable(
  "run_steps",
  {
    id: text("id").primaryKey(),
    runId: text("run_id")
      .notNull()
      .references(() => runs.id, { onDelete: "cascade" }),
    stepIndex: integer("step_index").notNull(),
    stepKey: text("step_key").notNull(),
    groupCode: text("group_code").notNull(),
    phase: text("phase").notNull(),
    round: integer("round"),
    agentId: text("agent_id"),
    stance: text("stance"),
    status: text("status").notNull().default("pending"),
    inputJson: text("input_json").notNull().default("{}"),
    outputJson: text("output_json"),
    startedAt: text("started_at"),
    completedAt: text("completed_at"),
    errorMessage: text("error_message"),
  },
  (table) => [
    uniqueIndex("run_steps_run_index_uq").on(table.runId, table.stepIndex),
    uniqueIndex("run_steps_run_key_uq").on(table.runId, table.stepKey),
    index("run_steps_run_status_idx").on(table.runId, table.status),
  ],
);

export const advanceRequests = sqliteTable(
  "advance_requests",
  {
    runId: text("run_id")
      .notNull()
      .references(() => runs.id, { onDelete: "cascade" }),
    idempotencyKey: text("idempotency_key").notNull(),
    ownerHash: text("owner_hash").notNull(),
    stepIndex: integer("step_index"),
    status: text("status").notNull().default("started"),
    responseJson: text("response_json"),
    createdAt: text("created_at").notNull().default(sql`CURRENT_TIMESTAMP`),
    completedAt: text("completed_at"),
  },
  (table) => [
    primaryKey({ columns: [table.runId, table.idempotencyKey] }),
    index("advance_requests_step_idx").on(table.runId, table.stepIndex),
  ],
);

export const llmAttempts = sqliteTable(
  "llm_attempts",
  {
    id: text("id").primaryKey(),
    runId: text("run_id")
      .notNull()
      .references(() => runs.id, { onDelete: "cascade" }),
    stepId: text("step_id")
      .notNull()
      .references(() => runSteps.id, { onDelete: "cascade" }),
    attemptNumber: integer("attempt_number").notNull(),
    provider: text("provider").notNull(),
    model: text("model").notNull(),
    requestHash: text("request_hash").notNull(),
    status: text("status").notNull(),
    httpStatus: integer("http_status"),
    latencyMs: integer("latency_ms"),
    responseJson: text("response_json"),
    errorMessage: text("error_message"),
    createdAt: text("created_at").notNull().default(sql`CURRENT_TIMESTAMP`),
    completedAt: text("completed_at"),
  },
  (table) => [
    uniqueIndex("llm_attempts_run_number_uq").on(table.runId, table.attemptNumber),
    index("llm_attempts_step_idx").on(table.stepId, table.createdAt),
  ],
);

export const events = sqliteTable(
  "events",
  {
    id: text("id").primaryKey(),
    runId: text("run_id")
      .notNull()
      .references(() => runs.id, { onDelete: "cascade" }),
    sequence: integer("sequence").notNull(),
    kind: text("kind").notNull(),
    message: text("message").notNull(),
    payloadJson: text("payload_json").notNull().default("{}"),
    createdAt: text("created_at").notNull().default(sql`CURRENT_TIMESTAMP`),
  },
  (table) => [
    uniqueIndex("events_run_sequence_uq").on(table.runId, table.sequence),
    index("events_run_created_idx").on(table.runId, table.createdAt),
  ],
);

export const evidenceItems = sqliteTable(
  "evidence_items",
  {
    id: text("id").primaryKey(),
    runId: text("run_id")
      .notNull()
      .references(() => runs.id, { onDelete: "cascade" }),
    evidenceId: text("evidence_id").notNull(),
    domain: text("domain").notNull(),
    source: text("source").notNull(),
    sourceUrl: text("source_url"),
    publishedAt: text("published_at").notNull(),
    availableAt: text("available_at").notNull(),
    analysisDate: text("analysis_date").notNull(),
    claim: text("claim").notNull(),
    value: text("value"),
    direction: text("direction").notNull(),
    uncertainty: text("uncertainty").notNull(),
    checksum: text("checksum").notNull(),
    isValid: integer("is_valid", { mode: "boolean" }).notNull().default(true),
    createdAt: text("created_at").notNull().default(sql`CURRENT_TIMESTAMP`),
  },
  (table) => [
    uniqueIndex("evidence_run_evidence_uq").on(table.runId, table.evidenceId),
    index("evidence_run_domain_idx").on(table.runId, table.domain),
  ],
);

export const results = sqliteTable(
  "results",
  {
    id: text("id").primaryKey(),
    runId: text("run_id")
      .notNull()
      .references(() => runs.id, { onDelete: "cascade" }),
    groupCode: text("group_code").notNull(),
    rawDecision: text("raw_decision").notNull(),
    finalDecision: text("final_decision").notNull(),
    confidence: integer("confidence").notNull(),
    thesis: text("thesis").notNull(),
    evidenceIdsJson: text("evidence_ids_json").notNull().default("[]"),
    gatekeeperJson: text("gatekeeper_json").notNull().default("{}"),
    backtestJson: text("backtest_json"),
    createdAt: text("created_at").notNull().default(sql`CURRENT_TIMESTAMP`),
  },
  (table) => [
    uniqueIndex("results_run_group_uq").on(table.runId, table.groupCode),
    index("results_run_idx").on(table.runId),
  ],
);

export const artifacts = sqliteTable(
  "artifacts",
  {
    id: text("id").primaryKey(),
    runId: text("run_id")
      .notNull()
      .references(() => runs.id, { onDelete: "cascade" }),
    ownerHash: text("owner_hash").notNull(),
    kind: text("kind").notNull(),
    r2Key: text("r2_key").notNull(),
    fileName: text("file_name").notNull(),
    contentType: text("content_type").notNull(),
    byteSize: integer("byte_size").notNull(),
    checksum: text("checksum").notNull(),
    status: text("status").notNull().default("ready"),
    createdAt: text("created_at").notNull().default(sql`CURRENT_TIMESTAMP`),
  },
  (table) => [
    uniqueIndex("artifacts_r2_key_uq").on(table.r2Key),
    index("artifacts_run_owner_idx").on(table.runId, table.ownerHash),
  ],
);

export const quotas = sqliteTable(
  "quotas",
  {
    scope: text("scope").notNull(),
    quotaKey: text("quota_key").notNull(),
    windowStart: text("window_start").notNull(),
    count: integer("count").notNull().default(0),
    updatedAt: text("updated_at").notNull().default(sql`CURRENT_TIMESTAMP`),
  },
  (table) => [
    primaryKey({ columns: [table.scope, table.quotaKey, table.windowStart] }),
    index("quotas_window_idx").on(table.windowStart, table.scope),
  ],
);

export type RunRecord = typeof runs.$inferSelect;
export type RunStepRecord = typeof runSteps.$inferSelect;
