export type PublishSourceKind = "artifact_versions" | "legacy_session";
export type PublishRunState =
  | "queued" | "running" | "waiting_for_login" | "waiting_for_human"
  | "needs_attention" | "succeeded" | "failed" | "cancelled";

export interface PublishSource {
  kind: PublishSourceKind;
  artifact_ids: string[];
  artifact_version_ids: string[];
  session_id: string | null;
  source_revision: string;
}

export interface PublishPackageV2 {
  schema_version: 2;
  package_id: string;
  project_id: string;
  source: PublishSource;
  artifact_refs: Array<{
    artifact_id: string;
    artifact_version_id: string;
    artifact_type: "video" | "cover" | "publish_copy" | "carousel_package" | "carousel_page";
    content_fingerprint: `sha256:${string}`;
  }>;
  video_manifest: {
    sha256: `sha256:${string}`;
    size_bytes: number;
    mime_type: `video/${string}`;
    path_token: `asset_${string}`;
    duration_ms?: number;
    width?: number;
    height?: number;
  } | null;
  carousel_manifests?: Array<{
    sha256: `sha256:${string}`;
    size_bytes: number;
    mime_type: `image/${string}`;
    path_token: `asset_${string}`;
    width?: number;
    height?: number;
  }>;
  cover_manifest?: {
    sha256: `sha256:${string}`;
    size_bytes: number;
    mime_type: `image/${string}`;
    path_token: `asset_${string}`;
    width?: number;
    height?: number;
  };
  platform_copy?: { title?: string; description?: string; hashtags?: string[] };
  policy: { human_confirmation_required: true; allow_final_publish: false; adapter_version?: string };
  package_fingerprint: `sha256:${string}`;
  created_at: string;
}

export interface PublishRun {
  schema_version: 1;
  run_id: string;
  package_id: string;
  account_id: string;
  platform: "douyin" | "video_channel" | "kuaishou" | "xiaohongshu";
  state: PublishRunState;
  state_version: number;
  attempt: number;
  current_step: string | null;
  idempotency_key: string;
  human_confirmation: { required: true; confirmed: boolean; confirmed_at: string | null; actor_ref: string | null };
  created_at: string;
  updated_at: string;
}
