import { env } from "cloudflare:workers";
import { drizzle } from "drizzle-orm/d1";
import * as schema from "./schema";

export type RuntimeBindings = {
  DB?: D1Database;
  ARTIFACTS?: R2Bucket;
  GEMINI_API_KEY?: string;
  GEMINI_MODEL?: string;
  OLLAMA_BASE_URL?: string;
  OLLAMA_MODEL?: string;
  LOCAL_MODE?: string;
  LOCAL_OWNER_EMAIL?: string;
  LOCAL_OWNER_NAME?: string;
  APP_ENV?: string;
  OWNER_KEY_PEPPER?: string;
};

const bindings = env as unknown as RuntimeBindings;
let schemaReady: Promise<void> | undefined;

export function getD1(): D1Database {
  if (!bindings.DB) {
    throw new Error("Cloudflare D1 binding `DB` is unavailable.");
  }
  return bindings.DB;
}

export function getArtifactsBucket(): R2Bucket {
  if (!bindings.ARTIFACTS) {
    throw new Error("Cloudflare R2 binding `ARTIFACTS` is unavailable.");
  }
  return bindings.ARTIFACTS;
}

export function getRuntimeBindings(): RuntimeBindings {
  return bindings;
}

export function getDb() {
  return drizzle(getD1(), { schema });
}

/**
 * The hosted deployment applies Drizzle migrations. This idempotent initializer
 * also makes local Miniflare and preview deployments usable before the first
 * control-plane migration. Every prepared statement contains exactly one SQL
 * statement, as required by D1.
 */
export async function ensureDatabaseSchema(): Promise<void> {
  if (!schemaReady) {
    schemaReady = initializeSchema().catch((error) => {
      schemaReady = undefined;
      throw error;
    });
  }
  return schemaReady;
}

async function initializeSchema(): Promise<void> {
  const db = getD1();
  const statements = SCHEMA_STATEMENTS.map((statement) => db.prepare(statement));
  await db.batch(statements);
}

