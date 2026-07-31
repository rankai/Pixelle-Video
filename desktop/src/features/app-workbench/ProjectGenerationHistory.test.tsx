import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const apiMocks = vi.hoisted(() => ({
  listGenerationRecords: vi.fn(),
  getGenerationRecordPreview: vi.fn(),
  generationRecordMediaBlobUrl: vi.fn(),
  downloadGenerationRecordMedia: vi.fn(),
}));

vi.mock("../../api", () => ({
  listGenerationRecords: apiMocks.listGenerationRecords,
  getGenerationRecordPreview: apiMocks.getGenerationRecordPreview,
  generationRecordMediaBlobUrl: apiMocks.generationRecordMediaBlobUrl,
  downloadGenerationRecordMedia: apiMocks.downloadGenerationRecordMedia,
}));

import type {
  GenerationRecordBlock,
  GenerationRecordPage,
  GenerationTextResultItem,
} from "../../api";
import { ProjectGenerationHistory } from "./ProjectGenerationHistory";

function titleRecord(id = "run-title-1"): GenerationRecordBlock {
  return {
    schema_version: 1,
    record_id: id,
    app_run_id: id,
    project_id: "project-1",
    app_id: "builtin.viral-titles",
    app_name: "爆款标题",
    result_shape: "multi_title",
    status: "completed",
    created_at: "2026-07-30T10:20:00Z",
    result_available_at: "2026-07-30T10:20:08Z",
    summary: "本次生成 6 个标题",
    compatibility: { state: "normal" },
    items: Array.from({ length: 6 }, (_, index) => ({
      item_id: `artifact-title:version-title:${index + 1}`,
      kind: "title" as const,
      label: `风格 ${index + 1}`,
      text: `下午茶标题 ${index + 1}`,
      actions: ["copy", "edit", "select"] as Array<"copy" | "edit" | "select">,
      selected: false,
    })),
  };
}

function copyRecord(): GenerationRecordBlock {
  return {
    schema_version: 1,
    record_id: "run-copy-1",
    app_run_id: "run-copy-1",
    project_id: "project-1",
    app_id: "builtin.marketing-copy",
    app_name: "门店营销文案",
    result_shape: "multi_copy",
    status: "completed",
    created_at: "2026-07-30T09:20:00Z",
    result_available_at: "2026-07-30T09:20:08Z",
    summary: "本次生成 2 条文案",
    compatibility: { state: "normal" },
    items: [
      {
        item_id: "artifact-copy:version-copy:1",
        kind: "copy",
        label: "老板口吻",
        text: "今天下午三点来店里坐坐，现磨咖啡和当日面包都准备好了。",
        actions: ["copy", "select"],
      },
      {
        item_id: "artifact-copy:version-copy:2",
        kind: "copy",
        label: "体验视角",
        text: "下班前给自己十分钟，喝一杯刚磨好的咖啡再出发。",
        actions: ["copy", "select"],
      },
    ],
  };
}

function page(records: GenerationRecordBlock[]): GenerationRecordPage {
  return {
    schema_version: 1,
    project_id: "project-1",
    scope: "current_app",
    app_id: "builtin.viral-titles",
    records,
    next_cursor: null,
  };
}

const callbacks = {
  onCopy: vi.fn(async () => undefined),
  onSelect: vi.fn(async () => undefined),
  onEdit: vi.fn(async () => undefined),
  onRunAction: vi.fn(async () => undefined),
};

