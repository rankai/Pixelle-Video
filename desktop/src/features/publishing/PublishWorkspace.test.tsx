import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { createPublishPackageFromSessionV2, downloadArtifact } from "../../api";
import { PublishWorkspace } from "./PublishWorkspace";

vi.mock("../../api", () => ({
  artifactBlobUrl: vi.fn().mockResolvedValue("blob:preview"),
  createPublishPackageFromSessionV2: vi.fn(),
  downloadArtifact: vi.fn().mockResolvedValue(undefined),
}));

const createPackage = vi.mocked(createPublishPackageFromSessionV2);
const download = vi.mocked(downloadArtifact);

const session = {
  session_id: "session-fallback-1",
  current_step: 6,
  completed_steps: [1, 2, 3, 4, 5],
  next_action: { key: "publish", step: 6, label: "发布", description: "", disabled: false },
  missing_requirements: [],
  step_status: { source: "done", copywriting: "done", voice: "done", digital_human: "done", postproduction: "done", publish: "ready" },
  notices: {},
  artifacts: { final_video: "trusted-video", cover: "trusted-cover", script: "trusted-script" },
  state: {
    final_video_path: "/private/should-not-render/video.mp4",
    cover_path: "/private/should-not-render/cover.png",
    title: "门店标题",
    description: "门店描述",
    hashtags: ["门店营销"],
    final_script: "口播文案",
  },
} as never;

describe("PublishWorkspace safe fallback", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    createPackage.mockRejectedValue(new Error("ADAPTER_UNAVAILABLE"));
    Object.assign(navigator, { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } });
  });

  it("keeps copy/download available after adapter failure without rendering paths", async () => {
    const downloadFinalVideo = vi.fn().mockResolvedValue(undefined);
    render(<PublishWorkspace session={session} downloadFinalVideo={downloadFinalVideo} onOpenPublishCenter={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: "打开抖音" }));
    expect(await screen.findByText("ADAPTER_UNAVAILABLE")).toBeInTheDocument();
    await waitFor(() => {
      const video = document.querySelector("video.publish-native-preview");
      const cover = document.querySelector("img.artifact-image-preview");
      expect(video).not.toBeNull();
      expect(video).toHaveAttribute("src", "blob:preview");
      expect(cover).not.toBeNull();
      expect(cover).toHaveAttribute("src", "blob:preview");
    });
    const copyButtons = screen.getAllByRole("button", { name: "复制该平台素材" });
    expect(copyButtons[0]).toBeEnabled();
    expect(screen.getByRole("button", { name: "下载最终视频" })).toBeEnabled();
    expect(screen.queryByText("/private/should-not-render/video.mp4")).not.toBeInTheDocument();
    expect(screen.queryByText("/private/should-not-render/cover.png")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "下载最终视频" }));
    await waitFor(() => expect(downloadFinalVideo).toHaveBeenCalledTimes(1));
    fireEvent.click(copyButtons[0]);
    expect((navigator.clipboard.writeText as ReturnType<typeof vi.fn>)).toHaveBeenCalled();
    expect(download).not.toHaveBeenCalled();
  });
});
