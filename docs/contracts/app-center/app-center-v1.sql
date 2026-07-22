-- COORD-0 dry-run schema only. Never run against production without PG-A approval.
-- AC-2 Entry: app_registry is a read-only snapshot seeded transactionally from
-- pixelle_video.app_center.registry.BUILTIN_MANIFESTS before AppRun/Handoff writes.
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS app_schema_migrations (
  migration_id TEXT PRIMARY KEY,
  schema_version INTEGER NOT NULL,
  checksum TEXT NOT NULL,
  applied_at TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS app_schema_version_guard
BEFORE INSERT ON app_schema_migrations
WHEN NEW.schema_version > 1
BEGIN
  SELECT RAISE(ABORT, 'UNSUPPORTED_FUTURE_SCHEMA');
END;

INSERT OR IGNORE INTO app_schema_migrations(migration_id, schema_version, checksum, applied_at)
VALUES ('app-center-v1', 1, 'sha256:app-center-v1', CURRENT_TIMESTAMP);

CREATE TABLE IF NOT EXISTS app_registry (
  app_id TEXT NOT NULL,
  schema_version INTEGER NOT NULL,
  version TEXT NOT NULL,
  manifest_json TEXT NOT NULL,
  status TEXT NOT NULL,
  feature_flag TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT 'builtin_code' CHECK (source = 'builtin_code'),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (app_id, version)
);

CREATE TABLE IF NOT EXISTS content_projects (
  project_id TEXT PRIMARY KEY,
  schema_version INTEGER NOT NULL DEFAULT 1 CHECK (schema_version = 1),
  name TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
  primary_goal TEXT NOT NULL,
  brand_id TEXT,
  current_context_snapshot_id TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY (current_context_snapshot_id) REFERENCES context_snapshots(context_snapshot_id)
);

CREATE TABLE IF NOT EXISTS artifacts (
  artifact_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES content_projects(project_id),
  source_app_run_id TEXT REFERENCES app_runs(app_run_id),
  artifact_type TEXT NOT NULL,
  name TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'ready', 'archived')),
  current_version_id TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS artifact_versions (
  artifact_version_id TEXT PRIMARY KEY,
  artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id),
  project_id TEXT NOT NULL REFERENCES content_projects(project_id),
  version_number INTEGER NOT NULL CHECK (version_number > 0),
  schema_version INTEGER NOT NULL,
  content_json TEXT,
  file_refs_json TEXT NOT NULL DEFAULT '[]',
  source TEXT NOT NULL CHECK (source IN ('generated', 'edited', 'imported', 'rendered')),
  content_fingerprint TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE (artifact_id, version_number),
  UNIQUE (artifact_id, content_fingerprint)
);

CREATE TABLE IF NOT EXISTS app_runs (
  app_run_id TEXT PRIMARY KEY,
  app_id TEXT NOT NULL,
  project_id TEXT NOT NULL REFERENCES content_projects(project_id),
  app_version TEXT NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('draft', 'queued', 'running', 'needs_review', 'completed', 'failed', 'cancelled')),
  state_version INTEGER NOT NULL DEFAULT 1 CHECK (state_version > 0),
  idempotency_key TEXT NOT NULL UNIQUE,
  input_schema_version INTEGER NOT NULL DEFAULT 1,
  input_json TEXT NOT NULL,
  context_snapshot_id TEXT REFERENCES context_snapshots(context_snapshot_id),
  prompt_version TEXT,
  session_id TEXT,
  output_artifact_ids_json TEXT NOT NULL DEFAULT '[]',
  error_code TEXT,
  completed_at TEXT,
  archived_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY (app_id, app_version) REFERENCES app_registry(app_id, version)
);

CREATE TABLE IF NOT EXISTS context_snapshots (
  context_snapshot_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES content_projects(project_id),
  schema_version INTEGER NOT NULL DEFAULT 1 CHECK (schema_version = 1),
  payload_json TEXT NOT NULL,
  source_brand_id TEXT,
  source_brand_revision_id TEXT,
  fingerprint TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS run_attempts (
  attempt_id TEXT PRIMARY KEY,
  app_run_id TEXT NOT NULL REFERENCES app_runs(app_run_id),
  attempt_number INTEGER NOT NULL CHECK (attempt_number > 0),
  task_id TEXT,
  state TEXT NOT NULL CHECK (state IN ('queued', 'running', 'needs_review', 'completed', 'failed', 'cancelled')),
  context_snapshot_id TEXT REFERENCES context_snapshots(context_snapshot_id),
  error_code TEXT,
  error_message TEXT,
  diagnostic_json TEXT,
  model_ref TEXT,
  provider_class TEXT,
  input_units INTEGER,
  output_units INTEGER,
  estimated_cost_micros INTEGER,
  started_at TEXT,
  completed_at TEXT,
  duration_ms INTEGER,
  created_at TEXT NOT NULL,
  UNIQUE (app_run_id, attempt_number)
);

CREATE TABLE IF NOT EXISTS app_events (
  event_id TEXT PRIMARY KEY,
  app_run_id TEXT NOT NULL REFERENCES app_runs(app_run_id),
  event_type TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS artifact_handoffs (
  handoff_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES content_projects(project_id),
  source_app_run_id TEXT REFERENCES app_runs(app_run_id),
  source_artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id),
  source_artifact_version_id TEXT NOT NULL REFERENCES artifact_versions(artifact_version_id),
  target_app_id TEXT NOT NULL,
  target_app_version TEXT NOT NULL,
  target_run_id TEXT REFERENCES app_runs(app_run_id),
  artifact_version_ids_json TEXT NOT NULL,
  mapping_version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  FOREIGN KEY (target_app_id, target_app_version) REFERENCES app_registry(app_id, version)
);
