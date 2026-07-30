import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  BrandProjectContextPanel,
  BrandProjectCreateDialog,
} from "./BrandProjectContext";
import {
  createContentProject,
  getBrandProjectSummary,
  getProjectMediaRevisionPreview,
  getProjectBrandSyncPreview,
  listProjectBrands,
  replaceProjectBrand,
  syncProjectBrand,
  updateProjectMaterial,
  type ContentProject,
  type ContextSnapshot,
} from "../../api";

vi.mock("../../api", () => ({
  createContentProject: vi.fn(),
  getBrandProjectSummary: vi.fn(),
  getProjectMediaRevisionPreview: vi.fn(),
  getProjectBrandSyncPreview: vi.fn(),
  listProjectBrands: vi.fn(),
  replaceProjectBrand: vi.fn(),
  syncProjectBrand: vi.fn(),
  updateProjectMaterial: vi.fn(),
}));

const project: ContentProject = {
  project_id: "project-1",
  schema_version: 1,
  name: "夏日项目",
  status: "active",
  primary_goal: "提升到店",
  brand_id: "brand-1",
  current_context_snapshot_id: "context-1",
  created_at: "2026-07-29T00:00:00Z",
  updated_at: "2026-07-29T00:00:00Z",
};

const snapshot: ContextSnapshot = {
  context_snapshot_id: "context-1",
  project_id: "project-1",
  schema_version: 3,
  source_brand_id: "brand-1",
  source_brand_revision_id: "7",
  fingerprint: "sha256:hidden",
  created_at: "2026-07-29T00:00:00Z",
  payload: {
    schema_version: 3,
    brand_context: {
      brand_id: "brand-1",
      domain_revision: 7,
      values: {
        display_name: "街角咖啡",
        logo_ref: null,
        store_address: "人民路 1 号",
        phone: "400-100-1000",
        primary_color: "#6D5DF6",
        secondary_color: "#F1ECFF",
        font_family: "Inter",
        default_subtitle_style: "清晰白字",
        default_bgm_ref: null,
        ending_card_text: "到店见",
        coupon_phrase: "到店立减",
      },
      overridden_fields: [],
    },
    project_brief: {
      subject_type: "campaign",
      offer: { name: "冰咖啡", category: "饮品", price_facts: [], promotion_facts: [] },
      marketing_goal: "提升到店",
      audience: { primary: "附近上班族", scenes: [] },
      selling_points: [],
      proof_points: [],
      required_facts: [],
      forbidden_claims: [],
      asset_refs: [],
    },
  },
};

