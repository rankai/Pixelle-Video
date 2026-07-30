import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  acceptIpBroadcastAppRun,
  artifactBlobUrl,
  cancelIpBroadcastAppRun,
  createContentProject,
  createIpBroadcastAppRun,
  createPublishPackageV2,
  downloadArtifact,
  executeIpBroadcastAppRun,
  getIpBroadcastAppRun,
  getCurrentContextSnapshot,
  getBrandProjectSummary,
  getProjectBrandSyncPreview,
  getProjectMediaRevisionPreview,
  listArtifactVersions,
  listApplications,
  listContentProjects,
  listProjectBrands,
  listProjectArtifacts,
  replaceProjectBrand,
  retryIpBroadcastAppRun,
  syncProjectBrand,
  updateProjectMaterial,
} from "../../api";
import { DigitalHumanApplicationView } from "./DigitalHumanApplicationView";

vi.mock("../../api", () => ({
  acceptIpBroadcastAppRun: vi.fn(),
  artifactBlobUrl: vi.fn(),
  cancelIpBroadcastAppRun: vi.fn(),
  createContentProject: vi.fn(),
  createIpBroadcastAppRun: vi.fn(),
  createPublishPackageV2: vi.fn(),
  downloadArtifact: vi.fn(),
  executeIpBroadcastAppRun: vi.fn(),
  getIpBroadcastAppRun: vi.fn(),
  getCurrentContextSnapshot: vi.fn(),
  getBrandProjectSummary: vi.fn(),
  getProjectBrandSyncPreview: vi.fn(),
  getProjectMediaRevisionPreview: vi.fn(),
  saveContextSnapshot: vi.fn(),
  listArtifactVersions: vi.fn(),
  listApplications: vi.fn(),
  listContentProjects: vi.fn(),
  listProjectBrands: vi.fn(),
  listProjectArtifacts: vi.fn(),
  replaceProjectBrand: vi.fn(),
  retryIpBroadcastAppRun: vi.fn(),
  syncProjectBrand: vi.fn(),
  updateProjectMaterial: vi.fn(),
}));

vi.mock("../assets/components/AssetPickerDialog", () => ({
  AssetPickerDialog: ({ open, context, onSelectScene }: { open: boolean; context?: { media_type?: "image" | "video" }; onSelectScene?: (item: unknown, sceneId: string) => void }) => {
    if (!open) return null;
    const mediaType = context?.media_type || "image";
    return (
      <button
        type="button"
        aria-label={`测试选择${mediaType === "video" ? "视频" : "图片"}场景`}
        onClick={() => onSelectScene?.({ resource_id: `portrait-${mediaType}`, name: `测试${mediaType === "video" ? "视频" : "图片"}数字人`, status: "ready", summary: { width: mediaType === "video" ? 1080 : 1080, height: mediaType === "video" ? 1920 : 1920, duration_ms: 0 }, scenes: [{ scene_id: `scene-${mediaType}`, preview_media_type: mediaType, source_revision_id: `revision-${mediaType}`, width: mediaType === "video" ? 1920 : 1080, height: mediaType === "video" ? 1080 : 1920, duration_ms: mediaType === "video" ? 12000 : 0 }] }, `scene-${mediaType}`)}
      >
        确认测试场景
      </button>
    );
  },
}));

