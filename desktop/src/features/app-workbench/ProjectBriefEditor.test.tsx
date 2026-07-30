import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ContextSnapshot } from "../../api";
import { mapLegacyContextToV2, ProjectBriefEditor } from "./ProjectBriefEditor";

const mocks = vi.hoisted(() => ({
  saveContextSnapshot: vi.fn(),
}));

vi.mock("../../api", () => ({
  saveContextSnapshot: mocks.saveContextSnapshot,
}));

const legacySnapshot: ContextSnapshot = {
  context_snapshot_id: "context-v1",
  project_id: "project-1",
  schema_version: 1,
  payload: {
    store_name: "街角咖啡",
    industry: "咖啡餐饮",
    product_or_service: "夏日冰咖",
    offer_category: "饮品",
    target_audience: "周边上班族",
    selling_points: ["现磨", "低糖"],
  },
  source_brand_id: null,
  source_brand_revision_id: null,
  fingerprint: "sha256:v1",
  created_at: "2026-07-28T00:00:00Z",
};

describe("ProjectBriefEditor", () => {
  beforeEach(() => {
    window.localStorage.clear();
    mocks.saveContextSnapshot.mockReset();
  });

  it("maps v1 into an explicit preview without writing a new snapshot", () => {
    const mapped = mapLegacyContextToV2(legacySnapshot.payload, "备用项目名");
    expect(mapped.store_or_brand.name).toBe("街角咖啡");
    expect(mapped.offer.name).toBe("夏日冰咖");
    expect(mapped.selling_points.map((fact) => fact.text)).toEqual(["现磨", "低糖"]);

    render(
      <ProjectBriefEditor
        projectId="project-1"
        projectName="咖啡项目"
        snapshot={legacySnapshot}
        onSaved={vi.fn()}
      />,
    );
    expect(screen.getByText("请确认已带入的项目信息")).toBeInTheDocument();
    expect(screen.getByLabelText("门店或品牌名称")).toHaveValue("街角咖啡");
    expect(screen.getByRole("button", { name: "保存项目信息" })).toBeEnabled();
    expect(mocks.saveContextSnapshot).not.toHaveBeenCalled();
  });

  it("persists a local draft and restores it after remount", () => {
    const first = render(
      <ProjectBriefEditor
        projectId="project-1"
        projectName="咖啡项目"
        snapshot={legacySnapshot}
        onSaved={vi.fn()}
      />,
    );
    fireEvent.change(screen.getByLabelText("商品卖点"), { target: { value: "现磨\n当天烘焙" } });
    first.unmount();

    render(
      <ProjectBriefEditor
        projectId="project-1"
        projectName="咖啡项目"
        snapshot={legacySnapshot}
        onSaved={vi.fn()}
      />,
    );
    expect(screen.getByText("已恢复上次未保存的修改")).toBeInTheDocument();
    expect(screen.getByLabelText("商品卖点")).toHaveValue("现磨\n当天烘焙");
  });

  it("warns when a restored draft is based on an older server snapshot", () => {
    const first = render(
      <ProjectBriefEditor
        projectId="project-1"
        projectName="咖啡项目"
        snapshot={legacySnapshot}
        onSaved={vi.fn()}
      />,
    );
    fireEvent.change(screen.getByLabelText("商品卖点"), { target: { value: "本机草稿卖点" } });
    first.unmount();

    const newerSnapshot: ContextSnapshot = {
      ...legacySnapshot,
      context_snapshot_id: "context-v2-newer",
      schema_version: 2,
      payload: mapLegacyContextToV2(legacySnapshot.payload, "咖啡项目") as unknown as Record<string, unknown>,
      fingerprint: "sha256:v2-newer",
    };
    render(
      <ProjectBriefEditor
        projectId="project-1"
        projectName="咖啡项目"
        snapshot={newerSnapshot}
        onSaved={vi.fn()}
      />,
    );

    expect(screen.getByText("项目信息后来有过更新")).toBeInTheDocument();
    expect(screen.getByText("请核对当前内容后保存，或放弃修改以恢复最新信息。")).toBeInTheDocument();
    expect(screen.getByLabelText("商品卖点")).toHaveValue("本机草稿卖点");
  });

  it("saves a complete v2 snapshot and clears the local draft", async () => {
    const saved: ContextSnapshot = {
      ...legacySnapshot,
      context_snapshot_id: "context-v2",
      schema_version: 2,
      payload: { schema_version: 2 },
      fingerprint: "sha256:v2",
    };
    mocks.saveContextSnapshot.mockResolvedValue(saved);
    const onSaved = vi.fn();
    render(
      <ProjectBriefEditor
        projectId="project-1"
        projectName="咖啡项目"
        snapshot={legacySnapshot}
        onSaved={onSaved}
      />,
    );
    fireEvent.change(screen.getByLabelText("商品卖点"), { target: { value: "现磨\n当天烘焙" } });
    fireEvent.click(screen.getByRole("button", { name: "保存项目信息" }));

    await waitFor(() => expect(mocks.saveContextSnapshot).toHaveBeenCalledWith(
      "project-1",
      expect.objectContaining({
        schema_version: 2,
        payload: expect.objectContaining({
          schema_version: 2,
          store_or_brand: expect.objectContaining({ name: "街角咖啡" }),
          selling_points: [
            expect.objectContaining({ fact_id: "selling-1", text: "现磨" }),
            expect.objectContaining({ fact_id: "selling-2", text: "当天烘焙" }),
          ],
        }),
      }),
    ));
    expect(onSaved).toHaveBeenCalledWith(saved);
    expect(window.localStorage.getItem("pixelle.app-workbench.context-draft.v2:project-1")).toBeNull();
  });
});
