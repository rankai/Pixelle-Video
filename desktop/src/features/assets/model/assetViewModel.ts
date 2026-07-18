import type { LibraryItemV2 } from "../../../api";
import type { AssetViewModel } from "./ux0Contracts";

const numberValue = (item: LibraryItemV2, key: string) => Number(item.summary[key] || 0);

/** Converts API projections into the discriminated view model used by cards.
 * Unknown summary keys stay available to the advanced diagnostics panel only.
 */
export function toAssetViewModel(item: LibraryItemV2): AssetViewModel {
  const base = {
    resource_id: item.resource_id,
    kind: item.kind,
    name: item.name,
    description: item.description || "",
    status: (item.status || "ready") as AssetViewModel["status"],
    cover_url: item.cover_url || undefined,
    tags: item.tags || [],
    favorite: Boolean(item.favorite),
    last_used_at: item.last_used_at || undefined,
    capabilities: item.capabilities || ["preview", "use", "favorite"],
  };
  switch (item.kind) {
    case "image":
      return { ...base, kind: "image", display: { width: numberValue(item, "width"), height: numberValue(item, "height"), aspect_ratio: numberValue(item, "aspect_ratio") || 0, transparent: Boolean(item.summary.transparent), purpose: typeof item.summary.purpose === "string" ? item.summary.purpose : undefined } };
    case "video":
      return { ...base, kind: "video", display: { duration_ms: numberValue(item, "duration_ms"), width: numberValue(item, "width"), height: numberValue(item, "height"), aspect_ratio: numberValue(item, "aspect_ratio") || 0, has_audio: Boolean(item.summary.has_audio) } };
    case "audio":
      return { ...base, kind: "audio", display: { duration_ms: numberValue(item, "duration_ms"), purpose: typeof item.summary.purpose === "string" ? item.summary.purpose : undefined, authorization_status: typeof item.summary.authorization_status === "string" ? item.summary.authorization_status : undefined } };
    case "voice":
      return { ...base, kind: "voice", display: { language: String(item.voice_profile?.language || item.summary.language || "未设置"), style: String(item.voice_profile?.style || item.summary.style || "未设置"), reference_duration_ms: numberValue(item, "reference_duration_ms"), authorization_status: String(item.voice_profile?.authorization_status || item.summary.authorization_status || "unknown") } };
    case "digital_human":
      return { ...base, kind: "digital_human", display: { scene_count: item.scenes?.length || 0, default_scene_id: typeof item.summary.default_scene_id === "string" ? item.summary.default_scene_id : undefined, media_types: Array.from(new Set((item.scenes || []).map((scene) => scene.preview_media_type).filter((value): value is "image" | "video" => value === "image" || value === "video"))) } };
    case "template":
      return { ...base, kind: "template", display: { canvas_width: numberValue(item, "canvas_width"), canvas_height: numberValue(item, "canvas_height"), subtitle_layout: String(item.summary.subtitle_layout || "标准字幕"), cover_layout: String(item.summary.cover_layout || "标准封面"), revision: numberValue(item, "revision") || Number(item.template?.revision || 1) } };
    case "brand":
      return { ...base, kind: "brand", display: { has_logo: Boolean(item.brand?.logo_asset_id), has_bgm: Boolean(item.brand?.default_bgm_asset_id), has_contact: Boolean(item.summary.has_contact), primary_color: String(item.summary.primary_color || ""), secondary_color: String(item.summary.secondary_color || "") } };
  }
}

