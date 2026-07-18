import { invoke } from "@tauri-apps/api/core";

export type RuntimeInfo = {
  apiBaseUrl: string;
  desktopToken: string;
};

export type IpBroadcastState = {
  session_id: string;
  current_step: number;
  completed_steps: number;
  next_action: {
    key: string;
    step: number;
    label: string;
    description: string;
    disabled: boolean;
  };
  missing_requirements: string[];
  step_status: Record<string, string>;
  notices: Record<string, { kind: string; message: string }>;
  artifacts: Record<string, string>;
  state: Record<string, unknown>;
};

export type DesktopConfig = {
  llm: {
    base_url: string;
    api_key: string;
    model: string;
  };
  runninghub: {
    api_key: string;
    instance_type: string;
  };
  output_dir: string;
};

export type VoiceAsset = {
  reference_id: string;
  name: string;
  filename: string;
  created_at: string;
  asset_path: string;
  file_url: string;
};

export type PortraitAsset = {
  portrait_id: string;
  name: string;
  filename: string;
  created_at: string;
  media_type: "image" | "video";
  asset_path: string;
  file_url: string;
};

export type VideoAsset = {
  asset_id: string;
  name: string;
  filename: string;
  created_at: string;
  duration: number;
  size: number;
  thumbnail_exists: boolean;
  asset_path: string;
  file_url: string;
  thumbnail_url: string;
};

export type ImageAsset = {
  asset_id: string;
  name: string;
  filename: string;
  created_at: string;
  size: number;
  asset_path: string;
  file_url: string;
};

export type AssetLibraryV2Item = {
  asset_id: string;
  legacy_id: string | null;
  media_kind: "image" | "video" | "audio";
  name: string;
  description: string;
  source: string;
  status: string;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
  revision: {
    revision_id: string | null;
    version: number | null;
    mime_type: string | null;
    bytes: number | null;
    sha256: string | null;
    width: number | null;
    height: number | null;
    aspect_ratio: number | null;
    duration_ms: number | null;
    frame_rate: number | null;
    has_audio: boolean | null;
    relative_path: string | null;
  };
  file_url: string;
  thumbnail_url: string | null;
  variants: Array<{
    variant_id: string;
    revision_id: string;
    role: string;
    mime_type: string;
    width: number | null;
    height: number | null;
    duration_ms: number | null;
    url: string;
  }>;
};

export type LibraryItemV2 = {
  resource_id: string;
  kind: "video" | "image" | "audio" | "voice" | "digital_human" | "brand" | "template";
  asset_id?: string;
  file_url?: string;
  name: string;
  description: string;
  status: string;
  cover_url: string | null;
  tags: string[];
  favorite: boolean;
  created_at: string;
  updated_at: string;
  summary: Record<string, string | number | boolean>;
  capabilities?: string[];
  last_used_at?: string | null;
  display?: Record<string, string | number | boolean>;
  voice_profile?: { voice_id: string; legacy_id?: string | null; language: string; style: string; authorization_status: string };
  revision?: { revision_id?: string | null; version?: number | null; bytes?: number | null; sha256?: string | null };
  scenes?: Array<{ scene_id: string; name: string; preview_url?: string; preview_media_type?: "image" | "video"; shot_size?: string | null; location?: string | null; outfit?: string | null; posture?: string | null; status?: string; sort_order?: number }>;
  brand?: { default_bgm_asset_id?: string | null; [key: string]: unknown };
  template?: { template_id?: string; display_name?: string; short_description?: string; full_description?: string; preview_url?: string | null; renderer_version?: string; cover_contract_json?: string; subtitle_contract_json?: string; [key: string]: unknown };
  layout_contract?: Record<string, unknown> | null;
};

export type AssetCollectionV2 = {
  collection_id: string;
  name: string;
  description: string;
  status: string;
  created_at: string;
  updated_at: string;
  item_count?: number;
};

type AssetLibraryV2Upload = {
  upload: {
    upload_id: string;
    status: string;
    asset_id: string | null;
    duplicate_asset_id: string | null;
    [key: string]: unknown;
  };
  asset?: AssetLibraryV2Item;
  duplicate_asset?: AssetLibraryV2Item;
};

export type PublishPlatform = "douyin" | "xiaohongshu" | "shipinhao" | "kuaishou";

export type IpTemplateAsset = {
  template_id: string;
  display_name: string;
  short_description: string;
  full_description: string;
  cover_template_path: string;
  preview_image_path: string;
  preview_url: string;
  subtitle_style: Record<string, unknown>;
  render_subtitle_style?: Record<string, unknown>;
  render_canvas?: { width: number; height: number };
};

export type IpPresetAsset = {
  preset_id: string;
  display_name: string;
  description: string;
  script_structure: string[];
  recommended_word_count: number;
  default_style_prompt: string;
  default_template_id: string;
  default_subtitle_enabled: boolean;
  recommended_visual_strategy: string;
  publish_platform_hints: string[];
};

