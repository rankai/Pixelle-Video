/** Runtime feature flags. Unknown/conflicting aliases fail closed. */

import { resolveFeatureFlags } from "./flagResolver";

export const featureFlags = resolveFeatureFlags(import.meta.env);
