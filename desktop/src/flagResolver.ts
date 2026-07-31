export type FeatureFlagEnv = Record<string, unknown>;

export type ResolvedFeatureFlags = {
  appCenterShell: boolean;
  contentProjects: boolean;
  contentApps: boolean;
  douyinCarousel: boolean;
  digitalHumanInAppCenter: boolean;
  digitalHumanDualModeV2: boolean;
  appWorkbenchV2: boolean;
  appWorkbenchTextV2: boolean;
  appWorkbenchCarouselV2: boolean;
  appWorkbenchDigitalHumanV2: boolean;
  appCenterNewNav: boolean;
  publishCenterV2: boolean;
  assetCenterV2: boolean;
  assetCenterSmbUx: boolean;
  brandProjectBoundaryV1: boolean;
  appResultHistoryV1: boolean;
};

export type RuntimeFeatureFlags = {
  brandProjectBoundaryV1: boolean;
  appResultHistoryV1: boolean;
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
    digitalHumanDualModeV2: readCanonicalWithAliases(
      env,
      "VITE_APP_CENTER_DIGITAL_HUMAN_DUAL_MODE",
      ["VITE_DIGITAL_HUMAN_DUAL_MODE_V2"],
      false,
    ),
    appWorkbenchV2: readCanonicalWithAliases(
      env,
      "VITE_APP_WORKBENCH_V2",
      ["PIXELLE_APP_WORKBENCH_V2"],
      false,
    ),
    appWorkbenchTextV2: readCanonicalWithAliases(
      env,
      "VITE_APP_WORKBENCH_TEXT_V2",
      ["PIXELLE_APP_WORKBENCH_TEXT_V2"],
      false,
    ),
    appWorkbenchCarouselV2: readCanonicalWithAliases(
      env,
      "VITE_APP_WORKBENCH_CAROUSEL_V2",
      ["PIXELLE_APP_WORKBENCH_CAROUSEL_V2"],
      false,
    ),
    appWorkbenchDigitalHumanV2: readCanonicalWithAliases(
      env,
      "VITE_APP_WORKBENCH_DIGITAL_HUMAN_V2",
      ["PIXELLE_APP_WORKBENCH_DIGITAL_HUMAN_V2"],
      false,
    ),
    appCenterNewNav: readFlag(env, "VITE_APP_CENTER_NEW_NAV", false),
    publishCenterV2: readCanonicalWithAliases(env, "VITE_PUBLISH_CENTER_V2", ["VITE_PUBLISH_V2_ENABLED"], false),
    assetCenterV2: readFlag(env, "VITE_ASSET_CENTER_V2", true),
    assetCenterSmbUx: readFlag(env, "VITE_ASSET_CENTER_SMB_UX", false),
    brandProjectBoundaryV1: readCanonicalWithAliases(
      env,
      "VITE_BRAND_PROJECT_BOUNDARY_V1",
      ["PIXELLE_BRAND_PROJECT_BOUNDARY_V1"],
      false,
    ),
    appResultHistoryV1: readCanonicalWithAliases(
      env,
      "VITE_APP_RESULT_HISTORY_V1",
      ["PIXELLE_APP_RESULT_HISTORY_V1"],
      false,
    ),
  };
}

export function mergeRuntimeFeatureFlags(
  buildFlags: ResolvedFeatureFlags,
  runtimeFlags: RuntimeFeatureFlags,
): ResolvedFeatureFlags {
  return {
    ...buildFlags,
    // A runtime override may only narrow a capability compiled into the
    // desktop bundle. This keeps browser development controlled by Vite
    // flags while allowing the packaged Tauri app to roll the brand/project
    // workflow back together with its FastAPI sidecar.
    brandProjectBoundaryV1:
      buildFlags.brandProjectBoundaryV1 && runtimeFlags.brandProjectBoundaryV1 === true,
    appResultHistoryV1:
      buildFlags.appResultHistoryV1 && runtimeFlags.appResultHistoryV1 === true,
  };
}
