import { Alert, Button, Card, Checkbox, Input, Modal, Popconfirm, Space, Tag, Typography } from "antd";
import { useEffect, useMemo, useState } from "react";

import {
  archivePublishAccount,
  clearPublishAccountProfile,
  createPublishAccount,
  listPublishAccounts,
  listPublishPlatforms,
  probePublishAccount,
  setDefaultPublishAccount,
  type PublishAccount,
  type PublishAccountPlatform,
  type PublishPlatformCapability,
} from "../../api";

const PLATFORM_LABELS: Record<PublishAccountPlatform, string> = {
  douyin: "抖音",
  video_channel: "视频号",
  kuaishou: "快手",
  xiaohongshu: "小红书",
};

const LOGIN_LABELS: Record<PublishAccount["login_state"], string> = {
  not_connected: "未连接",
  connecting: "检测中",
  login_required: "需要登录",
  authenticated: "已登录",
  expired: "登录过期",
  identity_changed: "身份变化",
  degraded: "检测异常",
  locked: "浏览器占用",
  revoked: "已归档",
};

export function PublishAccountsView() {
  const [accounts, setAccounts] = useState<PublishAccount[]>([]);
  const [platforms, setPlatforms] = useState<PublishPlatformCapability[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [modalPlatform, setModalPlatform] = useState<PublishAccountPlatform | null>(null);
  const [displayName, setDisplayName] = useState("");
  const [makeDefault, setMakeDefault] = useState(true);

  async function reload() {
    setLoading(true);
    setError("");
    try {
      const [accountResponse, platformResponse] = await Promise.all([listPublishAccounts(), listPublishPlatforms()]);
      setAccounts(accountResponse.items);
      setPlatforms(platformResponse.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void reload();
  }, []);

  const accountsByPlatform = useMemo(() => {
    const result: Partial<Record<PublishAccountPlatform, PublishAccount[]>> = {};
    for (const account of accounts) {
      (result[account.platform] ||= []).push(account);
    }
    return result;
  }, [accounts]);

  async function runAction(action: string, callback: () => Promise<PublishAccount>) {
    setBusy(action);
    setError("");
    try {
      const updated = await callback();
      setAccounts((current) => {
        if (updated.archived_at) return current.filter((item) => item.account_id !== updated.account_id);
        const found = current.some((item) => item.account_id === updated.account_id);
        return found ? current.map((item) => (item.account_id === updated.account_id ? updated : item)) : [...current, updated];
      });
      const platformResponse = await listPublishPlatforms();
      setPlatforms(platformResponse.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy("");
    }
  }

  async function submitCreate() {
    if (!modalPlatform || !displayName.trim()) return;
    await runAction(`create:${modalPlatform}`, () => createPublishAccount({
      platform: modalPlatform,
      display_name: displayName.trim(),
      make_default: makeDefault,
    }));
    setModalPlatform(null);
    setDisplayName("");
  }

  return (
    <section className="card wide publish-account-page">
      <div className="card-title">
        <div>
          <h2>发布账号</h2>
          <p className="muted">账号状态来自本机 publishing 数据与显式登录探测；系统不会把 Cookie、二维码或 profile 路径返回给页面。</p>
        </div>
        <Space>
          <Tag color="processing">本机账号</Tag>
          <Button onClick={() => void reload()} loading={loading}>刷新状态</Button>
        </Space>
      </div>
      {error ? <Alert type="error" showIcon title="账号数据加载失败" description={error} /> : null}
      {loading && !platforms.length ? <Typography.Text type="secondary">正在读取真实账号状态…</Typography.Text> : null}
      <div className="publish-account-grid">
        {platforms.map((platform) => {
          const platformAccounts = accountsByPlatform[platform.platform] || [];
          const label = PLATFORM_LABELS[platform.platform];
          return (
            <Card key={platform.platform} className="publish-account-card" title={label} extra={<Tag color={platform.release_state === "pilot" ? "processing" : "default"}>{platform.release_state === "pilot" ? "试点" : "未验证"}</Tag>}>
              <Space orientation="vertical" style={{ width: "100%" }}>
                <Typography.Text type="secondary">
                  {platformAccounts.length ? `${platformAccounts.length} 个本机账号` : "尚未创建本机账号"}
                </Typography.Text>
                {platformAccounts.map((account) => (
                  <AccountRow
                    key={account.account_id}
                    account={account}
                    busy={busy}
                    onProbe={() => void runAction(`probe:${account.account_id}`, () => probePublishAccount(account.account_id))}
                    onDefault={() => void runAction(`default:${account.account_id}`, () => setDefaultPublishAccount(account.account_id))}
                    onClear={() => void runAction(`clear:${account.account_id}`, () => clearPublishAccountProfile(account.account_id))}
                    onArchive={() => void runAction(`archive:${account.account_id}`, () => archivePublishAccount(account.account_id))}
                  />
                ))}
                <Button onClick={() => { setModalPlatform(platform.platform); setMakeDefault(platformAccounts.length === 0); }}>
                  添加本机账号
                </Button>
              </Space>
            </Card>
          );
        })}
      </div>
      <Alert
        type="info"
        showIcon
        title="安全边界"
        description="PUB-1 只管理本机账号与登录态。连接/检测需要显式点击；最终发布、平台 selector 和发布运行留到后续 Gate。"
      />
      <Modal
        open={Boolean(modalPlatform)}
        title={`添加${modalPlatform ? PLATFORM_LABELS[modalPlatform] : ""}本机账号`}
        okText="创建账号"
        cancelText="取消"
        confirmLoading={busy.startsWith("create:")}
        okButtonProps={{ disabled: !displayName.trim() }}
        onOk={() => void submitCreate()}
        onCancel={() => { setModalPlatform(null); setDisplayName(""); }}
      >
        <Space orientation="vertical" style={{ width: "100%" }}>
          <Input autoFocus placeholder="例如：门店主账号" value={displayName} onChange={(event) => setDisplayName(event.target.value)} maxLength={80} />
          <Checkbox checked={makeDefault} onChange={(event) => setMakeDefault(event.target.checked)}>设为该平台默认账号</Checkbox>
        </Space>
      </Modal>
    </section>
  );
}

function AccountRow({
  account,
  busy,
  onProbe,
  onDefault,
  onClear,
  onArchive,
}: {
  account: PublishAccount;
  busy: string;
  onProbe: () => void;
  onDefault: () => void;
  onClear: () => void;
  onArchive: () => void;
}) {
  const statusColor = account.login_state === "authenticated" ? "success" : account.login_state === "degraded" || account.login_state === "locked" ? "warning" : "default";
  return (
    <section className="publish-account-card" data-account-id={account.account_id}>
      <Space orientation="vertical" style={{ width: "100%" }}>
        <Space wrap>
          <strong>{account.display_name}</strong>
          <Tag color={statusColor}>{LOGIN_LABELS[account.login_state]}</Tag>
          {account.is_default ? <Tag color="processing">默认</Tag> : null}
        </Space>
        {account.login_subject_hint ? <Typography.Text type="secondary">身份提示：{account.login_subject_hint}</Typography.Text> : null}
        {account.last_error_code ? <Typography.Text type="danger">诊断：{account.last_error_code}</Typography.Text> : null}
        <Space wrap>
          <Button size="small" loading={busy === `probe:${account.account_id}`} onClick={onProbe}>检测登录</Button>
          {!account.is_default && account.enabled ? <Button size="small" loading={busy === `default:${account.account_id}`} onClick={onDefault}>设为默认</Button> : null}
          <Popconfirm title="清理本机 profile？账号记录会保留，但需要重新登录。" okText="清理" cancelText="取消" onConfirm={onClear}>
            <Button size="small" loading={busy === `clear:${account.account_id}`}>清理登录态</Button>
          </Popconfirm>
          <Popconfirm title="归档该账号？不会删除本机 profile。" okText="归档" cancelText="取消" onConfirm={onArchive}>
            <Button size="small" danger loading={busy === `archive:${account.account_id}`}>归档</Button>
          </Popconfirm>
        </Space>
      </Space>
    </section>
  );
}
