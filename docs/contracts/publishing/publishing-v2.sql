-- COORD-0 dry-run schema only. New V2 tables are additive; legacy V1 remains readable.
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS publishing_schema_migrations (
  migration_id TEXT PRIMARY KEY,
  schema_version INTEGER NOT NULL,
  applied_at TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS publishing_schema_version_guard
BEFORE INSERT ON publishing_schema_migrations
WHEN NEW.schema_version > 2
BEGIN
  SELECT RAISE(ABORT, 'UNSUPPORTED_FUTURE_SCHEMA');
END;

INSERT OR IGNORE INTO publishing_schema_migrations(migration_id, schema_version, applied_at)
VALUES ('publishing-v2', 2, CURRENT_TIMESTAMP);

CREATE TABLE IF NOT EXISTS publish_accounts (
  account_id TEXT PRIMARY KEY,
  schema_version INTEGER NOT NULL DEFAULT 1,
  platform TEXT NOT NULL,
  display_name TEXT NOT NULL,
  profile_ref TEXT NOT NULL UNIQUE,
  verification_state TEXT NOT NULL DEFAULT 'unverified',
  enabled INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0, 1)),
  created_at TEXT NOT NULL,
  last_verified_at TEXT
);

CREATE TABLE IF NOT EXISTS publish_packages_v2 (
  package_id TEXT PRIMARY KEY,
  schema_version INTEGER NOT NULL DEFAULT 2,
  project_id TEXT NOT NULL,
  source_kind TEXT NOT NULL CHECK (source_kind IN ('artifact_versions', 'legacy_session')),
  source_artifact_ids_json TEXT NOT NULL DEFAULT '[]',
  source_artifact_version_ids_json TEXT NOT NULL DEFAULT '[]',
  source_session_id TEXT,
  source_revision TEXT NOT NULL,
  artifact_refs_json TEXT NOT NULL,
  video_manifest_json TEXT NOT NULL DEFAULT '{}',
  carousel_manifests_json TEXT NOT NULL DEFAULT '[]',
  cover_manifest_json TEXT NOT NULL DEFAULT '{}',
  platform_copy_json TEXT NOT NULL DEFAULT '{}',
  policy_json TEXT NOT NULL DEFAULT '{}',
  package_fingerprint TEXT NOT NULL UNIQUE,
  invalidated_at TEXT,
  invalidation_reason TEXT,
  created_at TEXT NOT NULL,
  CHECK (
    (source_kind = 'artifact_versions'
      AND source_session_id IS NULL
      AND length(source_artifact_version_ids_json) > 2
      AND source_artifact_ids_json <> '[]')
    OR
    (source_kind = 'legacy_session'
      AND source_session_id IS NOT NULL
      AND source_artifact_ids_json = '[]'
      AND source_artifact_version_ids_json = '[]')
  )
);

CREATE TABLE IF NOT EXISTS publish_runs_v2 (
  run_id TEXT PRIMARY KEY,
  schema_version INTEGER NOT NULL DEFAULT 1,
  package_id TEXT NOT NULL REFERENCES publish_packages_v2(package_id),
  account_id TEXT NOT NULL REFERENCES publish_accounts(account_id),
  platform TEXT NOT NULL,
  state TEXT NOT NULL,
  state_version INTEGER NOT NULL DEFAULT 1 CHECK (state_version > 0),
  attempt INTEGER NOT NULL DEFAULT 1 CHECK (attempt > 0),
  current_step TEXT,
  idempotency_key TEXT NOT NULL UNIQUE,
  human_confirmation_required INTEGER NOT NULL DEFAULT 1 CHECK (human_confirmation_required = 1),
  human_confirmed INTEGER NOT NULL DEFAULT 0 CHECK (human_confirmed IN (0, 1)),
  confirmed_at TEXT,
  actor_ref TEXT,
  task_id TEXT,
  error_code TEXT,
  error_message TEXT,
  checkpoint_json TEXT NOT NULL DEFAULT '{}',
  cancel_requested INTEGER NOT NULL DEFAULT 0 CHECK (cancel_requested IN (0, 1)),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  CHECK (state <> 'succeeded' OR human_confirmed = 1),
  CHECK (state <> 'waiting_for_human' OR human_confirmed = 0)
);

CREATE TABLE IF NOT EXISTS publish_step_results (
  step_result_id TEXT PRIMARY KEY,
  schema_version INTEGER NOT NULL DEFAULT 1,
  run_id TEXT NOT NULL REFERENCES publish_runs_v2(run_id),
  step TEXT NOT NULL,
  state TEXT NOT NULL,
  evidence_kind TEXT NOT NULL,
  evidence_ref TEXT,
  evidence_redacted INTEGER NOT NULL DEFAULT 1 CHECK (evidence_redacted = 1),
  error_code TEXT,
  created_at TEXT NOT NULL
);

