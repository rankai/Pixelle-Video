import { beforeEach, describe, expect, it } from "vitest";

import { readRolloutTelemetry, recordRolloutTelemetry, sanitizeRolloutTelemetry } from "./rolloutTelemetry";

describe("rolloutTelemetry", () => {
  beforeEach(() => window.localStorage.clear());

  it("keeps only the content-free allowlist", () => {
    expect(sanitizeRolloutTelemetry("publish_run_state_seen", {
      platform: "douyin",
      step: "verify",
      title: "不应记录",
      account_id: "不应记录",
      signed_url: "不应记录",
    } as never)).toEqual({ platform: "douyin", step: "verify", event: "publish_run_state_seen" });
  });

  it("stores local bounded events and never needs a network client", () => {
    recordRolloutTelemetry("publish_center_viewed", { platform: "douyin", app_version: "0.1.0" });
    const events = readRolloutTelemetry();
    expect(events).toHaveLength(1);
    expect(events[0]).toMatchObject({ event: "publish_center_viewed", platform: "douyin", app_version: "0.1.0" });
    expect(events[0]).not.toHaveProperty("account_id");
  });
});