const mocks = {
  acceptIpBroadcastAppRun: vi.mocked(acceptIpBroadcastAppRun),
  artifactBlobUrl: vi.mocked(artifactBlobUrl),
  cancelIpBroadcastAppRun: vi.mocked(cancelIpBroadcastAppRun),
  createContentProject: vi.mocked(createContentProject),
  createIpBroadcastAppRun: vi.mocked(createIpBroadcastAppRun),
  createPublishPackageV2: vi.mocked(createPublishPackageV2),
  downloadArtifact: vi.mocked(downloadArtifact),
  executeIpBroadcastAppRun: vi.mocked(executeIpBroadcastAppRun),
  getIpBroadcastAppRun: vi.mocked(getIpBroadcastAppRun),
  getCurrentContextSnapshot: vi.mocked(getCurrentContextSnapshot),
  getBrandProjectSummary: vi.mocked(getBrandProjectSummary),
  getProjectBrandSyncPreview: vi.mocked(getProjectBrandSyncPreview),
  getProjectMediaRevisionPreview: vi.mocked(getProjectMediaRevisionPreview),
  listArtifactVersions: vi.mocked(listArtifactVersions),
  listApplications: vi.mocked(listApplications),
  listContentProjects: vi.mocked(listContentProjects),
  listProjectBrands: vi.mocked(listProjectBrands),
  listProjectArtifacts: vi.mocked(listProjectArtifacts),
  replaceProjectBrand: vi.mocked(replaceProjectBrand),
  retryIpBroadcastAppRun: vi.mocked(retryIpBroadcastAppRun),
  syncProjectBrand: vi.mocked(syncProjectBrand),
  updateProjectMaterial: vi.mocked(updateProjectMaterial),
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
  artifact_keys: ["video", "cover", "publish_copy", "spoken_script"],
  artifact_details: {
    video: { artifact_id: "artifact-video", artifact_version_id: "video-v1" },
    cover: { artifact_id: "artifact-cover", artifact_version_id: "cover-v1" },
    publish_copy: { artifact_id: "artifact-copy", artifact_version_id: "copy-v1" },
  },
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
    mocks.createPublishPackageV2.mockResolvedValue({ package_id: "publish-package-1" } as never);
    mocks.executeIpBroadcastAppRun.mockResolvedValue({ ...run, state: "queued", projection: { ...run.projection, when: "queued_for_execution", task_status: "pending", app_run_state: "queued" } });
    mocks.artifactBlobUrl.mockResolvedValue("blob:final-video");
    mocks.getIpBroadcastAppRun.mockResolvedValue(run);
    mocks.getCurrentContextSnapshot.mockResolvedValue(null);
    mocks.listProjectBrands.mockResolvedValue({ items: [] });
    mocks.getProjectBrandSyncPreview.mockResolvedValue({
      project_id: "project-1",
      status: "no_change",
      has_changes: false,
      result_code: "PROJECT_BRAND_SYNC_NO_CHANGE",
      changes_committed: false,
      changes: [],
    });
    mocks.cancelIpBroadcastAppRun.mockResolvedValue({ ...run, state: "cancelled" });
    mocks.retryIpBroadcastAppRun.mockResolvedValue({ ...run, state: "queued" });
    mocks.acceptIpBroadcastAppRun.mockResolvedValue({ ...run, state: "completed", projection: { ...run.projection, app_run_state: "completed", task_status: "completed", completion_allowed: true } });
  });

  it("keeps the new route non-actionable when the desktop flag is off", () => {
    render(<DigitalHumanApplicationView desktopEnabled={false} onBack={vi.fn()} />);
    expect(screen.getByText("数字人口播应用尚未进入桌面灰度")).toBeInTheDocument();
    expect(mocks.listContentProjects).not.toHaveBeenCalled();
  });

  it("adopts the shared workbench shell while preserving the digital-human input and result regions", async () => {
    render(<DigitalHumanApplicationView desktopEnabled workbenchV2 onBack={vi.fn()} />);
    expect(await screen.findByText("门店项目")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "数字人口播视频应用工作台" })).toBeInTheDocument();
    expect(document.getElementById("digital-human-workbench-input")).toBeInTheDocument();
    expect(document.getElementById("digital-human-workbench-result")).toBeInTheDocument();
    expect(screen.getByText("等待开始")).toBeInTheDocument();
  });

  it("shows explicit legacy-brand association for a null-snapshot digital-human project", async () => {
    render(
      <DigitalHumanApplicationView
        desktopEnabled
        workbenchV2
        brandProjectV1
        onBack={vi.fn()}
      />,
    );
    expect(await screen.findByText("这是旧项目")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "关联品牌包" })).toBeEnabled();
    expect(mocks.replaceProjectBrand).not.toHaveBeenCalled();
  });

  it("creates a blank-project AppRun through the new API without touching the legacy session API", async () => {
    mocks.listContentProjects.mockResolvedValue([{
      ...project,
      current_context_snapshot_id: "context-v2",
    }]);
    mocks.createIpBroadcastAppRun.mockResolvedValue({
      ...run,
      context_snapshot_id: "context-v2",
    });
    render(<DigitalHumanApplicationView desktopEnabled onBack={vi.fn()} />);
    expect(await screen.findByText("门店项目")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("制作目标"), { target: { value: "开业介绍" } });
    fireEvent.click(screen.getByLabelText("添加可读字幕"));
    fireEvent.click(screen.getByRole("button", { name: "选择数字人形象" }));
    fireEvent.click(screen.getByRole("button", { name: "测试选择图片场景" }));
    const startButton = screen.getByRole("button", { name: "开始生成" });
    fireEvent.click(startButton);
    fireEvent.click(startButton);

    await waitFor(() => expect(mocks.createIpBroadcastAppRun).toHaveBeenCalledWith(expect.objectContaining({
      project_id: "project-1",
      context_snapshot_id: "context-v2",
      input_payload: expect.objectContaining({ schema_version: 2, app_version: "1.1.0", project_id: "project-1", content_source: { mode: "custom_script", script: "开业介绍" }, digital_human: expect.objectContaining({ mode: "image_talking", scene_id: "scene-image", asset_revision_id: "revision-image" }), delivery: expect.objectContaining({ subtitle_enabled: false }) }),
    })));
    expect(mocks.createIpBroadcastAppRun).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(mocks.executeIpBroadcastAppRun).toHaveBeenCalledWith("run-1"));
    expect(screen.getByText("run-1")).toBeInTheDocument();
    const persistedPointer = JSON.parse(window.localStorage.getItem("pixelle_ip_broadcast_app_state_v1") || "{}");
    expect(persistedPointer).toEqual(expect.objectContaining({
      route: "/apps/digital-human-video",
      digital_human_mode: "image_talking",
      portrait_id: "portrait-image",
      digital_human_scene_id: "scene-image",
      digital_human_asset_revision_id: "revision-image",
      digital_human_media_type: "image",
      goal: "开业介绍",
    }));
    expect(mocks.getIpBroadcastAppRun).not.toHaveBeenCalled();
  });

  it("switches to video digital-human mode and filters the picker context without clearing the copy", async () => {
    render(<DigitalHumanApplicationView desktopEnabled onBack={vi.fn()} />);
    expect(await screen.findByText("门店项目")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("制作目标"), { target: { value: "打架先动手和后动手有什么区别" } });
    fireEvent.click(screen.getByRole("button", { name: "选择数字人形象" }));
    fireEvent.click(screen.getByRole("button", { name: "测试选择图片场景" }));
    expect(screen.getByText("图片场景")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "视频数字人" }));
    expect(screen.getByText(/保留源视频动作与背景/)).toBeInTheDocument();
    expect(screen.getByLabelText("制作目标")).toHaveValue("打架先动手和后动手有什么区别");
    expect(screen.getByRole("button", { name: "选择数字人形象" })).toBeInTheDocument();
    expect(screen.queryByText("图片场景")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "选择数字人形象" }));
    expect(screen.getByRole("button", { name: "测试选择视频场景" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "测试选择视频场景" }));
    expect(screen.getByRole("button", { name: "测试视频数字人" })).toBeInTheDocument();
    expect(screen.getByText("视频场景")).toBeInTheDocument();
    expect(screen.getByLabelText("数字人素材详情")).toHaveTextContent("1920×1080");
    expect(screen.getByLabelText("数字人素材详情")).toHaveTextContent("12 秒");
    expect(screen.getByLabelText("数字人素材详情")).toHaveTextContent("质量：已就绪");
  });

  it("shows final video, cover, and publish copy as the default result delivery", async () => {
    window.localStorage.setItem("pixelle_ip_broadcast_app_state_v1", JSON.stringify({
      route: "/apps/digital-human-video",
      project_id: "project-1",
      app_run_id: "run-1",
      session_id: "session-1",
      source_mode: "blank_project",
      source_revision: "sha256:source",
      context_snapshot_id: null,
      digital_human_mode: "image_talking",
      portrait_id: "portrait-image",
      digital_human_scene_id: "scene-image",
      digital_human_asset_revision_id: "revision-image",
      digital_human_media_type: "image",
    }));
    render(<DigitalHumanApplicationView desktopEnabled onBack={vi.fn()} />);
    expect(await screen.findByLabelText("生成结果")).toBeInTheDocument();
    expect(screen.getByText("默认预览：最终视频")).toBeInTheDocument();
    expect(screen.getByText("最终视频")).toBeInTheDocument();
    expect(screen.getByText("封面")).toBeInTheDocument();
    expect(screen.getByText("发布文案")).toBeInTheDocument();
    expect(screen.getByText("口播稿")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByLabelText("最终视频预览").querySelector("video")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "下载最终视频" }));
    expect(mocks.downloadArtifact).toHaveBeenCalledWith("session-1", "video");
    const inlineVideoDownload = screen.getAllByRole("button").find((button) => button.textContent?.replace(/\s/g, "") === "下载");
    expect(inlineVideoDownload).toBeDefined();
    fireEvent.click(inlineVideoDownload!);
    expect(mocks.downloadArtifact).toHaveBeenCalledWith("session-1", "video");
  });

  it("hands the completed digital-human artifacts to Publish Center without opening a platform", async () => {
    window.localStorage.setItem("pixelle_ip_broadcast_app_state_v1", JSON.stringify({
      route: "/apps/digital-human-video",
      project_id: "project-1",
      app_run_id: "run-1",
      session_id: "session-1",
      source_mode: "blank_project",
      source_revision: "sha256:source",
      context_snapshot_id: null,
      digital_human_mode: "image_talking",
      portrait_id: "portrait-image",
      digital_human_scene_id: "scene-image",
      digital_human_asset_revision_id: "revision-image",
      digital_human_media_type: "image",
    }));
    const onOpenPublishCenter = vi.fn();
    render(<DigitalHumanApplicationView desktopEnabled onBack={vi.fn()} onOpenPublishCenter={onOpenPublishCenter} />);
    expect(await screen.findByLabelText("生成结果")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "交给发布中心" }));
    await waitFor(() => expect(mocks.createPublishPackageV2).toHaveBeenCalledWith({
      project_id: "project-1",
      artifact_version_ids: ["video-v1", "cover-v1", "copy-v1"],
    }));
    expect(onOpenPublishCenter).toHaveBeenCalledWith("publish-package-1");
  });

  it("binds a selected title to an independent full-copy version and delivery fields", async () => {
    mocks.listProjectArtifacts.mockResolvedValue([
      { artifact_id: "title-1", project_id: "project-1", source_app_run_id: null, artifact_type: "selected_title", name: "标题产物", status: "draft", current_version_id: "title-v1", created_at: "now", updated_at: "now" },
      { artifact_id: "copy-1", project_id: "project-1", source_app_run_id: "copy-run", artifact_type: "copywriting", name: "完整文案", status: "draft", current_version_id: "copy-v1", created_at: "now", updated_at: "now" },
    ]);
    mocks.listArtifactVersions.mockImplementation(async (artifactId) => [{
      artifact_version_id: artifactId === "title-1" ? "title-v1" : "copy-v1",
      artifact_id: artifactId,
      project_id: "project-1",
      version_number: 1,
      schema_version: 1,
      content: artifactId === "title-1"
        ? { artifact_type: "selected_title", title: "门店纠纷先留证" }
        : { artifact_type: "copywriting", variants: [{ title: "完整口播", full_text: "打架先动手和后动手有什么区别？门店纠纷先保留证据，再按流程处理。" }] },
      file_refs: [],
      source: "generated",
      content_fingerprint: "sha",
      created_at: "now",
    }]);
    render(<DigitalHumanApplicationView desktopEnabled onBack={vi.fn()} />);
    expect(await screen.findByText("门店项目")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "标题＋文案" }));
    await waitFor(() => expect(screen.getByRole("combobox", { name: "来源产物" })).toHaveValue("title-1"));
    await waitFor(() => expect(screen.getByRole("combobox", { name: "完整文案产物" })).toHaveValue("copy-1"));
    fireEvent.change(screen.getByLabelText("发布标题"), { target: { value: "门店纠纷怎么处理" } });
    fireEvent.change(screen.getByLabelText("发布描述"), { target: { value: "先留证，再按流程处理。" } });
    fireEvent.change(screen.getByLabelText("封面标题"), { target: { value: "门店纠纷先留证" } });
    fireEvent.change(screen.getByLabelText("话题标签"), { target: { value: "门店经营 到店咨询" } });
    fireEvent.click(screen.getByRole("button", { name: "选择数字人形象" }));
    fireEvent.click(screen.getByRole("button", { name: "测试选择图片场景" }));
    fireEvent.click(screen.getByRole("button", { name: "开始生成" }));
    await waitFor(() => expect(mocks.createIpBroadcastAppRun).toHaveBeenCalledWith(expect.objectContaining({
      input_payload: expect.objectContaining({
        content_source: {
          mode: "title_plus_copywriting",
          title_artifact_version_id: "title-v1",
          source_artifact_version_id: "copy-v1",
          selected_variant_index: 0,
        },
        delivery: {
          subtitle_preset: "readable_v2",
          subtitle_enabled: true,
          publish_title: "门店纠纷怎么处理",
          publish_description: "先留证，再按流程处理。",
          cover_title: "门店纠纷先留证",
          hashtags: ["门店经营", "到店咨询"],
        },
      }),
    })));
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

  it("fails closed when an initial source version is missing from the current project", async () => {
    mocks.listProjectArtifacts.mockResolvedValue([
      { artifact_id: "copy-1", project_id: "project-1", source_app_run_id: null, artifact_type: "copywriting", name: "完整文案", status: "draft", current_version_id: "copy-v2", created_at: "now", updated_at: "now" },
    ]);
    mocks.listArtifactVersions.mockResolvedValue([{
      artifact_version_id: "copy-v2",
      artifact_id: "copy-1",
      project_id: "project-1",
      version_number: 2,
      schema_version: 1,
      content: { artifact_type: "copywriting", variants: [{ full_text: "当前文案" }] },
      file_refs: [],
      source: "edited",
      content_fingerprint: "sha2",
      created_at: "now",
    }]);

    render(<DigitalHumanApplicationView desktopEnabled onBack={vi.fn()} initialSourceArtifactVersionId="missing-version" />);
    expect(await screen.findByText(/带入的数字人来源版本不存在或已归档/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "开始生成" })).toBeDisabled();
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

    expect(await screen.findByText(/历史运行引用的来源(版本|产物)不存在或已归档/)).toBeInTheDocument();
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
      { artifact_id: "artifact-1", project_id: "project-1", source_app_run_id: null, artifact_type: "copywriting", name: "旧文案", status: "draft", current_version_id: "version-1", created_at: "now", updated_at: "now" },
      { artifact_id: "artifact-2", project_id: "project-1", source_app_run_id: null, artifact_type: "copywriting", name: "新文案", status: "draft", current_version_id: "version-2", created_at: "now", updated_at: "now" },
    ]);
    mocks.listArtifactVersions.mockImplementation(async (artifactId) => [{
      artifact_version_id: artifactId === "artifact-2" ? "version-2" : "version-1",
      artifact_id: artifactId,
      project_id: "project-1",
      version_number: 1,
      schema_version: 1,
      content: { artifact_type: "copywriting", variants: [{ full_text: artifactId === "artifact-2" ? "新文案" : "旧文案" }] },
      file_refs: [],
      source: "generated",
      content_fingerprint: "sha",
      created_at: "now",
    }]);
    window.localStorage.setItem("pixelle_ip_broadcast_app_pending_v1", JSON.stringify({
      route: "/apps/digital-human-video",
      project_id: "project-1",
      source_mode: "copywriting",
      source_artifact_id: "artifact-2",
      idempotency_key: "pending-key-2",
      input_payload: {
        schema_version: 2,
        app_version: "1.1.0",
        project_id: "project-1",
        content_source: { mode: "copywriting_artifact", source_artifact_version_id: "version-2", selected_variant_index: 0 },
        digital_human: { mode: "image_talking", portrait_id: "portrait-1", scene_id: "scene-1", asset_revision_id: "revision-1", workflow_profile: "stable" },
        delivery: { subtitle_preset: "readable_v2" },
      },
    }));
    render(<DigitalHumanApplicationView desktopEnabled onBack={vi.fn()} />);

    await waitFor(() => expect(screen.getByRole("combobox", { name: "来源产物" })).toHaveValue("artifact-2"));
    expect(screen.getByRole("tab", { name: "图片数字人" })).toHaveAttribute("aria-selected", "true");
    const startButton = screen.getByRole("button", { name: "开始生成" });
    await waitFor(() => expect(startButton).toBeEnabled(), { timeout: 10_000 });
    fireEvent.click(startButton);
    await waitFor(
      () => expect(mocks.createIpBroadcastAppRun).toHaveBeenCalledWith(expect.objectContaining({ idempotency_key: "pending-key-2" })),
      { timeout: 10_000 },
    );
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
    fireEvent.click(screen.getByRole("button", { name: "选择数字人形象" }));
    fireEvent.click(screen.getByRole("button", { name: "测试选择图片场景" }));
    fireEvent.click(screen.getByRole("button", { name: "开始生成" }));
    await waitFor(() => expect(screen.getByText("simulated response lost after server commit")).toBeInTheDocument());
    expect(window.localStorage.getItem("pixelle_ip_broadcast_app_pending_v1")).toContain("desktop-digital-human:project-1:");
  });

  it("keeps the execute phase and pinned AppRun when the execute response is lost", async () => {
    mocks.executeIpBroadcastAppRun.mockRejectedValue(new Error("execute response lost"));
    render(<DigitalHumanApplicationView desktopEnabled onBack={vi.fn()} />);
    expect(await screen.findByText("门店项目")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("制作目标"), { target: { value: "开业介绍" } });
    fireEvent.click(screen.getByRole("button", { name: "选择数字人形象" }));
    fireEvent.click(screen.getByRole("button", { name: "测试选择图片场景" }));
    fireEvent.click(screen.getByRole("button", { name: "开始生成" }));

    await waitFor(() => expect(screen.getByText("execute response lost")).toBeInTheDocument());
    expect(JSON.parse(window.localStorage.getItem("pixelle_ip_broadcast_app_pending_v1") || "{}")).toEqual(expect.objectContaining({
      phase: "execute",
      app_run_id: "run-1",
      idempotency_key: expect.any(String),
    }));
    expect(JSON.parse(window.localStorage.getItem("pixelle_ip_broadcast_app_state_v1") || "{}")).toEqual(expect.objectContaining({ app_run_id: "run-1" }));
  });

  it("restores a V2 pending custom script and derives media compatibility from the mode", async () => {
    window.localStorage.setItem("pixelle_ip_broadcast_app_pending_v1", JSON.stringify({
      route: "/apps/digital-human-video",
      project_id: "project-1",
      source_mode: "blank_project",
      source_artifact_id: null,
      idempotency_key: "pending-v2-blank",
      input_payload: {
        schema_version: 2,
        app_version: "1.1.0",
        project_id: "project-1",
        content_source: { mode: "custom_script", script: "打架先动手和后动手有什么区别" },
        digital_human: { mode: "video_lipsync", portrait_id: "portrait-video", scene_id: "scene-video", asset_revision_id: "revision-video", workflow_profile: "natural" },
        delivery: { subtitle_preset: "readable_v2" },
      },
    }));
    render(<DigitalHumanApplicationView desktopEnabled onBack={vi.fn()} />);

    await waitFor(() => expect(screen.getByLabelText("制作目标")).toHaveValue("打架先动手和后动手有什么区别"));
    expect(screen.getByRole("tab", { name: "视频数字人" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("button", { name: "已选择数字人" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "图片数字人" }));
    expect(screen.getByRole("tab", { name: "视频数字人" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText(/上次提交尚未收到确认，请先恢复或清理待提交状态，再切换数字人模式/)).toBeInTheDocument();
    expect(screen.getByLabelText("制作目标")).toHaveValue("打架先动手和后动手有什么区别");
  });
});
