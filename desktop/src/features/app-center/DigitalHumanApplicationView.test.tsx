import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  acceptIpBroadcastAppRun,
  cancelIpBroadcastAppRun,
  createContentProject,
  createIpBroadcastAppRun,
  executeIpBroadcastAppRun,
  getIpBroadcastAppRun,
  listArtifactVersions,
  listApplications,
  listContentProjects,
  listProjectArtifacts,
  retryIpBroadcastAppRun,
} from "../../api";
import { DigitalHumanApplicationView } from "./DigitalHumanApplicationView";

vi.mock("../../api", () => ({
  acceptIpBroadcastAppRun: vi.fn(),
  cancelIpBroadcastAppRun: vi.fn(),
  createContentProject: vi.fn(),
  createIpBroadcastAppRun: vi.fn(),
  executeIpBroadcastAppRun: vi.fn(),
  getIpBroadcastAppRun: vi.fn(),
  listArtifactVersions: vi.fn(),
  listApplications: vi.fn(),
  listContentProjects: vi.fn(),
  listProjectArtifacts: vi.fn(),
  retryIpBroadcastAppRun: vi.fn(),
}));

const mocks = {
  acceptIpBroadcastAppRun: vi.mocked(acceptIpBroadcastAppRun),
  cancelIpBroadcastAppRun: vi.mocked(cancelIpBroadcastAppRun),
  createContentProject: vi.mocked(createContentProject),
  createIpBroadcastAppRun: vi.mocked(createIpBroadcastAppRun),
  executeIpBroadcastAppRun: vi.mocked(executeIpBroadcastAppRun),
  getIpBroadcastAppRun: vi.mocked(getIpBroadcastAppRun),
  listArtifactVersions: vi.mocked(listArtifactVersions),
  listApplications: vi.mocked(listApplications),
  listContentProjects: vi.mocked(listContentProjects),
  listProjectArtifacts: vi.mocked(listProjectArtifacts),
  retryIpBroadcastAppRun: vi.mocked(retryIpBroadcastAppRun),
};

const project = {
  project_id: "project-1",
  schema_version: 1,
  name: "门店项目",
  status: "active" as const,
  primary_goal: "制作口播",
  brand_id: null,
  current_context_snapshot_id: null,
  created_at: "now",
  updated_at: "now",
};

const run = {
  app_run_id: "run-1",
  project_id: "project-1",
  app_id: "builtin.digital-human-video",
  app_version: "1.0.0",
  state: "needs_review",
  state_version: 2,
  session_id: "session-1",
  output_artifact_ids: ["artifact-video"],
  error_code: null,
  source_revision: "sha256:source",
  explicit_claim: false,
  projection: { when: "user_must_edit_or_confirm", task_status: "needs_review", app_run_state: "needs_review", completion_allowed: false },
  step_status: { "6": "ready" },
  notices: {},
  artifact_keys: ["video", "cover", "publish_copy"],
  created_at: "now",
  updated_at: "now",
};

