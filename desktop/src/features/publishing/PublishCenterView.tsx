import { Alert, Button, Card, Checkbox, Empty, Input, Modal, Space, Tag, Typography } from "antd";
import { useEffect, useMemo, useState } from "react";

import {
  getPublishPackageV2,
  getPublishRunV2,
  createPublishRunV2,
  createPublishAccount,
  probePublishAccount,
  cancelPublishRunV2,
  listPublishAccountsV2,
  listPublishPlatforms,
  listPublishRunEventsV2,
  markPublishRunOutcomeV2,
  preflightPublishPackageV2,
  retryPublishRunStepV2,
  resolvePublishPackageV2,
  resumePublishRunV2,
  setDefaultPublishAccount,
  type PublishAccount,
  type PublishAccountPlatform,
  type PublishPlatformCapability,
  type PublishPackageV2,
  type PublishRunEvent,
  type PublishRunV2,
} from "../../api";
import { featureFlags } from "../../featureFlags";
import { recordRolloutTelemetry } from "../../rolloutTelemetry";
import { PublishAccountsView } from "./PublishAccountsView";

type PublishCenterTab = "runs" | "accounts";
type BatchPublishState = "idle" | "running" | "paused" | "completed";
const retryablePublishSteps = new Set(["preflight", "media_preflight", "prepare_package", "verify_media", "await_login", "adapter_prepare", "resume"]);

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
  const [tab, setTab] = useState<PublishCenterTab>(() => (refs.packageId || refs.artifactId) && !refs.runId ? "accounts" : "runs");
  const [accounts, setAccounts] = useState<PublishAccount[]>([]);
  const [platforms, setPlatforms] = useState<PublishPlatformCapability[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [accountError, setAccountError] = useState("");
  const [packageData, setPackageData] = useState<PublishPackageV2 | null>(null);
  const [runData, setRunData] = useState<PublishRunV2 | null>(null);
  const [events, setEvents] = useState<PublishRunEvent[]>([]);
  const [startingAccountId, setStartingAccountId] = useState<string | null>(null);
  const [accountAction, setAccountAction] = useState("");
  const [runAction, setRunAction] = useState("");
  const [addAccountPlatform, setAddAccountPlatform] = useState<PublishAccountPlatform | null>(null);
  const [addAccountName, setAddAccountName] = useState("");
  const [makeDefault, setMakeDefault] = useState(false);
  const [selectedAccountIds, setSelectedAccountIds] = useState<string[]>([]);
  const [batchAccountIds, setBatchAccountIds] = useState<string[]>([]);
  const [batchPosition, setBatchPosition] = useState(-1);
  const [batchState, setBatchState] = useState<BatchPublishState>("idle");

  async function reloadAccounts() {
    setLoading(true);
    const [accountResult, platformResult] = await Promise.allSettled([
      listPublishAccountsV2(),
      listPublishPlatforms(),
    ]);
    const errors: string[] = [];
    if (accountResult.status === "fulfilled") setAccounts(accountResult.value.items);
    else {
      setAccounts([]);
      errors.push(accountResult.reason instanceof Error ? accountResult.reason.message : String(accountResult.reason));
    }
    if (platformResult.status === "fulfilled") setPlatforms(platformResult.value.items);
    else {
      // Keep the account data visible if the capability registry is briefly unavailable.
      setPlatforms([]);
      errors.push("平台能力暂时不可用，已保留账号状态。");
    }
    setAccountError(errors.join("；"));
    setLoading(false);
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
        setSelectedAccountIds([]);
        setBatchAccountIds([]);
        setBatchPosition(-1);
        setBatchState("idle");
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
    // Seed from the capability registry so a supported platform remains
    // visible even when no local account has been created yet. This keeps the
    // UI truthful about the four-platform rollout without inventing an
    // account or login state.
    platforms.forEach((platform) => grouped.set(platform.platform, []));
    accounts.forEach((account) => grouped.set(account.platform, [...(grouped.get(account.platform) || []), account]));
    return [...grouped.entries()];
  }, [accounts, platforms]);

  const duplicateIdentityIds = useMemo(() => {
    const byIdentity = new Map<string, string[]>();
    accounts.forEach((account) => {
      if (!account.login_subject_hint) return;
      byIdentity.set(account.login_subject_hint, [...(byIdentity.get(account.login_subject_hint) || []), account.account_id]);
    });
    return new Set([...byIdentity.values()].filter((ids) => ids.length > 1).flat());
  }, [accounts]);

  async function startRun(account: PublishAccount, fromBatch = false) {
    if (!packageData) return;
    setStartingAccountId(account.account_id);
    setError("");
    try {
      const accepted = await createPublishRunV2({
        package_id: packageData.package_id,
        account_id: account.account_id,
        platform: account.platform,
        idempotency_key: `publish-center:${packageData.package_id}:${account.account_id}`,
      });
      const [runResponse, eventResponse] = await Promise.all([
        getPublishRunV2(accepted.run_id),
        listPublishRunEventsV2(accepted.run_id),
      ]);
      setRunData(runResponse.run);
      setEvents(eventResponse.items);
      setTab("runs");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
      if (fromBatch) setBatchState("paused");
    } finally {
      setStartingAccountId(null);
    }
  }

  function toggleAccountSelection(account: PublishAccount, checked: boolean) {
    if (!account.enabled || account.platform_release_state !== "pilot" || account.login_state !== "authenticated") return;
    setSelectedAccountIds((current) => checked ? [...new Set([...current, account.account_id])] : current.filter((id) => id !== account.account_id));
  }

  async function startBatch() {
    if (!packageData || batchState === "running") return;
    const isResume = batchState === "paused" && batchAccountIds.length > 0;
    const sourceIds = isResume ? batchAccountIds : selectedAccountIds;
    const queueIds = isResume ? [...sourceIds] : sourceIds.filter((accountId) => {
      const account = accounts.find((item) => item.account_id === accountId);
      return Boolean(account && account.enabled && account.platform_release_state === "pilot" && account.login_state === "authenticated");
    });
    if (!queueIds.length) {
      setError("请先选择至少一个已登录的试点账号。");
      return;
    }
    const resumedCancelledRun = isResume && runData?.state === "cancelled";
    let startPosition = isResume ? batchPosition + (resumedCancelledRun ? 1 : 0) : 0;
    while (startPosition < queueIds.length) {
      const account = accounts.find((item) => item.account_id === queueIds[startPosition]);
      if (account && account.enabled && account.platform_release_state === "pilot" && account.login_state === "authenticated") break;
      startPosition += 1;
    }
    const firstAccount = accounts.find((account) => account.account_id === queueIds[startPosition]);
    if (!firstAccount) {
      setBatchState("completed");
      return;
    }
    setBatchAccountIds(queueIds);
    setBatchPosition(startPosition);
    setBatchState("running");
    await startRun(firstAccount, true);
  }

  function batchHasNext() {
    return batchState === "running" && batchPosition >= 0 && batchPosition < batchAccountIds.length - 1;
  }

  async function startNextBatchItem() {
    const nextPosition = batchPosition + 1;
    const nextAccountId = batchAccountIds[nextPosition];
    const nextAccount = accounts.find((account) => account.account_id === nextAccountId);
    if (!nextAccount) {
      setBatchState("completed");
      return;
    }
    setBatchPosition(nextPosition);
    setBatchState("running");
    await startRun(nextAccount, true);
  }

  async function refreshRun(runId: string) {
    const [runResponse, eventResponse] = await Promise.all([
      getPublishRunV2(runId),
      listPublishRunEventsV2(runId),
    ]);
    setRunData(runResponse.run);
    setEvents(eventResponse.items);
  }

  async function handleRunOutcome(outcome: "published_by_user" | "not_published") {
    if (!runData) return;
    setRunAction(outcome === "published_by_user" ? "mark-published" : "mark-not-published");
    setError("");
    try {
      await markPublishRunOutcomeV2(runData.run_id, outcome);
      await refreshRun(runData.run_id);
      if (outcome === "published_by_user") {
        if (batchHasNext()) {
          await startNextBatchItem();
        } else if (batchAccountIds.length) {
          setBatchState("completed");
        }
      } else if (batchAccountIds.length) {
        setBatchState("paused");
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setRunAction("");
    }
  }

  async function handleResumeRun() {
    if (!runData) return;
    setRunAction("resume");
    setError("");
    try {
      await resumePublishRunV2(runData.run_id);
      await refreshRun(runData.run_id);
      if (batchAccountIds.length) setBatchState("running");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setRunAction("");
    }
  }

  async function handleRetryRun() {
    if (!runData || !runData.current_step) return;
    setRunAction("retry");
    setError("");
    try {
      await retryPublishRunStepV2(runData.run_id, runData.current_step);
      await refreshRun(runData.run_id);
      if (batchAccountIds.length) setBatchState("running");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setRunAction("");
    }
  }

  async function handleCancelRun() {
    if (!runData) return;
    setRunAction("cancel");
    setError("");
    try {
      await cancelPublishRunV2(runData.run_id);
      await refreshRun(runData.run_id);
      if (batchAccountIds.length) setBatchState("paused");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setRunAction("");
    }
  }

  async function handleSkipRun() {
    if (!runData) return;
    const shouldAdvance = batchHasNext();
    setRunAction("skip");
    setError("");
    try {
      await cancelPublishRunV2(runData.run_id);
      await refreshRun(runData.run_id);
      if (shouldAdvance) await startNextBatchItem();
      else if (batchAccountIds.length) setBatchState("paused");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
      if (batchAccountIds.length) setBatchState("paused");
    } finally {
      setRunAction("");
    }
  }

  async function runAccountAction(action: string, callback: () => Promise<PublishAccount>) {
    setAccountAction(action);
    setError("");
    try {
      await callback();
      await reloadAccounts();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setAccountAction("");
    }
  }

  async function submitAccount() {
    if (!addAccountPlatform || !addAccountName.trim()) return;
    setAccountAction("create");
    setError("");
    try {
      await createPublishAccount({
        platform: addAccountPlatform,
        display_name: addAccountName.trim(),
        make_default: makeDefault,
      });
      await reloadAccounts();
      setAddAccountPlatform(null);
      setAddAccountName("");
      setMakeDefault(false);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setAccountAction("");
    }
  }

  function openAddAccount(platform: string) {
    if (!isPublishAccountPlatform(platform)) return;
    setAddAccountPlatform(platform);
    setAddAccountName("");
    setMakeDefault(!accounts.some((account) => account.platform === platform));
  }

  return (
    <section className="publish-center-v2" aria-label="发布中心">
      <div className="publish-center-v2-heading">
        <div>
          <Typography.Text className="publish-center-v2-eyebrow" type="secondary">PUBLISH CENTER · V2</Typography.Text>
          <Typography.Title className="publish-center-v2-title" level={2}>发布中心</Typography.Title>
          <Typography.Paragraph className="publish-center-v2-description" type="secondary">
            统一查看真实 package、账号和发布运行状态；选择账号后可启动一次受控的发布前填充，最终发布始终由人工确认。
          </Typography.Paragraph>
        </div>
        <Tag className="publish-center-v2-boundary-tag" color="processing">人工确认边界</Tag>
      </div>

      {error || accountError ? (
        <>
          <Alert className="publish-center-v2-alert" type="warning" showIcon title="发布中心数据暂时不可用" description={error || accountError} />
          <PublishFallbackActions />
        </>
      ) : null}
      <div className="publish-center-v2-tabs" role="tablist" aria-label="发布中心分区">
        <button className="publish-center-v2-tab" type="button" role="tab" aria-selected={tab === "runs"} onClick={() => setTab("runs")}>发布运行</button>
        <button className="publish-center-v2-tab" type="button" role="tab" aria-selected={tab === "accounts"} onClick={() => setTab("accounts")}>发布账号</button>
      </div>

      {tab === "runs" ? (
        packageData || runData ? <PublishRunProjection packageData={packageData} runData={runData} accountName={runData ? accounts.find((account) => account.account_id === runData.account_id)?.display_name : undefined} events={events} runAction={runAction} batchState={batchState} batchPosition={batchPosition} batchTotal={batchAccountIds.length} batchHasNext={batchHasNext()} onOutcome={handleRunOutcome} onResume={handleResumeRun} onRetry={handleRetryRun} onCancel={handleCancelRun} onSkip={handleSkipRun} /> : <PublishRunEmptyState />
      ) : <PublishAccountSummary
        accounts={accounts}
        groups={accountSummary}
        duplicateIdentityIds={duplicateIdentityIds}
        platforms={platforms}
        loading={loading}
        accountAction={accountAction}
        onReload={() => void reloadAccounts()}
        onAddAccount={openAddAccount}
        onProbe={(account) => void runAccountAction(`probe:${account.account_id}`, () => probePublishAccount(account.account_id))}
        onDefault={(account) => void runAccountAction(`default:${account.account_id}`, () => setDefaultPublishAccount(account.account_id))}
        packageReady={Boolean(packageData)}
        startingAccountId={startingAccountId}
        onStartRun={(account) => void startRun(account)}
        selectedAccountIds={new Set(selectedAccountIds)}
        batchState={batchState}
        batchPosition={batchPosition}
        batchTotal={batchAccountIds.length}
        onToggleSelection={toggleAccountSelection}
        onStartBatch={() => void startBatch()}
      />}
      <Modal
        open={Boolean(addAccountPlatform)}
        title={`添加${addAccountPlatform ? platformLabel(addAccountPlatform) : ""}本机账号`}
        okText="创建账号"
        cancelText="取消"
        confirmLoading={accountAction === "create"}
        okButtonProps={{ disabled: !addAccountName.trim() }}
        onOk={() => void submitAccount()}
        onCancel={() => { setAddAccountPlatform(null); setAddAccountName(""); setMakeDefault(false); }}
      >
        <Space orientation="vertical" size="middle" style={{ width: "100%" }}>
          <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
            每个账号使用独立本机浏览器 Profile，登录态互不覆盖；创建后点击“检测登录”完成扫码或登录。
          </Typography.Paragraph>
          <Input aria-label="账号名称" autoFocus placeholder="例如：抖音门店主号" value={addAccountName} onChange={(event) => setAddAccountName(event.target.value)} maxLength={80} />
          <Checkbox checked={makeDefault} onChange={(event) => setMakeDefault(event.target.checked)}>设为该平台默认账号</Checkbox>
        </Space>
      </Modal>
    </section>
  );
}

