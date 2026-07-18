export type LibraryItemKind =
  | "video"
  | "image"
  | "voice"
  | "digital_human"
  | "template"
  | "brand";

export type MediaKind = "video" | "image" | "audio" | "font";

export type ResourceStatus =
  | "processing"
  | "ready"
  | "warning"
  | "failed"
  | "archived";

export type LibraryItem = {
  resource_id: string;
  kind: LibraryItemKind;
  name: string;
  description: string;
  status: ResourceStatus;
  cover_url?: string;
  tags: string[];
  favorite: boolean;
  created_at: string;
  updated_at: string;
  summary: Record<string, string | number | boolean>;
};

export type MediaAsset = {
  asset_id: string;
  legacy_id?: string;
  media_kind: MediaKind;
  name: string;
  description: string;
  source: "upload" | "recording" | "generated" | "system" | "imported";
  current_revision_id?: string;
  status: ResourceStatus;
  created_at: string;
  updated_at: string;
  archived_at?: string;
};

export type AssetRevision = {
  revision_id: string;
  asset_id: string;
  version: number;
  parent_revision_id?: string;
  relative_path: string;
  mime_type: string;
  bytes: number;
  sha256: string;
  width?: number;
  height?: number;
  aspect_ratio?: number;
  duration_ms?: number;
  frame_rate?: number;
  has_audio?: boolean;
  has_transparency?: boolean;
  created_at: string;
};

export type ResourceSnapshot = {
  resource_kind: LibraryItemKind;
  resource_id: string;
  revision_id?: string;
  variant_id?: string;
  sha256?: string;
  resolved_relative_path?: string;
  template_revision?: number;
  renderer_version?: string;
};
