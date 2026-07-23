import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { createPublishRunV2, getPublishPackageV2, getPublishRunV2, listPublishAccountsV2, listPublishRunEventsV2, preflightPublishPackageV2, resolvePublishPackageV2 } from "../../api";
import { PublishCenterView } from "./PublishCenterView";

vi.mock("../../api", () => ({
  listPublishAccountsV2: vi.fn(),
  getPublishPackageV2: vi.fn(),
  preflightPublishPackageV2: vi.fn(),
  getPublishRunV2: vi.fn(),
  listPublishRunEventsV2: vi.fn(),
  createPublishRunV2: vi.fn(),
  resolvePublishPackageV2: vi.fn(),
}));

vi.mock("./PublishAccountsView", () => ({
  PublishAccountsView: () => <div data-testid="legacy-publish-accounts">旧发布账号页</div>,
}));

const api = vi.mocked(listPublishAccountsV2);
const packageApi = vi.mocked(getPublishPackageV2);
const preflightApi = vi.mocked(preflightPublishPackageV2);
const runApi = vi.mocked(getPublishRunV2);
const eventsApi = vi.mocked(listPublishRunEventsV2);
const createRunApi = vi.mocked(createPublishRunV2);
const resolvePackageApi = vi.mocked(resolvePublishPackageV2);

const account = {
  schema_version: 1,
  account_id: "acct_douyin_1",
  platform: "douyin" as const,
  display_name: "门店账号",
  profile_ref: "profile_ref",
  verification_state: "unverified" as const,
  login_state: "login_required" as const,
  enabled: true,
  is_default: true,
  profile_exists: true,
  platform_release_state: "pilot" as const,
  created_at: "2026-07-20T00:00:00Z",
  updated_at: "2026-07-20T00:00:00Z",
  last_verified_at: null,
  last_error_code: "LOGIN_REQUIRED",
  login_subject_hint: null,
  archived_at: null,
};

