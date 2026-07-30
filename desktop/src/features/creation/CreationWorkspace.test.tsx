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
  saveContextSnapshot: vi.fn(),
  listArtifactVersions: vi.fn(),
  completeAppRun: vi.fn(),
  executeAppRun: vi.fn(),
  downloadAppArtifactFile: vi.fn(),
  retryAppRun: vi.fn(),
  cancelAppRun: vi.fn(),
  archiveContentProject: vi.fn(),
  appendArtifactVersion: vi.fn(),
  createProjectArtifact: vi.fn(),
  createArtifactHandoff: vi.fn(),
  listStylePresets: vi.fn(),
  recordAppEvent: vi.fn(),
  listProjectArtifacts: vi.fn(),
  listLibraryItemsV2: vi.fn(),
  createPublishPackageV2: vi.fn(),
  retryCarouselPage: vi.fn(),
  listProjectBrands: vi.fn(),
  getProjectBrandSyncPreview: vi.fn(),
  getProjectMediaRevisionPreview: vi.fn(),
  updateProjectMaterial: vi.fn(),
  replaceProjectBrand: vi.fn(),
  syncProjectBrand: vi.fn(),
  getBrandProjectSummary: vi.fn(),
  assetPickerSelection: [
    { resource_id: "image-1", asset_id: "image-1", name: "门店图片 1" },
    { resource_id: "image-2", asset_id: "image-2", name: "门店图片 2" },
  ] as Array<{
    resource_id: string;
    asset_id?: string;
    name: string;
    revision?: { revision_id: string };
  }>,
}));
const { listContentProjects, listAppRuns, createContentProject } = mocks;

vi.mock("../../api", () => ({
  ...mocks,
}));

vi.mock("../assets/components/AssetPickerDialog", () => ({
  AssetPickerDialog: ({ open, onSelectMany }: { open: boolean; onSelectMany?: (items: Array<{ resource_id: string; asset_id?: string; name: string }>) => void }) => open
    ? <button type="button" onClick={() => onSelectMany?.(mocks.assetPickerSelection)}>确认选择</button>
    : null,
}));

