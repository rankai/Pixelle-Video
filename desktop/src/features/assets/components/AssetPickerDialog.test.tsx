import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { listLibraryItemsV2 } from "../../../api";
import { AssetPickerDialog } from "./AssetPickerDialog";

vi.mock("../../../api", () => ({
  assetBlobUrl: vi.fn(),
  createVoiceProfileV2: vi.fn(),
  listLibraryItemsV2: vi.fn(),
  uploadMediaAssetV2: vi.fn(),
}));

const mockedListLibraryItemsV2 = vi.mocked(listLibraryItemsV2);

const image = (resource_id: string, name: string) => ({
  resource_id,
  kind: "image" as const,
  asset_id: resource_id,
  name,
  description: "企业图片",
  status: "ready",
  cover_url: null,
  tags: [],
  favorite: false,
  created_at: "now",
  updated_at: "now",
  summary: {},
  // Match the production Asset Library V2 contract: carousel is a workflow,
  // not an asset capability.
  capabilities: ["preview", "use", "favorite", "archive", "edit"],
});

describe("AssetPickerDialog", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedListLibraryItemsV2.mockImplementation(async (_kind, query = "") => ({
      items: query ? [image("image-b", "图片 B")] : [image("image-a", "图片 A"), image("image-b", "图片 B")],
      total: query ? 1 : 2,
    }));
  });

  it("keeps a selected image when the user searches for and adds another image", async () => {
    const onSelectMany = vi.fn();
    render(
      <AssetPickerDialog
        open
        kind="image"
        selectionMode="multiple"
        onClose={vi.fn()}
        onSelect={vi.fn()}
        onSelectMany={onSelectMany}
        context={{
          session_id: "project-1",
          step: "carousel",
          purpose: "抖音图文图片",
          slot_id: "carousel-images",
          allowed_kinds: ["image"],
          required_capabilities: ["use"],
          selection_mode: "multiple",
        }}
      />,
    );

    expect(await screen.findByRole("button", { name: /图片 A/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /图片 A/ }));
    fireEvent.change(screen.getByPlaceholderText("搜索图片名称或文件名"), { target: { value: "B" } });
    await waitFor(() => expect(screen.queryByRole("button", { name: /图片 A/ })).not.toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /图片 B/ }));
    fireEvent.click(screen.getByRole("button", { name: "确认选择" }));

    expect(onSelectMany).toHaveBeenCalledWith([
      expect.objectContaining({ resource_id: "image-a" }),
      expect.objectContaining({ resource_id: "image-b" }),
    ]);
  });
});
