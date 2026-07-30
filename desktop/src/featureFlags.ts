/** Build flags narrowed by the packaged desktop runtime. */

import {
  mergeRuntimeFeatureFlags,
  resolveFeatureFlags,
  type RuntimeFeatureFlags,
} from "./flagResolver";

const buildFeatureFlags = resolveFeatureFlags(import.meta.env);

export let featureFlags = buildFeatureFlags;

export function applyRuntimeFeatureFlags(runtimeFlags: RuntimeFeatureFlags) {
  featureFlags = mergeRuntimeFeatureFlags(buildFeatureFlags, runtimeFlags);
  return featureFlags;
}
