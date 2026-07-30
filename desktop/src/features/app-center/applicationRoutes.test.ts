import { describe, expect, it } from "vitest";

import { applicationIdForRoute, applicationRouteForId } from "./applicationRoutes";

describe("application routes", () => {
  it("keeps every built-in application on its dedicated workbench route", () => {
    expect(applicationRouteForId("builtin.marketing-copy")).toBe("/apps/marketing-copy");
    expect(applicationRouteForId("builtin.viral-titles")).toBe("/apps/viral-titles");
    expect(applicationRouteForId("builtin.douyin-carousel")).toBe("/apps/douyin-carousel");
    expect(applicationRouteForId("builtin.digital-human-video")).toBe("/apps/digital-human-video");
  });

  it("resolves routed app ids and fails closed to the application directory", () => {
    expect(applicationIdForRoute("/apps/viral-titles?source=copy")).toBe("builtin.viral-titles");
    expect(applicationIdForRoute("/apps/unknown")).toBeNull();
    expect(applicationRouteForId("third-party.unknown")).toBe("/apps");
  });
});