export type BrandKit = {
  brand_id: string;
  brand_name: string;
  created_at: string;
  logo_path: string;
  primary_color: string;
  secondary_color: string;
  font_family: string;
  default_bgm_path: string;
  default_subtitle_style: string;
  ending_card_text: string;
  store_address: string;
  phone: string;
  coupon_phrase: string;
};

export type BgmAsset = {
  name: string;
  path: string;
  source: string;
  asset_id?: string;
};

export type TaskInfo = {
  task_id: string;
  display_name?: string;
  flow_name?: string;
  step_key?: string;
  session_id?: string;
  artifact_keys?: string[];
  duration_ms?: number | null;
  retry_payload?: Record<string, unknown> | null;
  created_at?: string;
  status: "pending" | "running" | "completed" | "failed" | "cancelled";
  progress?: {
    current: number;
    total: number;
    percentage: number;
    message: string;
  } | null;
  result?: unknown;
  error?: string;
};

export type PublishResult = {
  status: "login_required" | "uploading" | "draft_ready" | "failed" | "cancelled";
  platform: string;
  message: string;
  task_id?: string;
  draft_url?: string;
  requires_human_confirmation?: boolean;
  filled_fields?: string[];
};

export type TtsPreviewResult = {
  success: boolean;
  message: string;
  audio_path: string;
  duration: number;
};

export type DiagnosticCheck = {
  id: string;
  label: string;
  status: "ok" | "warning" | "missing";
  message: string;
};

export type DesktopDiagnostics = {
  ffmpeg: { available: boolean };
  playwright: { available: boolean };
  yt_dlp: { available: boolean };
  config: Record<string, unknown>;
  checks: DiagnosticCheck[];
};

export type ConfigCheckResult = {
  ok: boolean;
  checks: DiagnosticCheck[];
};

let runtime: RuntimeInfo | null = null;

export async function getRuntime(): Promise<RuntimeInfo> {
  if (runtime) return runtime;
  try {
    runtime = await invoke<RuntimeInfo>("desktop_runtime");
  } catch {
    const browserRuntime: RuntimeInfo = {
      apiBaseUrl: browserApiBaseUrl(),
      desktopToken: import.meta.env.VITE_DESKTOP_TOKEN || "",
    };
    browserRuntime.apiBaseUrl = await resolveBrowserApiBaseUrl();
    runtime = browserRuntime;
  }
  return runtime;
}

function browserApiBaseUrl() {
  const configured = import.meta.env.VITE_API_BASE_URL as string | undefined;
  if (configured !== undefined) return configured.replace(/\/$/, "");
  // Browser development uses the standalone API on 8100. Tauri receives its
  // debug/release URL from `desktop_runtime`; keeping this browser default
  // here prevents a confusing "API not connected" error when the API is
  // healthy on the documented 8100 port but VITE_API_BASE_URL was omitted.
  return ["5173", "5174", "1420"].includes(window.location.port)
    ? "http://127.0.0.1:8100"
    : "";
}

/**
 * Resolve the browser development API before the first real request. Vite
 * can render successfully while the standalone API is still booting, which
 * used to turn a harmless startup race into the misleading "API 未连接"
 * banner. Keep configured/proxied URLs intact, but probe local development
 * ports and fall back to the packaged sidecar port when it is available.
 */
async function resolveBrowserApiBaseUrl() {
  const preferred = browserApiBaseUrl();
  const configured = import.meta.env.VITE_API_BASE_URL as string | undefined;
  const candidates = [
    preferred,
    configured,
    window.location.port && ["5173", "5174", "1420"].includes(window.location.port)
      ? "http://127.0.0.1:8000"
      : "",
  ].filter((value, index, values): value is string => Boolean(value) && values.indexOf(value) === index);

  for (const candidate of candidates) {
    // Relative/proxied production URLs are resolved by the web server and
    // must not be replaced with a loopback address.
    if (candidate.startsWith("/")) return candidate.replace(/\/$/, "");
    try {
      const controller = new AbortController();
      const timer = window.setTimeout(() => controller.abort(), 1200);
      const response = await fetch(`${candidate.replace(/\/$/, "")}/health`, {
        method: "GET",
        cache: "no-store",
        signal: controller.signal,
      });
      window.clearTimeout(timer);
      if (response.ok) return candidate.replace(/\/$/, "");
    } catch {
      // Try the next local candidate; the final API request will preserve the
      // preferred URL in its user-facing error when none are reachable.
    }
  }
  return preferred;
}

