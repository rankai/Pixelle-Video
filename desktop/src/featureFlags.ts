/** Runtime feature flags. SMB UX stays off until the UX-E evidence review. */

function envFlag(value: unknown, fallback = false): boolean {
  if (typeof value !== "string") return fallback;
  return ["1", "true", "yes", "on"].includes(value.trim().toLowerCase());
}

export const featureFlags = {
  assetCenterV2: envFlag(import.meta.env.VITE_ASSET_CENTER_V2, true),
  assetCenterSmbUx: envFlag(import.meta.env.VITE_ASSET_CENTER_SMB_UX, false),
} as const;