describe("CreationWorkspace", () => {
  beforeEach(() => {
    listContentProjects.mockResolvedValue([]);
    listAppRuns.mockResolvedValue([]);
    mocks.getCurrentContextSnapshot.mockResolvedValue(null);
    mocks.listProjectArtifacts.mockResolvedValue([]);
    mocks.listLibraryItemsV2.mockResolvedValue({ items: [], total: 0 });
    mocks.listStylePresets.mockResolvedValue({ items: [] });
    mocks.createPublishPackageV2.mockResolvedValue({ package_id: "publish-package-1" });
    mocks.retryCarouselPage.mockResolvedValue({});
    mocks.listProjectBrands.mockResolvedValue({ items: [] });
    mocks.getProjectMediaRevisionPreview.mockResolvedValue({
      asset_id: "logo-1",
      asset_revision: "revision-1",
      media_kind: "image",
      mime_type: "image/png",
      file_url: "/api/v2/media-assets/logo-1/file?revision_id=revision-1",
      thumbnail_url: null,
    });
    mocks.getProjectBrandSyncPreview.mockResolvedValue({
      project_id: "p1",
      status: "no_change",
      has_changes: false,
      result_code: "PROJECT_BRAND_SYNC_NO_CHANGE",
      changes_committed: false,
      changes: [],
    });
    mocks.assetPickerSelection = [
      { resource_id: "image-1", asset_id: "image-1", name: "门店图片 1" },
      { resource_id: "image-2", asset_id: "image-2", name: "门店图片 2" },
    ];
    mocks.recordAppEvent.mockResolvedValue({});
    mocks.createProjectArtifact.mockResolvedValue({});
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
    mocks.createAppRun.mockResolvedValue({
      app_run_id: "run-new",
      project_id: "p1",
      app_id: "builtin.marketing-copy",
      app_version: "1.0.0",
      state: "draft",
      state_version: 1,
      idempotency_key: "run-new",
      input_payload: {},
      context_snapshot_id: null,
      output_artifact_ids: [],
      error_code: null,
      archived_at: null,
      created_at: "now",
      updated_at: "now",
    });
    mocks.executeAppRun.mockResolvedValue({});
    vi.clearAllMocks();
  });

  it("keeps project lifecycle actions out of the focused application workbench", () => {
    render(<CreationWorkspace focused workbenchV2 />);
    expect(screen.getByRole("region", { name: "创作配置" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "生成结果" })).toBeInTheDocument();
    expect(screen.getByText("先选择或新建项目")).toBeInTheDocument();
    expect(screen.getByText("还未生成")).toBeInTheDocument();
    expect(screen.queryByText("项目操作")).not.toBeInTheDocument();
    expect(screen.queryByText("保存项目")).not.toBeInTheDocument();
    expect(screen.queryByText("归档项目")).not.toBeInTheDocument();
    expect(screen.queryByText("结果版本")).not.toBeInTheDocument();
  });

  it.each([1440, 900])(
    "keeps a created v3 project editable after reload at %ipx",
    async (viewportWidth) => {
    const brandedProject = {
      project_id: "p1", schema_version: 1, name: "夏日新品视觉验收", status: "active" as const,
      primary_goal: "提升到店", brand_id: "brand-1", current_context_snapshot_id: "ctx-v3",
      created_at: "now", updated_at: "now",
    };
    const v3Snapshot = {
      context_snapshot_id: "ctx-v3",
      project_id: "p1",
      schema_version: 3,
      payload: {
        schema_version: 3,
        brand_context: {
          brand_id: "brand-1",
          domain_revision: 1,
          values: {
            display_name: "街角咖啡", logo_ref: null, store_address: "人民路 1 号",
            phone: "021-00000000", primary_color: "#6D5DF6", secondary_color: "#F1ECFF",
            font_family: "", default_subtitle_style: "", default_bgm_ref: null,
            ending_card_text: "欢迎到店", coupon_phrase: "到店立减",
          },
          overridden_fields: [],
        },
        project_brief: {
          subject_type: "campaign",
          offer: { name: "夏日新品", category: "饮品", price_facts: [], promotion_facts: [] },
          marketing_goal: "提升到店",
          audience: { primary: "附近上班族", scenes: [] },
          selling_points: [], proof_points: [], required_facts: [], forbidden_claims: [], asset_refs: [],
        },
      },
      source_brand_id: "brand-1",
      source_brand_revision_id: "1",
      fingerprint: "sha256:test",
      created_at: "now",
    };
    listContentProjects.mockResolvedValue([brandedProject]);
    mocks.getCurrentContextSnapshot.mockResolvedValue(v3Snapshot);
    const originalWidth = window.innerWidth;
    Object.defineProperty(window, "innerWidth", { configurable: true, value: viewportWidth });

    const firstMount = render(
      <CreationWorkspace focused workbenchV2 brandProjectV1 />,
    );
    expect(await screen.findByText("本次项目信息")).toBeInTheDocument();
    expect(screen.getByLabelText("目标受众")).toHaveValue("附近上班族");
    firstMount.unmount();

    render(<CreationWorkspace focused workbenchV2 brandProjectV1 />);
    expect(await screen.findByText("本次项目信息")).toBeInTheDocument();
    expect(screen.getByText("街角咖啡")).toBeInTheDocument();
    expect(screen.getByLabelText("目标受众")).toBeEnabled();
    Object.defineProperty(window, "innerWidth", { configurable: true, value: originalWidth });
    },
  );

  it.each([
    "builtin.marketing-copy",
    "builtin.viral-titles",
    "builtin.douyin-carousel",
  ])("shows explicit legacy-brand association for a null snapshot in %s", async (appId) => {
    listContentProjects.mockResolvedValue([{
      project_id: "p-null",
      schema_version: 1,
      name: "待关联旧项目",
      status: "active",
      primary_goal: "保留历史内容",
      brand_id: null,
      current_context_snapshot_id: null,
      created_at: "now",
      updated_at: "now",
    }]);
    mocks.getCurrentContextSnapshot.mockResolvedValue(null);
    render(<CreationWorkspace appId={appId} focused workbenchV2 brandProjectV1 />);
    expect(await screen.findByText("这是旧项目")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "关联品牌包" })).toBeEnabled();
    expect(mocks.replaceProjectBrand).not.toHaveBeenCalled();
  });

  it("creates a reusable project from the My Projects dialog", async () => {
    render(<CreationWorkspace focused workbenchV2 />);

    fireEvent.click(screen.getByRole("button", { name: "我的项目" }));
    fireEvent.click(await screen.findByText("＋ 新建项目", { selector: ".ant-select-item-option-content" }));
    expect(screen.getByText("新建项目", { selector: ".ant-modal-title" })).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("新项目名称"), { target: { value: "街角咖啡" } });
    fireEvent.change(screen.getByLabelText("新项目营销目标"), { target: { value: "吸引附近上班族到店" } });
    fireEvent.click(screen.getByRole("button", { name: "创建并完善资料" }));

    await waitFor(() => expect(createContentProject).toHaveBeenCalledWith({
      name: "街角咖啡",
      primary_goal: "吸引附近上班族到店",
    }));
    expect(screen.getByLabelText("当前创作项目").parentElement).toHaveTextContent("新项目");
  });

  it("saves a project draft and exposes an unsaved-change guard", async () => {
    render(<CreationWorkspace />);
    fireEvent.change(screen.getByPlaceholderText("项目名称"), { target: { value: "新项目" } });
    fireEvent.change(screen.getByPlaceholderText("本次营销目标"), { target: { value: "目标" } });
    fireEvent.click(screen.getByText("保存项目"));
    await waitFor(() => expect(createContentProject).toHaveBeenCalledWith({ name: "新项目", primary_goal: "目标" }));
    expect(screen.getByDisplayValue("新项目")).toBeInTheDocument();
  });

  it("makes the global new-project action visibly enter a fresh focused state", async () => {
    listContentProjects.mockResolvedValue([{
      project_id: "p1", schema_version: 1, name: "已有项目", status: "active", primary_goal: "目标",
      brand_id: null, current_context_snapshot_id: null, created_at: "now", updated_at: "now",
    }]);
    render(<CreationWorkspace />);
    await waitFor(() => expect(screen.getByDisplayValue("已有项目")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "我的项目" }));
    fireEvent.click(await screen.findByText("＋ 新建项目", { selector: ".ant-select-item-option-content" }));

    expect(screen.getByText("新建创作项目")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("项目名称")).toHaveValue("");
    expect(screen.getByPlaceholderText("本次营销目标")).toHaveValue("");
  });

  it("ignores a stale project response after a faster project switch", async () => {
    const projectOne = {
      project_id: "p1", schema_version: 1, name: "项目一", status: "active" as const, primary_goal: "目标一",
      brand_id: null, current_context_snapshot_id: "ctx1", created_at: "now", updated_at: "now",
    };
    const projectTwo = {
      project_id: "p2", schema_version: 1, name: "项目二", status: "active" as const, primary_goal: "目标二",
      brand_id: null, current_context_snapshot_id: "ctx2", created_at: "now", updated_at: "now",
    };
    let resolveRunsOne!: (value: []) => void;
    let resolveSnapshotOne!: (value: {
      context_snapshot_id: string;
      project_id: string;
      schema_version: number;
      payload: Record<string, unknown>;
      source_brand_id: null;
      source_brand_revision_id: null;
      fingerprint: string;
      created_at: string;
    }) => void;
    const runsOne = new Promise<[]>((resolve) => { resolveRunsOne = resolve; });
    const snapshotOne = new Promise<Parameters<typeof resolveSnapshotOne>[0]>((resolve) => { resolveSnapshotOne = resolve; });
    listContentProjects.mockResolvedValue([projectOne, projectTwo]);
    listAppRuns.mockImplementation((projectId: string) => projectId === "p1" ? runsOne : Promise.resolve([]));
    mocks.getCurrentContextSnapshot.mockImplementation((projectId: string) => projectId === "p1"
      ? snapshotOne
      : Promise.resolve({
          context_snapshot_id: "ctx2", project_id: "p2", schema_version: 1,
          payload: { store_name: "二号门店", industry: "餐饮", product_or_service: "套餐", offer_category: "餐饮", target_audience: "附近顾客" },
          source_brand_id: null, source_brand_revision_id: null, fingerprint: "sha2", created_at: "now",
        }));
    render(<CreationWorkspace focused workbenchV2 />);

    fireEvent.mouseDown(await screen.findByLabelText("当前创作项目"));
    fireEvent.click(await screen.findByText("项目二", { selector: ".ant-select-item-option-content" }));
    await waitFor(() => expect(screen.getByLabelText("门店或品牌名称")).toHaveValue("二号门店"));

    resolveRunsOne([]);
    resolveSnapshotOne({
      context_snapshot_id: "ctx1", project_id: "p1", schema_version: 1,
      payload: { store_name: "一号门店" },
      source_brand_id: null, source_brand_revision_id: null, fingerprint: "sha1", created_at: "now",
    });
    await Promise.resolve();
    await Promise.resolve();
    expect(screen.getByLabelText("门店或品牌名称")).toHaveValue("二号门店");
    expect(screen.getByLabelText("当前创作项目").parentElement).toHaveTextContent("项目二");
  });

  it("guards project switching while a context draft is unsaved", async () => {
    const first = {
      project_id: "p1", schema_version: 1, name: "项目一", status: "active" as const, primary_goal: "目标一",
      brand_id: null, current_context_snapshot_id: "ctx1", created_at: "now", updated_at: "now",
    };
    const second = {
      project_id: "p2", schema_version: 1, name: "项目二", status: "active" as const, primary_goal: "目标二",
      brand_id: null, current_context_snapshot_id: null, created_at: "now", updated_at: "now",
    };
    listContentProjects.mockResolvedValue([first, second]);
    mocks.getCurrentContextSnapshot.mockResolvedValue({
      context_snapshot_id: "ctx1", project_id: "p1", schema_version: 1,
      payload: { store_name: "一号门店", industry: "餐饮", product_or_service: "套餐", offer_category: "餐饮", target_audience: "附近顾客" },
      source_brand_id: null, source_brand_revision_id: null, fingerprint: "sha1", created_at: "now",
    });
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<CreationWorkspace focused workbenchV2 />);
    await waitFor(() => expect(screen.getByLabelText("门店或品牌名称")).toHaveValue("一号门店"));
    fireEvent.change(screen.getByLabelText("商品卖点"), { target: { value: "当天现做" } });

    fireEvent.mouseDown(screen.getByLabelText("当前创作项目"));
    fireEvent.click(await screen.findByText("项目二", { selector: ".ant-select-item-option-content" }));

    expect(confirm).toHaveBeenCalled();
    expect(screen.getByLabelText("当前创作项目").parentElement).toHaveTextContent("项目一");
    expect(screen.getByLabelText("商品卖点")).toHaveValue("当天现做");
    confirm.mockRestore();
  });

  it("binds a newly saved v2 context snapshot to the next structured app run", async () => {
    const currentProject = {
      project_id: "p1", schema_version: 1, name: "咖啡项目", status: "active" as const, primary_goal: "到店转化",
      brand_id: null, current_context_snapshot_id: "ctx1", created_at: "now", updated_at: "now",
    };
    const legacy = {
      context_snapshot_id: "ctx1", project_id: "p1", schema_version: 1,
      payload: { store_name: "街角咖啡", industry: "咖啡餐饮", product_or_service: "夏日冰咖", offer_category: "饮品", target_audience: "周边上班族" },
      source_brand_id: null, source_brand_revision_id: null, fingerprint: "sha1", created_at: "now",
    };
    const saved = {
      ...legacy,
      context_snapshot_id: "ctx2",
      schema_version: 2,
      payload: {
        schema_version: 2,
        subject_type: "store",
        store_or_brand: { name: "街角咖啡", industry: "咖啡餐饮", address: null, contact: null },
        offer: { name: "夏日冰咖", category: "饮品", price_facts: [], promotion_facts: [] },
        audience: { primary: "周边上班族", scenes: [] },
        selling_points: [{ fact_id: "selling-1", text: "现磨", source: "user" }],
        proof_points: [],
        required_facts: [],
        forbidden_claims: [],
        asset_refs: [],
        brand_revision_ref: null,
      },
      fingerprint: "sha2",
    };
    listContentProjects.mockResolvedValue([currentProject]);
    mocks.getCurrentContextSnapshot.mockResolvedValue(legacy);
    mocks.saveContextSnapshot.mockResolvedValue(saved);
    render(<CreationWorkspace focused workbenchV2 />);
    await waitFor(() => expect(screen.getByText("请确认已带入的项目信息")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "保存项目信息" }));
    await waitFor(() => expect(screen.queryByText("请确认已带入的项目信息")).not.toBeInTheDocument());
    fireEvent.change(screen.getByPlaceholderText("选择项目后会自动带入商品或服务"), { target: { value: "夏日冰咖" } });
    fireEvent.click(screen.getByRole("button", { name: "生成营销文案" }));

    await waitFor(() => expect(mocks.createAppRun).toHaveBeenCalledWith(expect.objectContaining({
      project_id: "p1",
      app_id: "builtin.marketing-copy",
      context_snapshot_id: "ctx2",
    })));
  });

  it("creates a carousel run from artifact and registered asset references", async () => {
    mocks.listProjectArtifacts.mockResolvedValue([{
      artifact_id: "source-artifact", project_id: "p1", source_app_run_id: null, artifact_type: "copywriting", name: "门店文案", status: "active", current_version_id: "artifact_version_source", created_at: "now", updated_at: "now",
    }]);
    mocks.listArtifactVersions.mockResolvedValue([{
      artifact_version_id: "artifact_version_source", artifact_id: "source-artifact", project_id: "p1", version_number: 1, schema_version: 1, content: { artifact_type: "copywriting" }, file_refs: [], source: "generated", content_fingerprint: "sha", created_at: "now",
    }]);
    render(<CreationWorkspace appId="builtin.douyin-carousel" />);
    fireEvent.change(screen.getByPlaceholderText("项目名称"), { target: { value: "图文项目" } });
    fireEvent.change(screen.getByPlaceholderText("本次营销目标"), { target: { value: "到店咨询" } });
    fireEvent.click(screen.getByText("保存项目"));
    await waitFor(() => expect(createContentProject).toHaveBeenCalled());

    await waitFor(() => expect(screen.getByLabelText("本次使用内容")).toBeInTheDocument());
    await waitFor(() => expect(mocks.listArtifactVersions).toHaveBeenCalledWith("source-artifact"));
    mocks.listLibraryItemsV2.mockResolvedValue({ items: [
      { resource_id: "image-1", kind: "image", asset_id: "image-1", name: "门店图片 1", description: "门店图片", status: "ready", cover_url: null, tags: [], favorite: false, created_at: "now", updated_at: "now", summary: {} },
      { resource_id: "image-2", kind: "image", asset_id: "image-2", name: "门店图片 2", description: "门店图片", status: "ready", cover_url: null, tags: [], favorite: false, created_at: "now", updated_at: "now", summary: {} },
    ], total: 2 });
    fireEvent.click(screen.getByText("选择图片资产"));
    fireEvent.click(screen.getByRole("button", { name: "确认选择" }));
    mocks.createAppRun.mockResolvedValue({
      app_run_id: "carousel-run-new",
      project_id: "p1",
      app_id: "builtin.douyin-carousel",
      app_version: "1.0.0",
      state: "draft",
      state_version: 1,
      idempotency_key: "carousel-run-new",
      input_payload: {},
      context_snapshot_id: null,
      output_artifact_ids: [],
      error_code: null,
      archived_at: null,
      created_at: "now",
      updated_at: "now",
    });
    fireEvent.click(screen.getByText("生成抖音图文"));
    await waitFor(() => expect(mocks.createAppRun).toHaveBeenCalledWith(expect.objectContaining({
      app_id: "builtin.douyin-carousel",
      input_payload: {
        goal: "到店咨询",
        page_count: 3,
        source_artifact_version_ids: ["artifact_version_source"],
        asset_refs: ["asset:image-1", "asset:image-2"],
      },
    })));
    await waitFor(() => expect(mocks.executeAppRun).toHaveBeenCalledWith("carousel-run-new"));
  });

  it("creates a carousel v2 run with pinned context, style, source, and asset revisions", async () => {
    listContentProjects.mockResolvedValue([{
      project_id: "p1", schema_version: 1, name: "咖啡图文", status: "active", primary_goal: "吸引附近上班族到店",
      brand_id: null, current_context_snapshot_id: "ctx-v2", created_at: "now", updated_at: "now",
    }]);
    mocks.getCurrentContextSnapshot.mockResolvedValue({
      context_snapshot_id: "ctx-v2", project_id: "p1", schema_version: 2,
      payload: {
        schema_version: 2,
        subject_type: "store",
        store_or_brand: { name: "街角咖啡", industry: "咖啡餐饮", address: null, contact: null },
        offer: { name: "午后咖啡套餐", category: "饮品", price_facts: [], promotion_facts: [] },
        audience: { primary: "附近上班族", scenes: ["午后休息"] },
        selling_points: [{ fact_id: "selling-1", text: "现磨咖啡", source: "user", source_ref: null }],
        proof_points: [],
        required_facts: [],
        forbidden_claims: [],
        asset_refs: [],
        brand_revision_ref: null,
      },
      source_brand_id: null, source_brand_revision_id: null, fingerprint: "sha256:ctx", created_at: "now",
    });
    mocks.listProjectArtifacts.mockResolvedValue([{
      artifact_id: "source-artifact", project_id: "p1", source_app_run_id: null, artifact_type: "selected_title",
      name: "午后咖啡标题", status: "active", current_version_id: "source-v2", created_at: "now", updated_at: "now",
    }]);
    mocks.listArtifactVersions.mockResolvedValue([{
      artifact_version_id: "source-v2", artifact_id: "source-artifact", project_id: "p1", version_number: 2, schema_version: 1,
      content: { artifact_type: "selected_title", title: "午后咖啡怎么选" },
      file_refs: [], source: "edited", content_fingerprint: "sha256:source", created_at: "now",
    }]);
    mocks.listStylePresets.mockResolvedValue({
      items: [{
        style_id: "carousel.store_recommendation",
        version: 1,
        family: "carousel",
        name: "门店推荐清单",
        description: "一页一个重点",
        example: "先讲场景，再讲卖点。",
      }],
    });
    mocks.assetPickerSelection = [{
      resource_id: "image-1",
      asset_id: "image-1",
      name: "午后咖啡",
      revision: { revision_id: "revision-image-1-v3" },
    }];
    mocks.createAppRun.mockResolvedValue({
      app_run_id: "carousel-v2-run",
      project_id: "p1",
      app_id: "builtin.douyin-carousel",
      app_version: "1.1.0",
      state: "draft",
      state_version: 1,
      idempotency_key: "carousel-v2-run",
      input_payload: {},
      context_snapshot_id: "ctx-v2",
      output_artifact_ids: [],
      error_code: null,
      archived_at: null,
      created_at: "now",
      updated_at: "now",
    });

    render(<CreationWorkspace focused workbenchV2 carouselAppsV2 appId="builtin.douyin-carousel" />);
    await waitFor(() => expect(screen.getByText("门店推荐清单")).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText(/已带入：午后咖啡怎么选/)).toBeInTheDocument());
    fireEvent.click(screen.getByText("选择图片资产"));
    fireEvent.click(screen.getByRole("button", { name: "确认选择" }));
    fireEvent.change(screen.getByLabelText("图文封面钩子"), { target: { value: "午后咖啡怎么选" } });
    fireEvent.click(screen.getByText("更多配置"));
    fireEvent.change(screen.getByLabelText("图文行动号召"), { target: { value: "收藏后到店体验" } });
    fireEvent.change(screen.getByLabelText("图文发布描述"), { target: { value: "午后现磨咖啡选择" } });
    fireEvent.change(screen.getByLabelText("图文话题"), { target: { value: "咖啡，门店" } });
    fireEvent.click(screen.getByRole("button", { name: "生成抖音图文" }));

    await waitFor(() => expect(mocks.createAppRun).toHaveBeenCalledWith(expect.objectContaining({
      project_id: "p1",
      app_id: "builtin.douyin-carousel",
      app_version: "1.1.0",
      context_snapshot_id: "ctx-v2",
      input_payload: expect.objectContaining({
        schema_version: 2,
        input_schema_ref: "douyin-carousel-input.v2",
        context_snapshot_id: "ctx-v2",
        source_artifact_version_ids: ["source-v2"],
        style_ref: { style_id: "carousel.store_recommendation", version: 1 },
        task_brief: expect.objectContaining({
          page_count: 3,
          template_id: "template:clean-01",
          asset_refs: ["asset:image-1@revision-image-1-v3"],
          cover_hook: "午后咖啡怎么选",
          cta: "收藏后到店体验",
          publish_description: "午后现磨咖啡选择",
          hashtags: ["咖啡", "门店"],
        }),
      }),
    })));
    await waitFor(() => expect(mocks.executeAppRun).toHaveBeenCalledWith("carousel-v2-run"));
  });

  it("shows a user-facing source preview without exposing provenance metadata", async () => {
    const recent = new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString();
    const old = new Date(Date.now() - 120 * 24 * 60 * 60 * 1000).toISOString();
    listContentProjects.mockResolvedValue([{
      project_id: "p1", schema_version: 1, name: "图文项目", status: "active", primary_goal: "到店咨询",
      brand_id: null, current_context_snapshot_id: null, created_at: recent, updated_at: recent,
    }]);
    listAppRuns.mockResolvedValue([
      {
        app_run_id: "copy-run", project_id: "p1", app_id: "builtin.marketing-copy", app_version: "1.0.0",
        state: "needs_review", state_version: 2, idempotency_key: "copy-run", input_payload: { goal: "新品到店转化" },
        context_snapshot_id: null, output_artifact_ids: ["recent-artifact"], error_code: null, archived_at: null, created_at: recent, updated_at: recent,
      },
      {
        app_run_id: "carousel-run", project_id: "p1", app_id: "builtin.douyin-carousel", app_version: "1.0.0",
        state: "completed", state_version: 3, idempotency_key: "carousel-run", input_payload: { source_artifact_version_ids: ["recent-v1"] },
        context_snapshot_id: null, output_artifact_ids: [], error_code: null, archived_at: null, created_at: recent, updated_at: recent,
      },
    ]);
    mocks.listProjectArtifacts.mockResolvedValue([
      { artifact_id: "recent-artifact", project_id: "p1", source_app_run_id: "copy-run", artifact_type: "copywriting", name: "新品文案", status: "active", current_version_id: "recent-v1", created_at: recent, updated_at: recent },
      { artifact_id: "old-artifact", project_id: "p1", source_app_run_id: "copy-run", artifact_type: "copywriting", name: "旧文案", status: "active", current_version_id: "old-v1", created_at: old, updated_at: old },
    ]);
    mocks.listArtifactVersions.mockImplementation(async (artifactId: string) => [{
      artifact_version_id: artifactId === "recent-artifact" ? "recent-v1" : "old-v1",
      artifact_id: artifactId, project_id: "p1", version_number: 1, schema_version: 1,
      content: { artifact_type: "copywriting", variants: [{ full_text: artifactId === "recent-artifact" ? "新品咖啡限时优惠，欢迎到店体验" : "旧文案内容" }] },
      file_refs: [], source: "generated", content_fingerprint: "sha", created_at: artifactId === "recent-artifact" ? recent : old,
    }]);
    render(<CreationWorkspace appId="builtin.douyin-carousel" />);

    await waitFor(() => expect(mocks.listArtifactVersions).toHaveBeenCalledWith("recent-artifact"));
    await waitFor(() => expect(screen.getByText(/已带入：新品咖啡限时优惠/)).toBeInTheDocument());
    expect(screen.queryByText(/营销目标：新品到店转化/)).not.toBeInTheDocument();
    expect(screen.queryByText("最近使用")).not.toBeInTheDocument();
    expect(screen.queryByText("固定内容版本")).not.toBeInTheDocument();
  });

  it("opens the carousel workflow with the latest result without exposing technical versions", async () => {
    listContentProjects.mockResolvedValue([{
      project_id: "p1", schema_version: 1, name: "文案项目", status: "active", primary_goal: "新品转化",
      brand_id: null, current_context_snapshot_id: null, created_at: "2026-01-01", updated_at: "2026-01-01",
    }]);
    listAppRuns.mockResolvedValue([{
      app_run_id: "copy-run", project_id: "p1", app_id: "builtin.marketing-copy", app_version: "1.0.0",
      state: "needs_review", state_version: 2, idempotency_key: "copy-run", input_payload: {}, context_snapshot_id: null,
      output_artifact_ids: ["copy-artifact"], error_code: null, archived_at: null, created_at: "2026-01-01", updated_at: "2026-01-01",
    }]);
    mocks.listArtifactVersions.mockResolvedValue([
      { artifact_version_id: "copy-v1", artifact_id: "copy-artifact", project_id: "p1", version_number: 1, schema_version: 1, content: { artifact_type: "copywriting" }, file_refs: [], source: "generated", content_fingerprint: "sha1", created_at: "2026-01-01" },
      { artifact_version_id: "copy-v2", artifact_id: "copy-artifact", project_id: "p1", version_number: 2, schema_version: 1, content: { artifact_type: "copywriting" }, file_refs: [], source: "edited", content_fingerprint: "sha2", created_at: "2026-01-02" },
    ]);
    mocks.listProjectArtifacts.mockResolvedValue([{
      artifact_id: "copy-artifact", project_id: "p1", source_app_run_id: "copy-run", artifact_type: "copywriting", name: "门店文案", status: "active", current_version_id: "copy-v2", created_at: "2026-01-01", updated_at: "2026-01-02",
    }]);
    const onOpenApp = vi.fn();
    render(<CreationWorkspace focused workbenchV2 textAppsV2 appId="builtin.marketing-copy" onOpenApp={onOpenApp} />);

    await waitFor(() => expect(mocks.listArtifactVersions).toHaveBeenCalledWith("copy-artifact"));
    expect(screen.queryByLabelText("结果版本")).not.toBeInTheDocument();
    const moreButtons = screen.getAllByRole("button", { name: "更多操作" });
    fireEvent.click(moreButtons[moreButtons.length - 1]);
    fireEvent.click(await screen.findByText("制作抖音图文"));
    await waitFor(() => expect(onOpenApp).toHaveBeenCalledWith("builtin.douyin-carousel", "copy-v2"));
    expect(mocks.createArtifactHandoff).toHaveBeenCalledWith(expect.objectContaining({
      source_artifact_version_id: "copy-v2",
      artifact_version_ids: ["copy-v2"],
    }));
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
    mocks.listProjectArtifacts.mockImplementation(async (projectId: string) => projectId === "p1" ? [{
      artifact_id: "source-artifact", project_id: "p1", source_app_run_id: "carousel-run-1", artifact_type: "copywriting", name: "门店文案", status: "active", current_version_id: "source-v5", created_at: "2026-01-03", updated_at: "2026-01-03",
    }] : []);
    mocks.listArtifactVersions.mockResolvedValue([{
      artifact_version_id: "source-v5", artifact_id: "source-artifact", project_id: "p1", version_number: 5, schema_version: 1, content: { artifact_type: "copywriting" }, file_refs: [], source: "generated", content_fingerprint: "sha", created_at: "2026-01-03",
    }]);
    mocks.listLibraryItemsV2.mockResolvedValue({ items: [
      { resource_id: "one", kind: "image", asset_id: "one", name: "门店图一", description: "", status: "ready", cover_url: null, tags: [], favorite: false, created_at: "now", updated_at: "now", summary: {} },
      { resource_id: "two", kind: "image", asset_id: "two", name: "门店图二", description: "", status: "ready", cover_url: null, tags: [], favorite: false, created_at: "now", updated_at: "now", summary: {} },
    ], total: 2 });
    render(<CreationWorkspace appId="builtin.douyin-carousel" />);

    await waitFor(() => expect(screen.getByLabelText("本次使用内容")).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText(/已带入：暂无文案摘要/)).toBeInTheDocument());
    expect(screen.getByText("门店图一")).toBeInTheDocument();
    expect(screen.getByText("5 页")).toBeInTheDocument();

    fireEvent.mouseDown(screen.getByLabelText("当前创作项目"));
    fireEvent.click(await screen.findByText("图文项目二", { selector: ".ant-select-item-option-content" }));
    await waitFor(() => expect(screen.queryByDisplayValue("source-v5")).not.toBeInTheDocument());
    await waitFor(() => expect(screen.queryByText(/已带入：暂无文案摘要/)).not.toBeInTheDocument());
    await waitFor(() => expect(screen.queryByText("门店图一")).not.toBeInTheDocument());
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
    await waitFor(() => expect(screen.getByText("下载图片")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "更多操作" }));
    fireEvent.click(await screen.findByText("下载全部"));
    fireEvent.click(screen.getByRole("button", { name: "更多操作" }));
    fireEvent.click(screen.getByText("复制发布文案"));
    await waitFor(() => expect(mocks.downloadAppArtifactFile).toHaveBeenCalledWith("package-artifact", "carousel-package.zip"));
    await waitFor(() => expect(navigator.clipboard.writeText).toHaveBeenCalledWith("标题"));
  });

  it("previews real carousel pages, rerenders only the edited page, and hands the fixed package to publishing", async () => {
    listContentProjects.mockResolvedValue([{
      project_id: "p1", schema_version: 1, name: "图文项目", status: "active", primary_goal: "到店",
      brand_id: null, current_context_snapshot_id: "ctx-v2", created_at: "now", updated_at: "now",
    }]);
    mocks.getCurrentContextSnapshot.mockResolvedValue({
      context_snapshot_id: "ctx-v2", project_id: "p1", schema_version: 2, payload: { schema_version: 2 },
      source_brand_id: null, source_brand_revision_id: null, fingerprint: "sha256:ctx", created_at: "now",
    });
    listAppRuns.mockResolvedValue([{
      app_run_id: "carousel-run", project_id: "p1", app_id: "builtin.douyin-carousel", app_version: "1.1.0",
      state: "needs_review", state_version: 2, idempotency_key: "carousel-run", input_payload: {},
      context_snapshot_id: "ctx-v2", output_artifact_ids: ["package-artifact", "plan-artifact", "page-artifact"],
      error_code: null, archived_at: null, created_at: "now", updated_at: "now",
    }]);
    mocks.listArtifactVersions.mockImplementation(async (artifactId: string) => {
      if (artifactId === "package-artifact") {
        return [{
          artifact_version_id: "package-version", artifact_id: artifactId, project_id: "p1", version_number: 1, schema_version: 1,
          content: { artifact_type: "carousel_package", title: "午后咖啡怎么选", description: "午后现磨咖啡", hashtags: ["咖啡"] },
          file_refs: [
            { file_key: "page-01.png", kind: "image", mime_type: "image/png" },
            { file_key: "carousel-package.zip", kind: "zip", mime_type: "application/zip" },
          ],
          source: "generated", content_fingerprint: "sha256:package", created_at: "now",
        }];
      }
      if (artifactId === "plan-artifact") {
        return [{
          artifact_version_id: "plan-version", artifact_id: artifactId, project_id: "p1", version_number: 1, schema_version: 1,
          content: { artifact_type: "carousel_plan", page_outline: [{ page_index: 1, purpose: "封面" }] },
          file_refs: [], source: "generated", content_fingerprint: "sha256:plan", created_at: "now",
        }];
      }
      return [{
        artifact_version_id: "page-version", artifact_id: artifactId, project_id: "p1", version_number: 1, schema_version: 1,
        content: { artifact_type: "carousel_page", page_index: 1, text: "午后咖啡怎么选", asset_refs: ["asset:image-1@revision-1"] },
        file_refs: [{ file_key: "page-01.png", kind: "image", mime_type: "image/png" }],
        source: "generated", content_fingerprint: "sha256:page", created_at: "now",
      }];
    });
    mocks.downloadAppArtifactFile.mockResolvedValue(new Blob(["png"]));
    mocks.retryCarouselPage.mockResolvedValue({
      page_artifact_version: {
        artifact_version_id: "page-version-2", artifact_id: "page-artifact", project_id: "p1", version_number: 2, schema_version: 1,
        content: { artifact_type: "carousel_page", page_index: 1, text: "午后现磨咖啡，三步选对", asset_refs: ["asset:image-1@revision-1"] },
        file_refs: [{ file_key: "page-01-v2.png", kind: "image", mime_type: "image/png" }],
        source: "edited", content_fingerprint: "sha256:page-v2", created_at: "now",
      },
      package_artifact_version: {
        artifact_version_id: "package-version-2", artifact_id: "package-artifact", project_id: "p1", version_number: 2, schema_version: 1,
        content: { artifact_type: "carousel_package", title: "午后咖啡怎么选", description: "午后现磨咖啡", hashtags: ["咖啡"] },
        file_refs: [
          { file_key: "page-01-v2.png", kind: "image", mime_type: "image/png" },
          { file_key: "carousel-package-v2.zip", kind: "zip", mime_type: "application/zip" },
        ],
        source: "edited", content_fingerprint: "sha256:package-v2", created_at: "now",
      },
    });
    mocks.createPublishPackageV2.mockResolvedValue({ package_id: "publish-package-fixed" });
    vi.stubGlobal("URL", { ...URL, createObjectURL: vi.fn(() => "blob:page"), revokeObjectURL: vi.fn() });
    const onOpenPublishCenter = vi.fn();

    render(<CreationWorkspace
      focused
      workbenchV2
      carouselAppsV2
      appId="builtin.douyin-carousel"
      onOpenPublishCenter={onOpenPublishCenter}
    />);

    await waitFor(() => expect(screen.getByAltText("图文第 1 页预览")).toHaveAttribute("src", "blob:page"));
    expect(screen.getByLabelText("图文分页计划")).toHaveTextContent("封面");
    fireEvent.click(screen.getAllByRole("button", { name: "更多操作" })[0]);
    expect(await screen.findByText("下载图片")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("图文第1页文案"), { target: { value: "午后现磨咖啡，三步选对" } });
    fireEvent.click(screen.getByText("保存本页"));
    await waitFor(() => expect(mocks.retryCarouselPage).toHaveBeenCalledWith("page-artifact", {
      text: "午后现磨咖啡，三步选对",
      asset_refs: ["asset:image-1@revision-1"],
    }));
    await screen.findByText("当前页已生成新版本，其他页面保持不变；旧发布包已安全失效。");
    fireEvent.click(screen.getByText("交给发布中心"));
    await waitFor(() => expect(mocks.createPublishPackageV2).toHaveBeenCalledWith({
      project_id: "p1",
      artifact_version_ids: ["package-version-2"],
    }));
    expect(onOpenPublishCenter).toHaveBeenCalledWith("publish-package-fixed");
  }, 15_000);

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
    await waitFor(() => expect(screen.getByText("请确认")).toBeInTheDocument());
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
    mocks.listProjectArtifacts.mockResolvedValue([{
      artifact_id: "artifact1", project_id: "p1", source_app_run_id: "run1", artifact_type: "copywriting", name: "门店文案", status: "active", current_version_id: "version1", created_at: "now", updated_at: "now",
    }]);
    mocks.createAppRun.mockResolvedValue({ app_run_id: "title-run", app_id: "builtin.viral-titles", app_version: "1.0.0" });
    mocks.createArtifactHandoff.mockResolvedValue({});
    render(<CreationWorkspace />);
    await waitFor(() => expect(screen.getByText("交给爆款标题")).toBeInTheDocument());
    fireEvent.click(screen.getByText("交给爆款标题"));
    await waitFor(() => expect(mocks.createAppRun).toHaveBeenCalledWith(expect.objectContaining({ context_snapshot_id: "ctx1" })));
    expect(mocks.createArtifactHandoff).toHaveBeenCalledWith(expect.objectContaining({ target_run_id: "title-run" }));
  });

  it("creates a marketing-copy v2 run with a pinned project snapshot and trusted style reference", async () => {
    listContentProjects.mockResolvedValue([{
      project_id: "p1", schema_version: 1, name: "咖啡项目", status: "active", primary_goal: "吸引附近上班族到店",
      brand_id: null, current_context_snapshot_id: "ctx-v2", created_at: "now", updated_at: "now",
    }]);
    mocks.getCurrentContextSnapshot.mockResolvedValue({
      context_snapshot_id: "ctx-v2",
      project_id: "p1",
      schema_version: 2,
      payload: {
        schema_version: 2,
        offer: { name: "午后咖啡套餐", category: "饮品" },
        audience: { primary: "附近上班族", scenes: [] },
        selling_points: [{ fact_id: "selling-1", text: "现磨", source: "user" }],
        required_facts: [],
      },
      source_brand_id: null,
      source_brand_revision_id: null,
      fingerprint: "sha256:ctx",
      created_at: "now",
    });
    mocks.listStylePresets.mockResolvedValue({
      items: [{
        style_id: "copy.owner_voice",
        version: 1,
        family: "copy",
        name: "老板口吻",
        description: "自然介绍",
        example: "我们每天认真做好这一杯。",
      }],
    });
    mocks.createAppRun.mockResolvedValue({
      app_run_id: "run-v2",
      project_id: "p1",
      app_id: "builtin.marketing-copy",
      app_version: "1.1.0",
      state: "draft",
      output_artifact_ids: [],
    });

    render(<CreationWorkspace focused workbenchV2 textAppsV2 />);
    await waitFor(() => expect(screen.getByText("老板口吻")).toBeInTheDocument());
    fireEvent.change(screen.getByPlaceholderText("选择项目后会自动带入商品或服务"), { target: { value: "午后咖啡套餐" } });
    fireEvent.change(screen.getByLabelText("营销利益点"), { target: { value: "到店，新品" } });
    fireEvent.click(screen.getByRole("button", { name: "生成营销文案" }));

    await waitFor(() => expect(mocks.createAppRun).toHaveBeenCalledWith(expect.objectContaining({
      project_id: "p1",
      app_id: "builtin.marketing-copy",
      app_version: "1.1.0",
      context_snapshot_id: "ctx-v2",
      input_payload: expect.objectContaining({
        schema_version: 2,
        input_schema_ref: "marketing-copy-input.v2",
        context_snapshot_id: "ctx-v2",
        style_ref: { style_id: "copy.owner_voice", version: 1 },
        task_brief: expect.objectContaining({
          offer_name: "午后咖啡套餐",
          selling_point_fact_ids: ["selling-1"],
          benefit_tags: ["到店", "新品"],
          audience: "附近上班族",
        }),
      }),
    })));
  });

  it("hands a pinned copywriting version to the title workbench without executing the target", async () => {
    const onOpenApp = vi.fn();
    listContentProjects.mockResolvedValue([{
      project_id: "p1", schema_version: 1, name: "已有项目", status: "active", primary_goal: "目标",
      brand_id: null, current_context_snapshot_id: "ctx-v2", created_at: "now", updated_at: "now",
    }]);
    listAppRuns.mockResolvedValue([{
      app_run_id: "run1", project_id: "p1", app_id: "builtin.marketing-copy", app_version: "1.1.0",
      state: "needs_review", state_version: 3, idempotency_key: "run1", input_payload: {},
      context_snapshot_id: "ctx-v2", output_artifact_ids: ["artifact1"], error_code: null, archived_at: null, created_at: "now", updated_at: "now",
    }]);
    mocks.getCurrentContextSnapshot.mockResolvedValue({
      context_snapshot_id: "ctx-v2", project_id: "p1", schema_version: 2, payload: {},
      source_brand_id: null, source_brand_revision_id: null, fingerprint: "sha", created_at: "now",
    });
    mocks.listArtifactVersions.mockResolvedValue([{
      artifact_version_id: "version1", artifact_id: "artifact1", project_id: "p1", version_number: 1, schema_version: 1,
      content: { schema_version: 1, artifact_type: "copywriting", variants: [], missing_facts: [], risk_flags: [] },
      file_refs: [], source: "generated", content_fingerprint: "sha", created_at: "now",
    }]);
    mocks.listProjectArtifacts.mockResolvedValue([{
      artifact_id: "artifact1", project_id: "p1", source_app_run_id: "run1", artifact_type: "copywriting", name: "门店文案", status: "active", current_version_id: "version1", created_at: "now", updated_at: "now",
    }]);
    mocks.createArtifactHandoff.mockResolvedValue({});

    render(<CreationWorkspace focused workbenchV2 textAppsV2 onOpenApp={onOpenApp} />);
    await waitFor(() => expect(screen.getByText("交给爆款标题")).toBeInTheDocument());
    fireEvent.click(screen.getByText("交给爆款标题"));

    await waitFor(() => expect(mocks.createArtifactHandoff).toHaveBeenCalledWith({
      project_id: "p1",
      source_artifact_id: "artifact1",
      source_artifact_version_id: "version1",
      target_app_id: "builtin.viral-titles",
      target_app_version: "1.1.0",
      artifact_version_ids: ["version1"],
      mapping_version: 2,
    }));
    expect(onOpenApp).toHaveBeenCalledWith("builtin.viral-titles", "version1");
    expect(mocks.executeAppRun).not.toHaveBeenCalled();
    expect(mocks.recordAppEvent).toHaveBeenCalledWith("run1", "handoff.completed", expect.objectContaining({
      artifact_version_id: "version1",
    }));
  });

  it("hands a selected title to the digital-human workbench with an idempotent selected-title version", async () => {
    const onOpenApp = vi.fn();
    listContentProjects.mockResolvedValue([{
      project_id: "p1", schema_version: 1, name: "标题项目", status: "active", primary_goal: "目标",
      brand_id: null, current_context_snapshot_id: null, created_at: "now", updated_at: "now",
    }]);
    listAppRuns.mockResolvedValue([{
      app_run_id: "title-run", project_id: "p1", app_id: "builtin.viral-titles", app_version: "1.1.0",
      state: "needs_review", state_version: 2, idempotency_key: "title-run", input_payload: {},
      context_snapshot_id: null, output_artifact_ids: ["title-artifact"], error_code: null, archived_at: null, created_at: "now", updated_at: "now",
    }]);
    mocks.listArtifactVersions.mockImplementation(async (artifactId: string) => artifactId === "selected-title-artifact"
      ? [{
          artifact_version_id: "selected-title-v1", artifact_id: "selected-title-artifact", project_id: "p1", version_number: 1, schema_version: 1,
          content: { artifact_type: "selected_title", title: "午后咖啡怎么选", source_title_set_artifact_id: "title-artifact", source_title_set_version_id: "title-v1", selected_index: 0 },
          file_refs: [], source: "edited", content_fingerprint: "selected-sha", created_at: "now",
        }]
      : [{
          artifact_version_id: "title-v1", artifact_id: "title-artifact", project_id: "p1", version_number: 1, schema_version: 1,
          content: { artifact_type: "title_set", candidates: [{ title: "午后咖啡怎么选", angle: "场景", length: 7 }] },
          file_refs: [], source: "generated", content_fingerprint: "sha", created_at: "now",
        }]);
    mocks.createProjectArtifact.mockResolvedValue({ artifact_id: "selected-title-artifact" });
    mocks.appendArtifactVersion.mockResolvedValue({
      artifact_version_id: "selected-title-v1", artifact_id: "selected-title-artifact", project_id: "p1", version_number: 1, schema_version: 1,
      content: { artifact_type: "selected_title", title: "午后咖啡怎么选" }, file_refs: [], source: "edited", content_fingerprint: "selected-sha", created_at: "now",
    });
    mocks.createArtifactHandoff.mockResolvedValue({});
    mocks.listProjectArtifacts.mockImplementation(async () => mocks.createProjectArtifact.mock.calls.length
      ? [{ artifact_id: "selected-title-artifact", project_id: "p1", source_app_run_id: "title-run", artifact_type: "selected_title", name: "午后咖啡怎么选", status: "active", current_version_id: "selected-title-v1", created_at: "now", updated_at: "now" }]
      : []);

    render(<CreationWorkspace focused workbenchV2 textAppsV2 appId="builtin.viral-titles" onOpenApp={onOpenApp} />);
    await waitFor(() => expect(screen.getByText("使用这个标题")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "更多操作" }));
    fireEvent.click(await screen.findByText("制作抖音图文"));
    await waitFor(() => expect(onOpenApp).toHaveBeenCalledWith("builtin.douyin-carousel", "selected-title-v1"));
    fireEvent.click(screen.getByText("制作数字人"));

    await waitFor(() => expect(onOpenApp).toHaveBeenCalledWith("builtin.digital-human-video", "selected-title-v1"));
    expect(mocks.createProjectArtifact).toHaveBeenCalledTimes(1);
    expect(mocks.createArtifactHandoff).toHaveBeenCalledWith(expect.objectContaining({
      source_artifact_id: "selected-title-artifact",
      source_artifact_version_id: "selected-title-v1",
      target_app_id: "builtin.douyin-carousel",
      artifact_version_ids: ["selected-title-v1"],
    }));
    expect(mocks.createArtifactHandoff).toHaveBeenCalledWith(expect.objectContaining({
      source_artifact_id: "selected-title-artifact",
      source_artifact_version_id: "selected-title-v1",
      target_app_id: "builtin.digital-human-video",
      artifact_version_ids: ["selected-title-v1"],
    }));
  }, 15_000);

  it("warns when a pinned title source has a newer upstream version", async () => {
    listContentProjects.mockResolvedValue([{
      project_id: "p1", schema_version: 1, name: "标题来源项目", status: "active", primary_goal: "目标",
      brand_id: null, current_context_snapshot_id: null, created_at: "now", updated_at: "now",
    }]);
    listAppRuns.mockResolvedValue([]);
    mocks.listProjectArtifacts.mockResolvedValue([{
      artifact_id: "copy-source", project_id: "p1", source_app_run_id: null, artifact_type: "copywriting", name: "门店文案", status: "active", current_version_id: "copy-source-v2", created_at: "now", updated_at: "now",
    }]);
    mocks.listArtifactVersions.mockResolvedValue([
      { artifact_version_id: "copy-source-v1", artifact_id: "copy-source", project_id: "p1", version_number: 1, schema_version: 1, content: { artifact_type: "copywriting", variants: [{ full_text: "旧版本" }] }, file_refs: [], source: "generated", content_fingerprint: "sha1", created_at: "now" },
      { artifact_version_id: "copy-source-v2", artifact_id: "copy-source", project_id: "p1", version_number: 2, schema_version: 1, content: { artifact_type: "copywriting", variants: [{ full_text: "新版本" }] }, file_refs: [], source: "edited", content_fingerprint: "sha2", created_at: "now" },
    ]);

    render(<CreationWorkspace focused workbenchV2 textAppsV2 appId="builtin.viral-titles" initialSourceArtifactVersionId="copy-source-v1" />);
    await waitFor(() => expect(screen.getByText("这段文案后来有过更新")).toBeInTheDocument());
    expect(screen.getByText(/本次仍使用你刚才确认的内容/)).toBeInTheDocument();
  });

  it("fails closed when an initial title source version is missing from the current project", async () => {
    listContentProjects.mockResolvedValue([{
      project_id: "p1", schema_version: 1, name: "标题来源项目", status: "active", primary_goal: "目标",
      brand_id: null, current_context_snapshot_id: null, created_at: "now", updated_at: "now",
    }]);
    listAppRuns.mockResolvedValue([]);
    mocks.listProjectArtifacts.mockResolvedValue([{
      artifact_id: "copy-source", project_id: "p1", source_app_run_id: null, artifact_type: "copywriting", name: "门店文案", status: "active", current_version_id: "copy-source-v2", created_at: "now", updated_at: "now",
    }]);
    mocks.listArtifactVersions.mockResolvedValue([{
      artifact_version_id: "copy-source-v2", artifact_id: "copy-source", project_id: "p1", version_number: 2, schema_version: 1,
      content: { artifact_type: "copywriting", variants: [{ full_text: "当前版本" }] }, file_refs: [], source: "edited", content_fingerprint: "sha2", created_at: "now",
    }]);

    render(<CreationWorkspace focused workbenchV2 textAppsV2 appId="builtin.viral-titles" initialSourceArtifactVersionId="missing-version" />);
    expect(await screen.findByText(/带入的标题来源版本不存在或已归档/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "生成爆款标题" })).toBeDisabled();
  });

  it("fails closed when an initial carousel source version is missing from the current project", async () => {
    listContentProjects.mockResolvedValue([{
      project_id: "p1", schema_version: 1, name: "图文来源项目", status: "active", primary_goal: "目标",
      brand_id: null, current_context_snapshot_id: null, created_at: "now", updated_at: "now",
    }]);
    listAppRuns.mockResolvedValue([]);
    mocks.listProjectArtifacts.mockResolvedValue([{
      artifact_id: "copy-source", project_id: "p1", source_app_run_id: null, artifact_type: "copywriting", name: "门店文案", status: "active", current_version_id: "copy-source-v2", created_at: "now", updated_at: "now",
    }]);
    mocks.listArtifactVersions.mockResolvedValue([{
      artifact_version_id: "copy-source-v2", artifact_id: "copy-source", project_id: "p1", version_number: 2, schema_version: 1,
      content: { artifact_type: "copywriting", variants: [{ full_text: "当前版本" }] }, file_refs: [], source: "edited", content_fingerprint: "sha2", created_at: "now",
    }]);

    render(<CreationWorkspace focused appId="builtin.douyin-carousel" initialSourceArtifactVersionId="missing-version" />);
    expect(await screen.findByText(/带入的图文来源版本不存在或已归档/)).toBeInTheDocument();
    expect(screen.getByLabelText("本次使用内容")).toHaveValue("");
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
    fireEvent.click(screen.getByText("保存本次编辑"));
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
    fireEvent.click(screen.getByText("保存本次编辑"));
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
    fireEvent.click(screen.getByText("保存本次编辑"));
    await waitFor(() => expect(mocks.appendArtifactVersion).toHaveBeenCalledWith(
      "title-artifact",
      expect.objectContaining({ candidates: expect.arrayContaining([expect.objectContaining({ title: "😀标题", length: 3 })]) }),
      "edited",
    ));
  });
});