describe("DigitalHumanApplicationView", () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.clearAllMocks();
    mocks.listApplications.mockResolvedValue({
      schema_version: 1,
      apps: [{
        schema_version: 1,
        app_id: "builtin.digital-human-video",
        version: "1.0.0",
        name: "数字人口播视频",
        description: "复用既有口播链路制作视频",
        category: "video",
        status: "pilot",
        icon: "Video",
        required_capabilities: ["llm"],
        feature_flag: "digitalHumanInAppCenter",
        sort_order: 40,
        enabled: true,
        readiness: { status: "ready", missing_capabilities: [], configured_capabilities: ["llm"] },
      }],
    });
    mocks.listContentProjects.mockResolvedValue([project]);
    mocks.listProjectArtifacts.mockResolvedValue([]);
    mocks.listArtifactVersions.mockResolvedValue([]);
    mocks.createIpBroadcastAppRun.mockResolvedValue(run);
    mocks.getIpBroadcastAppRun.mockResolvedValue(run);
    mocks.cancelIpBroadcastAppRun.mockResolvedValue({ ...run, state: "cancelled" });
    mocks.retryIpBroadcastAppRun.mockResolvedValue({ ...run, state: "queued" });
    mocks.acceptIpBroadcastAppRun.mockResolvedValue({ ...run, state: "completed", projection: { ...run.projection, app_run_state: "completed", task_status: "completed", completion_allowed: true } });
  });

  it("keeps the new route non-actionable when the desktop flag is off", () => {
    render(<DigitalHumanApplicationView desktopEnabled={false} onBack={vi.fn()} />);
    expect(screen.getByText("数字人口播应用尚未进入桌面灰度")).toBeInTheDocument();
    expect(mocks.listContentProjects).not.toHaveBeenCalled();
  });

  it("creates a blank-project AppRun through the new API without touching the legacy session API", async () => {
    render(<DigitalHumanApplicationView desktopEnabled onBack={vi.fn()} />);
    expect(await screen.findByText("门店项目")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("制作目标"), { target: { value: "开业介绍" } });
    fireEvent.click(screen.getByRole("button", { name: "创建应用运行" }));

    await waitFor(() => expect(mocks.createIpBroadcastAppRun).toHaveBeenCalledWith(expect.objectContaining({
      project_id: "project-1",
      input_payload: { project_id: "project-1", source_mode: "blank_project", goal: "开业介绍" },
    })));
    expect(screen.getByText("run-1")).toBeInTheDocument();
    expect(window.localStorage.getItem("pixelle_ip_broadcast_app_state_v1")).toContain("run-1");
    expect(JSON.parse(window.localStorage.getItem("pixelle_ip_broadcast_app_state_v1") || "{}").route).toBe("/apps/digital-human-video");
    expect(mocks.getIpBroadcastAppRun).not.toHaveBeenCalled();
  });

  it("fails closed when the backend Registry is disabled even if the desktop flag is on", async () => {
    mocks.listApplications.mockResolvedValue({
      schema_version: 1,
      apps: [{
        schema_version: 1,
        app_id: "builtin.digital-human-video",
        version: "1.0.0",
        name: "数字人口播视频",
        description: "复用既有口播链路制作视频",
        category: "video",
        status: "pilot",
        icon: "Video",
        required_capabilities: ["llm"],
        feature_flag: "digitalHumanInAppCenter",
        sort_order: 40,
        enabled: false,
        readiness: { status: "disabled", missing_capabilities: [], configured_capabilities: [] },
      }],
    });
    render(<DigitalHumanApplicationView desktopEnabled onBack={vi.fn()} />);
    expect(await screen.findByText("数字人口播应用暂不可用")).toBeInTheDocument();
    expect(mocks.listContentProjects).not.toHaveBeenCalled();
    expect(mocks.createIpBroadcastAppRun).not.toHaveBeenCalled();
  });

  it("reuses the persisted AppRun/session pointer after restart instead of creating another run", async () => {
    window.localStorage.setItem("pixelle_ip_broadcast_app_state_v1", JSON.stringify({
      route: "/apps/digital-human-video",
      project_id: "project-1",
      app_run_id: "run-1",
      session_id: "session-1",
      source_mode: "selected_title",
      source_revision: "sha256:source",
      context_snapshot_id: null,
    }));
    render(<DigitalHumanApplicationView desktopEnabled onBack={vi.fn()} />);

    expect(await screen.findByText(/已从上次安全停手位置恢复/)).toBeInTheDocument();
    expect(mocks.getIpBroadcastAppRun).toHaveBeenCalledWith("run-1", "project-1");
    expect(mocks.createIpBroadcastAppRun).not.toHaveBeenCalled();
  });

  it("restores the selected digital-human asset with the AppRun pointer after restart", async () => {
    window.localStorage.setItem("pixelle_ip_broadcast_app_state_v1", JSON.stringify({
      route: "/apps/digital-human-video",
      project_id: "project-1",
      app_run_id: "run-1",
      session_id: "session-1",
      source_mode: "blank_project",
      source_revision: "sha256:source",
      context_snapshot_id: null,
      portrait_id: "portrait-1",
      digital_human_scene_id: "scene-1",
    }));
    render(<DigitalHumanApplicationView desktopEnabled onBack={vi.fn()} />);

    expect(await screen.findByRole("button", { name: "已选择数字人" })).toBeInTheDocument();
    expect(screen.getByText("已选场景")).toBeInTheDocument();
    expect(mocks.createIpBroadcastAppRun).not.toHaveBeenCalled();
  });

  it("fails closed when a restored source artifact has been archived", async () => {
    mocks.listProjectArtifacts.mockResolvedValue([
      { artifact_id: "archived-title", project_id: "project-1", source_app_run_id: null, artifact_type: "selected_title", name: "已归档标题", status: "archived", current_version_id: "version-archived", created_at: "now", updated_at: "now" },
      { artifact_id: "active-title", project_id: "project-1", source_app_run_id: null, artifact_type: "selected_title", name: "当前标题", status: "draft", current_version_id: "version-active", created_at: "now", updated_at: "now" },
    ]);
    window.localStorage.setItem("pixelle_ip_broadcast_app_state_v1", JSON.stringify({
      route: "/apps/digital-human-video",
      project_id: "project-1",
      app_run_id: "run-1",
      session_id: "session-1",
      source_mode: "selected_title",
      source_revision: "sha256:source",
      context_snapshot_id: null,
      source_artifact_id: "archived-title",
      source_version_id: "version-archived",
    }));
    render(<DigitalHumanApplicationView desktopEnabled onBack={vi.fn()} />);

    expect(await screen.findByText(/历史运行引用的来源产物不存在或已归档/)).toBeInTheDocument();
    expect(window.localStorage.getItem("pixelle_ip_broadcast_app_state_v1")).toBeNull();
    expect(screen.getByRole("combobox", { name: "来源产物" })).toHaveValue("");
    expect(screen.queryByText("run-1")).not.toBeInTheDocument();
  });

  it("fails closed when a restored source version has been archived", async () => {
    mocks.listProjectArtifacts.mockResolvedValue([
      { artifact_id: "active-title", project_id: "project-1", source_app_run_id: null, artifact_type: "selected_title", name: "当前标题", status: "draft", current_version_id: "version-active", created_at: "now", updated_at: "now" },
    ]);
    mocks.listArtifactVersions.mockResolvedValue([{
      artifact_version_id: "version-active",
      artifact_id: "active-title",
      project_id: "project-1",
      version_number: 1,
      schema_version: 1,
      content: { artifact_type: "selected_title", title: "当前标题" },
      file_refs: [],
      source: "generated",
      content_fingerprint: "sha",
      created_at: "now",
    }]);
    window.localStorage.setItem("pixelle_ip_broadcast_app_state_v1", JSON.stringify({
      route: "/apps/digital-human-video",
      project_id: "project-1",
      app_run_id: "run-1",
      session_id: "session-1",
      source_mode: "selected_title",
      source_revision: "sha256:source",
      context_snapshot_id: null,
      source_artifact_id: "active-title",
      source_version_id: "version-archived",
    }));
    render(<DigitalHumanApplicationView desktopEnabled onBack={vi.fn()} />);

    expect(await screen.findByText(/历史运行引用的来源版本不存在或已归档/)).toBeInTheDocument();
    expect(window.localStorage.getItem("pixelle_ip_broadcast_app_state_v1")).toBeNull();
    expect(screen.queryByText("run-1")).not.toBeInTheDocument();
  });

  it("fails closed when the restored source revision does not match the server binding", async () => {
    window.localStorage.setItem("pixelle_ip_broadcast_app_state_v1", JSON.stringify({
      route: "/apps/digital-human-video",
      project_id: "project-1",
      app_run_id: "run-1",
      session_id: "session-1",
      source_mode: "blank_project",
      source_revision: "sha256:tampered",
      context_snapshot_id: null,
    }));
    render(<DigitalHumanApplicationView desktopEnabled onBack={vi.fn()} />);

    expect(await screen.findByText(/历史运行绑定校验未通过/)).toBeInTheDocument();
    expect(screen.queryByText("run-1")).not.toBeInTheDocument();
    expect(window.localStorage.getItem("pixelle_ip_broadcast_app_state_v1")).toBeNull();
  });

  it("restores a non-first source artifact and reuses its pending idempotency key", async () => {
    mocks.listProjectArtifacts.mockResolvedValue([
      { artifact_id: "artifact-1", project_id: "project-1", source_app_run_id: null, artifact_type: "selected_title", name: "旧标题", status: "draft", current_version_id: "version-1", created_at: "now", updated_at: "now" },
      { artifact_id: "artifact-2", project_id: "project-1", source_app_run_id: null, artifact_type: "selected_title", name: "新标题", status: "draft", current_version_id: "version-2", created_at: "now", updated_at: "now" },
    ]);
    mocks.listArtifactVersions.mockImplementation(async (artifactId) => [{
      artifact_version_id: artifactId === "artifact-2" ? "version-2" : "version-1",
      artifact_id: artifactId,
      project_id: "project-1",
      version_number: 1,
      schema_version: 1,
      content: { artifact_type: "selected_title", title: artifactId === "artifact-2" ? "新标题" : "旧标题" },
      file_refs: [],
      source: "generated",
      content_fingerprint: "sha",
      created_at: "now",
    }]);
    window.localStorage.setItem("pixelle_ip_broadcast_app_pending_v1", JSON.stringify({
      route: "/apps/digital-human-video",
      project_id: "project-1",
      source_mode: "selected_title",
      source_artifact_id: "artifact-2",
      idempotency_key: "pending-key-2",
      input_payload: { project_id: "project-1", source_mode: "selected_title", source_artifact_version_ids: ["version-2"] },
    }));
    render(<DigitalHumanApplicationView desktopEnabled onBack={vi.fn()} />);

    await waitFor(() => expect(screen.getByRole("combobox", { name: "来源产物" })).toHaveValue("artifact-2"));
    fireEvent.click(screen.getByRole("button", { name: "创建应用运行" }));
    await waitFor(() => expect(mocks.createIpBroadcastAppRun).toHaveBeenCalledWith(expect.objectContaining({ idempotency_key: "pending-key-2" })));
  });

  it("persists a pending idempotency key before POST so an unconfirmed response can be replayed", async () => {
    mocks.createIpBroadcastAppRun.mockImplementation(async () => {
      expect(JSON.parse(window.localStorage.getItem("pixelle_ip_broadcast_app_pending_v1") || "{}")).toEqual(expect.objectContaining({
        route: "/apps/digital-human-video",
        project_id: "project-1",
        source_mode: "blank_project",
        idempotency_key: expect.any(String),
      }));
      throw new Error("simulated response lost after server commit");
    });
    render(<DigitalHumanApplicationView desktopEnabled onBack={vi.fn()} />);
    expect(await screen.findByText("门店项目")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("制作目标"), { target: { value: "开业介绍" } });
    fireEvent.click(screen.getByRole("button", { name: "创建应用运行" }));
    await waitFor(() => expect(screen.getByText("simulated response lost after server commit")).toBeInTheDocument());
    expect(window.localStorage.getItem("pixelle_ip_broadcast_app_pending_v1")).toContain("desktop-digital-human:project-1:");
  });
});
