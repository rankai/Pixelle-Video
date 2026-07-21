import { Alert, Button, Card, Empty, Space, Tag, Typography } from "antd";
import { useEffect, useMemo, useState } from "react";

import {
  getPublishPackageV2,
  getPublishRunV2,
  listPublishAccountsV2,
  listPublishRunEventsV2,
  preflightPublishPackageV2,
  resolvePublishPackageV2,
  type PublishAccount,
  type PublishPackageV2,
  type PublishRunEvent,
  type PublishRunV2,
} from "../../api";
import { featureFlags } from "../../featureFlags";
import { recordRolloutTelemetry } from "../../rolloutTelemetry";
import { PublishAccountsView } from "./PublishAccountsView";

type PublishCenterTab = "runs" | "accounts";

export function PublishCenterView({ v2Enabled = featureFlags.publishCenterV2 }: { v2Enabled?: boolean }) {
  if (!v2Enabled) {
    return <FallbackPublishCenter />;
  }

  return <EnabledPublishCenter refs={readPublishRefs()} />;
}

function FallbackPublishCenter() {
  useEffect(() => {
    recordRolloutTelemetry("publish_center_fallback", { step: "legacy_fallback" });
  }, []);

  return (
      <section aria-label="发布中心">
        <Alert
          className="publish-center-v2-fallback"
          type="info"
          showIcon
          title="发布中心 V2 尚未开启"
          description="当前保留既有发布账号页和旧发布工作流；不会创建新的发布运行。"
        />
        <PublishAccountsView />
      </section>
  );
}

type PublishRefs = { packageId: string | null; artifactId: string | null; runId: string | null; error: string | null };

function readPublishRefs(): PublishRefs {
  if (typeof window === "undefined") return { packageId: null, artifactId: null, runId: null, error: null };
  const hash = window.location.hash;
  const query = hash.includes("?") ? hash.slice(hash.indexOf("?") + 1) : "";
  const params = new URLSearchParams(query);
  const allowed = new Set(["package_id", "artifact_id", "run_id"]);
  if ([...params.keys()].some((key) => !allowed.has(key) || !params.get(key))) return { packageId: null, artifactId: null, runId: null, error: "PUBLISH_REF_UNKNOWN" };
  return { packageId: params.get("package_id"), artifactId: params.get("artifact_id"), runId: params.get("run_id"), error: null };
}

