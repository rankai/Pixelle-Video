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
  downloadAppArtifactFile: vi.fn(),
  retryAppRun: vi.fn(),
  cancelAppRun: vi.fn(),
  archiveContentProject: vi.fn(),
  appendArtifactVersion: vi.fn(),
  createArtifactHandoff: vi.fn(),
}));
const { listContentProjects, listAppRuns, createContentProject } = mocks;

vi.mock("../../api", () => ({
  ...mocks,
}));

describe("CreationWorkspace", () => {
  beforeEach(() => {
    listContentProjects.mockResolvedValue([]);
    listAppRuns.mockResolvedValue([]);
    mocks.getCurrentContextSnapshot.mockResolvedValue(null);
    createContentProject.mockResolvedValue({
      project_id: "p1",
      schema_version: 1,
      name: "新项目",
      status: "active",
      primary_goal: "目标",
      brand_id: null,
      current_context_snapshot_id: null,
      created_at: "now",
      updated_at: "now",
    });
    vi.clearAllMocks();
  });

  it("saves a project draft and exposes an unsaved-change guard", async () => {
    render(<CreationWorkspace />);
    fireEvent.change(screen.getByPlaceholderText("项目名称"), { target: { value: "新项目" } });
    fireEvent.change(screen.getByPlaceholderText("本次营销目标"), { target: { value: "目标" } });
    fireEvent.click(screen.getByText("保存草稿"));
    await waitFor(() => expect(createContentProject).toHaveBeenCalledWith({ name: "新项目", primary_goal: "目标" }));
    expect(screen.getByText("项目草稿")).toBeInTheDocument();
  });

  it("creates a carousel run from artifact and registered asset references", async () => {
    render(<CreationWorkspace appId="builtin.douyin-carousel" />);
    fireEvent.change(screen.getByPlaceholderText("项目名称"), { target: { value: "图文项目" } });
    fireEvent.change(screen.getByPlaceholderText("本次营销目标"), { target: { value: "到店咨询" } });
    fireEvent.click(screen.getByText("保存草稿"));
    await waitFor(() => expect(createContentProject).toHaveBeenCalled());

    fireEvent.change(screen.getByLabelText("图文来源 ArtifactVersion"), { target: { value: "artifact_version_source" } });
    fireEvent.change(screen.getByLabelText("图文资产引用"), { target: { value: "asset:image-1, asset:image-2" } });
    fireEvent.click(screen.getByText("创建运行草稿"));
    await waitFor(() => expect(mocks.createAppRun).toHaveBeenCalledWith(expect.objectContaining({
      app_id: "builtin.douyin-carousel",
      input_payload: {
        goal: "到店咨询",
        page_count: 3,
        source_artifact_version_ids: ["artifact_version_source"],
        asset_refs: ["asset:image-1", "asset:image-2"],
      },
    })));
  });

  it("restores carousel inputs from the latest run and clears them on project switch", async () => {
    const projectOne = {
      project_id: "p1", schema_version: 1, name: "图文项目一", status: "active" as const, primary_goal: "到店咨询",
      brand_id: null, current_context_snapshot_id: null, created_at: "2026-01-01", updated_at: "2026-01-01",
    };
    const projectTwo = {
      project_id: "p2", schema_version: 1, name: "图文项目二", status: "active" as const, primary_goal: "提升复购",
      brand_id: null, current_context_snapshot_id: null, created_at: "2026-01-02", updated_at: "2026-01-02",
    };
    listContentProjects.mockResolvedValue([projectOne, projectTwo]);
    listAppRuns.mockImplementation(async (projectId: string) => projectId === "p1" ? [{
      app_run_id: "carousel-run-1", project_id: "p1", app_id: "builtin.douyin-carousel", app_version: "1.0.0",
      state: "draft", state_version: 1, idempotency_key: "carousel-run-1",
      input_payload: { page_count: 5, source_artifact_version_ids: ["source-v5"], asset_refs: ["asset:one", "asset:two"] },
      context_snapshot_id: null, output_artifact_ids: [], error_code: null, archived_at: null, created_at: "2026-01-03", updated_at: "2026-01-03",
    }] : []);
    render(<CreationWorkspace appId="builtin.douyin-carousel" />);

    await waitFor(() => expect(screen.getByDisplayValue("source-v5")).toBeInTheDocument());
    expect(screen.getByDisplayValue("asset:one, asset:two")).toBeInTheDocument();
    expect(screen.getByText("5 页")).toBeInTheDocument();

    fireEvent.click(screen.getByText("图文项目二"));
    await waitFor(() => expect(screen.queryByDisplayValue("source-v5")).not.toBeInTheDocument());
    expect(screen.getByLabelText("图文来源 ArtifactVersion")).toHaveValue("");
    expect(screen.getByLabelText("图文资产引用")).toHaveValue("");
    expect(screen.getByText("3 页")).toBeInTheDocument();
  });

  it("exposes carousel package download and publish-copy actions without Publish V2", async () => {
    listContentProjects.mockResolvedValue([{
      project_id: "p1", schema_version: 1, name: "图文项目", status: "active", primary_goal: "目标",
      brand_id: null, current_context_snapshot_id: null, created_at: "now", updated_at: "now",
    }]);
    listAppRuns.mockResolvedValue([{
      app_run_id: "carousel-run", project_id: "p1", app_id: "builtin.douyin-carousel", app_version: "1.0.0",
      state: "needs_review", state_version: 2, idempotency_key: "carousel-run", input_payload: {},
      context_snapshot_id: null, output_artifact_ids: ["package-artifact"], error_code: null, archived_at: null, created_at: "now", updated_at: "now",
    }]);
    mocks.listArtifactVersions.mockResolvedValue([{
      artifact_version_id: "package-version", artifact_id: "package-artifact", project_id: "p1", version_number: 1, schema_version: 1,
      // Shape emitted by the source-derived carousel flow: title is mapped from
      // selected_title while optional description/hashtags may remain empty.
      content: { artifact_type: "carousel_package", title: "标题", description: "", hashtags: [] },
      file_refs: [{ file_key: "carousel-package.zip", kind: "zip", mime_type: "application/zip" }], source: "generated", content_fingerprint: "sha", created_at: "now",
    }]);
    mocks.downloadAppArtifactFile.mockResolvedValue(new Blob(["zip"]));
    vi.stubGlobal("URL", { ...URL, createObjectURL: vi.fn(() => "blob:carousel"), revokeObjectURL: vi.fn() });
    Object.assign(navigator, { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } });
    render(<CreationWorkspace appId="builtin.douyin-carousel" />);

    await waitFor(() => expect(screen.getByText("查看版本")).toBeInTheDocument());
    fireEvent.click(screen.getByText("查看版本"));
    await waitFor(() => expect(screen.getByText("下载图文包")).toBeInTheDocument());
    fireEvent.click(screen.getByText("下载图文包"));
    fireEvent.click(screen.getByText("复制发布文案"));
    await waitFor(() => expect(mocks.downloadAppArtifactFile).toHaveBeenCalledWith("package-artifact", "carousel-package.zip"));
    await waitFor(() => expect(navigator.clipboard.writeText).toHaveBeenCalledWith("标题"));
  });

  it("restores context and exposes complete-review action for a pending output", async () => {
    listContentProjects.mockResolvedValue([{
      project_id: "p1", schema_version: 1, name: "已有项目", status: "active", primary_goal: "目标",
      brand_id: null, current_context_snapshot_id: "ctx1", created_at: "now", updated_at: "now",
    }]);
    listAppRuns.mockResolvedValue([{
      app_run_id: "run1", project_id: "p1", app_id: "builtin.marketing-copy", app_version: "1.0.0",
      state: "needs_review", state_version: 3, idempotency_key: "run1", input_payload: {},
      context_snapshot_id: "ctx1", output_artifact_ids: [], error_code: null, archived_at: null, created_at: "now", updated_at: "now",
    }]);
    mocks.getCurrentContextSnapshot.mockResolvedValue({ context_snapshot_id: "ctx1", project_id: "p1", schema_version: 1, payload: { store: "店" }, source_brand_id: null, source_brand_revision_id: null, fingerprint: "sha", created_at: "now" });
    mocks.completeAppRun.mockResolvedValue({});
    render(<CreationWorkspace />);
    await waitFor(() => expect(screen.getByText("待审核")).toBeInTheDocument());
    fireEvent.click(screen.getByText("确认完成"));
    await waitFor(() => expect(mocks.completeAppRun).toHaveBeenCalledWith("run1"));
    expect(screen.getByText("已恢复项目上下文快照")).toBeInTheDocument();
  });

  it("passes the current context when handing a copywriting artifact to titles", async () => {
    listContentProjects.mockResolvedValue([{
      project_id: "p1", schema_version: 1, name: "已有项目", status: "active", primary_goal: "目标",
      brand_id: null, current_context_snapshot_id: "ctx1", created_at: "now", updated_at: "now",
    }]);
    listAppRuns.mockResolvedValue([{
      app_run_id: "run1", project_id: "p1", app_id: "builtin.marketing-copy", app_version: "1.0.0",
      state: "needs_review", state_version: 3, idempotency_key: "run1", input_payload: {},
      context_snapshot_id: "ctx1", output_artifact_ids: ["artifact1"], error_code: null, archived_at: null, created_at: "now", updated_at: "now",
    }]);
    mocks.getCurrentContextSnapshot.mockResolvedValue(null);
    mocks.listArtifactVersions.mockResolvedValue([{ artifact_version_id: "version1", artifact_id: "artifact1", project_id: "p1", version_number: 1, schema_version: 1, content: { artifact_type: "copywriting" }, file_refs: [], source: "generated", content_fingerprint: "sha", created_at: "now" }]);
    mocks.createAppRun.mockResolvedValue({ app_run_id: "title-run", app_id: "builtin.viral-titles", app_version: "1.0.0" });
    mocks.createArtifactHandoff.mockResolvedValue({});
    render(<CreationWorkspace />);
    await waitFor(() => expect(screen.getByText("交给爆款标题")).toBeInTheDocument());
    fireEvent.click(screen.getByText("交给爆款标题"));
    await waitFor(() => expect(mocks.createAppRun).toHaveBeenCalledWith(expect.objectContaining({ context_snapshot_id: "ctx1" })));
    expect(mocks.createArtifactHandoff).toHaveBeenCalledWith(expect.objectContaining({ target_run_id: "title-run" }));
  });

  it("edits copy variants with deterministic full text and duration recalculation", async () => {
    listContentProjects.mockResolvedValue([{
      project_id: "p1", schema_version: 1, name: "已有项目", status: "active", primary_goal: "目标",
      brand_id: null, current_context_snapshot_id: null, created_at: "now", updated_at: "now",
    }]);
    listAppRuns.mockResolvedValue([{
      app_run_id: "run1", project_id: "p1", app_id: "builtin.marketing-copy", app_version: "1.0.0",
      state: "needs_review", state_version: 3, idempotency_key: "run1", input_payload: {},
      context_snapshot_id: null, output_artifact_ids: ["artifact1"], error_code: null, archived_at: null, created_at: "now", updated_at: "now",
    }]);
    mocks.listArtifactVersions.mockResolvedValue([{
      artifact_version_id: "version1", artifact_id: "artifact1", project_id: "p1", version_number: 1, schema_version: 1,
      content: {
        schema_version: 1, artifact_type: "copywriting", missing_facts: [], risk_flags: [], validation_facts: { input: {}, context: {} },
        variants: [
          { version_name: "版本1", angle: "利益", hook: "开头", body: "正文", cta: "行动", full_text: "开头正文行动", word_count: 6, estimated_seconds: 2 },
          { version_name: "版本2", angle: "好奇", hook: "开头2", body: "正文2", cta: "行动2", full_text: "开头2正文2行动2", word_count: 8, estimated_seconds: 2 },
          { version_name: "版本3", angle: "场景", hook: "开头3", body: "正文3", cta: "行动3", full_text: "开头3正文3行动3", word_count: 8, estimated_seconds: 2 },
        ],
      },
      file_refs: [], source: "generated", content_fingerprint: "sha", created_at: "now",
    }]);
    mocks.appendArtifactVersion.mockResolvedValue({});
    render(<CreationWorkspace />);
    await waitFor(() => expect(screen.getByText("查看版本")).toBeInTheDocument());
    fireEvent.click(screen.getAllByText("查看版本")[0]);
    await waitFor(() => expect(screen.getByLabelText("文案版本1正文")).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText("文案版本1正文"), { target: { value: "更长正文" } });
    expect(screen.getByText(/合成正文：开头更长正文行动（8 字，约 2 秒）/)).toBeInTheDocument();
    fireEvent.click(screen.getByText("保存编辑版本"));
    await waitFor(() => expect(mocks.appendArtifactVersion).toHaveBeenCalledWith(
      "artifact1",
      expect.objectContaining({
        variants: expect.arrayContaining([expect.objectContaining({ body: "更长正文", full_text: "开头更长正文行动", word_count: 8, estimated_seconds: 2 })]),
      }),
      "edited",
    ));
  });

  it("edits title candidates and recalculates Unicode length", async () => {
    listContentProjects.mockResolvedValue([{
      project_id: "p1", schema_version: 1, name: "标题项目", status: "active", primary_goal: "目标",
      brand_id: null, current_context_snapshot_id: null, created_at: "now", updated_at: "now",
    }]);
    listAppRuns.mockResolvedValue([{
      app_run_id: "run-title", project_id: "p1", app_id: "builtin.viral-titles", app_version: "1.0.0",
      state: "needs_review", state_version: 3, idempotency_key: "run-title", input_payload: {},
      context_snapshot_id: null, output_artifact_ids: ["title-artifact"], error_code: null, archived_at: null, created_at: "now", updated_at: "now",
    }]);
    mocks.listArtifactVersions.mockResolvedValue([{
      artifact_version_id: "title-version", artifact_id: "title-artifact", project_id: "p1", version_number: 1, schema_version: 1,
      content: {
        schema_version: 1, artifact_type: "title_set", missing_facts: [], risk_flags: [], validation_facts: { input: {}, context: {} },
        candidates: [1, 2, 3, 4, 5].map((index) => ({ title: `标题${index}`, angle: "场景", objective: "click", length: 3, banned_matches: [], risk_labels: ["无"] })),
      },
      file_refs: [], source: "generated", content_fingerprint: "sha", created_at: "now",
    }]);
    mocks.appendArtifactVersion.mockResolvedValue({});
    render(<CreationWorkspace appId="builtin.viral-titles" />);
    await waitFor(() => expect(screen.getByText("查看版本")).toBeInTheDocument());
    fireEvent.click(screen.getAllByText("查看版本")[0]);
    await waitFor(() => expect(screen.getByLabelText("标题候选1")).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText("标题候选1"), { target: { value: "更长标题" } });
    expect(screen.getByDisplayValue("更长标题")).toBeInTheDocument();
    fireEvent.click(screen.getByText("保存编辑版本"));
    await waitFor(() => expect(mocks.appendArtifactVersion).toHaveBeenCalledWith(
      "title-artifact",
      expect.objectContaining({ candidates: expect.arrayContaining([expect.objectContaining({ title: "更长标题", length: 4 })]) }),
      "edited",
    ));
  });

  it("uses Unicode code-point lengths for emoji edits", async () => {
    listContentProjects.mockResolvedValue([{
      project_id: "p1", schema_version: 1, name: "标题项目", status: "active", primary_goal: "目标",
      brand_id: null, current_context_snapshot_id: null, created_at: "now", updated_at: "now",
    }]);
    listAppRuns.mockResolvedValue([{
      app_run_id: "run-title", project_id: "p1", app_id: "builtin.viral-titles", app_version: "1.0.0",
      state: "needs_review", state_version: 3, idempotency_key: "run-title", input_payload: {},
      context_snapshot_id: null, output_artifact_ids: ["title-artifact"], error_code: null, archived_at: null, created_at: "now", updated_at: "now",
    }]);
    mocks.listArtifactVersions.mockResolvedValue([{
      artifact_version_id: "title-version", artifact_id: "title-artifact", project_id: "p1", version_number: 1, schema_version: 1,
      content: { schema_version: 1, artifact_type: "title_set", missing_facts: [], risk_flags: [], validation_facts: { input: {}, context: {} }, candidates: [1, 2, 3, 4, 5].map((index) => ({ title: `标题${index}`, angle: "场景", objective: "click", length: 3, banned_matches: [], risk_labels: ["无"] })) },
      file_refs: [], source: "generated", content_fingerprint: "sha", created_at: "now",
    }]);
    render(<CreationWorkspace appId="builtin.viral-titles" />);
    await waitFor(() => expect(screen.getByText("查看版本")).toBeInTheDocument());
    fireEvent.click(screen.getAllByText("查看版本")[0]);
    await waitFor(() => expect(screen.getByLabelText("标题候选1")).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText("标题候选1"), { target: { value: "😀标题" } });
    expect(screen.getAllByText("3 字").length).toBeGreaterThan(0);
    fireEvent.click(screen.getByText("保存编辑版本"));
    await waitFor(() => expect(mocks.appendArtifactVersion).toHaveBeenCalledWith(
      "title-artifact",
      expect.objectContaining({ candidates: expect.arrayContaining([expect.objectContaining({ title: "😀标题", length: 3 })]) }),
      "edited",
    ));
  });
});