-- PUB-2 canonical append-only event and attempt facts. The older
-- publish_step_results table remains readable for COORD-0 fixtures; new code
-- writes attempts here so retry never overwrites prior evidence.
CREATE TABLE IF NOT EXISTS publish_run_step_attempts (
  step_attempt_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES publish_runs_v2(run_id) ON DELETE CASCADE,
  step TEXT NOT NULL,
  attempt INTEGER NOT NULL CHECK (attempt > 0),
  state TEXT NOT NULL CHECK (state IN ('queued', 'running', 'waiting_for_login', 'waiting_for_human', 'needs_attention', 'succeeded', 'failed', 'cancelled')),
  evidence_kind TEXT NOT NULL DEFAULT 'none',
  evidence_ref TEXT,
  error_code TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(run_id, step, attempt)
);

CREATE TABLE IF NOT EXISTS publish_events (
  event_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES publish_runs_v2(run_id) ON DELETE CASCADE,
  event_seq INTEGER NOT NULL CHECK (event_seq > 0),
  event_type TEXT NOT NULL,
  state TEXT,
  state_version INTEGER NOT NULL CHECK (state_version > 0),
  payload_json TEXT NOT NULL DEFAULT '{}',
  redacted INTEGER NOT NULL DEFAULT 1 CHECK (redacted = 1),
  created_at TEXT NOT NULL,
  UNIQUE(run_id, event_seq)
);

CREATE INDEX IF NOT EXISTS publish_events_run_cursor
  ON publish_events(run_id, event_seq);

CREATE UNIQUE INDEX IF NOT EXISTS publish_active_run_by_account_platform
  ON publish_runs_v2(account_id, platform)
  WHERE state IN ('queued', 'running', 'waiting_for_login', 'waiting_for_human', 'needs_attention');

CREATE TRIGGER IF NOT EXISTS publish_run_state_guard
BEFORE INSERT ON publish_runs_v2
WHEN NEW.state NOT IN ('queued', 'running', 'waiting_for_login', 'waiting_for_human', 'needs_attention', 'succeeded', 'failed', 'cancelled')
  OR NEW.platform NOT IN ('douyin', 'video_channel', 'kuaishou', 'xiaohongshu')
  OR NEW.human_confirmation_required <> 1
  OR NEW.state <> 'queued'
  OR NEW.state_version <> 1
  OR NEW.attempt <> 1
  OR NEW.human_confirmed <> 0
  OR EXISTS (SELECT 1 FROM publish_packages_v2 p WHERE p.package_id = NEW.package_id AND p.invalidated_at IS NOT NULL)
  OR EXISTS (SELECT 1 FROM publish_accounts a WHERE a.account_id = NEW.account_id AND a.platform <> NEW.platform)
BEGIN
  SELECT RAISE(ABORT, 'INVALID_PUBLISH_RUN_INITIAL_STATE_OR_PLATFORM_OR_PACKAGE');
END;

CREATE TRIGGER IF NOT EXISTS publish_run_state_update_guard
BEFORE UPDATE OF state, state_version, attempt ON publish_runs_v2
WHEN NEW.state NOT IN ('queued', 'running', 'waiting_for_login', 'waiting_for_human', 'needs_attention', 'succeeded', 'failed', 'cancelled')
  OR NEW.platform NOT IN ('douyin', 'video_channel', 'kuaishou', 'xiaohongshu')
  OR NEW.state_version <> OLD.state_version + 1
  OR (OLD.state = 'queued' AND NEW.state NOT IN ('queued', 'running', 'cancelled', 'needs_attention'))
  OR (OLD.state = 'running' AND NEW.state NOT IN ('running', 'waiting_for_login', 'waiting_for_human', 'needs_attention', 'failed', 'cancelled'))
  OR (OLD.state = 'waiting_for_login' AND NEW.state NOT IN ('waiting_for_login', 'running', 'needs_attention', 'cancelled'))
  OR (OLD.state = 'waiting_for_human' AND NEW.state NOT IN ('waiting_for_human', 'succeeded', 'needs_attention', 'cancelled'))
  OR (OLD.state = 'needs_attention' AND NEW.state NOT IN ('needs_attention', 'queued', 'waiting_for_human', 'failed', 'cancelled'))
  OR (OLD.state = 'needs_attention' AND NEW.state = 'waiting_for_human' AND (
       json_extract(NEW.checkpoint_json, '$.last_stage') <> 'verify'
       OR json_extract(NEW.checkpoint_json, '$.final_action_guard_armed') <> 1
       OR json_extract(NEW.checkpoint_json, '$.final_publish_clicked') <> 0
       OR json_extract(NEW.checkpoint_json, '$.blocker_code') IS NOT NULL
       OR json_extract(NEW.checkpoint_json, '$.blocked_stage') IS NOT NULL
     ))
  OR (OLD.state IN ('succeeded', 'failed', 'cancelled') AND NEW.state <> OLD.state)
  OR (NEW.state = 'succeeded' AND (OLD.state <> 'waiting_for_human' OR NEW.human_confirmed <> 1))
  OR NEW.attempt < OLD.attempt
