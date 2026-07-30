import { describe, expect, it } from "vitest";

import type { ContentProject } from "../../api";
import { projectDisplayName } from "./ProjectContextSelector";

function project(overrides: Partial<ContentProject> = {}): ContentProject {
  return {
    project_id: "project_abc123",
    schema_version: 1,
    name: "街角咖啡",
    status: "active",
    primary_goal: "到店",
    brand_id: null,
    current_context_snapshot_id: null,
    created_at: "2026-07-28T09:00:00Z",
    updated_at: "2026-07-29T09:00:00Z",
    ...overrides,
  };
}

describe("projectDisplayName", () => {
  it("keeps a user-facing project name", () => {
    expect(projectDisplayName(project())).toBe("街角咖啡");
  });

  it("replaces a leaked internal id with a friendly dated fallback", () => {
    expect(projectDisplayName(project({ name: "project_abc123" }))).toBe("未命名项目 · 7/29");
  });
});
