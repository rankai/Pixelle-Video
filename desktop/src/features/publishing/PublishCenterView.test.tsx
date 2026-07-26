import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { cancelPublishRunV2, createPublishAccount, createPublishRunV2, getPublishPackageV2, getPublishRunV2, listPublishAccountsV2, listPublishPlatforms, listPublishRunEventsV2, markPublishRunOutcomeV2, preflightPublishPackageV2, resolvePublishPackageV2, retryPublishRunStepV2, resumePublishRunV2 } from "../../api";
import { PublishCenterView } from "./PublishCenterView";

vi.mock("../../api", () => ({
  listPublishAccountsV2: vi.fn(),
  listPublishPlatforms: vi.fn(),
  createPublishAccount: vi.fn(),
  getPublishPackageV2: vi.fn(),
  preflightPublishPackageV2: vi.fn(),
  getPublishRunV2: vi.fn(),
  listPublishRunEventsV2: vi.fn(),
  createPublishRunV2: vi.fn(),
  markPublishRunOutcomeV2: vi.fn(),
  resumePublishRunV2: vi.fn(),
  retryPublishRunStepV2: vi.fn(),
  cancelPublishRunV2: vi.fn(),
  resolvePublishPackageV2: vi.fn(),
}));

vi.mock("./PublishAccountsView", () => ({
  PublishAccountsView: () => <div data-testid="legacy-publish-accounts">旧发布账号页</div>,
}));

const api = vi.mocked(listPublishAccountsV2);
const platformsApi = vi.mocked(listPublishPlatforms);
const createAccountApi = vi.mocked(createPublishAccount);
const packageApi = vi.mocked(getPublishPackageV2);
const preflightApi = vi.mocked(preflightPublishPackageV2);
const runApi = vi.mocked(getPublishRunV2);
const eventsApi = vi.mocked(listPublishRunEventsV2);
const createRunApi = vi.mocked(createPublishRunV2);
const markOutcomeApi = vi.mocked(markPublishRunOutcomeV2);
const resumeRunApi = vi.mocked(resumePublishRunV2);
const retryRunApi = vi.mocked(retryPublishRunStepV2);
const cancelRunApi = vi.mocked(cancelPublishRunV2);
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

const authenticatedAccount = {
  ...account,
  account_id: "acct_douyin_2",
  display_name: "抖音副账号",
  is_default: false,
  login_state: "authenticated" as const,
  verification_state: "verified" as const,
  last_error_code: null,
};

