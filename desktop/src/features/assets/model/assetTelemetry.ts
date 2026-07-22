type AssetTelemetryEvent =
  | "asset_search_started"
  | "asset_result_selected"
  | "asset_upload_started"
  | "asset_upload_succeeded"
  | "asset_upload_failed"
  | "asset_upload_retried"
  | "asset_upload_cancelled"
  | "asset_duplicate_resolved"
  | "asset_preview_opened"
  | "asset_picker_opened"
  | "asset_picker_confirmed"
  | "asset_picker_incompatible_seen"
  | "asset_picker_cancelled"
  | "asset_applied_to_production"
  | "asset_archived"
  | "asset_restored"
  | "digital_human_scene_previewed"
  | "digital_human_scene_confirmed";

type TelemetryPayload = { kind?: string; entry?: "center" | "picker"; duration_bucket?: string; failure_code?: string };
const STORAGE_KEY = "pixelle.asset.telemetry.v1";

/** Local, content-free product telemetry for rollout comparison. */
export function recordAssetTelemetry(event: AssetTelemetryEvent, payload: TelemetryPayload = {}) {
  try {
    const current = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "[]") as Array<Record<string, unknown>>;
    current.push({ event, ...payload, at: new Date().toISOString() });
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(current.slice(-500)));
  } catch {
    // Telemetry must never affect asset work.
  }
}
