import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApplicationCenterView } from "./ApplicationCenterView";
import { listApplications } from "../../api";

vi.mock("../../api", () => ({ listApplications: vi.fn() }));

const mockedListApplications = vi.mocked(listApplications);

describe("ApplicationCenterView", () => {
  beforeEach(() => {
    mockedListApplications.mockResolvedValue({
      schema_version: 1,
      apps: [
        {
          schema_version: 1,
          app_id: "builtin.viral-titles",
          version: "1.0.0",
          name: "爆款标题",
          description: "生成多角度标题候选",
          category: "copywriting",
          status: "stable",
          icon: "BadgeCheck",
          required_capabilities: ["llm"],
          feature_flag: "contentApps",
          sort_order: 20,
          enabled: true,
          readiness: { status: "ready", missing_capabilities: [], configured_capabilities: ["llm"] },
        },
        {
          schema_version: 1,
          app_id: "builtin.digital-human-video",
          version: "1.0.0",
          name: "数字人口播视频",
          description: "复用既有口播链路制作视频",
          category: "video",
          status: "pilot",
          icon: "Video",
          required_capabilities: ["llm", "runninghub", "digital_human"],
          feature_flag: "digitalHumanInAppCenter",
          sort_order: 40,
          enabled: false,
          readiness: { status: "disabled", missing_capabilities: [], configured_capabilities: ["llm"] },
        },
      ],
    });
  });

  it("renders the backend registry and filters it by category/search", async () => {
    const onOpenApp = vi.fn();
    render(<ApplicationCenterView onOpenApp={onOpenApp} />);

    expect(await screen.findByText("爆款标题")).toBeInTheDocument();
    expect(screen.getByText("数字人口播视频")).toBeInTheDocument();
    expect(screen.getByText("待上线")).toBeInTheDocument();
    expect(screen.queryByText("可用", { exact: true })).not.toBeInTheDocument();
    expect(screen.queryByText("本地可导出", { exact: true })).not.toBeInTheDocument();
    expect(screen.queryByText("未开启", { exact: true })).not.toBeInTheDocument();
    expect(screen.queryByText("打开流程", { exact: true })).not.toBeInTheDocument();
    expect(screen.queryByText("查看规划", { exact: true })).not.toBeInTheDocument();
    expect(screen.queryByText("可试用", { exact: true })).not.toBeInTheDocument();
    const titleCard = screen.getByText("爆款标题").closest("article");
    expect(titleCard).not.toBeNull();
    expect(titleCard?.querySelector(".app-center-card-tags")).toHaveTextContent("文案创作");
    expect(titleCard?.querySelector(".app-center-card-tags")).not.toHaveTextContent("待上线");
    expect(titleCard?.querySelector(".app-center-card-footer")).toBeNull();
    fireEvent.click(titleCard as HTMLElement);
    expect(onOpenApp).toHaveBeenCalledWith(expect.objectContaining({ appId: "builtin.viral-titles" }));
    onOpenApp.mockClear();
    fireEvent.keyDown(titleCard as HTMLElement, { key: "Enter" });
    expect(onOpenApp).toHaveBeenCalledWith(expect.objectContaining({ appId: "builtin.viral-titles" }));

    fireEvent.click(screen.getByRole("tab", { name: "文案创作" }));
    expect(screen.getByText("爆款标题")).toBeInTheDocument();
    expect(screen.queryByText("数字人口播视频")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "全部" }));
    fireEvent.change(screen.getByLabelText("搜索应用"), { target: { value: "数字人口播" } });
    expect(screen.getByText("数字人口播视频")).toBeInTheDocument();
    expect(screen.queryByText("爆款标题")).not.toBeInTheDocument();
  });

  it("keeps disabled readiness cards non-actionable", async () => {
    const onOpenApp = vi.fn();
    render(<ApplicationCenterView onOpenApp={onOpenApp} />);
    const card = await screen.findByText("数字人口播视频");
    const parent = card.closest("article");
    expect(parent).not.toBeNull();
    expect(parent?.querySelector("button")).toBeNull();
    fireEvent.click(parent as HTMLElement);
    expect(onOpenApp).not.toHaveBeenCalled();
  });
});