describe("BrandProjectCreateDialog", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getBrandProjectSummary).mockResolvedValue({
      brand_id: "brand-1",
      domain_revision: 7,
      values: {} as never,
    });
    vi.mocked(createContentProject).mockResolvedValue(project);
  });

  it("supports zero brands and submits an unbound project only after confirmation", async () => {
    vi.mocked(listProjectBrands).mockResolvedValue({ items: [] });
    render(<BrandProjectCreateDialog open busy={false} onCancel={vi.fn()} onCreated={vi.fn()} />);
    expect(await screen.findByText("企业资产库中暂无可用品牌包")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "前往企业资产库" })).toHaveAttribute("href", "#/assets");
    expect(createContentProject).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("新项目名称"), { target: { value: "无品牌活动" } });
    fireEvent.change(screen.getByLabelText("新项目营销目标"), { target: { value: "验证市场" } });
    fireEvent.click(screen.getByRole("button", { name: "创建项目" }));
    await waitFor(() => expect(createContentProject).toHaveBeenCalledWith({
      name: "无品牌活动",
      primary_goal: "验证市场",
      brand_id: undefined,
      expected_brand_domain_revision: undefined,
    }));
  });

  it("auto-selects the only brand without a silent project write", async () => {
    vi.mocked(listProjectBrands).mockResolvedValue({
      items: [{ brand_id: "brand-1", name: "街角咖啡", status: "ready", summary: {} }],
    });
    render(<BrandProjectCreateDialog open busy={false} onCancel={vi.fn()} onCreated={vi.fn()} />);
    expect(await screen.findByText(/仅有一个品牌包，已为你选中/)).toBeInTheDocument();
    expect(screen.getByText("街角咖啡")).toBeInTheDocument();
    expect(createContentProject).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("新项目名称"), { target: { value: "新品活动" } });
    fireEvent.change(screen.getByLabelText("新项目营销目标"), { target: { value: "提升到店" } });
    expect(createContentProject).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "创建项目" }));
    await waitFor(() => expect(createContentProject).toHaveBeenCalledWith(expect.objectContaining({
      brand_id: "brand-1",
      expected_brand_domain_revision: 7,
    })));
  });

  it("requires an explicit choice when multiple brands are available", async () => {
    vi.mocked(listProjectBrands).mockResolvedValue({
      items: [
        { brand_id: "brand-1", name: "街角咖啡", status: "ready", summary: {} },
        { brand_id: "brand-2", name: "城市面包", status: "ready", summary: {} },
      ],
    });
    render(<BrandProjectCreateDialog open busy={false} onCancel={vi.fn()} onCreated={vi.fn()} />);
    const select = await screen.findByLabelText("新项目品牌包");
    expect(select).toHaveAttribute("aria-expanded", "false");
    fireEvent.mouseDown(select);
    fireEvent.change(select, { target: { value: "城市" } });
    fireEvent.click(await screen.findByText("城市面包", { selector: ".ant-select-item-option-content" }));
    expect(createContentProject).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("新项目名称"), { target: { value: "面包节" } });
    fireEvent.change(screen.getByLabelText("新项目营销目标"), { target: { value: "提升到店" } });
    fireEvent.click(screen.getByRole("button", { name: "创建项目" }));
    await waitFor(() => expect(getBrandProjectSummary).toHaveBeenCalledWith("brand-2"));
    expect(createContentProject).toHaveBeenCalledWith(expect.objectContaining({ brand_id: "brand-2" }));
  });
});