describe("PublishCenterView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.mockResolvedValue({ items: [account] });
    packageApi.mockResolvedValue({ package_id: "pkg_1", project_id: "project_1", source: { kind: "artifact_versions", artifact_ids: ["artifact_1"], artifact_version_ids: ["version_1"], session_id: null, source_revision: "rev_1" }, artifact_refs: [], video_manifest: null, carousel_manifests: null, cover_manifest: null, platform_copy: { title: "标题", description: "简介", hashtags: [] }, policy: { human_confirmation_required: true, allow_final_publish: false, adapter_version: "douyin@1" }, package_fingerprint: "fp", invalidated_at: null, invalidation_reason: null, created_at: "2026-07-20T00:00:00Z", schema_version: 1 });
    preflightApi.mockResolvedValue({ package_id: "pkg_1", status: "ready", video_manifest: null, carousel_manifests: [], cover_manifest: null });
    runApi.mockResolvedValue({ run: { run_id: "run_1", package_id: "pkg_1", account_id: "acct_douyin_1", platform: "douyin", state: "waiting_for_human", state_version: 1, attempt: 1, current_step: "human_confirmation", idempotency_key: "idem", human_confirmation: { required: true, confirmed: false, confirmed_at: null, actor_ref: null }, task_id: null, error_code: null, error_message: null, checkpoint: {}, created_at: "2026-07-20T00:00:00Z", updated_at: "2026-07-20T00:00:00Z", schema_version: 1 } });
    createRunApi.mockResolvedValue({ run_id: "run_1", task_id: null, state: "queued", requires_human_confirmation: true, idempotent_replay: false });
    eventsApi.mockResolvedValue({ items: [{ event_id: "event_1", run_id: "run_1", event_seq: 1, event_type: "waiting_for_human", state: "waiting_for_human", state_version: 1, payload: {}, created_at: "2026-07-20T00:00:00Z" }], next_after: 1 });
    resolvePackageApi.mockResolvedValue({ package_id: "pkg_1", project_id: "project_1", source: { kind: "artifact_versions", artifact_ids: ["artifact_1"], artifact_version_ids: ["version_1"], session_id: null, source_revision: "rev_1" }, artifact_refs: [{ artifact_id: "artifact_1", artifact_version_id: "version_1", artifact_type: "video", content_fingerprint: "fp" }], video_manifest: null, carousel_manifests: null, cover_manifest: null, platform_copy: { title: "标题", description: "简介", hashtags: [] }, policy: { human_confirmation_required: true, allow_final_publish: false, adapter_version: "douyin@1" }, package_fingerprint: "fp", invalidated_at: null, invalidation_reason: null, created_at: "2026-07-20T00:00:00Z", schema_version: 1 });
    window.location.hash = "";
  });

  it("keeps the existing publish page when the V2 flag is off", () => {
    render(<PublishCenterView v2Enabled={false} />);
    expect(screen.getByText("发布中心 V2 尚未开启")).toBeInTheDocument();
    expect(screen.getByTestId("legacy-publish-accounts")).toBeInTheDocument();
    expect(api).not.toHaveBeenCalled();
  });

  it("projects V2 account state without claiming a published result", async () => {
    render(<PublishCenterView v2Enabled />);
    expect(await screen.findByText("发布中心")).toBeInTheDocument();
    expect(api).toHaveBeenCalledTimes(1);
    expect(screen.getByText("尚未选择发布包或运行")).toBeInTheDocument();
    expect(screen.queryByText("已发布")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "发布账号" }));
    await waitFor(() => expect(screen.getByText("门店账号")).toBeInTheDocument());
    expect(screen.getByText("需要登录")).toBeInTheDocument();
    expect(screen.getByText("试点")).toBeInTheDocument();
  });

  it("loads package and run handoff from the canonical hash route", async () => {
    window.location.hash = "#/publish?package_id=pkg_1&run_id=run_1";
    render(<PublishCenterView v2Enabled />);
    expect(await screen.findByText("已恢复同一发布运行；最终发布仍需人工确认。")).toBeInTheDocument();
    expect(screen.getByText("1. waiting_for_human")).toBeInTheDocument();
    expect(packageApi).toHaveBeenCalledWith("pkg_1");
    expect(preflightApi).toHaveBeenCalledWith("pkg_1");
    expect(runApi).toHaveBeenCalledWith("run_1");
    expect(eventsApi).toHaveBeenCalledWith("run_1");
  });

  it("resolves artifact-only handoff to a trusted package", async () => {
    window.location.hash = "#/publish?artifact_id=artifact_1";
    packageApi.mockResolvedValueOnce({ package_id: "pkg_1", project_id: "project_1", source: { kind: "artifact_versions", artifact_ids: ["artifact_1"], artifact_version_ids: ["version_1"], session_id: null, source_revision: "rev_1" }, artifact_refs: [{ artifact_id: "artifact_1", artifact_version_id: "version_1", artifact_type: "video", content_fingerprint: "fp" }], video_manifest: null, carousel_manifests: null, cover_manifest: null, platform_copy: { title: "标题", description: "简介", hashtags: [] }, policy: { human_confirmation_required: true, allow_final_publish: false, adapter_version: "douyin@1" }, package_fingerprint: "fp", invalidated_at: null, invalidation_reason: null, created_at: "2026-07-20T00:00:00Z", schema_version: 1 });
    render(<PublishCenterView v2Enabled />);
    expect(await screen.findByRole("tab", { name: "发布账号" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "发布运行" }));
    expect(await screen.findByText("已接收应用产物 handoff，等待选择账号并创建发布运行。")).toBeInTheDocument();
    expect(resolvePackageApi).toHaveBeenCalledWith("artifact_1");
  });

  it("starts one idempotent pre-publish run from a package account", async () => {
    window.location.hash = "#/publish?package_id=pkg_1";
    render(<PublishCenterView v2Enabled />);
    const start = await screen.findByRole("button", { name: "开始填充草稿" });
    fireEvent.click(start);
    await waitFor(() => expect(createRunApi).toHaveBeenCalledWith({
      package_id: "pkg_1",
      account_id: "acct_douyin_1",
      platform: "douyin",
      idempotency_key: "publish-center:pkg_1:acct_douyin_1",
    }));
    expect(await screen.findByText("已恢复同一发布运行；最终发布仍需人工确认。")).toBeInTheDocument();
  });

  it("keeps an unverified platform on copy fallback", async () => {
    api.mockResolvedValueOnce({ items: [{ ...account, account_id: "acct_kuaishou_1", platform: "kuaishou", display_name: "快手账号", platform_release_state: "unverified", is_default: false }] });
    window.location.hash = "#/publish?package_id=pkg_1";
    render(<PublishCenterView v2Enabled />);
    expect(await screen.findByText("待独立 live gate；当前仅支持复制素材回退")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "开始填充草稿" })).not.toBeInTheDocument();
  });

  it("reloads when the artifact handoff ref changes", async () => {
    window.location.hash = "#/publish?artifact_id=artifact_1";
    packageApi.mockResolvedValueOnce({ package_id: "pkg_1", project_id: "project_1", source: { kind: "artifact_versions", artifact_ids: ["artifact_1"], artifact_version_ids: ["version_1"], session_id: null, source_revision: "rev_1" }, artifact_refs: [{ artifact_id: "artifact_1", artifact_version_id: "version_1", artifact_type: "video", content_fingerprint: "fp" }], video_manifest: null, carousel_manifests: null, cover_manifest: null, platform_copy: { title: "标题", description: "简介", hashtags: [] }, policy: { human_confirmation_required: true, allow_final_publish: false, adapter_version: "douyin@1" }, package_fingerprint: "fp", invalidated_at: null, invalidation_reason: null, created_at: "2026-07-20T00:00:00Z", schema_version: 1 });
    const view = render(<PublishCenterView v2Enabled />);
    await waitFor(() => expect(resolvePackageApi).toHaveBeenCalledWith("artifact_1"));
    window.location.hash = "#/publish?artifact_id=artifact_2";
    resolvePackageApi.mockResolvedValueOnce({ package_id: "pkg_2", project_id: "project_1", source: { kind: "artifact_versions", artifact_ids: ["artifact_2"], artifact_version_ids: ["version_2"], session_id: null, source_revision: "rev_2" }, artifact_refs: [{ artifact_id: "artifact_2", artifact_version_id: "version_2", artifact_type: "video", content_fingerprint: "fp2" }], video_manifest: null, carousel_manifests: null, cover_manifest: null, platform_copy: { title: "标题2", description: "简介2", hashtags: [] }, policy: { human_confirmation_required: true, allow_final_publish: false, adapter_version: "douyin@1" }, package_fingerprint: "fp2", invalidated_at: null, invalidation_reason: null, created_at: "2026-07-20T00:00:00Z", schema_version: 1 });
    packageApi.mockResolvedValueOnce({ package_id: "pkg_2", project_id: "project_1", source: { kind: "artifact_versions", artifact_ids: ["artifact_2"], artifact_version_ids: ["version_2"], session_id: null, source_revision: "rev_2" }, artifact_refs: [{ artifact_id: "artifact_2", artifact_version_id: "version_2", artifact_type: "video", content_fingerprint: "fp2" }], video_manifest: null, carousel_manifests: null, cover_manifest: null, platform_copy: { title: "标题2", description: "简介2", hashtags: [] }, policy: { human_confirmation_required: true, allow_final_publish: false, adapter_version: "douyin@1" }, package_fingerprint: "fp2", invalidated_at: null, invalidation_reason: null, created_at: "2026-07-20T00:00:00Z", schema_version: 1 });
    view.rerender(<PublishCenterView v2Enabled />);
    await waitFor(() => expect(resolvePackageApi).toHaveBeenCalledWith("artifact_2"));
  });

  it("fails closed for package/run mismatch and invalid event ownership/order", async () => {
    runApi.mockResolvedValueOnce({ run: { run_id: "run_1", package_id: "pkg_other", account_id: "acct_douyin_1", platform: "douyin", state: "waiting_for_human", state_version: 1, attempt: 1, current_step: "human_confirmation", idempotency_key: "idem", human_confirmation: { required: true, confirmed: false, confirmed_at: null, actor_ref: null }, task_id: null, error_code: null, error_message: null, checkpoint: {}, created_at: "2026-07-20T00:00:00Z", updated_at: "2026-07-20T00:00:00Z", schema_version: 1 } });
    window.location.hash = "#/publish?package_id=pkg_1&run_id=run_1";
    render(<PublishCenterView v2Enabled />);
    expect(await screen.findByText("PUBLISH_FACT_MISMATCH")).toBeInTheDocument();

    runApi.mockResolvedValue({ run: { run_id: "run_1", package_id: "pkg_1", account_id: "acct_douyin_1", platform: "douyin", state: "waiting_for_human", state_version: 1, attempt: 1, current_step: "human_confirmation", idempotency_key: "idem", human_confirmation: { required: true, confirmed: false, confirmed_at: null, actor_ref: null }, task_id: null, error_code: null, error_message: null, checkpoint: {}, created_at: "2026-07-20T00:00:00Z", updated_at: "2026-07-20T00:00:00Z", schema_version: 1 } });
    eventsApi.mockResolvedValue({ items: [{ event_id: "event_1", run_id: "wrong_run", event_seq: 1, event_type: "waiting_for_human", state: "waiting_for_human", state_version: 1, payload: {}, created_at: "2026-07-20T00:00:00Z" }], next_after: 1 });
    window.location.hash = "#/publish?package_id=pkg_1&run_id=run_1";
    render(<PublishCenterView v2Enabled />);
    expect(await screen.findByText("PUBLISH_EVENT_ORDER_INVALID")).toBeInTheDocument();
  });

  it("fails closed for artifact/run mismatch", async () => {
    resolvePackageApi.mockResolvedValueOnce({ package_id: "pkg_artifact", project_id: "project_1", source: { kind: "artifact_versions", artifact_ids: ["artifact_1"], artifact_version_ids: ["version_1"], session_id: null, source_revision: "rev_1" }, artifact_refs: [{ artifact_id: "artifact_1", artifact_version_id: "version_1", artifact_type: "video", content_fingerprint: "fp" }], video_manifest: null, carousel_manifests: null, cover_manifest: null, platform_copy: { title: "标题", description: "简介", hashtags: [] }, policy: { human_confirmation_required: true, allow_final_publish: false, adapter_version: "douyin@1" }, package_fingerprint: "fp", invalidated_at: null, invalidation_reason: null, created_at: "2026-07-20T00:00:00Z", schema_version: 1 });
    runApi.mockResolvedValueOnce({ run: { run_id: "run_1", package_id: "pkg_other", account_id: "acct_douyin_1", platform: "douyin", state: "waiting_for_human", state_version: 1, attempt: 1, current_step: "human_confirmation", idempotency_key: "idem", human_confirmation: { required: true, confirmed: false, confirmed_at: null, actor_ref: null }, task_id: null, error_code: null, error_message: null, checkpoint: {}, created_at: "2026-07-20T00:00:00Z", updated_at: "2026-07-20T00:00:00Z", schema_version: 1 } });
    window.location.hash = "#/publish?artifact_id=artifact_1&run_id=run_1";
    render(<PublishCenterView v2Enabled />);
    expect(await screen.findByText("PUBLISH_FACT_MISMATCH")).toBeInTheDocument();
  });

  it("fails closed when package preflight is stale or unavailable", async () => {
    preflightApi.mockRejectedValueOnce(new Error("PUBLISH_PACKAGE_STALE"));
    window.location.hash = "#/publish?package_id=pkg_1";
    render(<PublishCenterView v2Enabled />);
    expect(await screen.findByText("PUBLISH_PACKAGE_STALE")).toBeInTheDocument();
  });

  it("keeps a safe copy/download fallback when the adapter is unavailable", async () => {
    preflightApi.mockRejectedValueOnce(new Error("ADAPTER_UNAVAILABLE"));
    window.location.hash = "#/publish?package_id=pkg_1";
    render(<PublishCenterView v2Enabled />);
    expect(await screen.findByText("ADAPTER_UNAVAILABLE")).toBeInTheDocument();
    expect(screen.getByText("发布适配器暂时不可用。你仍可以回到生产工作区复制文案、预览或下载已生成素材；这里不会暴露本地路径，也不会自动发布。")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "返回工作区复制/下载素材" }));
    expect(window.location.hash).toBe("#/ip");
  });
});
