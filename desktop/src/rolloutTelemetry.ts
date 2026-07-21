export type RolloutTelemetryEvent =
  | "publish_center_viewed"
  | "publish_center_fallback"
  | "publish_run_state_seen"
  | "rollout_flag_resolved";

export type RolloutTelemetryPayload = Partial<{
  platform: string;
  adapter_version: string;
  step: string;
  error_code: string;
  duration_bucket: string;
  app_version: string;
}>;

export const ROLLOUT_TELEMETRY_ALLOWLIST = [
  "platform",
  "adapter_version",
  "step",
  "error_code",
  "duration_bucket",
  "app_version",
] as const;

const STORAGE_KEY = "pixelle.rollout.telemetry.v1";

export function sanitizeRolloutTelemetry(
  event: RolloutTelemetryEvent,
  payload: RolloutTelemetryPayload = {},
): Record<string, string> {
  const result: Record<string, string> = { event };
  for (const key of ROLLOUT_TELEMETRY_ALLOWLIST) {
    const value = payload[key];
    if (typeof value === "string" && value.length <= 120) result[key] = value;
  }
  return result;
}

/** Content-free, local-only telemetry. It never uploads or logs raw payloads. */
export function recordRolloutTelemetry(event: RolloutTelemetryEvent, payload: RolloutTelemetryPayload = {}) {
  if (typeof window === "undefined") return;
  try {
    const current = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "[]") as Array<Record<string, string>>;
    current.push({ ...sanitizeRolloutTelemetry(event, payload), at: new Date().toISOString() });
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(current.slice(-500)));
  } catch {
    // Telemetry must never affect the publishing workflow.
  }
}

export function readRolloutTelemetry(): Array<Record<string, string>> {
  if (typeof window === "undefined") return [];
  try {
    const value = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "[]");
    return Array.isArray(value) ? value : [];
  } catch {
    return [];
  }
}
