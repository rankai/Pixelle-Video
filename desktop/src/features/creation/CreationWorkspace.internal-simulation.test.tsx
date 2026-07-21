import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CreationWorkspace } from "./CreationWorkspace";

const mocks = vi.hoisted(() => ({
  listContentProjects: vi.fn(),
  listAppRuns: vi.fn(),
  createContentProject: vi.fn(),
  updateContentProject: vi.fn(),
  createAppRun: vi.fn(),
  getCurrentContextSnapshot: vi.fn(),
  listArtifactVersions: vi.fn(),
  completeAppRun: vi.fn(),
  executeAppRun: vi.fn(),
  retryAppRun: vi.fn(),
  cancelAppRun: vi.fn(),
  archiveContentProject: vi.fn(),
  appendArtifactVersion: vi.fn(),
  createArtifactHandoff: vi.fn(),
}));

vi.mock("../../api", () => ({ ...mocks }));

const scenarios = [
  ["火锅老板", "周末双人套餐", "火锅"],
  ["美容老板", "新客到店体验", "美容"],
  ["民宿老板", "工作日入住", "民宿"],
  ["洗衣老板", "换季洗护", "洗衣店"],
  ["培训老板", "试听报名", "培训"],
  ["零售老板", "新品到店", "零售"],
  ["咖啡老板", "下午茶到店", "咖啡"],
  ["烘焙老板", "新品试吃", "烘焙"],
  ["健身老板", "新客咨询", "健身"],
  ["宠物店老板", "洗护预约", "宠物店"],
] as const;

describe("CreationWorkspace synthetic internal precheck", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.listContentProjects.mockResolvedValue([]);
    mocks.listAppRuns.mockResolvedValue([]);
    mocks.getCurrentContextSnapshot.mockResolvedValue(null);
    mocks.createContentProject.mockImplementation(async ({ name, primary_goal }) => ({
      project_id: "simulation-project",
      schema_version: 1,
      name,
      status: "active",
      primary_goal,
      brand_id: null,
      current_context_snapshot_id: null,
      created_at: "now",
      updated_at: "now",
    }));
    mocks.createAppRun.mockResolvedValue({ app_run_id: "simulation-run", app_id: "builtin.marketing-copy", app_version: "1.0.0" });
    mocks.executeAppRun.mockResolvedValue({ app_run_id: "simulation-run", state: "needs_review" });
    mocks.completeAppRun.mockResolvedValue({ app_run_id: "simulation-run", state: "completed" });
  });

  it.each(scenarios)("%s completes the first-copy flow without helper text", async (persona, goal, product) => {
    const draftRun = {
      app_run_id: "simulation-run",
      project_id: "simulation-project",
      app_id: "builtin.marketing-copy",
      app_version: "1.0.0",
      state: "draft" as const,
      state_version: 1,
      idempotency_key: `simulation-${persona}`,
      input_payload: {},
      context_snapshot_id: null,
      output_artifact_ids: [],
      error_code: null,
      archived_at: null,
      created_at: "now",
      updated_at: "now",
    };
    const reviewRun = { ...draftRun, state: "needs_review" as const, state_version: 2 };
    mocks.listAppRuns.mockResolvedValueOnce([draftRun]).mockResolvedValueOnce([reviewRun]).mockResolvedValueOnce([{ ...reviewRun, state: "completed" as const, state_version: 3 }]);

    render(<CreationWorkspace />);
    fireEvent.change(screen.getByPlaceholderText("项目名称"), { target: { value: persona } });
    fireEvent.change(screen.getByPlaceholderText("本次营销目标"), { target: { value: goal } });
    fireEvent.change(screen.getByPlaceholderText("产品或服务"), { target: { value: product } });
    fireEvent.click(screen.getByText("保存草稿"));
    await waitFor(() => expect(mocks.createContentProject).toHaveBeenCalledWith({ name: persona, primary_goal: goal }));

    fireEvent.click(screen.getByText("创建运行草稿"));
    await waitFor(() => expect(mocks.createAppRun).toHaveBeenCalledWith(expect.objectContaining({
      app_id: "builtin.marketing-copy",
      input_payload: expect.objectContaining({ goal, product_or_service: product }),
    })));
    fireEvent.click(await screen.findByRole("button", { name: /执\s*行/ }));
    await waitFor(() => expect(mocks.executeAppRun).toHaveBeenCalledWith("simulation-run"));
    fireEvent.click(await screen.findByRole("button", { name: "确认完成" }));
    await waitFor(() => expect(mocks.completeAppRun).toHaveBeenCalledWith("simulation-run"));
  });
});
