import { describe, expect, it } from "vitest";

import { resolveFeatureFlags } from "./flagResolver";

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
});