function EnabledPublishCenter({ refs }: { refs: PublishRefs }) {
  const [tab, setTab] = useState<PublishCenterTab>("runs");
  const [accounts, setAccounts] = useState<PublishAccount[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [packageData, setPackageData] = useState<PublishPackageV2 | null>(null);
  const [runData, setRunData] = useState<PublishRunV2 | null>(null);
  const [events, setEvents] = useState<PublishRunEvent[]>([]);

  async function reloadAccounts() {
    setLoading(true);
    setError("");
    try {
      const response = await listPublishAccountsV2();
      setAccounts(response.items);
    } catch (reason) {
      setAccounts([]);
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    recordRolloutTelemetry("publish_center_viewed", { step: "publish_center" });
    void reloadAccounts();
  }, []);

  useEffect(() => {
    let active = true;
    async function loadHandoff() {
      if (refs.error) {
        setError(refs.error);
        setPackageData(null);
        setRunData(null);
        setEvents([]);
        return;
      }
      if (!refs.packageId && !refs.artifactId && !refs.runId) return;
      try {
        const run = refs.runId ? (await getPublishRunV2(refs.runId)).run : null;
        const resolvedPackage = refs.artifactId && !refs.packageId ? await resolvePublishPackageV2(refs.artifactId) : null;
        const packageId = refs.packageId || resolvedPackage?.package_id || run?.package_id;
        if (!packageId) throw new Error("PUBLISH_REF_REQUIRED");
        if (run && run.package_id !== packageId) throw new Error("PUBLISH_FACT_MISMATCH");
        const [packageResponse, preflightResponse, eventResponse] = await Promise.all([
          getPublishPackageV2(packageId),
          preflightPublishPackageV2(packageId),
          run ? listPublishRunEventsV2(run.run_id) : Promise.resolve({ items: [], next_after: 0 }),
        ]);
        if (!active) return;
        if (refs.artifactId && !packageResponse.artifact_refs.some((ref) => ref.artifact_id === refs.artifactId)) throw new Error("PUBLISH_FACT_MISMATCH");
        setPackageData(packageResponse);
        setRunData(run);
        let previousSeq = 0;
        const eventIds = new Set<string>();
        for (const event of eventResponse.items) {
          if (event.run_id !== (run?.run_id || "") || event.event_seq <= previousSeq || eventIds.has(event.event_id)) {
            throw new Error("PUBLISH_EVENT_ORDER_INVALID");
          }
          previousSeq = event.event_seq;
          eventIds.add(event.event_id);
        }
        setEvents(eventResponse.items);
        if (preflightResponse.status !== "ready") throw new Error("PUBLISH_PREFLIGHT_INVALID");
      } catch (reason) {
        if (!active) return;
        setPackageData(null);
        setRunData(null);
        setEvents([]);
        setError(reason instanceof Error ? reason.message : String(reason));
      }
    }
    void loadHandoff();
    return () => {
      active = false;
    };
  }, [refs.artifactId, refs.error, refs.packageId, refs.runId]);

  const accountSummary = useMemo(() => {
    const grouped = new Map<string, PublishAccount[]>();
    accounts.forEach((account) => grouped.set(account.platform, [...(grouped.get(account.platform) || []), account]));
    return [...grouped.entries()];
  }, [accounts]);

  return (
    <section className="publish-center-v2" aria-label="发布中心">
      <div className="publish-center-v2-heading">
        <div>
          <Typography.Text type="secondary">PUBLISH CENTER · V2</Typography.Text>
          <Typography.Title level={2}>发布中心</Typography.Title>
          <Typography.Paragraph type="secondary">
            统一查看真实 package、账号和发布运行状态。当前批次只接入安全只读投影，最终发布始终由人工确认。
          </Typography.Paragraph>
        </div>
        <Tag color="processing">人工确认边界</Tag>
      </div>

      {error ? (
        <>
          <Alert type="warning" showIcon title="发布中心数据暂时不可用" description={error} />
          <PublishFallbackActions />
        </>
      ) : null}
      <div className="publish-center-v2-tabs" role="tablist" aria-label="发布中心分区">
        <button type="button" role="tab" aria-selected={tab === "runs"} onClick={() => setTab("runs")}>发布运行</button>
        <button type="button" role="tab" aria-selected={tab === "accounts"} onClick={() => setTab("accounts")}>发布账号</button>
      </div>

      {tab === "runs" ? (
        packageData || runData ? <PublishRunProjection packageData={packageData} runData={runData} events={events} /> : <PublishRunEmptyState />
      ) : <PublishAccountSummary accounts={accounts} groups={accountSummary} loading={loading} onReload={() => void reloadAccounts()} />}
    </section>
  );
}

function PublishFallbackActions() {
  function openLegacyWorkspace() {
    if (typeof window !== "undefined") window.location.hash = "#/ip";
  }

  return (
    <Card className="publish-center-v2-fallback-actions" title="安全回退">
      <Typography.Paragraph type="secondary">
        发布适配器暂时不可用。你仍可以回到生产工作区复制文案、预览或下载已生成素材；这里不会暴露本地路径，也不会自动发布。
      </Typography.Paragraph>
      <Button onClick={openLegacyWorkspace}>返回工作区复制/下载素材</Button>
    </Card>
  );
}

function PublishRunProjection({ packageData, runData, events }: { packageData: PublishPackageV2 | null; runData: PublishRunV2 | null; events: PublishRunEvent[] }) {
  const state = runData?.state || "package_ready";
  return (
    <Card className="publish-center-v2-card" title="发布运行">
      <Space direction="vertical" size="middle" style={{ width: "100%" }}>
        <Space wrap>
          <Tag color="processing">{state}</Tag>
          {packageData ? <Tag>包 {packageData.package_id}</Tag> : null}
          {runData ? <Tag>运行 {runData.run_id}</Tag> : null}
        </Space>
        <Typography.Text type="secondary">
          {runData ? "已恢复同一发布运行；最终发布仍需人工确认。" : "已接收应用产物 handoff，等待选择账号并创建发布运行。"}
        </Typography.Text>
        {events.length ? <div aria-label="发布事件时间线">{events.map((event) => <div key={`${event.run_id}-${event.event_seq}`}>{event.event_seq}. {event.event_type}</div>)}</div> : null}
      </Space>
    </Card>
  );
}

function PublishRunEmptyState() {
  return (
    <Card className="publish-center-v2-card" title="发布运行">
      <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="尚未选择发布包或运行" />
      <Typography.Paragraph type="secondary" style={{ textAlign: "center" }}>
        从项目或应用产物进入发布中心后，这里会显示真实的 PublishPackage、账号、字段清单和 run timeline；当前不会伪造已发布状态。
      </Typography.Paragraph>
    </Card>
  );
}

function PublishAccountSummary({
  accounts,
  groups,
  loading,
  onReload,
}: {
  accounts: PublishAccount[];
  groups: Array<[string, PublishAccount[]]>;
  loading: boolean;
  onReload: () => void;
}) {
  return (
    <Card
      className="publish-center-v2-card"
      title="发布账号"
      extra={<Button onClick={onReload} loading={loading}>刷新状态</Button>}
    >
      {!loading && !accounts.length ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无本机发布账号" /> : null}
      <div className="publish-center-v2-account-grid">
        {groups.map(([platform, platformAccounts]) => (
          <section key={platform} className="publish-center-v2-account-group" aria-label={`${platform}账号`}>
            <Space>
              <Typography.Title level={4}>{platformLabel(platform)}</Typography.Title>
              <Tag color="default">{platformAccounts.length} 个账号</Tag>
            </Space>
            {platformAccounts.map((account) => <AccountProjection key={account.account_id} account={account} />)}
          </section>
        ))}
      </div>
    </Card>
  );
}

function AccountProjection({ account }: { account: PublishAccount }) {
  const status = account.login_state === "authenticated" ? "已登录" : account.login_state === "login_required" ? "需要登录" : account.login_state === "expired" ? "登录过期" : "未连接";
  const color = account.login_state === "authenticated" ? "success" : account.login_state === "degraded" || account.login_state === "locked" ? "warning" : "default";
  return (
    <div className="publish-center-v2-account-row" data-account-id={account.account_id}>
      <Space wrap>
        <strong>{account.display_name}</strong>
        <Tag color={color}>{status}</Tag>
        {account.is_default ? <Tag color="processing">默认</Tag> : null}
        <Tag color={account.platform_release_state === "pilot" ? "processing" : "default"}>{account.platform_release_state === "pilot" ? "试点" : "未验证"}</Tag>
      </Space>
      {account.last_error_code ? <Typography.Text type="secondary">诊断：{account.last_error_code}</Typography.Text> : null}
    </div>
  );
}

function platformLabel(platform: string) {
  return { douyin: "抖音", video_channel: "视频号", shipinhao: "视频号", kuaishou: "快手", xiaohongshu: "小红书" }[platform] || platform;
}
