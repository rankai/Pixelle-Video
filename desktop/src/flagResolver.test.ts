import { describe, expect, it } from "vitest";

import { mergeRuntimeFeatureFlags, resolveFeatureFlags } from "./flagResolver";

describe("resolveFeatureFlags", () => {
  it("uses canonical names and preserves safe defaults", () => {
    expect(resolveFeatureFlags({
      VITE_APP_CENTER_SHELL: "true",
      VITE_PUBLISH_CENTER_V2: "true",
    })).toMatchObject({
      appCenterShell: true,
      publishCenterV2: true,
      contentApps: false,
      digitalHumanInAppCenter: false,
      appWorkbenchV2: false,
      appWorkbenchTextV2: false,
      appWorkbenchCarouselV2: false,
      appWorkbenchDigitalHumanV2: false,
      appResultHistoryV1: false,
      assetCenterV2: true,
    });
  });

  it("normalizes documented aliases when the canonical name is absent", () => {
    expect(resolveFeatureFlags({
      VITE_DIGITAL_HUMAN_IN_APP_CENTER: "on",
      VITE_PUBLISH_V2_ENABLED: "1",
    })).toMatchObject({
      digitalHumanInAppCenter: true,
      publishCenterV2: true,
    });
  });

  it("fails closed when canonical and alias values conflict", () => {
    expect(resolveFeatureFlags({
      VITE_PUBLISH_CENTER_V2: "true",
      VITE_PUBLISH_V2_ENABLED: "false",
      VITE_APP_CENTER_DIGITAL_HUMAN: "true",
      VITE_DIGITAL_HUMAN_IN_APP_CENTER: "false",
    })).toMatchObject({
      publishCenterV2: false,
      digitalHumanInAppCenter: false,
    });
  });

  it("fails closed for unknown values", () => {
    expect(resolveFeatureFlags({ VITE_PUBLISH_CENTER_V2: "maybe" }).publishCenterV2).toBe(false);
    expect(resolveFeatureFlags({ VITE_APP_WORKBENCH_V2: "maybe" }).appWorkbenchV2).toBe(false);
  });

  it("resolves application workbench flags and rejects conflicting rollout aliases", () => {
    expect(resolveFeatureFlags({
      VITE_APP_WORKBENCH_V2: "true",
      VITE_APP_WORKBENCH_TEXT_V2: "1",
      VITE_APP_WORKBENCH_CAROUSEL_V2: "on",
      VITE_APP_WORKBENCH_DIGITAL_HUMAN_V2: "yes",
    })).toMatchObject({
      appWorkbenchV2: true,
      appWorkbenchTextV2: true,
      appWorkbenchCarouselV2: true,
      appWorkbenchDigitalHumanV2: true,
    });
    expect(resolveFeatureFlags({
      VITE_APP_WORKBENCH_V2: "true",
      PIXELLE_APP_WORKBENCH_V2: "false",
    }).appWorkbenchV2).toBe(false);
  });

  it("resolves result history only from a consistent canonical or alias value", () => {
    expect(resolveFeatureFlags({
      VITE_APP_RESULT_HISTORY_V1: "true",
    }).appResultHistoryV1).toBe(true);
    expect(resolveFeatureFlags({
      PIXELLE_APP_RESULT_HISTORY_V1: "on",
    }).appResultHistoryV1).toBe(true);
    expect(resolveFeatureFlags({
      VITE_APP_RESULT_HISTORY_V1: "true",
      PIXELLE_APP_RESULT_HISTORY_V1: "false",
    }).appResultHistoryV1).toBe(false);
  });

  it("fails closed for present non-string values, including the true-default asset flag", () => {
    expect(resolveFeatureFlags({ VITE_ASSET_CENTER_V2: 123 }).assetCenterV2).toBe(false);
    expect(resolveFeatureFlags({ VITE_ASSET_CENTER_V2: null }).assetCenterV2).toBe(false);
    expect(resolveFeatureFlags({ VITE_ASSET_CENTER_V2: undefined }).assetCenterV2).toBe(false);
  });

  it("does not ignore an invalid canonical value when an alias is enabled", () => {
    expect(resolveFeatureFlags({
      VITE_PUBLISH_CENTER_V2: { enabled: true },
      VITE_PUBLISH_V2_ENABLED: "true",
    }).publishCenterV2).toBe(false);
  });

  it("keeps the packaged brand-project flag aligned with the desktop runtime", () => {
    const enabledBuild = resolveFeatureFlags({
      VITE_BRAND_PROJECT_BOUNDARY_V1: "true",
    });
    expect(mergeRuntimeFeatureFlags(enabledBuild, {
      brandProjectBoundaryV1: true,
      appResultHistoryV1: false,
    }).brandProjectBoundaryV1).toBe(true);
    expect(mergeRuntimeFeatureFlags(enabledBuild, {
      brandProjectBoundaryV1: false,
      appResultHistoryV1: false,
    }).brandProjectBoundaryV1).toBe(false);
  });

  it("never lets the desktop runtime enable a capability absent from the bundle", () => {
    const disabledBuild = resolveFeatureFlags({
      VITE_BRAND_PROJECT_BOUNDARY_V1: "false",
    });
    expect(mergeRuntimeFeatureFlags(disabledBuild, {
      brandProjectBoundaryV1: true,
      appResultHistoryV1: false,
    }).brandProjectBoundaryV1).toBe(false);
  });

  it("keeps packaged result history aligned with the sidecar runtime", () => {
    const enabledBuild = resolveFeatureFlags({
      VITE_APP_RESULT_HISTORY_V1: "true",
    });
    const enabled = mergeRuntimeFeatureFlags(enabledBuild, {
      brandProjectBoundaryV1: false,
      appResultHistoryV1: true,
    });
    const disabled = mergeRuntimeFeatureFlags(enabledBuild, {
      brandProjectBoundaryV1: false,
      appResultHistoryV1: false,
    });
    const enabledAgain = mergeRuntimeFeatureFlags(enabledBuild, {
      brandProjectBoundaryV1: false,
      appResultHistoryV1: true,
    });

    expect([
      enabled.appResultHistoryV1,
      disabled.appResultHistoryV1,
      enabledAgain.appResultHistoryV1,
    ]).toEqual([true, false, true]);
  });
});
