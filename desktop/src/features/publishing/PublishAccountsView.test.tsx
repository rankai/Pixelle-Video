import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PublishAccountsView } from "./PublishAccountsView";
import type { PublishAccount } from "../../api";

const api = vi.hoisted(() => ({
  listPublishAccounts: vi.fn(),
  listPublishPlatforms: vi.fn(),
  createPublishAccount: vi.fn(),
  setDefaultPublishAccount: vi.fn(),
  archivePublishAccount: vi.fn(),
  clearPublishAccountProfile: vi.fn(),
  probePublishAccount: vi.fn(),
}));

vi.mock("../../api", () => ({
  ...api,
}));

const platforms = [
  { platform: "douyin", display_name: "抖音", release_state: "pilot", account_count: 0, default_account_id: null },
  { platform: "video_channel", display_name: "视频号", release_state: "unverified", account_count: 0, default_account_id: null },
  { platform: "kuaishou", display_name: "快手", release_state: "unverified", account_count: 0, default_account_id: null },
  { platform: "xiaohongshu", display_name: "小红书", release_state: "unverified", account_count: 0, default_account_id: null },
];

const account: PublishAccount = {
  schema_version: 1,
  account_id: "acct_douyin_1",
  platform: "douyin",
  display_name: "门店账号",
  profile_ref: "profile_douyin_1",
  verification_state: "unverified",
  login_state: "login_required",
  enabled: true,
  is_default: true,
  profile_exists: true,
  platform_release_state: "pilot",
  created_at: "2026-07-20T00:00:00Z",
  updated_at: "2026-07-20T00:00:00Z",
  last_verified_at: null,
  last_error_code: "LOGIN_REQUIRED",
  login_subject_hint: null,
  archived_at: null,
};

describe("PublishAccountsView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.listPublishAccounts.mockResolvedValue({ items: [] });
    api.listPublishPlatforms.mockResolvedValue({ items: platforms });
    api.createPublishAccount.mockResolvedValue(account);
    api.setDefaultPublishAccount.mockResolvedValue(account);
    api.archivePublishAccount.mockResolvedValue({ ...account, archived_at: "2026-07-20T00:01:00Z" });
    api.clearPublishAccountProfile.mockResolvedValue({ ...account, login_state: "not_connected", last_error_code: null });
    api.probePublishAccount.mockResolvedValue(account);
  });

  it("renders release state from the API instead of static green available cards", async () => {
    render(<PublishAccountsView />);
    await waitFor(() => expect(screen.getByText("抖音")).toBeInTheDocument());
    expect(screen.getByText("试点")).toBeInTheDocument();
    expect(screen.getAllByText("未验证")).toHaveLength(3);
    expect(screen.queryByText("可用")).not.toBeInTheDocument();
    expect(api.listPublishAccounts).toHaveBeenCalledTimes(1);
  });

  it("creates an account through the API and exposes login-required state", async () => {
    api.listPublishAccounts.mockResolvedValueOnce({ items: [] }).mockResolvedValue({ items: [account] });
    render(<PublishAccountsView />);
    await waitFor(() => expect(screen.getAllByText("添加本机账号")).toHaveLength(4));
    fireEvent.click(screen.getAllByText("添加本机账号")[0]);
    fireEvent.change(screen.getByPlaceholderText("例如：门店主账号"), { target: { value: "门店账号" } });
    fireEvent.click(screen.getByRole("button", { name: "创建账号" }));
    await waitFor(() => expect(api.createPublishAccount).toHaveBeenCalledWith({
      platform: "douyin",
      display_name: "门店账号",
      make_default: true,
    }));
    await waitFor(() => expect(screen.getByText("需要登录")).toBeInTheDocument());
  });
});
