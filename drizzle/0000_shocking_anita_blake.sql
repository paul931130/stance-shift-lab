CREATE TABLE `advance_requests` (
	`run_id` text NOT NULL,
	`idempotency_key` text NOT NULL,
	`owner_hash` text NOT NULL,
	`step_index` integer,
	`status` text DEFAULT 'started' NOT NULL,
	`response_json` text,
	`created_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	`completed_at` text,
	PRIMARY KEY(`run_id`, `idempotency_key`),
	FOREIGN KEY (`run_id`) REFERENCES `runs`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE INDEX `advance_requests_step_idx` ON `advance_requests` (`run_id`,`step_index`);--> statement-breakpoint
CREATE TABLE `artifacts` (
	`id` text PRIMARY KEY NOT NULL,
	`run_id` text NOT NULL,
	`owner_hash` text NOT NULL,
	`kind` text NOT NULL,
	`r2_key` text NOT NULL,
	`file_name` text NOT NULL,
	`content_type` text NOT NULL,
	`byte_size` integer NOT NULL,
	`checksum` text NOT NULL,
	`status` text DEFAULT 'ready' NOT NULL,
	`created_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	FOREIGN KEY (`run_id`) REFERENCES `runs`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `artifacts_r2_key_uq` ON `artifacts` (`r2_key`);--> statement-breakpoint
CREATE INDEX `artifacts_run_owner_idx` ON `artifacts` (`run_id`,`owner_hash`);--> statement-breakpoint
CREATE TABLE `events` (
	`id` text PRIMARY KEY NOT NULL,
	`run_id` text NOT NULL,
	`sequence` integer NOT NULL,
	`kind` text NOT NULL,
	`message` text NOT NULL,
	`payload_json` text DEFAULT '{}' NOT NULL,
	`created_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	FOREIGN KEY (`run_id`) REFERENCES `runs`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `events_run_sequence_uq` ON `events` (`run_id`,`sequence`);--> statement-breakpoint
CREATE INDEX `events_run_created_idx` ON `events` (`run_id`,`created_at`);--> statement-breakpoint
CREATE TABLE `evidence_items` (
	`id` text PRIMARY KEY NOT NULL,
	`run_id` text NOT NULL,
	`evidence_id` text NOT NULL,
	`domain` text NOT NULL,
	`source` text NOT NULL,
	`source_url` text,
	`published_at` text NOT NULL,
	`available_at` text NOT NULL,
	`analysis_date` text NOT NULL,
	`claim` text NOT NULL,
	`value` text,
	`direction` text NOT NULL,
	`uncertainty` text NOT NULL,
	`checksum` text NOT NULL,
	`is_valid` integer DEFAULT true NOT NULL,
	`created_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	FOREIGN KEY (`run_id`) REFERENCES `runs`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `evidence_run_evidence_uq` ON `evidence_items` (`run_id`,`evidence_id`);--> statement-breakpoint
CREATE INDEX `evidence_run_domain_idx` ON `evidence_items` (`run_id`,`domain`);--> statement-breakpoint
CREATE TABLE `llm_attempts` (
	`id` text PRIMARY KEY NOT NULL,
	`run_id` text NOT NULL,
	`step_id` text NOT NULL,
	`attempt_number` integer NOT NULL,
	`provider` text NOT NULL,
	`model` text NOT NULL,
	`request_hash` text NOT NULL,
	`status` text NOT NULL,
	`http_status` integer,
	`latency_ms` integer,
	`response_json` text,
	`error_message` text,
	`created_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	`completed_at` text,
	FOREIGN KEY (`run_id`) REFERENCES `runs`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`step_id`) REFERENCES `run_steps`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `llm_attempts_run_number_uq` ON `llm_attempts` (`run_id`,`attempt_number`);--> statement-breakpoint
CREATE INDEX `llm_attempts_step_idx` ON `llm_attempts` (`step_id`,`created_at`);--> statement-breakpoint
CREATE TABLE `quotas` (
	`scope` text NOT NULL,
	`quota_key` text NOT NULL,
	`window_start` text NOT NULL,
	`count` integer DEFAULT 0 NOT NULL,
	`updated_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	PRIMARY KEY(`scope`, `quota_key`, `window_start`)
);
--> statement-breakpoint
CREATE INDEX `quotas_window_idx` ON `quotas` (`window_start`,`scope`);--> statement-breakpoint
CREATE TABLE `results` (
	`id` text PRIMARY KEY NOT NULL,
	`run_id` text NOT NULL,
	`group_code` text NOT NULL,
	`raw_decision` text NOT NULL,
	`final_decision` text NOT NULL,
	`confidence` integer NOT NULL,
	`thesis` text NOT NULL,
	`evidence_ids_json` text DEFAULT '[]' NOT NULL,
	`gatekeeper_json` text DEFAULT '{}' NOT NULL,
	`backtest_json` text,
	`created_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	FOREIGN KEY (`run_id`) REFERENCES `runs`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `results_run_group_uq` ON `results` (`run_id`,`group_code`);--> statement-breakpoint
CREATE INDEX `results_run_idx` ON `results` (`run_id`);--> statement-breakpoint
CREATE TABLE `run_steps` (
	`id` text PRIMARY KEY NOT NULL,
	`run_id` text NOT NULL,
	`step_index` integer NOT NULL,
	`step_key` text NOT NULL,
	`group_code` text NOT NULL,
	`phase` text NOT NULL,
	`round` integer,
	`agent_id` text,
	`stance` text,
	`status` text DEFAULT 'pending' NOT NULL,
	`input_json` text DEFAULT '{}' NOT NULL,
	`output_json` text,
	`started_at` text,
	`completed_at` text,
	`error_message` text,
	FOREIGN KEY (`run_id`) REFERENCES `runs`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `run_steps_run_index_uq` ON `run_steps` (`run_id`,`step_index`);--> statement-breakpoint
CREATE UNIQUE INDEX `run_steps_run_key_uq` ON `run_steps` (`run_id`,`step_key`);--> statement-breakpoint
CREATE INDEX `run_steps_run_status_idx` ON `run_steps` (`run_id`,`status`);--> statement-breakpoint
CREATE TABLE `runs` (
	`id` text PRIMARY KEY NOT NULL,
	`owner_hash` text NOT NULL,
	`ticker` text NOT NULL,
	`analysis_date` text NOT NULL,
	`experiment_mode` text DEFAULT 'full' NOT NULL,
	`model` text NOT NULL,
	`status` text DEFAULT 'queued' NOT NULL,
	`current_step` integer DEFAULT 0 NOT NULL,
	`total_steps` integer DEFAULT 20 NOT NULL,
	`logical_calls` integer DEFAULT 0 NOT NULL,
	`provider_attempts` integer DEFAULT 0 NOT NULL,
	`version` integer DEFAULT 0 NOT NULL,
	`demo_mode` integer DEFAULT false NOT NULL,
	`published` integer DEFAULT false NOT NULL,
	`input_json` text DEFAULT '{}' NOT NULL,
	`lease_token` text,
	`lease_expires_at` integer,
	`decision_locked_at` text,
	`error_message` text,
	`created_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	`updated_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	`completed_at` text,
	`cancelled_at` text
);
--> statement-breakpoint
CREATE INDEX `runs_owner_created_idx` ON `runs` (`owner_hash`,`created_at`);--> statement-breakpoint
CREATE INDEX `runs_owner_status_idx` ON `runs` (`owner_hash`,`status`);--> statement-breakpoint
CREATE INDEX `runs_public_idx` ON `runs` (`published`,`completed_at`);
--> statement-breakpoint
CREATE UNIQUE INDEX `runs_one_active_owner_uq` ON `runs` (`owner_hash`) WHERE `status` IN ('queued','running');
--> statement-breakpoint
CREATE TRIGGER `quotas_limit_insert`
BEFORE INSERT ON `quotas`
WHEN (NEW.`scope` = 'user' AND NEW.`count` > 3) OR (NEW.`scope` = 'site' AND NEW.`count` > 10)
BEGIN SELECT RAISE(ABORT, 'quota_limit'); END;
--> statement-breakpoint
CREATE TRIGGER `quotas_limit_update`
BEFORE UPDATE OF `count` ON `quotas`
WHEN (NEW.`scope` = 'user' AND NEW.`count` > 3) OR (NEW.`scope` = 'site' AND NEW.`count` > 10)
BEGIN SELECT RAISE(ABORT, 'quota_limit'); END;
