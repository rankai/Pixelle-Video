export type FeatureFlagEnv = Record<string, unknown>;

export type ResolvedFeatureFlags = {
  appCenterShell: boolean;
  contentProjects: boolean;
  contentApps: boolean;
  douyinCarousel: boolean;
  digitalHumanInAppCenter: boolean;
  appCenterNewNav: boolean;
  publishCenterV2: boolean;
  assetCenterV2: boolean;
  assetCenterSmbUx: boolean;
};

const TRUE_VALUES = new Set(["1", "true", "yes", "on"]);
const FALSE_VALUES = new Set(["0", "false", "no", "off"]);

function parseFlag(value: unknown): boolean {
  if (typeof value !== "string") return false;
  const normalized = value.trim().toLowerCase();
  if (TRUE_VALUES.has(normalized)) return true;
  if (FALSE_VALUES.has(normalized)) return false;
  return false;
}

function readFlag(env: FeatureFlagEnv, name: string, fallback: boolean): boolean {
  return Object.prototype.hasOwnProperty.call(env, name) ? parseFlag(env[name]) : fallback;
}

function readCanonicalWithAliases(
  env: FeatureFlagEnv,
  canonical: string,
  aliases: string[],
  fallback: boolean,
): boolean {
  const configured = [canonical, ...aliases]
    .filter((name) => Object.prototype.hasOwnProperty.call(env, name))
    .map((name) => parseFlag(env[name]));
  if (configured.length === 0) return fallback;
  // Conflicting aliases are unsafe: do not let build-time precedence silently
  // enable a rollout. Returning false preserves the legacy-safe path.
  if (new Set(configured).size > 1) return false;
  return configured[0];
}

export function resolveFeatureFlags(env: FeatureFlagEnv): ResolvedFeatureFlags {
  return {
    appCenterShell: readFlag(env, "VITE_APP_CENTER_SHELL", false),
    contentProjects: readFlag(env, "VITE_CONTENT_PROJECTS", false),
    contentApps: readFlag(env, "VITE_CONTENT_APPS", false),
    douyinCarousel: readFlag(env, "VITE_DOUYIN_CAROUSEL", false),
    digitalHumanInAppCenter: readCanonicalWithAliases(
      env,
      "VITE_APP_CENTER_DIGITAL_HUMAN",
      ["VITE_DIGITAL_HUMAN_IN_APP_CENTER"],
      false,
    ),
    appCenterNewNav: readFlag(env, "VITE_APP_CENTER_NEW_NAV", false),
    publishCenterV2: readCanonicalWithAliases(env, "VITE_PUBLISH_CENTER_V2", ["VITE_PUBLISH_V2_ENABLED"], false),
    assetCenterV2: readFlag(env, "VITE_ASSET_CENTER_V2", true),
    assetCenterSmbUx: readFlag(env, "VITE_ASSET_CENTER_SMB_UX", false),
  };
}
