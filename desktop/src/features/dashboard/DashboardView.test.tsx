import { describe, expect, it } from "vitest";

import { taskDisplayName } from "./DashboardView";

describe("taskDisplayName", () => {
  it.each([
    ["builtin.marketing-copy", "门店营销文案"],
    ["builtin.viral-titles", "爆款标题"],
    ["builtin.douyin-carousel", "抖音图文"],
    ["builtin.digital-human-video", "数字人口播视频"],
  ])("hides the internal application id %s", (internalId, label) => {
    expect(taskDisplayName({ display_name: internalId }, "生产任务")).toBe(label);
  });

  it("keeps a user-created task name and falls back for an empty name", () => {
    expect(taskDisplayName({ display_name: "夏日新品推广" }, "生产任务")).toBe("夏日新品推广");
    expect(taskDisplayName({}, "生产任务")).toBe("生产任务");
  });
});