describe("ProjectGenerationHistory", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.sessionStorage.clear();
    apiMocks.listGenerationRecords.mockResolvedValue(page([titleRecord()]));
    apiMocks.generationRecordMediaBlobUrl.mockImplementation(
      async (path: string) => `blob:${path}`,
    );
    apiMocks.getGenerationRecordPreview.mockResolvedValue({
      schema_version: 1,
      kind: "carousel",
      record_id: "run-carousel",
      title: "三公里上班族下午茶",
      page_count: 5,
      pages: Array.from({ length: 5 }, (_, index) => ({
        page_index: index + 1,
        image_url: `/api/pages/${index + 1}`,
      })),
      publish_copy: {
        title: "三公里上班族下午茶",
        description: "工作日下午茶已经准备好了。",
        hashtags: ["下午茶"],
      },
      download_url: "/api/download",
    });
  });

  it("shows all six titles inside one generation record without technical ids", async () => {
    render(
      <ProjectGenerationHistory
        projectId="project-1"
        appId="builtin.viral-titles"
        {...callbacks}
      />,
    );

    const record = await screen.findByRole("region", { name: /生成记录/ });
    expect(within(record).getAllByRole("article")).toHaveLength(6);
    expect(screen.getByText("下午茶标题 1")).toBeInTheDocument();
    expect(screen.getByText("下午茶标题 6")).toBeInTheDocument();
    expect(screen.getByText("本次生成 6 个标题")).toBeInTheDocument();
    expect(screen.queryByText("run-title-1")).not.toBeInTheDocument();
    expect(screen.queryByText("artifact-title")).not.toBeInTheDocument();
    expect(apiMocks.listGenerationRecords).toHaveBeenCalledWith("project-1", {
      scope: "current_app",
      app_id: "builtin.viral-titles",
      limit: 10,
    });
  });

  it("keeps copy, edit and adopt next to one result and persists the edit", async () => {
    const record = titleRecord();
    apiMocks.listGenerationRecords.mockResolvedValue(page([record]));
    render(
      <ProjectGenerationHistory
        projectId="project-1"
        appId="builtin.viral-titles"
        {...callbacks}
      />,
    );
    const first = await screen.findByRole("article", { name: "标题 1" });
    fireEvent.click(within(first).getByRole("button", { name: /复制/ }));
    await waitFor(() => expect(callbacks.onCopy).toHaveBeenCalledWith(record, record.items[0]));

    fireEvent.click(within(first).getByRole("button", { name: /编辑/ }));
    const input = await screen.findByRole("textbox", { name: "标题内容" });
    fireEvent.change(input, { target: { value: "修改后的下午茶标题" } });
    fireEvent.click(screen.getByRole("button", { name: "保存修改" }));
    await waitFor(() => expect(callbacks.onEdit).toHaveBeenCalledWith(
      record,
      record.items[0],
      "修改后的下午茶标题",
    ));

    fireEvent.click(within(first).getByRole("button", { name: /^采用$/ }));
    await waitFor(() => expect(callbacks.onSelect).toHaveBeenCalledWith(record, record.items[0]));
    await waitFor(() => expect(
      within(screen.getByRole("article", { name: "标题 1" }))
        .getByRole("button", { name: "已采用" }),
    ).toBeDisabled());
  });

  it("keeps the edit open with the user's text when saving fails", async () => {
    const record = titleRecord();
    const failedOnEdit = vi.fn(async () => {
      throw new Error("保存失败，请重试");
    });
    apiMocks.listGenerationRecords.mockResolvedValue(page([record]));
    render(
      <ProjectGenerationHistory
        projectId="project-1"
        appId="builtin.viral-titles"
        {...callbacks}
        onEdit={failedOnEdit}
      />,
    );

    const first = await screen.findByRole("article", { name: "标题 1" });
    fireEvent.click(within(first).getByRole("button", { name: /编辑/ }));
    const input = await screen.findByRole("textbox", { name: "标题内容" });
    fireEvent.change(input, { target: { value: "不能丢失的标题修改" } });
    fireEvent.click(screen.getByRole("button", { name: "保存修改" }));

    expect(await screen.findByText("保存失败，请重试")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "标题内容" }))
      .toHaveValue("不能丢失的标题修改");
    expect(screen.getByRole("dialog", { name: "编辑标题" })).toBeInTheDocument();
  });

  it("shows repeated generations as separate newest-first blocks", async () => {
    apiMocks.listGenerationRecords.mockResolvedValue(page([
      titleRecord("run-new"),
      titleRecord("run-old"),
    ]));
    render(
      <ProjectGenerationHistory
        projectId="project-1"
        appId="builtin.viral-titles"
        {...callbacks}
      />,
    );
    await screen.findByText("2 次生成");
    expect(screen.getAllByText("本次生成 6 个标题")).toHaveLength(2);
    expect(screen.getAllByRole("article")).toHaveLength(12);
  });

  it("does not append an older scope response after the user switches scope", async () => {
    let resolveOlder!: (value: GenerationRecordPage) => void;
    const olderPage = new Promise<GenerationRecordPage>((resolve) => {
      resolveOlder = resolve;
    });
    apiMocks.listGenerationRecords
      .mockResolvedValueOnce({
        ...page([titleRecord("run-current")]),
        next_cursor: "cursor-current",
      })
      .mockReturnValueOnce(olderPage)
      .mockResolvedValueOnce({
        ...page([{
          ...titleRecord("run-all"),
          items: [{
              ...(titleRecord("run-all").items[0] as GenerationTextResultItem),
            text: "全部成果里的新标题",
          }],
        }]),
        scope: "all_results",
        app_id: null,
      });
    render(
      <ProjectGenerationHistory
        projectId="project-1"
        appId="builtin.viral-titles"
        {...callbacks}
      />,
    );

    fireEvent.click(await screen.findByRole("button", { name: "加载更早记录" }));
    fireEvent.click(screen.getByText("全部成果"));
    expect(await screen.findByText("全部成果里的新标题")).toBeInTheDocument();
    resolveOlder({
      ...page([{
        ...titleRecord("run-stale"),
        items: [{
              ...(titleRecord("run-stale").items[0] as GenerationTextResultItem),
          text: "不应追加的旧范围标题",
        }],
      }]),
      next_cursor: null,
    });
    await waitFor(() => expect(
      screen.queryByText("不应追加的旧范围标题"),
    ).not.toBeInTheDocument());
  });

  it("switches to all results and renders other app products without a button wall", async () => {
    const mediaRecord: GenerationRecordBlock = {
      ...titleRecord("run-carousel"),
      app_id: "builtin.douyin-carousel",
      app_name: "抖音图文",
      result_shape: "single_carousel",
      summary: "下午茶图文",
      items: [{
        item_id: "artifact-carousel",
        kind: "carousel",
        title: "三公里上班族下午茶",
        cover_url: "/api/cover",
        preview_url: "/api/preview",
        download_url: "/api/download",
        page_count: 5,
        actions: ["preview", "publish"],
        details_available: ["pages", "publish_copy"],
        artifact_version_ids: ["carousel-v1"],
      }],
    };
    apiMocks.listGenerationRecords
      .mockResolvedValueOnce(page([titleRecord()]))
      .mockResolvedValueOnce({
        ...page([mediaRecord]),
        scope: "all_results",
        app_id: null,
      });
    render(
      <ProjectGenerationHistory
        projectId="project-1"
        appId="builtin.viral-titles"
        {...callbacks}
      />,
    );
    await screen.findByText("下午茶标题 1");
    fireEvent.click(screen.getByText("全部成果"));
    expect(await screen.findByText("三公里上班族下午茶")).toBeInTheDocument();
    expect(screen.getByText("5 页")).toBeInTheDocument();
    expect(screen.queryByText("成品已保存")).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "预览" })).toHaveLength(1);
    expect(screen.queryByRole("button", { name: "去发布" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "预览" }));
    expect(await screen.findByRole("img", { name: "图文第 5 页" })).toBeInTheDocument();
    expect(screen.getAllByRole("img", { name: /图文第/ })).toHaveLength(5);
    expect(screen.getAllByRole("button", { name: "下载本页" })).toHaveLength(5);
    fireEvent.click(screen.getAllByRole("button", { name: "下载本页" })[0]);
    expect(apiMocks.downloadGenerationRecordMedia).toHaveBeenCalledWith(
      "/api/pages/1",
      "三公里上班族下午茶-第1页.png",
    );
    expect(screen.getByRole("button", { name: "下载成品" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "复制发布文案" })).toBeInTheDocument();
    expect(screen.queryByText(/artifact|version|provider/i)).not.toBeInTheDocument();
    expect(apiMocks.listGenerationRecords).toHaveBeenLastCalledWith("project-1", {
      scope: "all_results",
      limit: 10,
    });
    expect(window.sessionStorage.getItem("pixelle.app-result-history.scope.v1")).toBe("all_results");
  });

  it("shows a plain-language empty state", async () => {
    apiMocks.listGenerationRecords.mockResolvedValue(page([]));
    render(
      <ProjectGenerationHistory
        projectId="project-1"
        appId="builtin.viral-titles"
        {...callbacks}
      />,
    );
    expect(await screen.findByText("还没有生成记录")).toBeInTheDocument();
    expect(screen.getByText("完成左侧设置并点击生成，结果会保存在这里。")).toBeInTheDocument();
  });

  it("keeps download and copy available when one carousel page cannot preview", async () => {
    const mediaRecord: GenerationRecordBlock = {
      ...titleRecord("run-carousel"),
      app_id: "builtin.douyin-carousel",
      app_name: "抖音图文",
      result_shape: "single_carousel",
      summary: "下午茶图文",
      items: [{
        item_id: "artifact-carousel",
        kind: "carousel",
        title: "三公里上班族下午茶",
        cover_url: "/api/cover",
        preview_url: "/api/preview",
        download_url: "/api/download",
        page_count: 5,
        actions: ["preview", "publish"],
        details_available: ["pages", "publish_copy"],
        artifact_version_ids: ["carousel-v1"],
      }],
    };
    apiMocks.listGenerationRecords.mockResolvedValue({
      ...page([mediaRecord]),
      app_id: "builtin.douyin-carousel",
    });
    apiMocks.generationRecordMediaBlobUrl.mockImplementation(async (path: string) => {
      if (path.endsWith("/2")) throw new Error("page unavailable");
      return `blob:${path}`;
    });
    const revokeSpy = vi.spyOn(URL, "revokeObjectURL");

    render(
      <ProjectGenerationHistory
        projectId="project-1"
        appId="builtin.douyin-carousel"
      />,
    );

    fireEvent.click(await screen.findByRole("button", { name: "预览" }));
    expect(await screen.findByText("第 2 页暂时无法预览")).toBeInTheDocument();
    expect(screen.getAllByText("部分页面暂时无法显示，仍可下载成品或复制发布文案。")).toHaveLength(2);
    expect(screen.getAllByRole("button", { name: "下载成品" })).toHaveLength(2);
    expect(screen.getByRole("button", { name: "复制发布文案" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /关\s*闭/ }));
    await waitFor(() => expect(revokeSpy).toHaveBeenCalledWith("blob:/api/pages/1"));
  });

  it("does not split a full copy batch into history rows", async () => {
    const record = copyRecord();
    apiMocks.listGenerationRecords.mockResolvedValue(page([record]));
    render(
      <ProjectGenerationHistory
        projectId="project-1"
        appId="builtin.marketing-copy"
        {...callbacks}
      />,
    );
    expect(await screen.findAllByRole("article")).toHaveLength(2);
    expect(screen.getByText("本次生成 2 条文案")).toBeInTheDocument();
    expect(screen.getByText("老板口吻")).toBeInTheDocument();
    expect(screen.getByText("体验视角")).toBeInTheDocument();
  });
});
