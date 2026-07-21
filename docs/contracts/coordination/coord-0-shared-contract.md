# COORD-0 Shared Contract

- schema_version: `1`
- owner: Program coordination
- scope: AC-0 + PUB-0 only
- status: frozen for COORD-0; changes require a Change Request after PG-A review

## Fact ownership

```text
ArtifactVersion
  = application center editable creative output

PublishPackage V2
  = publishing-owned immutable snapshot

PublishRun
  = one account/platform execution over one package

Generic Task
  = progress projection only; never a project/package/run fact source
```

The application center may create a `publish_package_ref` artifact containing `package_id`, package schema version, fingerprint and source version IDs. It must not create a second editable PublishPackage record.

## Source compatibility

New applications use `source_kind=artifact_versions` with one or more immutable ArtifactVersion IDs. The existing IP broadcast path may use `source_kind=legacy_session` until AC-5. `source_session_id` is nullable in the shared contract and required only by the legacy adapter.

## Storage ownership

| Store | Owns | Does not own |
| --- | --- | --- |
| `app_center.sqlite` | project/context/AppRun/Artifact/Version/Handoff | account/profile/cookie/browser evidence |
| `publishing.sqlite3` | account/package/publish run/step/event | editable content project |
| `desktop_tasks.sqlite` | generic task projection | project/package/run facts |
| `asset_library.sqlite3` | media/domain assets and revisions | creative versions/publish state |

## Model boundary

P0 application Executors use `AppLLMPort -> PixelleVideoCore.llm -> LLMService -> ConfigManager.llm`. No request, manifest, task, artifact or log may contain API keys or arbitrary provider/model paths.

## Routing and final action

`/#/publish` is the single publishing route owner. Browser automation must stop at `waiting_for_human`; `FinalActionGuard` rejects the platform's final publish action.

## AC-2 Entry frozen boundaries

### AppRun lifecycle

`AppRun.state` is the application-center business state and is limited to:
`draft`, `queued`, `running`, `needs_review`, `completed`, `failed`, `cancelled`.
`completed` means the user-visible artifact version is accepted. `succeeded` is reserved for
`PublishRun`/publish-step compatibility and must not be written to `AppRun`; publish-only
`waiting_for_login`, `waiting_for_human`, and `needs_attention` are not AppRun states.

### Registry ownership and seeding

The trusted Python `BUILTIN_MANIFESTS` registry is the P0 source of truth for executable
manifest metadata. `app_registry` in `app_center.sqlite` is a read-only, versioned snapshot
seeded transactionally from that registry at database initialization. There is no P0 API for
writing manifests and no user-provided executor or feature flag is loaded from SQLite.
The seed operation is idempotent on `(app_id, version)` and the snapshot primary key is
`(app_id, version)`, so multiple immutable manifest versions can coexist for recovery and
old AppRuns. It must complete before any `AppRun`/`Handoff` row referencing `app_registry` is inserted. A future admin/control plane
may replace the seed writer behind an explicit ADR; it cannot silently change P0 ownership.

### SQLite field contract

`app-center-v1.sql` is the executable contract for the AC-2 repository. It includes the
schema-versioned project/context snapshot, `AppRun` state/version/idempotency fields,
attempt diagnostics and non-sensitive model metadata, immutable artifact versions with
fingerprints, and handoff source/target fields. The implementation must not introduce a
second table or rename these IDs without a Change Request.