function PublishFallbackActions() {
  function openLegacyWorkspace() {
    if (typeof window !== "undefined") window.location.hash = "#/ip";
  }

  return (
    <Card className="publish-center-v2-card publish-center-v2-fallback-actions" title="安全回退">
      <Typography.Paragraph type="secondary">
        发布适配器暂时不可用。你仍可以回到生产工作区复制文案、预览或下载已生成素材；这里不会暴露本地路径，也不会自动发布。
      </Typography.Paragraph>
      <Button className="publish-center-v2-action" onClick={openLegacyWorkspace}>返回工作区复制/下载素材</Button>
    </Card>
  );
}

function PublishRunProjection({ packageData, runData, accountName, events, runAction, batchState, batchPosition, batchTotal, batchHasNext, onOutcome, onResume, onRetry, onCancel, onSkip }: {
  packageData: PublishPackageV2 | null;
  runData: PublishRunV2 | null;
  accountName?: string;
  events: PublishRunEvent[];
  runAction: string;
  batchState: BatchPublishState;
  batchPosition: number;
  batchTotal: number;
  batchHasNext: boolean;
  onOutcome: (outcome: "published_by_user" | "not_published") => void;
  onResume: () => void;
  onRetry: () => void;
  onCancel: () => void;
  onSkip: () => void;
}) {
  const state = runData?.state || "package_ready";
  const meta = publishRunStateMeta(state);
  return (
    <Card className="publish-center-v2-card publish-center-v2-run-card" title="发布运行">
      <Space orientation="vertical" size="middle" style={{ width: "100%" }}>
        <Space wrap>
          <Tag color={meta.color}>{meta.label}</Tag>
          {batchState !== "idle" ? <Tag color={batchState === "paused" ? "warning" : batchState === "completed" ? "success" : "processing"}>批量队列 {batchPosition + 1}/{batchTotal}</Tag> : null}
          {runData ? <Tag>{platformLabel(runData.platform)} · {accountName || "本机账号"}</Tag> : null}
          {packageData ? <Tag>包 {packageData.package_id}</Tag> : null}
          {runData ? <Tag>运行 {runData.run_id}</Tag> : null}
        </Space>
        <Typography.Text type="secondary">
          {runData ? meta.description : "已接收应用产物 handoff，等待选择账号并创建发布运行。"}
        </Typography.Text>
        {runData?.error_code ? <Alert type="error" showIcon title={accountErrorLabel(runData.error_code)} description={runData.error_message || undefined} /> : null}
        {runData?.state === "waiting_for_human" ? (
          <Alert
            type="warning"
            showIcon
            title="平台页面已填充，等待人工发布"
            description="请在已打开的平台窗口检查预览并手动点击最终发布按钮，完成后回到这里确认结果。"
          />
        ) : null}
        {runData ? (
          <Space wrap>
            {runData.state === "waiting_for_human" ? (
              <>
                <Button type="primary" loading={runAction === "mark-published"} onClick={() => onOutcome("published_by_user")}>{batchHasNext ? "我已完成发布，下一平台" : "我已完成发布"}</Button>
                <Button loading={runAction === "mark-not-published"} onClick={() => onOutcome("not_published")}>未发布，取消运行</Button>
              </>
            ) : null}
            {runData.state === "waiting_for_login" ? <Button type="primary" loading={runAction === "resume"} onClick={onResume}>我已完成登录，继续</Button> : null}
            {runData.state === "needs_attention" && isRetryablePublishStep(runData.current_step) ? <Button type="primary" loading={runAction === "retry"} onClick={onRetry}>重试当前步骤</Button> : null}
            {runData.state === "needs_attention" && !isRetryablePublishStep(runData.current_step) ? <Typography.Text type="secondary">当前步骤不可自动重试，请停止运行后更换素材或账号。</Typography.Text> : null}
            {batchHasNext && ["waiting_for_login", "needs_attention", "failed"].includes(runData.state) ? <Button loading={runAction === "skip"} onClick={onSkip}>跳过当前，下一平台</Button> : null}
            {!["succeeded", "failed", "cancelled"].includes(runData.state) ? <Button loading={runAction === "cancel"} onClick={onCancel}>停止运行</Button> : null}
          </Space>
        ) : null}
        {events.length ? <div aria-label="发布事件时间线">{events.map((event) => <div key={`${event.run_id}-${event.event_seq}`}>{event.event_seq}. {event.event_type}</div>)}</div> : null}
      </Space>
    </Card>
  );
}

