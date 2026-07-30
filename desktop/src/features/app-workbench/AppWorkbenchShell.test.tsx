import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AppWorkbenchShell } from "./AppWorkbenchShell";

describe("AppWorkbenchShell", () => {
  it("exposes two labelled panes and evidence-backed result state copy", () => {
    render(
      <AppWorkbenchShell
        eyebrow="CONTENT APP"
        title="门店营销文案"
        description="测试说明"
        input={<button type="button">生成文案</button>}
        result={<div>暂无结果</div>}
        resultState="running"
      />,
    );

    expect(screen.getByRole("region", { name: "创作配置" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "生成结果" })).toBeInTheDocument();
    expect(screen.getByText("生成中")).toBeInTheDocument();
    expect(screen.getByText(/正在为你生成内容/)).toBeInTheDocument();
  });

  it("switches the narrow-window tab state without removing either pane", () => {
    render(
      <AppWorkbenchShell
        eyebrow="CONTENT APP"
        title="爆款标题"
        description="测试说明"
        input={<div>标题输入</div>}
        result={<div>标题结果</div>}
      />,
    );

    const inputTab = screen.getByRole("tab", { name: "创作配置" });
    const resultTab = screen.getByRole("tab", { name: "生成结果" });
    expect(inputTab).toHaveAttribute("aria-selected", "true");
    fireEvent.click(resultTab);
    expect(resultTab).toHaveAttribute("aria-selected", "true");
    expect(inputTab).toHaveAttribute("aria-selected", "false");
    expect(screen.getByText("标题输入")).toBeInTheDocument();
    expect(screen.getByText("标题结果")).toBeInTheDocument();
  });

  it("supports arrow-key navigation between input and result tabs", () => {
    render(
      <AppWorkbenchShell
        eyebrow="CONTENT APP"
        title="抖音图文"
        description="测试说明"
        input={<div>图文输入</div>}
        result={<div>图文结果</div>}
      />,
    );
    const inputTab = screen.getByRole("tab", { name: "创作配置" });
    const resultTab = screen.getByRole("tab", { name: "生成结果" });
    inputTab.focus();
    fireEvent.keyDown(inputTab, { key: "ArrowRight" });
    expect(resultTab).toHaveFocus();
    expect(resultTab).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(resultTab, { key: "Home" });
    expect(inputTab).toHaveFocus();
    expect(inputTab).toHaveAttribute("aria-selected", "true");
  });
});