const SCHEMA_STATEMENTS = [
  `CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY NOT NULL,
    owner_hash TEXT NOT NULL,
    ticker TEXT NOT NULL,
    analysis_date TEXT NOT NULL,
    experiment_mode TEXT NOT NULL DEFAULT 'full',
    model TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued' CHECK(status IN ('queued','running','completed','cancelled','failed')),
    current_step INTEGER NOT NULL DEFAULT 0,
    total_steps INTEGER NOT NULL DEFAULT 20,
    logical_calls INTEGER NOT NULL DEFAULT 0,
    provider_attempts INTEGER NOT NULL DEFAULT 0,
    version INTEGER NOT NULL DEFAULT 0,
    demo_mode INTEGER NOT NULL DEFAULT 0,
    published INTEGER NOT NULL DEFAULT 0,
    input_json TEXT NOT NULL DEFAULT '{}',
    lease_token TEXT,
    lease_expires_at INTEGER,
    decision_locked_at TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT,
    cancelled_at TEXT
  )`,
  "CREATE INDEX IF NOT EXISTS runs_owner_created_idx ON runs (owner_hash, created_at)",
  "CREATE INDEX IF NOT EXISTS runs_owner_status_idx ON runs (owner_hash, status)",
  "CREATE INDEX IF NOT EXISTS runs_public_idx ON runs (published, completed_at)",
  "CREATE UNIQUE INDEX IF NOT EXISTS runs_one_active_owner_uq ON runs (owner_hash) WHERE status IN ('queued','running')",
  `CREATE TABLE IF NOT EXISTS run_steps (
    id TEXT PRIMARY KEY NOT NULL,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    step_index INTEGER NOT NULL,
    step_key TEXT NOT NULL,
    group_code TEXT NOT NULL,
    phase TEXT NOT NULL,
    round INTEGER,
    agent_id TEXT,
    stance TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','running','completed')),
    input_json TEXT NOT NULL DEFAULT '{}',
    output_json TEXT,
    started_at TEXT,
    completed_at TEXT,
    error_message TEXT
  )`,
  "CREATE UNIQUE INDEX IF NOT EXISTS run_steps_run_index_uq ON run_steps (run_id, step_index)",
  "CREATE UNIQUE INDEX IF NOT EXISTS run_steps_run_key_uq ON run_steps (run_id, step_key)",
  "CREATE INDEX IF NOT EXISTS run_steps_run_status_idx ON run_steps (run_id, status)",
  `CREATE TABLE IF NOT EXISTS advance_requests (
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    idempotency_key TEXT NOT NULL,
    owner_hash TEXT NOT NULL,
    step_index INTEGER,
    status TEXT NOT NULL DEFAULT 'started' CHECK(status IN ('started','completed','failed')),
    response_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT,
    PRIMARY KEY (run_id, idempotency_key)
  )`,
  "CREATE INDEX IF NOT EXISTS advance_requests_step_idx ON advance_requests (run_id, step_index)",
  `CREATE TABLE IF NOT EXISTS llm_attempts (
    id TEXT PRIMARY KEY NOT NULL,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    step_id TEXT NOT NULL REFERENCES run_steps(id) ON DELETE CASCADE,
    attempt_number INTEGER NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('started','completed','failed')),
    http_status INTEGER,
    latency_ms INTEGER,
    response_json TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT
  )`,
  "CREATE UNIQUE INDEX IF NOT EXISTS llm_attempts_run_number_uq ON llm_attempts (run_id, attempt_number)",
  "CREATE INDEX IF NOT EXISTS llm_attempts_step_idx ON llm_attempts (step_id, created_at)",
  `CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY NOT NULL,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL,
    kind TEXT NOT NULL,
    message TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
  )`,
  "CREATE UNIQUE INDEX IF NOT EXISTS events_run_sequence_uq ON events (run_id, sequence)",
  "CREATE INDEX IF NOT EXISTS events_run_created_idx ON events (run_id, created_at)",
  `CREATE TABLE IF NOT EXISTS evidence_items (
    id TEXT PRIMARY KEY NOT NULL,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    evidence_id TEXT NOT NULL,
    domain TEXT NOT NULL,
    source TEXT NOT NULL,
    source_url TEXT,
    published_at TEXT NOT NULL,
    available_at TEXT NOT NULL,
    analysis_date TEXT NOT NULL,
    claim TEXT NOT NULL,
    value TEXT,
    direction TEXT NOT NULL,
    uncertainty TEXT NOT NULL,
    checksum TEXT NOT NULL,
    is_valid INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
  )`,
  "CREATE UNIQUE INDEX IF NOT EXISTS evidence_run_evidence_uq ON evidence_items (run_id, evidence_id)",
  "CREATE INDEX IF NOT EXISTS evidence_run_domain_idx ON evidence_items (run_id, domain)",
  `CREATE TABLE IF NOT EXISTS results (
    id TEXT PRIMARY KEY NOT NULL,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    group_code TEXT NOT NULL,
    raw_decision TEXT NOT NULL,
    final_decision TEXT NOT NULL,
    confidence INTEGER NOT NULL,
    thesis TEXT NOT NULL,
    evidence_ids_json TEXT NOT NULL DEFAULT '[]',
    gatekeeper_json TEXT NOT NULL DEFAULT '{}',
    backtest_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
  )`,
  "CREATE UNIQUE INDEX IF NOT EXISTS results_run_group_uq ON results (run_id, group_code)",
  "CREATE INDEX IF NOT EXISTS results_run_idx ON results (run_id)",
  `CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY NOT NULL,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    owner_hash TEXT NOT NULL,
    kind TEXT NOT NULL,
    r2_key TEXT NOT NULL,
    file_name TEXT NOT NULL,
    content_type TEXT NOT NULL,
    byte_size INTEGER NOT NULL,
    checksum TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ready',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
  )`,
  "CREATE UNIQUE INDEX IF NOT EXISTS artifacts_r2_key_uq ON artifacts (r2_key)",
  "CREATE INDEX IF NOT EXISTS artifacts_run_owner_idx ON artifacts (run_id, owner_hash)",
  `CREATE TABLE IF NOT EXISTS quotas (
    scope TEXT NOT NULL,
    quota_key TEXT NOT NULL,
    window_start TEXT NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (scope, quota_key, window_start)
  )`,
  "CREATE INDEX IF NOT EXISTS quotas_window_idx ON quotas (window_start, scope)",
  `CREATE TRIGGER IF NOT EXISTS quotas_limit_insert
    BEFORE INSERT ON quotas
    WHEN (NEW.scope = 'user' AND NEW.count > 3) OR (NEW.scope = 'site' AND NEW.count > 10)
    BEGIN SELECT RAISE(ABORT, 'quota_limit'); END`,
  `CREATE TRIGGER IF NOT EXISTS quotas_limit_update
    BEFORE UPDATE OF count ON quotas
    WHEN (NEW.scope = 'user' AND NEW.count > 3) OR (NEW.scope = 'site' AND NEW.count > 10)
    BEGIN SELECT RAISE(ABORT, 'quota_limit'); END`,
] as const;