function PublishRunEmptyState() {
  return (
    <Card className="publish-center-v2-card publish-center-v2-run-card" title="发布运行">
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
  duplicateIdentityIds,
  platforms,
  loading,
  accountAction,
  onReload,
  onAddAccount,
  onProbe,
  onDefault,
  packageReady,
  startingAccountId,
  onStartRun,
  selectedAccountIds,
  batchState,
  batchPosition,
  batchTotal,
  onToggleSelection,
  onStartBatch,
}: {
  accounts: PublishAccount[];
  groups: Array<[string, PublishAccount[]]>;
  duplicateIdentityIds: Set<string>;
  platforms: PublishPlatformCapability[];
  loading: boolean;
  accountAction: string;
  onReload: () => void;
  onAddAccount: (platform: string) => void;
  onProbe: (account: PublishAccount) => void;
  onDefault: (account: PublishAccount) => void;
  packageReady: boolean;
  startingAccountId: string | null;
  onStartRun: (account: PublishAccount) => void;
  selectedAccountIds: Set<string>;
  batchState: BatchPublishState;
  batchPosition: number;
  batchTotal: number;
  onToggleSelection: (account: PublishAccount, checked: boolean) => void;
  onStartBatch: () => void;
}) {
  return (
    <Card
      className="publish-center-v2-card publish-center-v2-account-card"
      title="发布账号"
      extra={<Button className="publish-center-v2-action" onClick={onReload} loading={loading}>刷新状态</Button>}
    >
      {packageReady ? (
        <Alert
          className="publish-center-v2-package-ready"
          type="success"
          showIcon
          title="发布包已准备"
          description="可选择一个或多个已登录账号；批量队列会逐个填充草稿并暂停，平台最终发布按钮仍需你本人点击。"
        />
      ) : (
        <Alert
          className="publish-center-v2-package-pending"
          type="info"
          showIcon
          title="尚未接收发布包"
          description="请先在口播视频页完成合成，并点击去发布，系统会自动创建发布包并跳转到这里。"
        />
      )}
      {packageReady ? (
        <div className="publish-center-v2-batch-bar">
          <div>
            <strong>批量发布</strong>
            <Typography.Text type="secondary">
              选择多个平台/账号后按队列逐个处理，同一时间只打开一个平台窗口；每次填充完成都会暂停，最终发布按钮始终由你本人点击。
            </Typography.Text>
          </div>
          <Space wrap>
            <Tag color={batchState === "running" ? "processing" : batchState === "paused" ? "warning" : batchState === "completed" ? "success" : "default"}>
              {batchState === "running" ? `队列进行中 ${Math.max(batchPosition + 1, 0)}/${batchTotal}` : batchState === "paused" ? "队列已暂停" : batchState === "completed" ? "队列已完成" : `已选 ${selectedAccountIds.size} 个`}
            </Tag>
            <Button type="primary" className="publish-center-v2-action" disabled={!selectedAccountIds.size || batchState === "running"} onClick={onStartBatch}>
              {batchState === "paused" ? "继续批量发布" : "开始批量发布"}
            </Button>
          </Space>
        </div>
      ) : null}
      {!loading && !accounts.length ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无本机发布账号" /> : null}
      <div className="publish-center-v2-account-grid">
        {groups.map(([platform, platformAccounts]) => (
          <section key={platform} className="publish-center-v2-account-group" aria-label={`${platform}账号`}>
            <Space>
              <Typography.Title level={4}>{platformLabel(platform)}</Typography.Title>
              <Tag color="default">{platformAccounts.length} 个账号</Tag>
              {platforms.find((item) => item.platform === platform)?.release_state === "pilot" ? <Tag color="processing">试点</Tag> : null}
              <Button className="publish-center-v2-action" size="small" onClick={() => onAddAccount(platform)}>添加账号</Button>
            </Space>
            {!platformAccounts.length ? <Typography.Text type="secondary">尚未创建本机账号</Typography.Text> : null}
            {platformAccounts.map((account) => <AccountProjection key={account.account_id} account={account} duplicateIdentity={duplicateIdentityIds.has(account.account_id)} packageReady={packageReady} starting={startingAccountId === account.account_id} accountAction={accountAction} selected={selectedAccountIds.has(account.account_id)} onProbe={onProbe} onDefault={onDefault} onStartRun={onStartRun} onToggleSelection={onToggleSelection} />)}
          </section>
        ))}
      </div>
    </Card>
  );
}

function AccountProjection({ account, duplicateIdentity, packageReady, starting, accountAction, selected, onProbe, onDefault, onStartRun, onToggleSelection }: { account: PublishAccount; duplicateIdentity: boolean; packageReady: boolean; starting: boolean; accountAction: string; selected: boolean; onProbe: (account: PublishAccount) => void; onDefault: (account: PublishAccount) => void; onStartRun: (account: PublishAccount) => void; onToggleSelection: (account: PublishAccount, checked: boolean) => void }) {
  const status = account.login_state === "authenticated" ? "已登录" : account.login_state === "login_required" ? "需要登录" : account.login_state === "expired" ? "登录过期" : "未连接";
  const color = account.login_state === "authenticated" ? "success" : account.login_state === "degraded" || account.login_state === "locked" ? "warning" : "default";
  const canStart = packageReady && account.platform_release_state === "pilot" && account.login_state === "authenticated";
  const canSelect = canStart && account.enabled;
  return (
    <div className="publish-center-v2-account-row" data-account-id={account.account_id}>
      <Space wrap>
        {packageReady ? <Checkbox aria-label={`选择${account.display_name}`} checked={selected} disabled={!canSelect} onChange={(event) => onToggleSelection(account, event.target.checked)} /> : null}
        <strong>{account.display_name}</strong>
        <Tag color={color}>{status}</Tag>
        {account.is_default ? <Tag color="processing">默认</Tag> : null}
        {duplicateIdentity ? <Tag color="warning">远端身份重复</Tag> : null}
        <Tag color={account.platform_release_state === "pilot" ? "processing" : "default"}>{account.platform_release_state === "pilot" ? "试点" : "未验证"}</Tag>
      </Space>
      {account.last_error_code ? <Typography.Text type="secondary">诊断：{accountErrorLabel(account.last_error_code)}</Typography.Text> : null}
      <Space wrap>
        <Button className="publish-center-v2-action" size="small" loading={accountAction === `probe:${account.account_id}`} onClick={() => onProbe(account)}>检测登录</Button>
        {!account.is_default && account.enabled ? <Button className="publish-center-v2-action" size="small" loading={accountAction === `default:${account.account_id}`} onClick={() => onDefault(account)}>设为默认</Button> : null}
      </Space>
      {canStart ? (
            <Button className="publish-center-v2-action" size="small" type="primary" loading={starting} onClick={() => onStartRun(account)}>开始填充草稿</Button>
      ) : packageReady && account.platform_release_state === "pilot" && account.login_state !== "authenticated" ? (
            <Typography.Text type="secondary">请先检测登录并完成扫码</Typography.Text>
      ) : packageReady ? (
        <Typography.Text type="secondary">待独立 live gate；当前仅支持复制素材回退</Typography.Text>
      ) : null}
    </div>
  );
}

function platformLabel(platform: string) {
  return { douyin: "抖音", video_channel: "视频号", shipinhao: "视频号", kuaishou: "快手", xiaohongshu: "小红书" }[platform] || platform;
}

function accountErrorLabel(code: string) {
  return {
    LOGIN_REQUIRED: "需要扫码或登录",
    LOGIN_EXPIRED: "登录已过期，请重新检测",
    PROFILE_LOCKED: "账号窗口正在使用",
    LOGIN_PROBE_FAILED: "登录状态检测失败，请重试",
    IDENTITY_CHANGED: "登录账号发生变化，请重新确认",
  }[code] || code;
}

function isRetryablePublishStep(step: string | null) {
  return retryablePublishSteps.has(step || "");
}

function publishRunStateMeta(state: string) {
  return {
    package_ready: { label: "发布包已准备", color: "processing" as const, description: "已接收应用产物 handoff，等待选择账号并创建发布运行。" },
    queued: { label: "排队中", color: "processing" as const, description: "发布运行已创建，正在等待执行。" },
    running: { label: "填充中", color: "processing" as const, description: "正在打开平台页面并填充发布素材，系统不会点击最终发布按钮。" },
    waiting_for_login: { label: "等待登录", color: "warning" as const, description: "账号尚未完成登录，请在账号页检测登录或完成扫码后继续。" },
    waiting_for_human: { label: "等待人工发布", color: "warning" as const, description: "素材已填充到平台页面，最终发布仍需人工确认。" },
    needs_attention: { label: "需要处理", color: "error" as const, description: "运行遇到可恢复问题，请查看诊断后重试或停止。" },
    succeeded: { label: "已完成", color: "success" as const, description: "已记录人工发布完成。" },
    failed: { label: "失败", color: "error" as const, description: "运行失败，请查看诊断信息。" },
    cancelled: { label: "已取消", color: "default" as const, description: "本次发布运行已取消，未执行最终发布。" },
  }[state] || { label: state, color: "default" as const, description: "发布运行状态已更新。" };
}

function isPublishAccountPlatform(platform: string): platform is PublishAccountPlatform {
  return ["douyin", "video_channel", "kuaishou", "xiaohongshu"].includes(platform);
}
