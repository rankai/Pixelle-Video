/** UX-0 typed projections; the SMB UI must consume these instead of summary keys. */

export type AssetViewKind =
  | "image"
  | "video"
  | "audio"
  | "voice"
  | "digital_human"
  | "template"
  | "brand";

export type AssetViewStatus = "processing" | "ready" | "warning" | "failed" | "archived";

export type AssetViewBase = {
  resource_id: string;
  kind: AssetViewKind;
  name: string;
  description: string;
  status: AssetViewStatus;
  cover_url?: string;
  tags: string[];
  favorite: boolean;
  last_used_at?: string;
  capabilities: string[];
};

export type ImageAssetViewModel = AssetViewBase & {
  kind: "image";
  display: { width: number; height: number; aspect_ratio: number; transparent: boolean; purpose?: string };
};

export type VideoAssetViewModel = AssetViewBase & {
  kind: "video";
  display: { duration_ms: number; width: number; height: number; aspect_ratio: number; has_audio: boolean };
};

export type AudioAssetViewModel = AssetViewBase & {
  kind: "audio";
  display: { duration_ms: number; purpose?: string; authorization_status?: string };
};

export type VoiceAssetViewModel = AssetViewBase & {
  kind: "voice";
  display: { language: string; style: string; reference_duration_ms?: number; authorization_status: string };
};

export type DigitalHumanAssetViewModel = AssetViewBase & {
  kind: "digital_human";
  display: { scene_count: number; default_scene_id?: string; media_types: Array<"image" | "video"> };
};

export type TemplateAssetViewModel = AssetViewBase & {
  kind: "template";
  display: { canvas_width: number; canvas_height: number; subtitle_layout: string; cover_layout: string; revision: number };
};

export type BrandAssetViewModel = AssetViewBase & {
  kind: "brand";
  display: { has_logo: boolean; has_bgm: boolean; has_contact: boolean; primary_color: string; secondary_color: string };
};

export type AssetViewModel =
  | ImageAssetViewModel
  | VideoAssetViewModel
  | AudioAssetViewModel
  | VoiceAssetViewModel
  | DigitalHumanAssetViewModel
  | TemplateAssetViewModel
  | BrandAssetViewModel;

export type PickerContext = {
  session_id: string;
  step: string;
  purpose: string;
  slot_id: string;
  allowed_kinds: AssetViewKind[];
  aspect_ratio?: number;
  max_duration_ms?: number;
  required_capabilities: string[];
  selection_mode: "single" | "multiple";
};

export type PickerAction = "preview" | "use" | "favorite" | "edit" | "archive" | "confirm" | "cancel";
export type ActionMatrix = Record<"management" | "picker", Record<AssetViewKind, PickerAction[]>>;

export type AssetErrorCode =
  | "asset_service_unavailable"
  | "list_load_failed"
  | "preview_failed"
  | "upload_failed"
  | "duplicate_decision_required"
  | "cursor_stale"
  | "cursor_filter_mismatch"
  | "incompatible_asset"
  | "archive_failed";

export type DeferredUploadStatus =
  | "created"
  | "uploading"
  | "analyzing"
  | "uploaded"
  | "awaiting_duplicate_decision"
  | "finalized"
  | "expired"
  | "failed"
  | "cancelled";

export type DuplicatePolicy = "reuse_existing" | "attach_revision" | "create_separate";

export const RESTART_RECOVERY_COPY = "应用已重启，请重新选择原文件继续上传";