describe("BrandProjectContextPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(listProjectBrands).mockResolvedValue({
      items: [{ brand_id: "brand-1", name: "街角咖啡", status: "ready", summary: {} }],
    });
    vi.mocked(getBrandProjectSummary).mockResolvedValue({
      brand_id: "brand-1",
      domain_revision: 7,
      values: {} as never,
    });
    vi.mocked(getProjectMediaRevisionPreview).mockResolvedValue({
      asset_id: "logo-1",
      asset_revision: "logo-revision-7",
      media_kind: "image",
      mime_type: "image/png",
      file_url: "/api/v2/media-assets/logo-1/file?revision_id=logo-revision-7",
      thumbnail_url: "/api/v2/media-assets/logo-1/variants/thumbnail?revision_id=logo-revision-7",
    });
    vi.mocked(getProjectBrandSyncPreview).mockResolvedValue({
      project_id: "project-1",
      status: "no_change",
      has_changes: false,
      result_code: "PROJECT_BRAND_SYNC_NO_CHANGE",
      changes_committed: false,
      changes: [],
    });
    vi.mocked(updateProjectMaterial).mockResolvedValue({ ...snapshot, context_snapshot_id: "context-2" });
    vi.mocked(replaceProjectBrand).mockResolvedValue(project);
    vi.mocked(syncProjectBrand).mockResolvedValue({});
  });

  it("shows campaign fields, keeps technical fields hidden, and restores overrides", async () => {
    render(
      <BrandProjectContextPanel
        project={project}
        snapshot={snapshot}
        open
        onClose={vi.fn()}
        onSaved={vi.fn()}
        onReload={vi.fn().mockResolvedValue(undefined)}
      />,
    );
    expect(screen.getByText("街角咖啡")).toBeInTheDocument();
    expect(screen.getByLabelText("推广对象")).toHaveValue("冰咖啡");
    expect(screen.queryByText(/context-1|brand-1|revision|fingerprint/i)).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("本项目品牌设置"));
    const address = await screen.findByLabelText("地址");
    fireEvent.change(address, { target: { value: "快闪店地址" } });
    expect(screen.getByText("仅本项目使用")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "恢复品牌默认" }));
    expect(screen.queryByText("仅本项目使用")).not.toBeInTheDocument();
  });

  it("previews changes without writing and synchronizes only after explicit confirmation", async () => {
    vi.mocked(getProjectBrandSyncPreview).mockResolvedValue({
      project_id: "project-1",
      status: "changes_available",
      has_changes: true,
      result_code: null,
      changes_committed: false,
      changes: [
        { field: "primary_color", label: "品牌主色", status: "updated" },
        { field: "ending_card_text", label: "结尾卡文案", status: "preserved_project_override" },
      ],
    });
    const reload = vi.fn().mockResolvedValue(undefined);
    render(
      <BrandProjectContextPanel
        project={project}
        snapshot={snapshot}
        open={false}
        onClose={vi.fn()}
        onSaved={vi.fn()}
        onReload={reload}
      />,
    );
    const viewChanges = await screen.findByRole("button", { name: "查看变化" });
    expect(syncProjectBrand).not.toHaveBeenCalled();
    fireEvent.click(viewChanges);
    expect(await screen.findByText("将同步更新")).toBeInTheDocument();
    expect(screen.getByText("保留本项目设置")).toBeInTheDocument();
    expect(syncProjectBrand).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "同步最新品牌资料" }));
    await waitFor(() => expect(syncProjectBrand).toHaveBeenCalledTimes(1));
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it("explicitly associates a null-snapshot legacy project without an automatic write", async () => {
    const legacyProject = { ...project, brand_id: null, current_context_snapshot_id: null };
    const reload = vi.fn().mockResolvedValue(undefined);
    render(
      <BrandProjectContextPanel
        project={legacyProject}
        snapshot={null}
        open={false}
        onClose={vi.fn()}
        onSaved={vi.fn()}
        onReload={reload}
      />,
    );
    const legacyRegion = screen.getByRole("region", { name: "旧项目品牌关联" });
    expect(legacyRegion).toBeInTheDocument();
    expect(legacyRegion.querySelector(".ant-alert")).toHaveClass("brand-project-status-alert");
    expect(legacyRegion.querySelector(".ant-alert-actions")).toBeInTheDocument();
    expect(screen.getByText("这是旧项目")).toBeInTheDocument();
    expect(replaceProjectBrand).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "关联品牌包" }));
    const select = await screen.findByLabelText("选择项目品牌包");
    fireEvent.mouseDown(select);
    fireEvent.click(await screen.findByText("街角咖啡", { selector: ".ant-select-item-option-content" }));
    fireEvent.click(screen.getByRole("button", { name: "确认关联" }));
    await waitFor(() => expect(replaceProjectBrand).toHaveBeenCalledWith(
      "project-1",
      {
        brand_id: "brand-1",
        expected_context_snapshot_id: null,
        expected_domain_revision: 7,
      },
    ));
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it.each([1, 2])(
    "keeps a schema v%i project unchanged until explicit brand association",
    async (schemaVersion) => {
      const legacySnapshot: ContextSnapshot = {
        ...snapshot,
        context_snapshot_id: `legacy-${schemaVersion}`,
        schema_version: schemaVersion,
        payload: { schema_version: schemaVersion },
        source_brand_id: null,
        source_brand_revision_id: null,
      };
      render(
        <BrandProjectContextPanel
          project={{
            ...project,
            brand_id: null,
            current_context_snapshot_id: legacySnapshot.context_snapshot_id,
          }}
          snapshot={legacySnapshot}
          open={false}
          onClose={vi.fn()}
          onSaved={vi.fn()}
          onReload={vi.fn().mockResolvedValue(undefined)}
        />,
      );
      expect(await screen.findByText("这是旧项目")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "关联品牌包" })).toBeEnabled();
      expect(replaceProjectBrand).not.toHaveBeenCalled();
    },
  );

  it("loads the pinned Logo revision and never reads the current media list", async () => {
    const pinnedSnapshot = {
      ...snapshot,
      payload: {
        ...snapshot.payload,
        brand_context: {
          ...(snapshot.payload.brand_context as Record<string, unknown>),
          values: {
            ...((snapshot.payload.brand_context as { values: Record<string, unknown> }).values),
            logo_ref: { asset_id: "logo-1", asset_revision: "logo-revision-7" },
          },
        },
      },
    };
    const { rerender } = render(
      <BrandProjectContextPanel
        project={project}
        snapshot={pinnedSnapshot}
        open={false}
        onClose={vi.fn()}
        onSaved={vi.fn()}
        onReload={vi.fn().mockResolvedValue(undefined)}
      />,
    );
    await waitFor(() => expect(getProjectMediaRevisionPreview).toHaveBeenCalledWith(
      "logo-1",
      "logo-revision-7",
    ));
    vi.mocked(getProjectMediaRevisionPreview).mockRejectedValueOnce(new Error("品牌素材版本无法读取"));
    const nextPinnedSnapshot = {
      ...pinnedSnapshot,
      context_snapshot_id: "context-2",
      payload: {
        ...pinnedSnapshot.payload,
        brand_context: {
          ...(pinnedSnapshot.payload.brand_context as Record<string, unknown>),
          values: {
            ...((pinnedSnapshot.payload.brand_context as { values: Record<string, unknown> }).values),
            logo_ref: { asset_id: "logo-1", asset_revision: "logo-revision-8" },
          },
        },
      },
    };
    rerender(
      <BrandProjectContextPanel
        project={{ ...project, current_context_snapshot_id: "context-2" }}
        snapshot={nextPinnedSnapshot}
        open={false}
        onClose={vi.fn()}
        onSaved={vi.fn()}
        onReload={vi.fn().mockResolvedValue(undefined)}
      />,
    );
    await waitFor(() => expect(screen.getByText("Logo 暂不可用")).toBeInTheDocument());
    expect(getProjectMediaRevisionPreview).toHaveBeenLastCalledWith("logo-1", "logo-revision-8");
    expect(screen.queryByText(/logo-revision|logo-1/i)).not.toBeInTheDocument();
  });

  it("keeps the historical summary readable and exposes preview and brand-list failures", async () => {
    vi.mocked(getProjectBrandSyncPreview).mockRejectedValue(
      new Error("这个品牌当前不可用于新项目"),
    );
    vi.mocked(listProjectBrands).mockRejectedValue(
      new Error("后端服务未连接，请确认 API 服务已启动。"),
    );
    render(
      <BrandProjectContextPanel
        project={project}
        snapshot={snapshot}
        open={false}
        onClose={vi.fn()}
        onSaved={vi.fn()}
        onReload={vi.fn().mockResolvedValue(undefined)}
      />,
    );
    expect(screen.getByText("街角咖啡")).toBeInTheDocument();
    const archivedMessage = await screen.findByText(/无法检查品牌更新：这个品牌当前不可用于新项目/);
    expect(archivedMessage).toBeInTheDocument();
    expect(archivedMessage.closest(".ant-alert")).toHaveClass("brand-project-status-alert");
    expect(archivedMessage.closest(".ant-alert")?.querySelector(".brand-project-status-alert__actions")).not.toBeNull();
    expect(screen.getByText(/品牌列表加载失败：后端服务未连接/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "同步最新品牌资料" })).toBeDisabled();
    expect(screen.getAllByRole("button", { name: "重新关联品牌" }).length).toBeGreaterThan(0);
    expect(syncProjectBrand).not.toHaveBeenCalled();
  });
});