BEGIN
  SELECT RAISE(ABORT, 'INVALID_PUBLISH_RUN_TRANSITION_OR_CAS');
END;

CREATE TRIGGER IF NOT EXISTS publish_run_account_platform_update_guard
BEFORE UPDATE OF account_id, platform, package_id ON publish_runs_v2
WHEN EXISTS (SELECT 1 FROM publish_accounts a WHERE a.account_id = NEW.account_id AND a.platform <> NEW.platform)
  OR EXISTS (SELECT 1 FROM publish_packages_v2 p WHERE p.package_id = NEW.package_id AND p.invalidated_at IS NOT NULL)
BEGIN
  SELECT RAISE(ABORT, 'PUBLISH_RUN_PACKAGE_ACCOUNT_PLATFORM_MISMATCH');
END;

CREATE TRIGGER IF NOT EXISTS publish_package_immutable_guard
BEFORE UPDATE ON publish_packages_v2
WHEN OLD.project_id <> NEW.project_id
  OR OLD.source_kind <> NEW.source_kind
  OR OLD.source_artifact_ids_json <> NEW.source_artifact_ids_json
  OR OLD.source_artifact_version_ids_json <> NEW.source_artifact_version_ids_json
  OR COALESCE(OLD.source_session_id, '') <> COALESCE(NEW.source_session_id, '')
  OR OLD.source_revision <> NEW.source_revision
  OR OLD.artifact_refs_json <> NEW.artifact_refs_json
  OR OLD.schema_version <> NEW.schema_version
  OR OLD.video_manifest_json <> NEW.video_manifest_json
  OR OLD.carousel_manifests_json <> NEW.carousel_manifests_json
  OR OLD.cover_manifest_json <> NEW.cover_manifest_json
  OR OLD.platform_copy_json <> NEW.platform_copy_json
  OR OLD.policy_json <> NEW.policy_json
  OR OLD.package_fingerprint <> NEW.package_fingerprint
  OR OLD.created_at <> NEW.created_at
BEGIN
  SELECT RAISE(ABORT, 'PUBLISH_PACKAGE_IMMUTABLE');
END;

CREATE TRIGGER IF NOT EXISTS publish_package_invalidation_guard
BEFORE UPDATE ON publish_packages_v2
WHEN ((NEW.invalidated_at IS NULL) <> (NEW.invalidation_reason IS NULL))
  OR (OLD.invalidated_at IS NOT NULL AND (
    NEW.invalidated_at IS NULL
    OR NEW.invalidation_reason IS NULL
    OR NEW.invalidated_at <> OLD.invalidated_at
    OR NEW.invalidation_reason <> OLD.invalidation_reason
  ))
BEGIN
  SELECT RAISE(ABORT, 'PUBLISH_PACKAGE_INVALIDATION_ONE_WAY');
END;


-- PUB-1 account operational metadata. These tables contain state and
-- redacted references only; cookies, tokens, QR payloads and browser storage
-- remain inside the canonical local profile directory.
CREATE TABLE IF NOT EXISTS publish_account_state (
  account_id TEXT PRIMARY KEY REFERENCES publish_accounts(account_id) ON DELETE CASCADE,
  platform TEXT NOT NULL,
  login_state TEXT NOT NULL DEFAULT 'not_connected',
  is_default INTEGER NOT NULL DEFAULT 0 CHECK (is_default IN (0, 1)),
  profile_exists INTEGER NOT NULL DEFAULT 0 CHECK (profile_exists IN (0, 1)),
  login_subject_hint TEXT,
  identity_fingerprint TEXT,
  last_error_code TEXT,
  archived_at TEXT,
  updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS publish_account_default_by_platform
  ON publish_account_state(platform)
  WHERE is_default = 1 AND archived_at IS NULL;

CREATE TABLE IF NOT EXISTS publish_profile_locks (
  account_id TEXT PRIMARY KEY REFERENCES publish_accounts(account_id) ON DELETE CASCADE,
  owner_ref TEXT NOT NULL,
  pid INTEGER,
  acquired_at TEXT NOT NULL,
  heartbeat_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS publish_context_registry (
  context_id TEXT PRIMARY KEY,
  account_id TEXT NOT NULL REFERENCES publish_accounts(account_id) ON DELETE CASCADE,
  window_ref TEXT,
  status TEXT NOT NULL CHECK (status IN ('open', 'closed', 'stale')),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