describe("PublishCenterView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.mockResolvedValue({ items: [account] });
    createAccountApi.mockResolvedValue({ ...account, account_id: "acct_douyin_2", display_name: "抖音副账号", is_default: false });
    platformsApi.mockResolvedValue({ items: [
      { platform: "douyin", display_name: "抖音", release_state: "pilot", account_count: 1, default_account_id: "acct_douyin_1" },
      { platform: "video_channel", display_name: "视频号", release_state: "pilot", account_count: 0, default_account_id: null },
      { platform: "kuaishou", display_name: "快手", release_state: "pilot", account_count: 0, default_account_id: null },
      { platform: "xiaohongshu", display_name: "小红书", release_state: "pilot", account_count: 0, default_account_id: null },
    ] });
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
    expect(platformsApi).toHaveBeenCalledTimes(1);
    expect(screen.getByText("尚未选择发布包或运行")).toBeInTheDocument();
    expect(screen.queryByText("已发布")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "发布账号" }));
    await waitFor(() => expect(screen.getByText("门店账号")).toBeInTheDocument());
    expect(screen.getByText("需要登录")).toBeInTheDocument();
    expect(screen.getAllByText("试点").length).toBeGreaterThan(0);
    expect(screen.getByRole("region", { name: "video_channel账号" })).toHaveTextContent("视频号");
    expect(screen.getByRole("region", { name: "video_channel账号" })).toHaveTextContent("尚未创建本机账号");
  });

  it("loads package and run handoff from the canonical hash route", async () => {
    window.location.hash = "#/publish?package_id=pkg_1&run_id=run_1";
    render(<PublishCenterView v2Enabled />);
    expect(await screen.findByText("素材已填充到平台页面，最终发布仍需人工确认。")).toBeInTheDocument();
    expect(screen.getByText("1. waiting_for_human")).toBeInTheDocument();
    expect(packageApi).toHaveBeenCalledWith("pkg_1");
    expect(preflightApi).toHaveBeenCalledWith("pkg_1");
    expect(runApi).toHaveBeenCalledWith("run_1");
    expect(eventsApi).toHaveBeenCalledWith("run_1");
  });

  it("creates another account for the same platform from the V2 account summary", async () => {
    render(<PublishCenterView v2Enabled />);
    fireEvent.click(await screen.findByRole("tab", { name: "发布账号" }));
    const douyinGroup = await screen.findByRole("region", { name: "douyin账号" });
    fireEvent.click(within(douyinGroup).getByRole("button", { name: "添加账号" }));
    fireEvent.change(screen.getByLabelText("账号名称"), { target: { value: "抖音副账号" } });
    fireEvent.click(screen.getByRole("button", { name: "创建账号" }));
    await waitFor(() => expect(createAccountApi).toHaveBeenCalledWith({
      platform: "douyin",
      display_name: "抖音副账号",
      make_default: false,
    }));
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
    api.mockResolvedValueOnce({ items: [{ ...account, login_state: "authenticated", verification_state: "verified", last_error_code: null }] });
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
    expect(await screen.findByText("素材已填充到平台页面，最终发布仍需人工确认。")).toBeInTheDocument();
  });

  it("records the human publish outcome without clicking a platform button", async () => {
    window.location.hash = "#/publish?package_id=pkg_1&run_id=run_1";
    runApi
      .mockResolvedValueOnce({ run: { run_id: "run_1", package_id: "pkg_1", account_id: "acct_douyin_1", platform: "douyin", state: "waiting_for_human", state_version: 1, attempt: 1, current_step: "await_human_publish", idempotency_key: "idem", human_confirmation: { required: true, confirmed: false, confirmed_at: null, actor_ref: null }, task_id: null, error_code: null, error_message: null, checkpoint: {}, created_at: "2026-07-20T00:00:00Z", updated_at: "2026-07-20T00:00:00Z", schema_version: 1 } })
      .mockResolvedValueOnce({ run: { run_id: "run_1", package_id: "pkg_1", account_id: "acct_douyin_1", platform: "douyin", state: "succeeded", state_version: 2, attempt: 1, current_step: "human_published", idempotency_key: "idem", human_confirmation: { required: true, confirmed: true, confirmed_at: "2026-07-20T00:00:01Z", actor_ref: "desktop_user" }, task_id: null, error_code: null, error_message: null, checkpoint: {}, created_at: "2026-07-20T00:00:00Z", updated_at: "2026-07-20T00:00:01Z", schema_version: 1 } });
    markOutcomeApi.mockResolvedValue({ run: { run_id: "run_1", package_id: "pkg_1", account_id: "acct_douyin_1", platform: "douyin", state: "succeeded", state_version: 2, attempt: 1, current_step: "human_published", idempotency_key: "idem", human_confirmation: { required: true, confirmed: true, confirmed_at: "2026-07-20T00:00:01Z", actor_ref: "desktop_user" }, task_id: null, error_code: null, error_message: null, checkpoint: {}, created_at: "2026-07-20T00:00:00Z", updated_at: "2026-07-20T00:00:01Z", schema_version: 1 } });
    render(<PublishCenterView v2Enabled />);
    fireEvent.click(await screen.findByRole("button", { name: "我已完成发布" }));
    await waitFor(() => expect(markOutcomeApi).toHaveBeenCalledWith("run_1", "published_by_user"));
    expect(await screen.findByText("已完成")).toBeInTheDocument();
  });

  it("keeps an unverified platform on copy fallback", async () => {
    api.mockResolvedValueOnce({ items: [{ ...account, account_id: "acct_kuaishou_1", platform: "kuaishou", display_name: "快手账号", platform_release_state: "unverified", is_default: false }] });
    window.location.hash = "#/publish?package_id=pkg_1";
    render(<PublishCenterView v2Enabled />);
    expect(await screen.findByText("待独立 live gate；当前仅支持复制素材回退")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "开始填充草稿" })).not.toBeInTheDocument();
  });

  it("requires account login before exposing draft fill", async () => {
    window.location.hash = "#/publish?package_id=pkg_1";
    render(<PublishCenterView v2Enabled />);
    expect(await screen.findByText("请先检测登录并完成扫码")).toBeInTheDocument();
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

  it("runs selected accounts serially and opens the next item only after human confirmation", async () => {
    api.mockResolvedValueOnce({ items: [{ ...account, login_state: "authenticated", verification_state: "verified", last_error_code: null }, authenticatedAccount] });
    window.location.hash = "#/publish?package_id=pkg_1";
    createRunApi
      .mockResolvedValueOnce({ run_id: "run_1", task_id: null, state: "queued", requires_human_confirmation: true, idempotent_replay: false })
      .mockResolvedValueOnce({ run_id: "run_2", task_id: null, state: "queued", requires_human_confirmation: true, idempotent_replay: false });
    runApi.mockImplementation(async (runId) => ({ run: { run_id: runId, package_id: "pkg_1", account_id: runId === "run_2" ? "acct_douyin_2" : "acct_douyin_1", platform: "douyin", state: "waiting_for_human", state_version: 1, attempt: 1, current_step: "await_human_publish", idempotency_key: `idem-${runId}`, human_confirmation: { required: true, confirmed: false, confirmed_at: null, actor_ref: null }, task_id: null, error_code: null, error_message: null, checkpoint: {}, created_at: "2026-07-20T00:00:00Z", updated_at: "2026-07-20T00:00:00Z", schema_version: 1 } }));
    render(<PublishCenterView v2Enabled />);
    fireEvent.click(await screen.findByRole("tab", { name: "发布账号" }));
    fireEvent.click(await screen.findByLabelText("选择门店账号"));
    fireEvent.click(await screen.findByLabelText("选择抖音副账号"));
    fireEvent.click(screen.getByRole("button", { name: "开始批量发布" }));
    await waitFor(() => expect(createRunApi).toHaveBeenCalledTimes(1));
    expect(await screen.findByText("我已完成发布，下一平台")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "我已完成发布，下一平台" }));
    await waitFor(() => expect(createRunApi).toHaveBeenCalledTimes(2));
    expect(createRunApi.mock.calls[1][0].account_id).toBe("acct_douyin_2");
    expect(screen.getByText(/抖音副账号/)).toBeInTheDocument();
  });

  it("does not expose retry for a non-retryable needs-attention step", async () => {
    runApi.mockResolvedValueOnce({ run: { run_id: "run_1", package_id: "pkg_1", account_id: "acct_douyin_1", platform: "douyin", state: "needs_attention", state_version: 1, attempt: 1, current_step: "profile_lock", idempotency_key: "idem", human_confirmation: { required: true, confirmed: false, confirmed_at: null, actor_ref: null }, task_id: null, error_code: "PROFILE_LOCKED", error_message: "profile locked", checkpoint: {}, created_at: "2026-07-20T00:00:00Z", updated_at: "2026-07-20T00:00:00Z", schema_version: 1 } });
    window.location.hash = "#/publish?package_id=pkg_1&run_id=run_1";
    render(<PublishCenterView v2Enabled />);
    expect(await screen.findByText("当前步骤不可自动重试，请停止运行后更换素材或账号。")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "重试当前步骤" })).not.toBeInTheDocument();
  });

  it("keeps accounts visible when the platform registry is unavailable and clears the warning after recovery", async () => {
    platformsApi.mockRejectedValueOnce(new Error("registry down"));
    render(<PublishCenterView v2Enabled />);
    fireEvent.click(await screen.findByRole("tab", { name: "发布账号" }));
    expect(await screen.findByText("门店账号")).toBeInTheDocument();
    expect(await screen.findByText("平台能力暂时不可用，已保留账号状态。")).toBeInTheDocument();
    platformsApi.mockResolvedValueOnce({ items: [
      { platform: "douyin", display_name: "抖音", release_state: "pilot", account_count: 1, default_account_id: "acct_douyin_1" },
      { platform: "video_channel", display_name: "视频号", release_state: "pilot", account_count: 0, default_account_id: null },
    ] });
    fireEvent.click(screen.getByRole("button", { name: "刷新状态" }));
    await waitFor(() => expect(screen.queryByText("平台能力暂时不可用，已保留账号状态。")).not.toBeInTheDocument());
  });
});
