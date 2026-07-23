import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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
    render(<ApplicationCenterView onOpenApp={vi.fn()} />);

    expect(await screen.findByText("爆款标题")).toBeInTheDocument();
    expect(screen.getByText("数字人口播视频")).toBeInTheDocument();
    expect(screen.getByText("可试用")).toBeInTheDocument();
    expect(screen.getByText("未开启")).toBeInTheDocument();
    const titleCard = screen.getByText("爆款标题").closest("article");
    expect(titleCard).not.toBeNull();
    expect(titleCard?.querySelector(".app-center-card-tags")).toHaveTextContent("文案创作");
    expect(titleCard?.querySelector(".app-center-card-footer")).not.toHaveTextContent("文案创作");

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
    const button = parent?.querySelector("button");
    expect(button).toBeDisabled();
    fireEvent.click(button as HTMLButtonElement);
    await waitFor(() => expect(onOpenApp).not.toHaveBeenCalled());
  });
});