function apiUrl(apiBaseUrl: string, path: string) {
  if (apiBaseUrl.endsWith("/api") && path.startsWith("/api/")) {
    return `${apiBaseUrl}${path.slice(4)}`;
  }
  return `${apiBaseUrl}${path}`;
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const { apiBaseUrl, desktopToken } = await getRuntime();
  const headers = new Headers(init.headers);
  if (!(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (desktopToken) {
    headers.set("X-Pixelle-Desktop-Token", desktopToken);
  }
  let response: Response;
  try {
    response = await fetch(apiUrl(apiBaseUrl, path), {
      ...init,
      headers,
    });
  } catch (err) {
    throw new Error(formatNetworkError(err, apiBaseUrl));
  }
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(formatHttpError(response, detail));
  }
  return response.json() as Promise<T>;
}

function formatHttpError(response: Response, detail: string) {
  return formatHttpErrorDetail(response.status, detail, "请求未完成，请检查输入后重试。");
}

function formatHttpErrorDetail(status: number, detail: string, fallback: string) {
  if (status === 413 || detail.includes("Request Entity Too Large")) {
    return "上传文件过大，当前服务器入口限制了请求体大小。请调大外层 Nginx 的 client_max_body_size 后重试。";
  }
  if (status >= 500) {
    return "服务器暂时不可用，请稍后重试。";
  }
  if (detail.trim().startsWith("<html") || detail.includes("<body")) {
    return `服务器返回 ${status} 错误，请查看服务日志或反向代理配置。`;
  }
  try {
    const payload = JSON.parse(detail) as { detail?: unknown };
    if (typeof payload.detail === "string" && payload.detail.trim()) return payload.detail;
  } catch {
    // Keep non-JSON validation messages below.
  }
  return detail || fallback;
}

function formatNetworkError(err: unknown, _apiBaseUrl: string) {
  const message = err instanceof Error ? err.message : String(err);
  if (message.includes("Failed to fetch") || message.includes("NetworkError")) {
    return "后端服务未连接，请确认 API 服务已启动。";
  }
  return message;
}

export function createSession() {
  return apiFetch<IpBroadcastState>("/api/ip-broadcast/sessions", { method: "POST" });
}

export function getSession(sessionId: string) {
  return apiFetch<IpBroadcastState>(`/api/ip-broadcast/sessions/${sessionId}`);
}

export function updateSessionConfig(sessionId: string, values: Record<string, unknown>) {
  return apiFetch<IpBroadcastState>(`/api/ip-broadcast/sessions/${sessionId}/config`, {
    method: "PATCH",
    body: JSON.stringify(values),
  });
}

export function runStep(sessionId: string, stepKey: string) {
  return apiFetch<{ session_id: string; step_key: string; task_id: string }>(
    `/api/ip-broadcast/sessions/${sessionId}/steps/${stepKey}/run`,
    { method: "POST" },
  );
}

export function getTask(taskId: string) {
  return apiFetch<TaskInfo>(`/api/tasks/${taskId}`);
}

export function listTasks(status = "", limit = 50) {
  const query = new URLSearchParams();
  if (status) query.set("status", status);
  query.set("limit", String(limit));
  return apiFetch<TaskInfo[]>(`/api/tasks?${query.toString()}`);
}

export function cancelTask(taskId: string) {
  return apiFetch<{ success: boolean; message: string }>(`/api/tasks/${taskId}`, {
    method: "DELETE",
  });
}

export function retryTask(taskId: string) {
  return apiFetch<TaskInfo>(`/api/tasks/${taskId}/retry`, { method: "POST" });
}

export function prepareDouyinPublish(values: {
  session_id: string;
  platform: "douyin";
  video_path: string;
  title: string;
  description?: string;
  hashtags?: string[];
  cover_path?: string;
}) {
  return preparePlatformPublish(values);
}

export function preparePlatformPublish(values: {
  session_id: string;
  platform: PublishPlatform;
  video_path: string;
  title: string;
  description?: string;
  hashtags?: string[];
  cover_path?: string;
}) {
  return apiFetch<PublishResult>(`/api/publish/${values.platform}/prepare`, {
    method: "POST",
    body: JSON.stringify(values),
  });
}

export function getDesktopConfig() {
  return apiFetch<DesktopConfig>("/api/desktop/config");
}

export function saveDesktopConfig(config: Partial<DesktopConfig>) {
  return apiFetch<DesktopConfig>("/api/desktop/config", {
    method: "PATCH",
    body: JSON.stringify(config),
  });
}

export function getDiagnostics() {
  return apiFetch<DesktopDiagnostics>("/api/desktop/diagnostics");
}

export function checkDesktopConfig(config: Partial<DesktopConfig>) {
  return apiFetch<ConfigCheckResult>("/api/desktop/config/check", {
    method: "POST",
    body: JSON.stringify(config),
  });
}

export function synthesizeTtsPreview(values: {
  text: string;
  inference_mode: "local" | "comfyui";
  workflow?: string;
  voice?: string;
  speed?: number;
  pitch?: number | string;
  volume?: number | string;
}) {
  return apiFetch<TtsPreviewResult>("/api/tts/synthesize", {
    method: "POST",
    body: JSON.stringify(values),
  });
}

export function listVoiceAssets() {
  return apiFetch<{ items: VoiceAsset[] }>("/api/assets/voices");
}

export function uploadVoiceAsset(name: string, file: File) {
  const form = new FormData();
  form.set("name", name);
  form.set("file", file);
  return apiFetch<VoiceAsset>("/api/assets/voices", { method: "POST", body: form });
}

export function deleteVoiceAsset(referenceId: string) {
  return apiFetch<{ deleted: boolean }>(`/api/assets/voices/${referenceId}`, {
    method: "DELETE",
  });
}

export function listPortraitAssets() {
  return apiFetch<{ items: PortraitAsset[] }>("/api/assets/portraits");
}

export function uploadPortraitAsset(name: string, file: File) {
  const form = new FormData();
  form.set("name", name);
  form.set("file", file);
  return apiFetch<PortraitAsset>("/api/assets/portraits", { method: "POST", body: form });
}

export function deletePortraitAsset(portraitId: string) {
  return apiFetch<{ deleted: boolean }>(`/api/assets/portraits/${portraitId}`, {
    method: "DELETE",
  });
}

export function listVideoAssets() {
  return apiFetch<{ items: VideoAsset[] }>("/api/assets/videos");
}

export function uploadVideoAsset(name: string, file: File) {
  const form = new FormData();
  form.set("name", name);
  form.set("file", file);
  return apiFetch<VideoAsset>("/api/assets/videos", { method: "POST", body: form });
}

export function deleteVideoAsset(assetId: string) {
  return apiFetch<{ deleted: boolean }>(`/api/assets/videos/${assetId}`, {
    method: "DELETE",
  });
}

export function listImageAssets() {
  return apiFetch<{ items: ImageAsset[] }>("/api/assets/images");
}

export function uploadImageAsset(name: string, file: File) {
  const form = new FormData();
  form.set("name", name);
  form.set("file", file);
  return apiFetch<ImageAsset>("/api/assets/images", { method: "POST", body: form });
}

export function deleteImageAsset(assetId: string) {
  return apiFetch<{ deleted: boolean }>(`/api/assets/images/${assetId}`, {
    method: "DELETE",
  });
}

export function listMediaAssetsV2(kind: "image" | "video" | "audio") {
  const query = new URLSearchParams({ kind, limit: "500" });
  return apiFetch<{ items: AssetLibraryV2Item[]; total: number }>(
    `/api/v2/library/items?${query.toString()}`,
  );
}

export function listLibraryItemsV2(
  kind?: LibraryItemV2["kind"],
  query = "",
  options: { favorite?: boolean; tags?: string[]; sort?: "updated" | "recent" | "name"; includeArchived?: boolean; cursor?: string | null; limit?: number; offset?: number; collectionId?: string; recentlyUsed?: boolean; orientation?: "portrait" | "landscape" | "square"; aspect?: "portrait" | "landscape" | "square"; status?: string; source?: string; minDurationMs?: number; maxDurationMs?: number; signal?: AbortSignal } = {},
) {
  const params = new URLSearchParams({ limit: String(options.limit || 50) });
  if (kind) params.set("kind", kind);
  if (query) params.set("q", query);
  if (options.favorite !== undefined) params.set("favorite", String(options.favorite));
  for (const tag of options.tags || []) params.append("tags", tag);
  if (options.sort) params.set("sort", options.sort);
  if (options.includeArchived) params.set("include_archived", "true");
  if (options.cursor) params.set("cursor", options.cursor);
  if (options.offset) params.set("offset", String(options.offset));
  if (options.collectionId) params.set("collection_id", options.collectionId);
  if (options.recentlyUsed !== undefined) params.set("recently_used", String(options.recentlyUsed));
  if (options.orientation) params.set("orientation", options.orientation);
  if (options.aspect) params.set("aspect", options.aspect);
  if (options.status) params.set("status", options.status);
  if (options.source) params.set("source", options.source);
  if (options.minDurationMs !== undefined) params.set("min_duration_ms", String(options.minDurationMs));
  if (options.maxDurationMs !== undefined) params.set("max_duration_ms", String(options.maxDurationMs));
  return apiFetch<{ items: LibraryItemV2[]; total: number; next_cursor?: string | null; facets?: { kinds: Record<string, number>; statuses: Record<string, number>; tags: Record<string, number> } }>(
    `/api/v2/library/items?${params.toString()}`,
    { signal: options.signal },
  );
}

export function setLibraryFavoriteV2(kind: LibraryItemV2["kind"], resourceId: string, favorite: boolean) {
  return apiFetch<{ kind: string; resource_id: string; favorite: boolean }>(`/api/v2/library/items/${kind}/${resourceId}/favorite`, {
    method: "PUT",
    body: JSON.stringify({ favorite }),
  });
}

export function setLibraryTagsV2(kind: LibraryItemV2["kind"], resourceId: string, tags: string[]) {
  return apiFetch<{ kind: string; resource_id: string; tags: string[] }>(`/api/v2/library/items/${kind}/${resourceId}/tags`, {
    method: "PUT",
    body: JSON.stringify({ tags }),
  });
}

export function patchMediaAssetV2(assetId: string, payload: { name?: string; description?: string }) {
  return apiFetch<AssetLibraryV2Item>(`/api/v2/media-assets/${assetId}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export function archiveLibraryItemV2(kind: LibraryItemV2["kind"], resourceId: string) {
  return apiFetch<{ kind: string; resource_id: string; status: string }>(`/api/v2/library/${kind}/${resourceId}/archive`, { method: "POST" });
}

export function restoreLibraryItemV2(kind: LibraryItemV2["kind"], resourceId: string) {
  return apiFetch<{ kind: string; resource_id: string; status: string }>(`/api/v2/library/${kind}/${resourceId}/restore`, { method: "POST" });
}

export function createDigitalHumanV2(payload: {
  name: string;
  provider?: string;
  poster_asset_id?: string | null;
  source_asset_id?: string | null;
  source_revision_id?: string | null;
  gender?: string | null;
  style?: string | null;
  posture?: string | null;
  scene_name?: string;
  shot_size?: string;
  location?: string;
  outfit?: string;
}) {
  return apiFetch<LibraryItemV2>("/api/v2/domain/digital-humans", { method: "POST", body: JSON.stringify(payload) });
}

export function createDigitalHumanSceneV2(profileId: string, payload: {
  name: string;
  source_asset_id?: string | null;
  source_revision_id?: string | null;
  shot_size?: string;
  location?: string;
  outfit?: string;
  posture?: string;
}) {
  return apiFetch<Record<string, unknown>>(`/api/v2/domain/digital-humans/${profileId}/scenes`, { method: "POST", body: JSON.stringify(payload) });
}

export function patchDigitalHumanV2(profileId: string, payload: { name?: string; provider?: string; poster_asset_id?: string | null; gender?: string | null; style?: string | null; posture?: string | null; supported_workflows?: string[]; default_scene_id?: string | null; quality_state?: string; status?: string }) {
  return apiFetch<LibraryItemV2>(`/api/v2/domain/digital-humans/${encodeURIComponent(profileId)}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export function listDigitalHumanScenesV2(profileId: string) {
  return apiFetch<{ items: Array<Record<string, unknown>> }>(`/api/v2/domain/digital-humans/${encodeURIComponent(profileId)}/scenes`);
}

export function patchDigitalHumanSceneV2(sceneId: string, payload: { name?: string; source_asset_id?: string | null; source_revision_id?: string | null; shot_size?: string; location?: string; outfit?: string; posture?: string; status?: "ready" | "archived" }) {
  return apiFetch<Record<string, unknown>>(`/api/v2/domain/digital-human-scenes/${encodeURIComponent(sceneId)}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export function archiveDigitalHumanSceneV2(sceneId: string) {
  return apiFetch<Record<string, unknown>>(`/api/v2/domain/digital-human-scenes/${encodeURIComponent(sceneId)}/archive`, { method: "POST" });
}

export function reorderDigitalHumanScenesV2(profileId: string, sceneIds: string[]) {
  return apiFetch<{ items: Array<Record<string, unknown>> }>(`/api/v2/domain/digital-humans/${encodeURIComponent(profileId)}/scenes/reorder`, { method: "POST", body: JSON.stringify({ scene_ids: sceneIds }) });
}

export type BrandKitV2Payload = {
  brand_name?: string;
  logo_asset_id?: string | null;
  default_bgm_asset_id?: string | null;
  primary_color?: string;
  secondary_color?: string;
  font_family?: string;
  default_subtitle_style?: string;
  ending_card_text?: string;
  store_address?: string;
  phone?: string;
  coupon_phrase?: string;
};

export function createBrandKitV2(payload: {
  brand_name: string;
  logo_asset_id?: string | null;
  default_bgm_asset_id?: string | null;
  primary_color?: string;
  secondary_color?: string;
  font_family?: string;
  ending_card_text?: string;
  store_address?: string;
  phone?: string;
  coupon_phrase?: string;
}) {
  return apiFetch<LibraryItemV2>("/api/v2/domain/brands", { method: "POST", body: JSON.stringify(payload) });
}

export function patchBrandKitV2(brandId: string, payload: BrandKitV2Payload) {
  return apiFetch<LibraryItemV2>(`/api/v2/domain/brands/${encodeURIComponent(brandId)}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export function createTemplateV2(payload: {
  template_id?: string | null;
  display_name: string;
  short_description?: string;
  full_description?: string;
  renderer_version?: string;
  schema_version?: number;
  cover_contract?: Record<string, unknown>;
  subtitle_contract?: Record<string, unknown>;
  layout_contract?: Record<string, unknown>;
}) {
  return apiFetch<LibraryItemV2>("/api/v2/domain/templates", { method: "POST", body: JSON.stringify(payload) });
}

export function previewTemplateV2(draftContract: Record<string, unknown>, sample: Record<string, unknown> = {}) {
  return apiFetch<{ preview_url?: string | null; resolved_contract: Record<string, unknown>; resolved_fonts: Array<Record<string, unknown>>; layout_boxes: Record<string, unknown>; warnings: string[] }>("/api/v2/domain/templates/preview", { method: "POST", body: JSON.stringify({ draft_contract: draftContract, sample }) });
}

export function patchTemplateV2(templateId: string, payload: { display_name?: string; short_description?: string; full_description?: string; preview_url?: string | null; schema_version?: number; renderer_version?: string; cover_contract?: Record<string, unknown>; subtitle_contract?: Record<string, unknown>; layout_contract?: Record<string, unknown>; status?: string }) {
  return apiFetch<LibraryItemV2>(`/api/v2/domain/templates/${encodeURIComponent(templateId)}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export function createVoiceProfileV2(payload: { name: string; audio_asset_id: string; audio_revision_id?: string | null; language?: string; style?: string; authorization_status?: string }) {
  return apiFetch<LibraryItemV2>("/api/v2/domain/voices", { method: "POST", body: JSON.stringify(payload) });
}

export function archiveVoiceProfileV2(voiceId: string) {
  return apiFetch<LibraryItemV2>(`/api/v2/domain/voices/${voiceId}/archive`, { method: "POST" });
}

export function restoreVoiceProfileV2(voiceId: string) {
  return apiFetch<LibraryItemV2>(`/api/v2/domain/voices/${voiceId}/restore`, { method: "POST" });
}

export function listLibraryFacetsV2(kind?: LibraryItemV2["kind"], options: { query?: string; includeArchived?: boolean; favorite?: boolean; recentlyUsed?: boolean; collectionId?: string; aspect?: "portrait" | "landscape" | "square"; status?: string; source?: string; signal?: AbortSignal } = {}) {
  const params = new URLSearchParams();
  if (kind) params.set("kind", kind);
  if (options.query) params.set("q", options.query);
  if (options.includeArchived) params.set("include_archived", "true");
  if (options.favorite !== undefined) params.set("favorite", String(options.favorite));
  if (options.recentlyUsed !== undefined) params.set("recently_used", String(options.recentlyUsed));
  if (options.collectionId) params.set("collection_id", options.collectionId);
  if (options.aspect) params.set("aspect", options.aspect);
  if (options.status) params.set("status", options.status);
  if (options.source) params.set("source", options.source);
  const query = params.toString() ? `?${params.toString()}` : "";
  return apiFetch<{ kinds: Record<string, number>; statuses: Record<string, number>; tags: Record<string, number> }>(`/api/v2/library/facets${query}`, { signal: options.signal });
}

export function bulkLibraryActionV2(payload: { action: "archive" | "restore" | "favorite" | "unfavorite" | "tag" | "untag"; items: Array<{ kind: LibraryItemV2["kind"]; resource_id: string }>; tags?: string[] }) {
  return apiFetch<{ items: Array<{ kind: string; resource_id: string; ok: boolean; error?: string }>; succeeded: number; failed: number }>("/api/v2/library/bulk", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function listAssetCollectionsV2() {
  return apiFetch<{ items: AssetCollectionV2[] }>("/api/v2/collections");
}

export function createAssetCollectionV2(payload: { name: string; description?: string }) {
  return apiFetch<AssetCollectionV2>("/api/v2/collections", { method: "POST", body: JSON.stringify(payload) });
}

export function patchAssetCollectionV2(collectionId: string, payload: { name?: string; description?: string }) {
  return apiFetch<AssetCollectionV2>(`/api/v2/collections/${encodeURIComponent(collectionId)}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export function archiveAssetCollectionV2(collectionId: string) {
  return apiFetch<AssetCollectionV2>(`/api/v2/collections/${encodeURIComponent(collectionId)}/archive`, { method: "POST" });
}

export function deleteAssetCollectionV2(collectionId: string) {
  return apiFetch<{ deleted: boolean }>(`/api/v2/collections/${encodeURIComponent(collectionId)}`, { method: "DELETE" });
}

export function listAssetCollectionItemsV2(collectionId: string) {
  return apiFetch<{ items: Array<{ collection_id: string; resource_kind: LibraryItemV2["kind"]; resource_id: string }> }>(`/api/v2/collections/${encodeURIComponent(collectionId)}/items`);
}

export function addAssetCollectionItemV2(collectionId: string, kind: LibraryItemV2["kind"], resourceId: string) {
  const params = new URLSearchParams({ kind, resource_id: resourceId });
  return apiFetch<{ collection_id: string; kind: string; resource_id: string }>(`/api/v2/collections/${encodeURIComponent(collectionId)}/items?${params.toString()}`, { method: "POST" });
}

export function removeAssetCollectionItemV2(collectionId: string, kind: LibraryItemV2["kind"], resourceId: string) {
  return apiFetch<{ deleted: boolean }>(`/api/v2/collections/${encodeURIComponent(collectionId)}/items/${encodeURIComponent(kind)}/${encodeURIComponent(resourceId)}`, { method: "DELETE" });
}

export function listResourceUsageV2(kind: string, resourceId: string) {
  return apiFetch<{ items: Array<Record<string, unknown>> }>(`/api/v2/library/${kind}/${resourceId}/usage`);
}

export function reconcileSessionResourceUsageV2(sessionId: string, references: Array<{ resource_kind: string; resource_id: string; revision_id?: string | null; step: string; purpose: string; slot_id: string }>) {
  return apiFetch<{ desired: number; written: number }>(`/api/v2/sessions/${sessionId}/reconcile`, {
    method: "POST",
    body: JSON.stringify({ references }),
  });
}

export async function createMediaAssetRevisionV2(assetId: string, file: File, onProgress?: (percentage: number) => void) {
  const { apiBaseUrl, desktopToken } = await getRuntime();
  return new Promise<AssetLibraryV2Item>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", apiUrl(apiBaseUrl, `/api/v2/media-assets/${assetId}/revisions?filename=${encodeURIComponent(file.name)}`));
    xhr.setRequestHeader("Content-Type", file.type || "application/octet-stream");
    xhr.setRequestHeader("X-Filename", file.name);
    if (desktopToken) xhr.setRequestHeader("X-Pixelle-Desktop-Token", desktopToken);
    xhr.upload.onprogress = (event) => { if (event.lengthComputable) onProgress?.(Math.round((event.loaded / event.total) * 100)); };
    xhr.onerror = () => reject(new Error("网络错误，版本上传未完成"));
    xhr.onload = () => {
      if (xhr.status < 200 || xhr.status >= 300) { reject(new Error(xhr.responseText || `版本上传失败（${xhr.status}）`)); return; }
      try { resolve(JSON.parse(xhr.responseText) as AssetLibraryV2Item); } catch { reject(new Error("服务端返回了无效的版本结果")); }
    };
    xhr.send(file);
  });
}

export function activateMediaAssetRevisionV2(assetId: string, revisionId: string) {
  return apiFetch<AssetLibraryV2Item>(`/api/v2/media-assets/${assetId}/revisions/${revisionId}/activate`, { method: "POST" });
}

export function retryMediaAssetAnalysisV2(assetId: string, revisionId?: string) {
  const query = revisionId ? `?revision_id=${encodeURIComponent(revisionId)}` : "";
  return apiFetch<AssetLibraryV2Item>(`/api/v2/media-assets/${assetId}/analysis/retry${query}`, { method: "POST" });
}

export function listMediaAssetRevisionsV2(assetId: string) {
  return apiFetch<{ items: Array<{ revision_id: string; version: number; sha256: string; bytes: number; created_at: string }> }>(`/api/v2/media-assets/${assetId}/revisions`);
}

export function cancelMediaUploadV2(uploadId: string) {
  return apiFetch<{ upload_id: string; status: string }>(`/api/v2/uploads/${uploadId}/cancel`, { method: "POST" });
}

export function finalizeDeferredMediaUploadV2(uploadId: string, duplicatePolicy?: "reuse_existing" | "attach_revision" | "create_separate", targetAssetId?: string) {
  return apiFetch<AssetLibraryV2Upload>(`/api/v2/uploads/${uploadId}/finalize`, {
    method: "POST",
    body: JSON.stringify({ ...(duplicatePolicy ? { duplicate_policy: duplicatePolicy } : {}), ...(targetAssetId ? { target_asset_id: targetAssetId } : {}) }),
  });
}

export async function uploadDeferredMediaAssetV2(
  kind: "image" | "video" | "audio",
  name: string,
  file: File,
  onProgress?: (percentage: number) => void,
  onUploadId?: (uploadId: string) => void,
  signal?: AbortSignal,
): Promise<{ upload: { upload_id: string; status: string; duplicate_asset_id?: string | null; [key: string]: unknown }; asset?: AssetLibraryV2Item; duplicate_asset?: AssetLibraryV2Item }> {
  const created = await apiFetch<{ upload_id: string }>("/api/v2/uploads", {
    method: "POST",
    body: JSON.stringify({ filename: file.name, declared_bytes: file.size, target_kind: kind, name: name || file.name, deferred: true, idempotency_key: `desktop-${crypto.randomUUID()}` }),
  });
  onUploadId?.(created.upload_id);
  const { apiBaseUrl, desktopToken } = await getRuntime();
  const result = await new Promise<AssetLibraryV2Upload>( (resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", apiUrl(apiBaseUrl, `/api/v2/uploads/${created.upload_id}/content`));
    xhr.setRequestHeader("Content-Type", file.type || "application/octet-stream");
    if (desktopToken) xhr.setRequestHeader("X-Pixelle-Desktop-Token", desktopToken);
    xhr.upload.onprogress = (event) => { if (event.lengthComputable) onProgress?.(Math.round((event.loaded / event.total) * 100)); };
    xhr.onerror = () => reject(new Error("网络错误，上传未完成"));
    xhr.onabort = () => reject(new Error("上传已取消"));
    signal?.addEventListener("abort", () => xhr.abort(), { once: true });
    xhr.onload = () => { if (xhr.status < 200 || xhr.status >= 300) { reject(new Error(formatHttpErrorDetail(xhr.status, xhr.responseText, `上传失败（${xhr.status}）`))); return; } try { resolve(JSON.parse(xhr.responseText) as AssetLibraryV2Upload); } catch { reject(new Error("服务端返回了无效的上传结果")); } };
    xhr.send(file);
  });
  return result;
}

export async function uploadMediaAssetV2(
  kind: "image" | "video" | "audio",
  name: string,
  file: File,
  onProgress?: (percentage: number) => void,
  onUploadId?: (uploadId: string) => void,
  signal?: AbortSignal,
): Promise<AssetLibraryV2Item> {
  const created = await apiFetch<{ upload_id: string }>("/api/v2/uploads", {
    method: "POST",
    body: JSON.stringify({
      filename: file.name,
      declared_bytes: file.size,
      target_kind: kind,
      name: name || file.name,
    }),
  });
  onUploadId?.(created.upload_id);
  const { apiBaseUrl, desktopToken } = await getRuntime();
  const headers = new Headers({
    "Content-Type": file.type || "application/octet-stream",
  });
  if (desktopToken) headers.set("X-Pixelle-Desktop-Token", desktopToken);
  const result = await new Promise<AssetLibraryV2Upload>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", apiUrl(apiBaseUrl, `/api/v2/uploads/${created.upload_id}/content`));
    headers.forEach((value, key) => xhr.setRequestHeader(key, value));
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress?.(Math.round((event.loaded / event.total) * 100));
    };
    xhr.onerror = () => reject(new Error("网络错误，上传未完成"));
    xhr.onabort = () => reject(new Error("上传已取消"));
    signal?.addEventListener("abort", () => xhr.abort(), { once: true });
    xhr.onload = () => {
      if (xhr.status < 200 || xhr.status >= 300) {
        reject(new Error(formatHttpErrorDetail(xhr.status, xhr.responseText, `上传失败（${xhr.status}）`)));
        return;
      }
      try {
        resolve(JSON.parse(xhr.responseText) as AssetLibraryV2Upload);
      } catch {
        reject(new Error("服务端返回了无效的上传结果"));
      }
    };
    xhr.send(file);
  });
  const asset = result.asset || result.duplicate_asset;
  if (!asset) throw new Error("上传已完成，但服务端没有返回素材记录");
  return asset;
}

export function archiveMediaAssetV2(assetId: string) {
  return apiFetch<{ asset_id: string; status: string }>(`/api/v2/media-assets/${assetId}/archive`, {
    method: "POST",
  });
}

export function listIpTemplateAssets() {
  return apiFetch<{ items: IpTemplateAsset[] }>("/api/assets/templates/ip-broadcast");
}

export function listIpPresetAssets() {
  return apiFetch<{ items: IpPresetAsset[] }>("/api/assets/presets/ip-broadcast");
}

export function listBrandKits() {
  return apiFetch<{ items: BrandKit[] }>("/api/assets/brand-kits");
}

export function listBgm() {
  return apiFetch<{ success: boolean; message: string; bgm_files: BgmAsset[] }>("/api/resources/bgm");
}

export function createBrandKit(values: Partial<BrandKit>) {
  return apiFetch<BrandKit>("/api/assets/brand-kits", {
    method: "POST",
    body: JSON.stringify(values),
  });
}

export function updateBrandKit(brandId: string, values: Partial<BrandKit>) {
  return apiFetch<BrandKit>(`/api/assets/brand-kits/${brandId}`, {
    method: "PATCH",
    body: JSON.stringify(values),
  });
}

export function deleteBrandKit(brandId: string) {
  return apiFetch<{ deleted: boolean }>(`/api/assets/brand-kits/${brandId}`, {
    method: "DELETE",
  });
}

export async function assetUrl(path: string) {
  const { apiBaseUrl } = await getRuntime();
  return apiUrl(apiBaseUrl, path);
}

export async function assetBlobUrl(path: string) {
  const { apiBaseUrl, desktopToken } = await getRuntime();
  const headers = new Headers();
  if (desktopToken) {
    headers.set("X-Pixelle-Desktop-Token", desktopToken);
  }
  const response = await fetch(apiUrl(apiBaseUrl, path), { headers });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return URL.createObjectURL(await response.blob());
}

export async function artifactBlobUrl(sessionId: string, artifactKey: string) {
  const { apiBaseUrl, desktopToken } = await getRuntime();
  const headers = new Headers();
  if (desktopToken) {
    headers.set("X-Pixelle-Desktop-Token", desktopToken);
  }
  const response = await fetch(
    apiUrl(apiBaseUrl, `/api/ip-broadcast/sessions/${sessionId}/artifacts/${artifactKey}`),
    { headers },
  );
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return URL.createObjectURL(await response.blob());
}

export async function downloadArtifact(sessionId: string, artifactKey: string) {
  const { apiBaseUrl, desktopToken } = await getRuntime();
  const headers = new Headers();
  if (desktopToken) {
    headers.set("X-Pixelle-Desktop-Token", desktopToken);
  }
  const response = await fetch(
    apiUrl(apiBaseUrl, `/api/ip-broadcast/sessions/${sessionId}/artifacts/${artifactKey}`),
    { headers },
  );
  if (!response.ok) {
    throw new Error(await response.text());
  }
  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition") || "";
  const filename = disposition.match(/filename="?([^"]+)"?/)?.[1] || `${artifactKey}.mp4`;
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}
