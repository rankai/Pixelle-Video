import {
  AlertCircle,
  CheckCircle2,
  Clapperboard,
  Home,
  Images,
  Loader2,
  Mic2,
  MonitorStop,
  Package,
  Settings,
  Share2,
  UserSquare2,
  Video,
} from "lucide-react";
import {
  Alert,
  Button,
  Card,
  ConfigProvider,
  Divider,
  Layout,
  Menu,
  Progress,
  Segmented,
  Space,
  Steps,
  Switch,
  Tabs,
  Tag,
  Typography,
} from "antd";
import type { MenuProps } from "antd";
import { useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";
import {
  artifactBlobUrl,
  assetBlobUrl,
  cancelTask,
  checkDesktopConfig,
  createBrandKit,
  createSession,
  deleteBrandKit,
  deletePortraitAsset,
  deleteVideoAsset,
  deleteVoiceAsset,
  downloadArtifact,
  getDesktopConfig,
  getDiagnostics,
  getSession,
  getTask,
  listBgm,
  listBrandKits,
  listIpPresetAssets,
  listIpTemplateAssets,
  listPortraitAssets,
  listTasks,
  listVideoAssets,
  listVoiceAssets,
  prepareDouyinPublish,
  PortraitAsset,
  BrandKit,
  ConfigCheckResult,
  DesktopConfig,
  DesktopDiagnostics,
  DiagnosticCheck,
  IpBroadcastState,
  IpPresetAsset,
  IpTemplateAsset,
  retryTask,
  runStep,
  saveDesktopConfig,
  synthesizeTtsPreview,
  TaskInfo,
  updateBrandKit,
  updateSessionConfig,
  uploadPortraitAsset,
  uploadVideoAsset,
  uploadVoiceAsset,
  BgmAsset,
  PublishResult,
  VideoAsset,
  VoiceAsset,
} from "./api";
import { createAntdTheme, readStoredThemeSkin, themeSkins, type ThemeSkin } from "./theme";

type View = "home" | "ip" | "assets" | "publish_accounts" | "tasks" | "config" | "diagnostics";
type AssetTab = "voices" | "portraits" | "templates" | "videos" | "brands";
type NavKey =
  | "home"
  | "ip"
  | "portraits"
  | "voices"
  | "templates"
  | "videos"
  | "publish_accounts"
  | "tasks"
  | "config";

type AssetState = {
  voices: VoiceAsset[];
  portraits: PortraitAsset[];
  templates: IpTemplateAsset[];
  presets: IpPresetAsset[];
  videos: VideoAsset[];
  brands: BrandKit[];
  bgm: BgmAsset[];
};

type ReadinessItem = {
  label: string;
  description: string;
  ready: boolean;
  action: string;
  onClick: () => void;
  recommended?: boolean;
};

type StorySegment = {
  segment_id: string;
  index: number;
  text: string;
};

type VisualGroup = {
  group_id: string;
  segment_ids: string[];
  visual_type: "digital_human" | "ai_video" | "uploaded_video";
  prompt: string;
  uploaded_video_path: string;
  video_asset_id: string;
  status: string;
};

type VideoPlanSegment = {
  segment_id: string;
  index: number;
  text: string;
  visual_type: "digital_human" | "ai_video" | "uploaded_video";
  label: string;
  asset_keywords: string[];
  prompt: string;
  reason: string;
};

type VideoPlan = {
  goal: string;
  status: string;
  summary: string;
  visual_strategy: string;
  segments: VideoPlanSegment[];
};

type PortraitMediaType = PortraitAsset["media_type"];

type AssetPreview =
  | { kind: "audio"; title: string; src: string }
  | { kind: "image"; title: string; src: string }
  | { kind: "video"; title: string; src: string };

type PendingDelete = {
  title: string;
  name: string;
  description: string;
  confirmLabel: string;
  confirm: () => Promise<void>;
};

const stepTitles = [
  "搞定文案",
  "配音制作",
  "数字人出镜",
  "一键成片",
  "发布素材",
];

const sourceModeLabels: Record<string, string> = {
  video_extract: "视频提取",
  paste: "粘贴脚本",
  industry_persona: "行业+人设",
  ip_learning: "IP学习",
};

const appReleaseInfo = {
  version: "桌面版 v1",
  date: "2026-05-29",
  status: "React 工作台预览版",
  notes: [
    "新增首页工作台、配置状态检查和 5 步短视频生产入口。",
    "素材资产独立维护，流程内支持快速添加音色、形象和视频素材。",
    "补齐云端声音生成方式和参数配置。",
    "优化画面模板、画面规划和发布素材包的交付体验。",
  ],
};

const ttsWorkflowOptions = [
  {
    value: "runninghub/tts_index_custom.json",
    label: "老板声音克隆（推荐）",
    kind: "index",
    supportsReference: true,
    supportsAdvanced: true,
  },
  {
    value: "runninghub/tts_index2.json",
    label: "老板声音克隆 2",
    kind: "index",
    supportsReference: true,
    supportsAdvanced: false,
  },
  {
    value: "runninghub/tts_edge.json",
    label: "云端默认配音",
    kind: "edge",
    supportsReference: false,
    supportsAdvanced: true,
  },
  {
    value: "runninghub/tts_spark.json",
    label: "情绪配音",
    kind: "spark",
    supportsReference: false,
    supportsAdvanced: true,
  },
] as const;

const digitalHumanWorkflowOptions: Array<{
  value: string;
  label: string;
  supportedMediaTypes: PortraitMediaType[];
  supportsPrompt: boolean;
  defaultWidth?: number;
  defaultHeight?: number;
}> = [
  {
    value: "workflows/runninghub/digital_combination.json",
    label: "标准图片出镜",
    supportedMediaTypes: ["image"],
    supportsPrompt: false,
    defaultWidth: 720,
    defaultHeight: 1280,
  },
  {
    value: "workflows/runninghub/digital_talk_image_prompt.json",
    label: "可控图片出镜",
    supportedMediaTypes: ["image"],
    supportsPrompt: true,
    defaultWidth: 720,
    defaultHeight: 1280,
  },
  {
    value: "workflows/runninghub/digital_talk_fast_720p.json",
    label: "快速可控出镜",
    supportedMediaTypes: ["image"],
    supportsPrompt: true,
    defaultWidth: 720,
    defaultHeight: 1280,
  },
  {
    value: "workflows/runninghub/digital_lip_sync_video.json",
    label: "真人视频改口型",
    supportedMediaTypes: ["video"],
    supportsPrompt: false,
    defaultWidth: 480,
    defaultHeight: 832,
  },
];

const edgeVoiceOptions = [
  { value: "zh-CN-YunjianNeural", label: "中文 · 云健（男声）" },
  { value: "zh-CN-XiaoxiaoNeural", label: "中文 · 晓晓（女声）" },
  { value: "zh-CN-YunxiNeural", label: "中文 · 云希（男声）" },
  { value: "zh-CN-XiaoyiNeural", label: "中文 · 晓伊（女声）" },
  { value: "zh-CN-YunyangNeural", label: "中文 · 云扬（男声）" },
];

const comfyEdgeVoiceOptions = [
  { value: "[Chinese] zh-CN Yunjian", label: "中文 · Yunjian" },
  { value: "[Chinese] zh-CN Xiaoxiao", label: "中文 · Xiaoxiao" },
  { value: "[Chinese] zh-CN Yunxi", label: "中文 · Yunxi" },
  { value: "[Chinese] zh-CN Xiaoyi", label: "中文 · Xiaoyi" },
  { value: "[Chinese] zh-CN Yunyang", label: "中文 · Yunyang" },
];

const toneOptions = [
  { value: "low", label: "低" },
  { value: "moderate", label: "标准" },
  { value: "high", label: "高" },
];

const emptyAssets: AssetState = {
  voices: [],
  portraits: [],
  templates: [],
  presets: [],
  videos: [],
  brands: [],
  bgm: [],
};

const navItems: MenuProps["items"] = [
  { key: "home", icon: <Home size={16} />, label: "首页" },
  { key: "ip", icon: <Video size={16} />, label: "短视频生产" },
  { type: "divider" },
  { key: "portraits", icon: <UserSquare2 size={16} />, label: "数字人库" },
  { key: "voices", icon: <Mic2 size={16} />, label: "音色库" },
  { key: "templates", icon: <Images size={16} />, label: "画面模板" },
  { key: "videos", icon: <Clapperboard size={16} />, label: "视频素材" },
  { type: "divider" },
  { key: "publish_accounts", icon: <Share2 size={16} />, label: "发布账号" },
  { key: "tasks", icon: <CheckCircle2 size={16} />, label: "任务记录" },
  { key: "config", icon: <Settings size={16} />, label: "配置" },
];

function autoAdvanceStepAfter(stepKey?: string) {
  return (
    {
      source: 1,
      postproduction: 5,
    }[stepKey || ""] || 0
  );
}

export function App() {
  const [view, setView] = useState<View>("home");
  const [assetTab, setAssetTab] = useState<AssetTab>("voices");
  const [themeSkin, setThemeSkinState] = useState<ThemeSkin>(() => readStoredThemeSkin());
  const [assets, setAssets] = useState<AssetState>(emptyAssets);
  const [session, setSession] = useState<IpBroadcastState | null>(null);
  const [activeStep, setActiveStep] = useState(1);
  const [task, setTask] = useState<TaskInfo | null>(null);
  const [busy, setBusy] = useState(false);
  const [configSaving, setConfigSaving] = useState(false);
  const [appError, setAppError] = useState("");
  const [appRecovering, setAppRecovering] = useState(false);
  const [workflowError, setWorkflowError] = useState("");
  const [storyboardOpen, setStoryboardOpen] = useState(false);

  useEffect(() => {
    recoverAppState().catch((err) => setAppError(formatUiError(err)));
  }, []);

  function setThemeSkin(skin: ThemeSkin) {
    window.localStorage.setItem("pixelle_desktop_theme_skin", skin);
    setThemeSkinState(skin);
  }

  async function restoreOrCreateSession() {
    const storedSessionId = window.localStorage.getItem("pixelle_ipb_session_id");
    if (storedSessionId) {
      try {
        const restored = await getSession(storedSessionId);
        setSession(restored);
        setActiveStep(1);
        return;
      } catch {
        window.localStorage.removeItem("pixelle_ipb_session_id");
      }
    }
    const created = await createSession();
    window.localStorage.setItem("pixelle_ipb_session_id", created.session_id);
    setSession(created);
    setActiveStep(1);
  }

  async function recoverAppState() {
    setAppRecovering(true);
    try {
      await restoreOrCreateSession();
      await reloadAssets();
      setAppError("");
    } catch (err) {
      setAppError(formatUiError(err));
      throw err;
    } finally {
      setAppRecovering(false);
    }
  }

  useEffect(() => {
    if (!task || !session) return;
    if (!["pending", "running"].includes(task.status)) return;
    const timer = window.setInterval(async () => {
      try {
        const latestTask = await getTask(task.task_id);
        setTask(latestTask);
        if (["completed", "failed", "cancelled"].includes(latestTask.status)) {
          setBusy(false);
          const fresh = await getSession(session.session_id);
          setSession(fresh);
          if (latestTask.status === "completed") {
            const nextStep = autoAdvanceStepAfter(latestTask.step_key || task.step_key);
            if (nextStep) setActiveStep(nextStep);
          }
          if (latestTask.status === "failed") setWorkflowError(latestTask.error || "任务执行失败");
        }
      } catch (err) {
        setBusy(false);
        setWorkflowError(formatUiError(err));
      }
    }, 1500);
    return () => window.clearInterval(timer);
  }, [activeStep, session, task]);

  const completedStepCount = useMemo(() => {
    if (!session) return 0;
    return completedProductionSteps(session);
  }, [session]);

  const completedPercent = useMemo(() => {
    if (!session) return 0;
    return Math.round((completedStepCount / stepTitles.length) * 100);
  }, [completedStepCount, session]);

  async function reloadAssets() {
    const [voices, portraits, templates, presets, videos, brands, bgm] = await Promise.all([
      listVoiceAssets(),
      listPortraitAssets(),
      listIpTemplateAssets(),
      listIpPresetAssets(),
      listVideoAssets(),
      listBrandKits(),
      listBgm(),
    ]);
    setAssets({
      voices: voices.items,
      portraits: portraits.items,
      templates: templates.items,
      presets: presets.items,
      videos: videos.items,
      brands: brands.items,
      bgm: bgm.bgm_files,
    });
  }

  async function execute(stepKey: string) {
    if (!session || configSaving) return;
    setBusy(true);
    setWorkflowError("");
    setTask(null);
    try {
      const result = await runStep(session.session_id, stepKey);
      setTask({ task_id: result.task_id, status: "pending", step_key: stepKey });
    } catch (err) {
      setBusy(false);
      setWorkflowError(formatUiError(err));
    }
  }

  async function stopCurrentTask() {
    if (!task) return;
    try {
      await cancelTask(task.task_id);
      setBusy(false);
      setTask({ ...task, status: "cancelled" });
    } catch (err) {
      setWorkflowError(formatUiError(err));
    }
  }

  async function patch(values: Record<string, unknown>) {
    if (!session) return;
    const currentSessionId = session.session_id;
    setConfigSaving(true);
    setSession((current) =>
      current && current.session_id === currentSessionId
        ? { ...current, state: { ...current.state, ...values } }
        : current,
    );
    try {
      const updated = await updateSessionConfig(currentSessionId, values);
      setSession(updated);
    } finally {
      setConfigSaving(false);
    }
  }

  function openAssetTab(tab: AssetTab) {
    setAssetTab(tab);
    setView("assets");
  }

  function openView(nextView: View) {
    if (nextView === "ip") {
      setActiveStep(1);
    }
    setView(nextView);
  }

  function openNavItem(key: NavKey) {
    if (key === "portraits") return openAssetTab("portraits");
    if (key === "voices") return openAssetTab("voices");
    if (key === "templates") return openAssetTab("templates");
    if (key === "videos") return openAssetTab("videos");
    if (key === "publish_accounts") {
      setView("publish_accounts");
      return;
    }
    openView(key);
  }

  function selectedNavKey(): string {
    if (view === "assets") return assetTab;
    return view;
  }

  async function startNewIpSession() {
    setBusy(false);
    setTask(null);
    setWorkflowError("");
    const created = await createSession();
    window.localStorage.setItem("pixelle_ipb_session_id", created.session_id);
    setSession(created);
    setActiveStep(1);
    setView("ip");
  }

  async function downloadFinalVideo() {
    if (!session) return;
    try {
      await downloadArtifact(session.session_id, "final_video");
    } catch (err) {
      setWorkflowError(formatUiError(err));
    }
  }

  return (
    <ConfigProvider theme={createAntdTheme(themeSkin)}>
      <Layout className="app-shell" data-theme={themeSkin}>
        <Layout.Sider className="app-sidebar" width={224}>
          <div className="brand-mark">
            <div className="brand-logo">PV</div>
            <div>
              <strong>Pixelle Video</strong>
              <span>老板 IP 口播</span>
            </div>
          </div>
          <Menu
            className="side-menu"
            mode="inline"
            selectedKeys={[selectedNavKey()]}
            items={navItems}
            onClick={(item) => openNavItem(item.key as NavKey)}
          />
        </Layout.Sider>
        <Layout>
          <Layout.Header className="app-header">
            <div>
              <Typography.Title level={3}>
                {view === "ip" ? "短视频生产" : "老板 IP 口播平台"}
              </Typography.Title>
              <Typography.Text type="secondary">
                {view === "ip"
                  ? "按步骤完成文案、配音、数字人、成片和发布。"
                  : "为门店老板准备的短视频生产与发布工具。"}
              </Typography.Text>
            </div>
            <Tag color="processing">{themeSkins[themeSkin].label}</Tag>
          </Layout.Header>
          <Layout.Content className="app-content">
            {appError ? (
              <Alert
                className="global-alert"
                type="error"
                showIcon
                message={appError}
                action={
                  <Space>
                    <Button size="small" loading={appRecovering} onClick={() => recoverAppState().catch(() => {})}>
                      重试连接
                    </Button>
                    <Button size="small" type="text" onClick={() => setAppError("")}>
                      关闭
                    </Button>
                  </Space>
                }
                icon={<AlertCircle size={16} />}
              />
            ) : null}

            {view === "ip" && session ? (
              <section className="workspace">
                <ProductionConsole
                  session={session}
                  task={task}
                  busy={busy || configSaving}
                  completedPercent={completedPercent}
                  completedStepCount={completedStepCount}
                  onContinue={() => execute(session.next_action.key)}
                />

                <StepBar
                  session={session}
                  activeStep={activeStep}
                  onSelect={(step) => setActiveStep(step)}
                />

                <section className="step-workspace">
                  <StepPanel
                    step={activeStep}
                    session={session}
                    assets={assets}
                    patch={patch}
                    execute={execute}
                    busy={busy || configSaving}
                    task={task}
                    error={workflowError}
                    onStop={stopCurrentTask}
                    openStoryboard={() => setStoryboardOpen(true)}
                    openAssetTab={openAssetTab}
                    reloadAssets={reloadAssets}
                    downloadFinalVideo={downloadFinalVideo}
                    goToStep={setActiveStep}
                  />
                </section>

                {storyboardOpen ? (
                  <StoryboardModal
                    session={session}
                    videos={assets.videos}
                    patch={patch}
                    reloadAssets={reloadAssets}
                    openAssetTab={openAssetTab}
                    onClose={() => setStoryboardOpen(false)}
                  />
                ) : null}
              </section>
            ) : null}

      {view === "home" ? (
        <HomeView
          assets={assets}
          onStart={() => startNewIpSession().catch((err) => setAppError(formatUiError(err)))}
          onAssets={() => setView("assets")}
          onAssetTab={openAssetTab}
          onConfig={() => setView("config")}
          onDiagnostics={() => setView("diagnostics")}
          onTasks={() => setView("tasks")}
        />
      ) : null}

      {view === "assets" ? (
        <AssetsView
          assets={assets}
          activeTab={assetTab}
          setActiveTab={setAssetTab}
          reload={reloadAssets}
        />
      ) : null}
      {view === "publish_accounts" ? <PublishAccountsView /> : null}
      {view === "tasks" ? <TaskCenterView /> : null}
      {view === "config" ? <ConfigView themeSkin={themeSkin} setThemeSkin={setThemeSkin} /> : null}
      {view === "diagnostics" ? <DiagnosticsView /> : null}
          </Layout.Content>
        </Layout>
      </Layout>
    </ConfigProvider>
  );
}

function HomeView({
  assets,
  onStart,
  onAssets,
  onAssetTab,
  onConfig,
  onDiagnostics,
  onTasks,
}: {
  assets: AssetState;
  onStart: () => void;
  onAssets: () => void;
  onAssetTab: (tab: AssetTab) => void;
  onConfig: () => void;
  onDiagnostics: () => void;
  onTasks: () => void;
}) {
  const [config, setConfig] = useState<DesktopConfig | null>(null);
  const [tasks, setTasks] = useState<TaskInfo[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([getDesktopConfig(), listTasks("", 100)])
      .then(([nextConfig, nextTasks]) => {
        setConfig(nextConfig);
        setTasks(nextTasks);
      })
      .catch((err) => setError(String(err)));
  }, []);

  const llmReady = hasConfiguredKey(config?.llm.api_key);
  const runninghubReady = hasConfiguredKey(config?.runninghub.api_key);
  const configReady = llmReady && runninghubReady;
  const productionReady =
    configReady &&
    assets.voices.length > 0 &&
    assets.portraits.length > 0 &&
    assets.templates.length > 0 &&
    !error;
  const assetCount =
    assets.voices.length + assets.portraits.length + assets.templates.length + assets.videos.length;
  const taskStats = buildTaskStats(tasks);
  const latestTask = tasks[0];
  const recentTasks = tasks.slice(0, 4);
  const requiredReadinessItems: ReadinessItem[] = [
    { label: "账号配置", description: "用于生成文案和发布素材", ready: llmReady, action: "去配置", onClick: onConfig },
    { label: "云端生成能力", description: "用于生成配音和数字人", ready: runninghubReady, action: "去配置", onClick: onConfig },
    {
      label: "商家口播声音",
      description: "用于生成商家口播声音",
      ready: assets.voices.length > 0,
      action: "去音色库",
      onClick: () => onAssetTab("voices"),
    },
    {
      label: "出镜数字人形象",
      description: "用于数字人口播画面",
      ready: assets.portraits.length > 0,
      action: "去形象库",
      onClick: () => onAssetTab("portraits"),
    },
    {
      label: "视频画面模板",
      description: "用于控制标题和字幕样式",
      ready: assets.templates.length > 0,
      action: "去模板库",
      onClick: () => onAssetTab("templates"),
    },
    { label: "系统诊断", description: "检查本机依赖和输出目录", ready: !error, action: "查看诊断", onClick: onDiagnostics },
  ];
  const recommendedReadinessItems: ReadinessItem[] = [
    {
      label: "视频素材",
      description: "推荐补充门店环境和产品画面，不影响生成",
      ready: assets.videos.length > 0,
      action: "去视频素材库",
      onClick: () => onAssetTab("videos"),
      recommended: true,
    },
  ];
  const readinessItems = [...requiredReadinessItems, ...recommendedReadinessItems];

  return (
    <section className="home-page">
      <Card className="home-workbench-hero" variant="borderless">
        <div className="home-workbench-copy">
          <span className="home-hero-eyebrow">老板口播 · 门店短视频 · 本地生活</span>
          <Typography.Title>
            老板 IP
            <br />
            <span>口播平台</span>
          </Typography.Title>
          <Typography.Paragraph>
            给老板、门店和本地生活团队用的口播生产台。打开首页先看系统是否准备好，再继续任务或新建一条可发布的视频。
          </Typography.Paragraph>
        </div>
        <SystemStatusPanel
          items={readinessItems}
          requiredItems={requiredReadinessItems}
          ready={productionReady}
          onConfig={onConfig}
        />
      </Card>

      <div className="home-metrics">
        <MetricCard label="全部任务" value={taskStats.total} />
        <MetricCard label="成功任务" value={taskStats.completed} tone="success" />
        <MetricCard label="失败任务" value={taskStats.failed} tone="danger" />
        <MetricCard label="素材资产" value={assetCount} />
        <MetricCard label="音色" value={assets.voices.length} />
        <MetricCard label="数字人形象" value={assets.portraits.length} />
        <MetricCard label="视频素材" value={assets.videos.length} />
        <MetricCard label="画面模板" value={assets.templates.length} />
      </div>

      <div className="home-workbench-grid">
        <div className="home-left-stack">
          <QuickAccessCard ready={productionReady} onAssets={onAssets} onConfig={onConfig} />
        </div>
        <div className="home-right-stack">
          <CurrentTaskCard
            task={latestTask}
            ready={productionReady}
            onStart={onStart}
            onConfig={onConfig}
            onTasks={onTasks}
          />
          <RecentTasksCard tasks={recentTasks} onTasks={onTasks} />
        </div>
      </div>

      <HomeReleaseInfo />
    </section>
  );
}

function SystemStatusPanel({
  items,
  requiredItems,
  ready,
  onConfig,
}: {
  items: ReadinessItem[];
  requiredItems: ReadinessItem[];
  ready: boolean;
  onConfig: () => void;
}) {
  const missing = requiredItems.filter((item) => !item.ready);
  const recommendedMissing = items.filter((item) => item.recommended && !item.ready);
  const displayItems = missing.length ? [...missing, ...recommendedMissing] : items;
  const visibleMissingItems = displayItems.slice(0, 4);
  const primaryAction = missing[0];
  return (
    <div className="home-system-status" aria-label="系统状态">
      <div className="system-status-head">
        <span>系统状态</span>
        <Tag color={ready ? "success" : "warning"}>{ready ? "可以生成" : `${missing.length} 项待处理`}</Tag>
      </div>
      <div className="system-status-list">
        {visibleMissingItems.map((item) => (
          <div key={item.label} className="system-status-item">
            <span className={item.ready ? "ready-dot success" : "ready-dot warning"} />
            <div>
              <strong>{item.label}</strong>
              <small>{item.description}</small>
            </div>
            <em>{item.ready ? "已完成" : item.recommended ? "推荐补充" : "待设置"}</em>
            {!item.ready ? (
              <button type="button" className="system-status-action" onClick={item.onClick}>
                {item.action}
              </button>
            ) : null}
          </div>
        ))}
        {displayItems.length > visibleMissingItems.length ? (
          <button
            type="button"
            className="system-status-more"
            onClick={displayItems[visibleMissingItems.length]?.onClick || onConfig}
          >
            还有 {displayItems.length - visibleMissingItems.length} 项待处理
          </button>
        ) : null}
      </div>
      {!ready ? (
        <Button type="primary" onClick={primaryAction?.onClick || onConfig}>
          {primaryAction ? `先补齐：${primaryAction.label}` : "补齐配置"}
        </Button>
      ) : null}
    </div>
  );
}

function QuickAccessCard({
  ready,
  onAssets,
  onConfig,
}: {
  ready: boolean;
  onAssets: () => void;
  onConfig: () => void;
}) {
  return (
    <Card className="home-work-card quick-access-card" variant="borderless">
      <div className="work-card-title compact">
        <strong>常用准备</strong>
        <Tag color={ready ? "success" : "warning"}>{ready ? "基础完成" : "建议先检查"}</Tag>
      </div>
      <p>管理声音、数字人形象、画面模板和系统配置。素材准备好后，生成视频会更顺。</p>
      <div className="quick-access-actions">
        <button onClick={onAssets}>
          <Package size={20} />
          <strong>管理声音/形象/模板</strong>
          <span>维护后可直接在流程中选择</span>
        </button>
        <button onClick={onConfig}>
          <Settings size={20} />
          <strong>系统配置</strong>
          <span>检查 API Key、输出目录和外观设置</span>
        </button>
      </div>
    </Card>
  );
}

function CurrentTaskCard({
  task,
  ready,
  onStart,
  onConfig,
  onTasks,
}: {
  task?: TaskInfo;
  ready: boolean;
  onStart: () => void;
  onConfig: () => void;
  onTasks: () => void;
}) {
  return (
    <Card className="home-work-card current-task-card" variant="borderless">
      <div className="work-card-title">
        <div>
          <Tag color="processing">当前任务</Tag>
          <strong>{task ? task.display_name || task.flow_name || "未命名口播任务" : "暂无进行中的任务"}</strong>
        </div>
        {task ? <Tag color={taskStatusColor(task.status)}>{taskStatusLabel(task.status)}</Tag> : null}
      </div>
      {task ? (
        <>
          <p>{task.progress?.message || task.step_key || "可进入任务记录查看详情。"}</p>
          <Progress
            percent={Math.round(task.progress?.percentage || (task.status === "completed" ? 100 : 0))}
            status={task.status === "failed" ? "exception" : undefined}
          />
          {task.error ? <Alert type="error" showIcon message={task.error} /> : null}
        </>
      ) : (
        <p>还没有任务。可以从素材链接、粘贴文案、行业人设或 IP 学习开始创建第一条口播视频。</p>
      )}
      <Space wrap>
        <Button type="primary" onClick={ready ? onStart : onConfig}>
          {task ? "继续生产" : ready ? "新建口播视频" : "先完成配置"}
        </Button>
        <Button onClick={onTasks}>查看任务记录</Button>
      </Space>
    </Card>
  );
}

function RecentTasksCard({
  tasks,
  onTasks,
}: {
  tasks: TaskInfo[];
  onTasks: () => void;
}) {
  return (
    <Card className="home-work-card recent-task-card" variant="borderless">
      <div className="work-card-title compact">
        <strong>最近项目</strong>
        <Button size="small" onClick={onTasks}>全部任务</Button>
      </div>
      {tasks.length ? (
        <div className="recent-task-list">
          {tasks.map((task) => (
            <div key={task.task_id} className="recent-task-row">
              <div>
                <strong>{task.display_name || task.flow_name || "口播任务"}</strong>
                <span>{task.progress?.message || task.step_key || task.task_id}</span>
              </div>
              <Tag color={taskStatusColor(task.status)}>{taskStatusLabel(task.status)}</Tag>
            </div>
          ))}
        </div>
      ) : (
        <div className="empty-state compact-empty">暂无最近项目。</div>
      )}
    </Card>
  );
}

function HomeReleaseInfo() {
  return (
    <section className="home-release-strip" aria-label="当前版本和更新说明">
      <div>
        <span>当前版本</span>
        <strong>{appReleaseInfo.version}</strong>
        <em>{appReleaseInfo.status} · {appReleaseInfo.date}</em>
      </div>
      <details>
        <summary>更新说明</summary>
        <ul>
          {appReleaseInfo.notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      </details>
    </section>
  );
}

function MetricCard({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: number;
  tone?: "neutral" | "success" | "danger";
}) {
  return (
    <Card className={`metric-card ${tone}`} variant="borderless">
      <span>{label}</span>
      <strong>{value}</strong>
    </Card>
  );
}

function hasConfiguredKey(value?: string) {
  const key = (value || "").trim();
  return Boolean(key && key !== "请输入 API Key" && !key.toLowerCase().includes("your-api-key"));
}

function buildTaskStats(tasks: TaskInfo[]) {
  return {
    total: tasks.length,
    completed: tasks.filter((task) => task.status === "completed").length,
    failed: tasks.filter((task) => task.status === "failed").length,
  };
}

function formatUiError(err: unknown) {
  const message = err instanceof Error ? err.message : String(err);
  return message.replace(/^Error:\s*/, "");
}

function taskStatusColor(status: TaskInfo["status"]) {
  const colors: Record<TaskInfo["status"], string> = {
    pending: "default",
    running: "processing",
    completed: "success",
    failed: "error",
    cancelled: "default",
  };
  return colors[status] || "default";
}

function ProductionConsole({
  session,
  task,
  busy,
  completedPercent,
  completedStepCount,
  onContinue,
}: {
  session: IpBroadcastState;
  task: TaskInfo | null;
  busy: boolean;
  completedPercent: number;
  completedStepCount: number;
  onContinue: () => void;
}) {
  const taskStatus = task
    ? `当前任务：${taskStatusLabel(task.status)} · ${task.task_id.slice(0, 8)}`
    : "当前无任务";
  return (
    <section className="console" aria-label="生产状态">
      <div className="console-main">
        <Space align="center" size={10}>
          <strong>生产状态</strong>
          <Tag color={completedStepCount >= stepTitles.length ? "success" : "processing"}>
            {completedStepCount}/{stepTitles.length} 已完成
          </Tag>
        </Space>
        <span className="console-description">{session.next_action.description}</span>
        <Progress percent={completedPercent} showInfo={false} />
        <span className="console-missing">
          {session.missing_requirements.length
            ? `缺失项：${session.missing_requirements.join(" · ")}`
            : "关键素材已准备好。"}
        </span>
      </div>
      <div className="task-panel">
        <Tag>{taskStatus}</Tag>
        <Space>
          <Button
            type="primary"
            disabled={busy || session.next_action.disabled}
            onClick={onContinue}
          >
            自动继续生产
          </Button>
          <Typography.Text type="secondary">下一步：{session.next_action.label}</Typography.Text>
        </Space>
      </div>
    </section>
  );
}

function StepBar({
  session,
  activeStep,
  onSelect,
}: {
  session: IpBroadcastState;
  activeStep: number;
  onSelect: (step: number) => void;
}) {
  return (
    <Card className="stepbar-card" variant="borderless">
      <Steps
        type="navigation"
        current={activeStep - 1}
        onChange={(index) => onSelect(index + 1)}
        items={stepTitles.map((title, index) => {
          const step = index + 1;
          const status = uiStepStatus(session, step);
          return {
            title,
            status: stepAntdStatus(status),
          };
        })}
      />
    </Card>
  );
}

function StepPanel({
  step,
  session,
  assets,
  patch,
  execute,
  busy,
  task,
  error,
  onStop,
  openStoryboard,
  openAssetTab,
  reloadAssets,
  downloadFinalVideo,
  goToStep,
}: {
  step: number;
  session: IpBroadcastState;
  assets: AssetState;
  patch: (values: Record<string, unknown>) => Promise<void>;
  execute: (stepKey: string) => Promise<void>;
  busy: boolean;
  task: TaskInfo | null;
  error: string;
  onStop: () => void;
  openStoryboard: () => void;
  openAssetTab: (tab: AssetTab) => void;
  reloadAssets: () => Promise<void>;
  downloadFinalVideo: () => Promise<void>;
  goToStep: (step: number) => void;
}) {
  const notice = uiStepNotice(session, step);
  return (
    <Card className="step-card" variant="borderless">
      <div className="step-heading">
        <div>
          <Typography.Title level={3}>
            {step}. {stepTitles[step - 1]}
          </Typography.Title>
          <Typography.Text type="secondary">{stepHint(step)}</Typography.Text>
        </div>
      </div>
      {step === 1 ? (
        <DraftStep
          session={session}
          presets={assets.presets}
          brands={assets.brands}
          patch={patch}
          execute={execute}
          busy={busy}
          goToStep={goToStep}
          step={step}
        />
      ) : null}
      {step === 2 ? (
        <VoiceStep
          session={session}
          voices={assets.voices}
          patch={patch}
          execute={execute}
          busy={busy}
          reloadAssets={reloadAssets}
          openAssetTab={openAssetTab}
          goToStep={goToStep}
          step={step}
        />
      ) : null}
      {step === 3 ? (
        <PortraitStep
          session={session}
          portraits={assets.portraits}
          patch={patch}
          execute={execute}
          busy={busy}
          reloadAssets={reloadAssets}
          openAssetTab={openAssetTab}
          goToStep={goToStep}
          step={step}
        />
      ) : null}
      {step === 4 ? (
        <PostproductionStep
          session={session}
          templates={assets.templates}
          videos={assets.videos}
          bgm={assets.bgm}
          patch={patch}
          execute={execute}
          busy={busy}
          openStoryboard={openStoryboard}
          openAssetTab={openAssetTab}
          goToStep={goToStep}
          step={step}
        />
      ) : null}
      {step === 5 ? (
        <PublishStep session={session} downloadFinalVideo={downloadFinalVideo} />
      ) : null}
      <StepStatusNotice
        step={step}
        session={session}
        notice={notice}
        task={task}
        busy={busy}
        error={error}
        onStop={onStop}
      />
    </Card>
  );
}

function StepStatusNotice({
  step,
  session,
  notice,
  task,
  busy,
  error,
  onStop,
}: {
  step: number;
  session: IpBroadcastState;
  notice?: { kind: string; message: string };
  task: TaskInfo | null;
  busy: boolean;
  error: string;
  onStop: () => void;
}) {
  const taskStep = task ? stepNumberForTaskKey(task.step_key || "") : 0;
  const taskBelongsToStep = taskStep === step;
  const isTaskRunning = taskBelongsToStep && ["pending", "running"].includes(task?.status || "");
  const isTaskFailed = taskBelongsToStep && task?.status === "failed";
  const isTaskCancelled = taskBelongsToStep && task?.status === "cancelled";
  const isLocalRunning = busy && step === stepNumberForTaskKey(session.next_action.key);

  if (isTaskFailed || error) {
    return (
      <Alert
        className="step-notice"
        type="error"
        showIcon
        message={isTaskFailed ? task?.error || "任务执行失败" : error}
      />
    );
  }

  if (isTaskCancelled) {
    return (
      <Alert
        className="step-notice"
        type="warning"
        showIcon
        message="已停止当前生产任务，已有素材不会被清空。"
      />
    );
  }

  if (isTaskRunning || isLocalRunning) {
    const progress = Math.round(task?.progress?.percentage || (isTaskRunning ? 8 : 0));
    return (
      <div className="step-notice step-notice-running">
        <div className="step-notice-running-main">
          <Loader2 className="spin" size={16} />
          <div>
            <strong>正在执行：{taskStepLabel(task?.step_key || session.next_action.key)}</strong>
            <span>{task?.progress?.message || "任务已提交，正在等待执行结果..."}</span>
          </div>
        </div>
        <Progress percent={progress} showInfo={false} />
        {task ? (
          <Button size="small" onClick={onStop} icon={<MonitorStop size={14} />}>
            停止
          </Button>
        ) : null}
      </div>
    );
  }

  if (!notice) return null;

  return (
    <Alert
      className="step-notice"
      type={noticeKind(notice.kind)}
      showIcon
      message={notice.message}
    />
  );
}

function DraftStep({
  session,
  presets,
  brands,
  patch,
  execute,
  busy,
  goToStep,
  step,
}: {
  session: IpBroadcastState;
  presets: IpPresetAsset[];
  brands: BrandKit[];
  patch: (values: Record<string, unknown>) => Promise<void>;
  execute: (stepKey: string) => Promise<void>;
  busy: boolean;
  goToStep: (step: number) => void;
  step: number;
}) {
  const sourceMode = String(session.state.source_mode || "video_extract");
  const ipTopics = Array.isArray(session.state.ip_learning_topics)
    ? (session.state.ip_learning_topics as string[])
    : [];
  const ipLearningNeedsTopicConfirmation =
    sourceMode === "ip_learning" && Boolean(session.state.ip_learning_requires_topic_confirmation);
  const selectedIpLearningTopic = String(session.state.ip_learning_selected_topic || "");
  async function confirmScriptAndContinue() {
    await patch({ copywriting_confirmed: true });
    goToStep(2);
  }
  return (
    <div className="draft-step-layout">
      <div className="draft-step-source">
        <SourceStep
          session={session}
          presets={presets}
          brands={brands}
          patch={patch}
          execute={execute}
          busy={busy}
          goToStep={goToStep}
          step={step}
          showPanelActions={false}
        />
      </div>
      <div className="draft-step-copy">
        <CopywritingStep
          session={session}
          patch={patch}
          execute={execute}
          busy={busy}
          goToStep={goToStep}
          step={step}
          showPanelActions={false}
        />
      </div>
      <div className="panel-actions sticky-step-actions">
        <StepNavButtons step={step} goToStep={goToStep} />
        {!ipLearningNeedsTopicConfirmation ? (
          <div className="panel-primary-actions">
            {!session.state.final_script ? (
              <Button type="primary" onClick={() => execute("source")} disabled={busy}>
                {busy ? "执行中..." : sourceActionLabel(sourceMode, ipTopics.length)}
              </Button>
            ) : (
              <>
                <Button onClick={() => execute("copywriting")} disabled={busy}>
                  {busy ? "正在优化..." : "AI 改写/优化文案"}
                </Button>
                <Button type="primary" onClick={confirmScriptAndContinue} disabled={busy}>
                  确认文案，去配音
                </Button>
              </>
            )}
          </div>
        ) : null}
      </div>
    </div>
  );
}

function SourceStep({
  session,
  presets,
  brands,
  patch,
  execute,
  busy,
  goToStep,
  step,
  showPanelActions = true,
}: {
  session: IpBroadcastState;
  presets: IpPresetAsset[];
  brands: BrandKit[];
  patch: (values: Record<string, unknown>) => Promise<void>;
  execute: (stepKey: string) => Promise<void>;
  busy: boolean;
  goToStep: (step: number) => void;
  step: number;
  showPanelActions?: boolean;
}) {
  const selectedPreset = presets.find((item) => item.preset_id === session.state.business_preset_id);
  const selectedBrand = brands.find((item) => item.brand_id === session.state.brand_kit_id);
  const sourceMode = String(session.state.source_mode || "video_extract");
  const ipTopics = Array.isArray(session.state.ip_learning_topics)
    ? (session.state.ip_learning_topics as string[])
    : [];
  const ipScripts = Array.isArray(session.state.ip_learning_scripts)
    ? (session.state.ip_learning_scripts as Array<Record<string, string>>)
    : [];
  const ipErrors = Array.isArray(session.state.ip_learning_errors)
    ? (session.state.ip_learning_errors as Array<Record<string, string>>)
    : [];
  const ipLearningNeedsTopicConfirmation =
    sourceMode === "ip_learning" && Boolean(session.state.ip_learning_requires_topic_confirmation);
  const selectedIpLearningTopic = String(session.state.ip_learning_selected_topic || "");
  async function confirmIpLearningTopic() {
    if (!selectedIpLearningTopic) return;
    await execute("source");
  }
  async function applyPreset(presetId: string) {
    const preset = presets.find((item) => item.preset_id === presetId);
    if (!preset) {
      await patch({
        business_preset_id: "",
        business_goal_name: "",
        business_script_structure: [],
        business_visual_strategy: "",
        business_publish_platforms: [],
      });
      return;
    }
    await patch({
      business_preset_id: preset.preset_id,
      business_goal_name: preset.display_name,
      business_script_structure: preset.script_structure,
      business_visual_strategy: preset.recommended_visual_strategy,
      business_publish_platforms: preset.publish_platform_hints,
      word_count: preset.recommended_word_count,
      style_prompt: preset.default_style_prompt,
      template_id: preset.default_template_id,
      subtitle_enabled: preset.default_subtitle_enabled,
    });
  }
  return (
    <div>
      <section className="business-goal-section">
        <div className="section-titleline">
          <div>
            <label>本条视频目标</label>
            <p className="muted">先选这条视频要完成的业务目标，系统会影响文案结构、画面建议和发布平台。</p>
          </div>
          <Tag color={selectedPreset ? "processing" : "default"}>
            {selectedPreset ? "已应用目标" : "自由创作"}
          </Tag>
        </div>
        <div className="business-goal-grid">
          <button
            className={`business-goal-card ${!selectedPreset ? "selected" : ""}`}
            onClick={() => applyPreset("")}
          >
            <strong>自由创作</strong>
            <span className="business-goal-tooltip">
              不套业务结构，保留你手动设置的风格、字数和模板。适合临时想法、测试素材或已有完整脚本。
            </span>
          </button>
          {presets.map((preset) => (
            <button
              key={preset.preset_id}
              className={`business-goal-card ${
                session.state.business_preset_id === preset.preset_id ? "selected" : ""
              }`}
              onClick={() => applyPreset(preset.preset_id)}
            >
              <strong>{humanGoalLabel(preset)}</strong>
              <span className="business-goal-tooltip">
                {preset.description}
                <br />
                推荐结构：{preset.script_structure.join(" → ")}
                <br />
                画面策略：{preset.recommended_visual_strategy}
              </span>
            </button>
          ))}
        </div>
        {selectedPreset ? (
          <div className="goal-impact-note">
            <span>本目标会影响：文案结构、画面建议、发布平台。</span>
            <span>推荐画面：{selectedPreset.recommended_visual_strategy}</span>
          </div>
        ) : null}
      </section>

      <div className="section-title source-title">
        <span>素材来源</span>
        <small>有视频就提取文案，已有稿子就粘贴，想从门店定位生成就选行业+人设。</small>
      </div>
      <Tabs
        className="source-tabs"
        activeKey={sourceMode}
        onChange={(key) => patch({ source_mode: key })}
        items={[
          {
            key: "video_extract",
            label: sourceModeLabels.video_extract,
            children: (
              <div className="source-panel">
                <Typography.Paragraph type="secondary">
                  粘贴抖音分享口令、短链或视频链接，系统会解析真实视频并提取口播文案。
                </Typography.Paragraph>
                <label>视频链接或抖音分享文本</label>
                <textarea
                  className="small-textarea"
                  defaultValue={
                    ((session.state.video_input as string) || session.state.source_text || "") as string
                  }
                  onBlur={(event) =>
                    patch({
                      source_mode: "video_extract",
                      video_input: event.target.value,
                      source_text: event.target.value,
                    })
                  }
                  placeholder="例如：https://v.douyin.com/... 或“复制打开抖音...”完整分享文本"
                />
              </div>
            ),
          },
          {
            key: "paste",
            label: sourceModeLabels.paste,
            children: (
              <div className="source-panel">
                <Typography.Paragraph type="secondary">
                  适合已有文案、手动整理的视频文案，或从其他工具复制来的脚本。
                </Typography.Paragraph>
                <label>粘贴脚本文字</label>
                <textarea
                  defaultValue={(session.state.source_text as string) || ""}
                  onBlur={(event) =>
                    patch({ source_mode: "paste", source_text: event.target.value })
                  }
                  placeholder="将视频口播文案粘贴到此处..."
                />
              </div>
            ),
          },
          {
            key: "industry_persona",
            label: sourceModeLabels.industry_persona,
            children: (
              <div className="source-panel">
                <Typography.Paragraph type="secondary">
                  没有现成素材时，补充门店、人设和卖点，系统会按上方“本条视频目标”生成第一版口播文案。
                </Typography.Paragraph>
                <div className="source-goal-hint">
                  <strong>当前目标：{selectedPreset ? humanGoalLabel(selectedPreset) : "自由创作"}</strong>
                  <span>
                    {selectedPreset
                      ? `将优先按“${selectedPreset.script_structure.join(" → ")}”组织文案。`
                      : "未选择业务目标时，系统会按通用口播结构生成。"}
                  </span>
                </div>
                <label>行业/门店类型与人设身份</label>
                <textarea
                  className="small-textarea"
                  defaultValue={(session.state.industry_persona as string) || ""}
                  onBlur={(event) =>
                    patch({ source_mode: "industry_persona", industry_persona: event.target.value })
                  }
                  placeholder="例如：重庆火锅店老板，开店十年，熟悉牛油锅底和本地客群"
                />
                <div className="grid2">
                  <div>
                    <label>产品/服务/活动与核心卖点</label>
                    <textarea
                      className="small-textarea"
                      defaultValue={(session.state.selling_points as string) || ""}
                      onBlur={(event) =>
                        patch({ source_mode: "industry_persona", selling_points: event.target.value })
                      }
                      placeholder="例如：牛油锅底每天现炒，鲜切黄牛肉，午市双人餐"
                    />
                  </div>
                  <div>
                    <label>适合什么客户</label>
                    <textarea
                      className="small-textarea"
                      defaultValue={(session.state.target_customer as string) || ""}
                      onBlur={(event) =>
                        patch({ source_mode: "industry_persona", target_customer: event.target.value })
                      }
                      placeholder="例如：附近上班族、朋友聚餐、家庭聚会"
                    />
                  </div>
                </div>
                <label>优惠/预约/到店提示</label>
                <input
                  defaultValue={(session.state.conversion_phrase as string) || ""}
                  onBlur={(event) =>
                    patch({ source_mode: "industry_persona", conversion_phrase: event.target.value })
                  }
                  placeholder="例如：到店报口令打九折"
                />
                <label>补充信息（可选）</label>
                <textarea
                  className="small-textarea"
                  defaultValue={(session.state.business_intent_note as string) || ""}
                  onBlur={(event) =>
                    patch({ source_mode: "industry_persona", business_intent_note: event.target.value })
                  }
                  placeholder="例如：99元双人火锅套餐，下班两个人来吃很划算。"
                />
                <small className="muted">
                  不需要再选择视频类型或文案类型，业务目标已经决定文案结构。补充越具体，文案越贴近门店。
                </small>
              </div>
            ),
          },
          {
            key: "ip_learning",
            label: sourceModeLabels.ip_learning,
            children: (
              <div className="source-panel">
                <Typography.Paragraph type="secondary">
                  输入一个 IP 主页，学习最近 5 条视频口播内容并生成选题。主页抓取失败时可展开手动兜底。
                </Typography.Paragraph>
                <label>IP 主页链接或主页分享文本</label>
                <textarea
                  className="small-textarea"
                  defaultValue={
                    ((session.state.ip_profile_url as string) || session.state.source_text || "") as string
                  }
                  onBlur={(event) =>
                    patch({
                      source_mode: "ip_learning",
                      ip_profile_url: event.target.value,
                      source_text: event.target.value,
                    })
                  }
                  placeholder="例如：https://www.douyin.com/user/..."
                />
                <details className="advanced">
                  <summary>手动兜底：粘贴最近 5 条视频链接</summary>
                  <textarea
                    className="small-textarea"
                    defaultValue={(session.state.ip_manual_video_links as string) || ""}
                    onBlur={(event) =>
                      patch({ source_mode: "ip_learning", ip_manual_video_links: event.target.value })
                    }
                    placeholder="每行一条视频链接，或每段粘贴一条完整抖音分享文本"
                  />
                </details>
                {session.state.ip_learning_summary ? (
                  <div className="summary-box subtle">
                    <strong>{session.state.ip_learning_summary as string}</strong>
                    {ipScripts.length ? (
                      <details className="source-learning-details">
                        <summary>查看已提取文案</summary>
                        {ipScripts.map((item, index) => (
                          <div key={`${item.source}-${index}`} className="source-learning-item">
                            <strong>视频 {index + 1}</strong>
                            <small>{item.source}</small>
                            <p>{item.script}</p>
                          </div>
                        ))}
                      </details>
                    ) : null}
                    {ipErrors.length ? (
                      <details className="source-learning-details">
                        <summary>查看失败链接</summary>
                        {ipErrors.map((item, index) => (
                          <div key={`${item.source}-${index}`} className="source-learning-item error">
                            <strong>失败 {index + 1}</strong>
                            <small>{item.source}</small>
                            <p>{item.error}</p>
                          </div>
                        ))}
                      </details>
                    ) : null}
                  </div>
                ) : null}
                {ipTopics.length ? (
                  <>
                    <Alert
                      className="step-notice"
                      type="info"
                      showIcon
                      message="已生成候选选题，请选择 1 个再生成文案。"
                    />
                    <div className="topic-grid">
                      {ipTopics.map((topic) => (
                        <button
                          key={topic}
                          className={`topic-card ${
                            session.state.ip_learning_selected_topic === topic ? "selected" : ""
                          }`}
                          onClick={() =>
                            patch({ source_mode: "ip_learning", ip_learning_selected_topic: topic })
                          }
                        >
                          {topic}
                        </button>
                      ))}
                    </div>
                    <div className="topic-confirm-row">
                      <Button
                        type="primary"
                        onClick={confirmIpLearningTopic}
                        disabled={busy || !selectedIpLearningTopic}
                      >
                        {busy ? "正在生成文案..." : selectedIpLearningTopic ? "确认选题并生成文案" : "请选择一个学习选题"}
                      </Button>
                      <Typography.Text type="secondary">
                        先确认一个选题，再进入口播文案生成，避免系统自动使用第一个选题。
                      </Typography.Text>
                    </div>
                  </>
                ) : null}
              </div>
            ),
          },
        ]}
      />
      <details className="advanced source-advanced">
        <summary>高级设置</summary>
        <div className="grid2">
          <div>
            <label>品牌包</label>
            <select
              value={(session.state.brand_kit_id as string) || ""}
              onChange={(event) => {
                const brand = brands.find((item) => item.brand_id === event.target.value);
                patch({
                  brand_kit_id: event.target.value,
                  bgm_path: brand?.default_bgm_path || session.state.bgm_path || "",
                });
              }}
            >
              <option value="">不使用品牌包</option>
              {brands.map((brand) => (
                <option key={brand.brand_id} value={brand.brand_id}>
                  {brand.brand_name}
                </option>
              ))}
            </select>
            {selectedBrand ? <small className="muted">{selectedBrand.coupon_phrase}</small> : null}
          </div>
        </div>
      </details>
      {showPanelActions && !ipLearningNeedsTopicConfirmation ? (
      <div className="panel-actions">
        <StepNavButtons step={step} goToStep={goToStep} />
        <div className="panel-primary-actions">
          {session.state.final_script ? (
            <>
            <Button type="primary" onClick={() => goToStep(step + 1)} disabled={busy}>
              使用当前文案继续
            </Button>
            <Button onClick={() => execute("source")} disabled={busy}>
              重新生成
            </Button>
            </>
          ) : (
            <Button
              type="primary"
              onClick={() => execute("source")}
              disabled={busy || (ipLearningNeedsTopicConfirmation && !selectedIpLearningTopic)}
            >
              {busy
                ? "执行中..."
                : ipLearningNeedsTopicConfirmation
                  ? selectedIpLearningTopic
                    ? "确认选题并生成文案"
                    : "请选择一个学习选题"
                  : sourceActionLabel(sourceMode, ipTopics.length)}
            </Button>
          )}
        </div>
      </div>
      ) : null}
    </div>
  );
}

function CopywritingStep({
  session,
  patch,
  execute,
  busy,
  goToStep,
  step,
  showPanelActions = true,
}: {
  session: IpBroadcastState;
  patch: (values: Record<string, unknown>) => Promise<void>;
  execute: (stepKey: string) => Promise<void>;
  busy: boolean;
  goToStep: (step: number) => void;
  step: number;
  showPanelActions?: boolean;
}) {
  const finalScript = (session.state.final_script as string) || "";
  const [scriptDraft, setScriptDraft] = useState(finalScript);

  useEffect(() => {
    setScriptDraft(finalScript);
  }, [finalScript]);

  return (
    <div>
      <div className="script-editor-head">
        <label>最终口播文案</label>
        <span className="script-word-count">{scriptCharCount(scriptDraft)} 字</span>
      </div>
      <textarea
        className="script-editor"
        value={scriptDraft}
        onChange={(event) => setScriptDraft(event.target.value)}
        onBlur={(event) => patch({ final_script: event.target.value })}
      />
      <div className="grid2">
        <div>
          <label>写作风格指令</label>
          <input
            defaultValue={(session.state.style_prompt as string) || ""}
            onBlur={(event) => patch({ style_prompt: event.target.value })}
          />
        </div>
        <div>
          <label>目标字数</label>
          <input
            type="number"
            defaultValue={(session.state.word_count as number) || 200}
            onBlur={(event) => patch({ word_count: Number(event.target.value) })}
          />
        </div>
      </div>
      {showPanelActions ? (
      <div className="panel-actions">
        <StepNavButtons step={step} goToStep={goToStep} />
        <div className="panel-primary-actions">
          {session.state.copywriting_confirmed ? (
            <>
            <button className="primary" onClick={() => goToStep(step + 1)} disabled={busy}>
              确认文案并继续
            </button>
            <button className="secondary-action" onClick={() => execute("copywriting")} disabled={busy}>
              重新改写
            </button>
            </>
          ) : (
            <button className="primary" onClick={() => execute("copywriting")} disabled={busy}>
              {busy ? "正在改写..." : "AI 改写/优化文案"}
            </button>
          )}
        </div>
      </div>
      ) : null}
    </div>
  );
}

function ScriptSegmentsPreview({
  segments,
  emptyText,
}: {
  segments: StorySegment[];
  emptyText: string;
}) {
  if (!segments.length) {
    return <div className="preview-empty-state">{emptyText}</div>;
  }
  return (
    <div className="script-segment-list">
      {segments.map((segment) => (
        <section key={segment.segment_id} className="script-segment-row">
          <span>{String(segment.index).padStart(2, "0")}</span>
          <p>{segment.text}</p>
        </section>
      ))}
    </div>
  );
}

function VoiceStep({
  session,
  voices,
  patch,
  execute,
  busy,
  reloadAssets,
  openAssetTab,
  goToStep,
  step,
}: {
  session: IpBroadcastState;
  voices: VoiceAsset[];
  patch: (values: Record<string, unknown>) => Promise<void>;
  execute: (stepKey: string) => Promise<void>;
  busy: boolean;
  reloadAssets: () => Promise<void>;
  openAssetTab: (tab: AssetTab) => void;
  goToStep: (step: number) => void;
  step: number;
}) {
  const inferenceMode = (session.state.tts_inference_mode as string) || "local";
  const selectedWorkflow =
    (session.state.tts_workflow as string) || "runninghub/tts_index_custom.json";
  const selectedWorkflowConfig = getTtsWorkflow(selectedWorkflow);
  const workflowKind = selectedWorkflowConfig.kind;
  const showReferenceLibrary =
    inferenceMode === "comfyui" && selectedWorkflowConfig.supportsReference;
  const [addVoiceOpen, setAddVoiceOpen] = useState(false);
  const [preview, setPreview] = useState<AssetPreview | null>(null);
  const [systemVoiceOpen, setSystemVoiceOpen] = useState(false);
  const [referenceVoiceOpen, setReferenceVoiceOpen] = useState(false);

  async function selectVoice(voice: VoiceAsset) {
    await patch({
      tts_ref_audio_id: voice.reference_id,
      tts_ref_audio_path: voice.asset_path,
    });
  }

  const scriptSegments = splitSegments((session.state.final_script as string) || "");
  const selectedReferenceVoice = voices.find(
    (voice) => voice.asset_path === session.state.tts_ref_audio_path,
  );

  return (
    <div className="production-split voice-step-layout">
      <aside className="production-left-panel script-preview-panel">
        <div className="panel-titleline">
          <div>
            <strong>口播文案</strong>
            <span>配音会按这些段落生成，请先确认文案自然、顺口。</span>
          </div>
          <Tag>{scriptSegments.length || 0} 段</Tag>
        </div>
        <ScriptSegmentsPreview segments={scriptSegments} emptyText="还没有最终文案，请先回到搞定文案生成或确认口播稿。" />
      </aside>

      <section className="production-main-panel">
        <div className="panel-titleline">
          <div>
            <strong>配音设置</strong>
            <span>选择声音来源、音色和语速，生成后在下方试听。</span>
          </div>
        </div>
        <div className="voice-param-grid">
          <div>
            <label>配音方式</label>
            <select
              value={inferenceMode}
              onChange={(event) => patch({ tts_inference_mode: event.target.value })}
            >
              <option value="local">系统默认配音</option>
              <option value="comfyui">云端声音克隆</option>
            </select>
          </div>
        </div>

        {inferenceMode === "local" ? (
          <LocalVoiceConfig session={session} patch={patch} onOpenVoicePicker={() => setSystemVoiceOpen(true)} />
        ) : null}

        {inferenceMode === "comfyui" ? (
          <>
            <div className="voice-config-panel">
              <div className="voice-param-grid">
                <div>
                  <label>声音生成方式</label>
                  <select
                    value={selectedWorkflow}
                    onChange={(event) => patch({ tts_workflow: event.target.value })}
                  >
                    {ttsWorkflowOptions.map((workflow) => (
                      <option key={workflow.value} value={workflow.value}>
                        {workflow.label}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
              <p className="muted">{ttsWorkflowNotice(workflowKind)}</p>
            </div>
            {showReferenceLibrary ? (
              <ReferenceVoiceSummaryCard
                voice={selectedReferenceVoice}
                count={voices.length}
                onOpen={() => setReferenceVoiceOpen(true)}
                onManage={() => openAssetTab("voices")}
              />
            ) : null}
            {workflowKind === "edge" ? (
              <ComfyEdgeConfig session={session} patch={patch} onOpenVoicePicker={() => setSystemVoiceOpen(true)} />
            ) : null}
            {workflowKind === "spark" ? <SparkVoiceConfig session={session} patch={patch} /> : null}
          </>
        ) : null}

        <div className={`generated-preview-card voice-result-card ${session.state.audio_path ? "" : "placeholder"}`}>
          <div>
            <strong>{session.state.audio_path ? "已生成配音" : "配音结果"}</strong>
            <small>
              {session.state.audio_path
                ? "请试听确认音色、语速和情绪，没有问题再继续下一步。"
                : "生成后这里会出现音频播放器，方便你确认声音效果。"}
            </small>
          </div>
          {session.state.audio_path ? (
            <ArtifactMediaPreview
              sessionId={session.session_id}
              artifactKey="audio"
              kind="audio"
              enabled={Boolean(session.state.audio_path)}
            />
          ) : (
            <div className="preview-empty-state">等待生成配音</div>
          )}
        </div>
      </section>

      <div className="panel-actions">
        <StepNavButtons step={step} goToStep={goToStep} />
        <div className="panel-primary-actions">
          {session.state.audio_path ? (
            <>
            <button className="primary" onClick={() => goToStep(step + 1)} disabled={busy}>
              使用当前配音继续
            </button>
            <button className="secondary-action" onClick={() => execute("voice")} disabled={busy}>
              重新生成
            </button>
            </>
          ) : (
            <button className="primary" onClick={() => execute("voice")} disabled={busy}>
              {busy ? "正在生成..." : "生成配音"}
            </button>
          )}
        </div>
      </div>
      <SystemVoicePickerModal
        open={systemVoiceOpen}
        mode={inferenceMode === "local" ? "local" : "workflow"}
        session={session}
        patch={patch}
        onClose={() => setSystemVoiceOpen(false)}
      />
      <ReferenceVoicePickerModal
        open={referenceVoiceOpen}
        voices={voices}
        selectedPath={(session.state.tts_ref_audio_path as string) || ""}
        onClose={() => setReferenceVoiceOpen(false)}
        onSelect={selectVoice}
        onAdd={() => setAddVoiceOpen(true)}
        onPreview={(voice) => setPreview({ kind: "audio", title: voice.name, src: voice.file_url })}
      />
      <VoiceAssetModal
        open={addVoiceOpen}
        onClose={() => setAddVoiceOpen(false)}
        onUploaded={async (voice) => {
          await selectVoice(voice);
          await reloadAssets();
          setAddVoiceOpen(false);
          setReferenceVoiceOpen(false);
        }}
      />
      <AssetPreviewModal preview={preview} onClose={() => setPreview(null)} />
    </div>
  );
}

function VoiceChoiceSummaryCard({
  title,
  value,
  description,
  onOpen,
}: {
  title: string;
  value: string;
  description: string;
  onOpen: () => void;
}) {
  return (
    <button className="choice-summary-card voice-choice-summary" onClick={onOpen}>
      <span className="choice-summary-icon">
        <Mic2 size={18} />
      </span>
      <span>
        <strong>{title}：{value}</strong>
        <small>{description}</small>
      </span>
      <i>›</i>
    </button>
  );
}

function ReferenceVoiceSummaryCard({
  voice,
  count,
  onOpen,
  onManage,
}: {
  voice?: VoiceAsset;
  count: number;
  onOpen: () => void;
  onManage: () => void;
}) {
  return (
    <div className="voice-config-panel">
      <button className="choice-summary-card voice-choice-summary" onClick={onOpen}>
        <span className="choice-summary-icon">
          <Mic2 size={18} />
        </span>
        <span>
          <strong>参考音色：{voice?.name || "请选择老板参考音色"}</strong>
          <small>{voice ? voice.filename : `音色库已有 ${count} 条参考音频`}</small>
        </span>
        <i>›</i>
      </button>
      <div className="choice-summary-foot">
        <span>声音克隆会读取选中的参考音频，复杂采样参数已使用最佳配置。</span>
        <Button size="small" onClick={onManage}>
          管理音色库
        </Button>
      </div>
    </div>
  );
}

function SystemVoicePickerModal({
  open,
  mode,
  session,
  patch,
  onClose,
}: {
  open: boolean;
  mode: "local" | "workflow";
  session: IpBroadcastState;
  patch: (values: Record<string, unknown>) => Promise<void>;
  onClose: () => void;
}) {
  const [category, setCategory] = useState("热门");
  const isLocal = mode === "local";
  const voiceOptions = isLocal ? edgeVoiceOptions : comfyEdgeVoiceOptions;
  const selectedVoice = isLocal
    ? ((session.state.tts_voice as string) || "zh-CN-YunjianNeural")
    : ((session.state.tts_workflow_voice as string) || "[Chinese] zh-CN Yunjian");
  const speedKey = isLocal ? "tts_speed" : "tts_workflow_speed";
  const speed = Number.isFinite(session.state[speedKey] as number)
    ? (session.state[speedKey] as number)
    : isLocal ? 1.2 : 1;
  const [pendingVoice, setPendingVoice] = useState(selectedVoice);
  const [pendingSpeed, setPendingSpeed] = useState(speed);
  const [previewAudioSrc, setPreviewAudioSrc] = useState("");
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState("");
  const filteredOptions = voiceOptions.filter((voice) => voiceMatchesCategory(voice, category));

  useEffect(() => {
    if (open) {
      setPendingVoice(selectedVoice);
      setPendingSpeed(speed);
      setPreviewAudioSrc("");
      setPreviewError("");
    }
  }, [open, selectedVoice, speed]);

  if (!open) return null;

  async function confirmSelection() {
    await patch({
      [isLocal ? "tts_voice" : "tts_workflow_voice"]: pendingVoice,
      [speedKey]: pendingSpeed,
    });
    onClose();
  }

  async function previewVoice() {
    setPreviewLoading(true);
    setPreviewError("");
    setPreviewAudioSrc("");
    try {
      const result = await synthesizeTtsPreview({
        text: voicePreviewText((session.state.final_script as string) || ""),
        inference_mode: isLocal ? "local" : "comfyui",
        workflow: isLocal ? undefined : ((session.state.tts_workflow as string) || "runninghub/tts_edge.json"),
        voice: pendingVoice,
        speed: pendingSpeed,
        pitch: isLocal
          ? Number(session.state.tts_pitch ?? 0)
          : Number(session.state.tts_workflow_pitch ?? 0),
        volume: isLocal ? Number(session.state.tts_volume ?? 0) : undefined,
      });
      setPreviewAudioSrc(`/api/files/${result.audio_path}`);
    } catch (err) {
      setPreviewError(err instanceof Error ? err.message : String(err));
    } finally {
      setPreviewLoading(false);
    }
  }

  return (
    <div className="modal-backdrop asset-modal-backdrop">
      <section className="modal voice-picker-modal">
        <div className="modal-title">
          <div>
            <h2>解说音色</h2>
            <p>选择适合本条视频的系统音色，底部可同步调整语速。</p>
          </div>
          <button onClick={onClose}>关闭</button>
        </div>
        <div className="voice-category-tabs">
          {["热门", "男声", "女声", "特色"].map((item) => (
            <button
              key={item}
              className={category === item ? "selected" : ""}
              onClick={() => setCategory(item)}
            >
              {item}
            </button>
          ))}
        </div>
        <div className="voice-picker-grid">
          {filteredOptions.map((voice, index) => (
            <button
              key={voice.value}
              className={`voice-picker-card ${pendingVoice === voice.value ? "selected" : ""}`}
              onClick={() => setPendingVoice(voice.value)}
            >
              <span className="voice-avatar">{index === 0 && category === "热门" ? "荐" : voiceInitial(voice.label)}</span>
              <strong>{voiceDisplayName(voice.label, index)}</strong>
              <small>{voiceGenderLabel(voice.label)}</small>
            </button>
          ))}
        </div>
        <div className="voice-picker-speedbar">
          <div className="range-field">
            <div className="range-field-head">
              <span>语速</span>
              <strong>{pendingSpeed.toFixed(2)}x</strong>
            </div>
            <input
              type="range"
              min={0.5}
              max={2}
              step={0.05}
              value={pendingSpeed}
              onChange={(event) => setPendingSpeed(Number(event.target.value))}
            />
            <div className="range-field-foot">
              <span>0.50x</span>
              <em>1.0x 为正常速度</em>
              <span>2.00x</span>
            </div>
          </div>
          {previewAudioSrc || previewError ? (
            <div className={`voice-picker-preview ${previewError ? "error" : ""}`}>
              {previewAudioSrc ? <ProtectedMedia kind="audio" src={previewAudioSrc} /> : null}
              {previewError ? <span>{previewError}</span> : null}
            </div>
          ) : null}
          <div className="voice-picker-actions">
            <button type="button" onClick={onClose}>
              取消
            </button>
            <button type="button" className="secondary-action" onClick={previewVoice} disabled={previewLoading}>
              {previewLoading ? "试听生成中..." : "试听音色"}
            </button>
            <button type="button" className="primary" onClick={confirmSelection}>
              确认使用
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}

function ReferenceVoicePickerModal({
  open,
  voices,
  selectedPath,
  onClose,
  onSelect,
  onAdd,
  onPreview,
}: {
  open: boolean;
  voices: VoiceAsset[];
  selectedPath: string;
  onClose: () => void;
  onSelect: (voice: VoiceAsset) => Promise<void>;
  onAdd: () => void;
  onPreview: (voice: VoiceAsset) => void;
}) {
  const [pendingPath, setPendingPath] = useState(selectedPath);

  useEffect(() => {
    if (open) {
      setPendingPath(selectedPath);
    }
  }, [open, selectedPath]);

  if (!open) return null;

  const pendingVoice = voices.find((voice) => voice.asset_path === pendingPath);

  async function confirmSelection() {
    if (!pendingVoice) return;
    await onSelect(pendingVoice);
    onClose();
  }

  return (
    <div className="modal-backdrop asset-modal-backdrop">
      <section className="modal voice-picker-modal reference-voice-modal">
        <div className="modal-title">
          <div>
            <h2>选择参考音色</h2>
            <p>选择一段老板本人或品牌声音参考音频，系统会按最佳配置克隆。</p>
          </div>
          <button onClick={onClose}>关闭</button>
        </div>
        <div className="reference-voice-grid">
          {voices.map((voice) => (
            <div
              key={voice.reference_id}
              className={`reference-voice-card ${pendingPath === voice.asset_path ? "selected" : ""}`}
              role="button"
              tabIndex={0}
              onClick={() => setPendingPath(voice.asset_path)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  setPendingPath(voice.asset_path);
                }
              }}
            >
              <span className="choice-summary-icon">
                <Mic2 size={18} />
              </span>
              <span>
                <strong>{voice.name}</strong>
                <small>{voice.filename}</small>
              </span>
              <Button
                size="small"
                onClick={(event) => {
                  event.stopPropagation();
                  onPreview(voice);
                }}
                disabled={!voice.file_url}
              >
                试听
              </Button>
            </div>
          ))}
          <AddAssetCard
            title="添加参考音色"
            description={voices.length ? "上传或录制新的参考音频" : "暂无音色，点击添加"}
            onClick={onAdd}
          />
        </div>
        <div className="modal-actions reference-voice-actions">
          <button onClick={onClose}>取消</button>
          <button className="primary" onClick={confirmSelection} disabled={!pendingVoice}>
            确定使用
          </button>
        </div>
      </section>
    </div>
  );
}

function LocalVoiceConfig({
  session,
  patch,
  onOpenVoicePicker,
}: {
  session: IpBroadcastState;
  patch: (values: Record<string, unknown>) => Promise<void>;
  onOpenVoicePicker: () => void;
}) {
  const selectedVoice = (session.state.tts_voice as string) || "zh-CN-YunjianNeural";
  const selectedVoiceLabel = voiceOptionLabel(edgeVoiceOptions, selectedVoice);
  const speed = Number.isFinite(session.state.tts_speed as number)
    ? (session.state.tts_speed as number)
    : 1.2;
  return (
    <div className="voice-config-panel">
      <VoiceChoiceSummaryCard
        title="解说音色"
        value={`${selectedVoiceLabel} · ${speed.toFixed(2)}x`}
        description="系统默认配音，适合快速生成口播。"
        onOpen={onOpenVoicePicker}
      />
      <details className="advanced voice-tuning-panel">
        <summary>更多声音参数</summary>
        <div className="voice-param-grid">
          <RangeField
            label="音调"
            value={session.state.tts_pitch as number}
            fallback={0}
            min={-50}
            max={50}
            step={1}
            patchKey="tts_pitch"
            patch={patch}
            format={(item) => `${item >= 0 ? "+" : ""}${item}Hz`}
            hint="0Hz 为原始音调"
          />
          <RangeField
            label="音量增益"
            value={session.state.tts_volume as number}
            fallback={0}
            min={-50}
            max={100}
            step={5}
            patchKey="tts_volume"
            patch={patch}
            format={(item) => `${item >= 0 ? "+" : ""}${item}%`}
            hint="0% 为原始音量"
          />
        </div>
      </details>
    </div>
  );
}

function ComfyEdgeConfig({
  session,
  patch,
  onOpenVoicePicker,
}: {
  session: IpBroadcastState;
  patch: (values: Record<string, unknown>) => Promise<void>;
  onOpenVoicePicker: () => void;
}) {
  const selectedVoice =
    (session.state.tts_workflow_voice as string) || "[Chinese] zh-CN Yunjian";
  const selectedVoiceLabel = voiceOptionLabel(comfyEdgeVoiceOptions, selectedVoice);
  const speed = Number.isFinite(session.state.tts_workflow_speed as number)
    ? (session.state.tts_workflow_speed as number)
    : 1;
  return (
    <div className="voice-config-panel">
      <VoiceChoiceSummaryCard
        title="解说音色"
        value={`${selectedVoiceLabel} · ${speed.toFixed(2)}x`}
        description="云端默认配音，适合需要稳定音色时使用。"
        onOpen={onOpenVoicePicker}
      />
      <details className="advanced voice-tuning-panel">
        <summary>更多声音参数</summary>
        <div className="voice-param-grid">
          <RangeField
            label="音调"
            value={session.state.tts_workflow_pitch as number}
            fallback={0}
            min={-50}
            max={50}
            step={1}
            patchKey="tts_workflow_pitch"
            patch={patch}
            format={(item) => `${item >= 0 ? "+" : ""}${item}Hz`}
            hint="0Hz 为原始音调"
          />
        </div>
      </details>
    </div>
  );
}

function SparkVoiceConfig({
  session,
  patch,
}: {
  session: IpBroadcastState;
  patch: (values: Record<string, unknown>) => Promise<void>;
}) {
  return (
    <div className="voice-config-panel">
      <div className="voice-param-grid four">
        <div>
          <label>音色性别</label>
          <select
            value={(session.state.tts_spark_gender as string) || "male"}
            onChange={(event) => patch({ tts_spark_gender: event.target.value })}
          >
            <option value="male">男声</option>
            <option value="female">女声</option>
          </select>
        </div>
        <ToneSelect label="语速" value={(session.state.tts_spark_speed as string) || "moderate"} patchKey="tts_spark_speed" patch={patch} />
        <ToneSelect label="音调" value={(session.state.tts_spark_pitch as string) || "moderate"} patchKey="tts_spark_pitch" patch={patch} />
        <RangeField
          label="表现强度"
          value={session.state.tts_temperature as number}
          fallback={0.8}
          min={0.2}
          max={1.2}
          step={0.05}
          patchKey="tts_temperature"
          patch={patch}
          format={(item) => item.toFixed(2)}
          hint="越高越有表现力"
        />
      </div>
    </div>
  );
}

function ToneSelect({
  label,
  value,
  patchKey,
  patch,
}: {
  label: string;
  value: string;
  patchKey: string;
  patch: (values: Record<string, unknown>) => Promise<void>;
}) {
  return (
    <div>
      <label>{label}</label>
      <select value={value} onChange={(event) => patch({ [patchKey]: event.target.value })}>
        {toneOptions.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  );
}

function RangeField({
  label,
  value,
  fallback,
  min,
  max,
  step,
  patchKey,
  patch,
  format,
  hint,
}: {
  label: string;
  value: number | undefined;
  fallback: number;
  min: number;
  max: number;
  step: number;
  patchKey: string;
  patch: (values: Record<string, unknown>) => Promise<void>;
  format?: (value: number) => string;
  hint?: string;
}) {
  const current = Number.isFinite(value) ? Number(value) : fallback;
  const [draft, setDraft] = useState(current);

  useEffect(() => {
    setDraft(current);
  }, [current]);

  const formatted = format ? format(draft) : String(draft);
  async function commit() {
    await patch({ [patchKey]: draft });
  }

  return (
    <div className="range-field">
      <div className="range-field-head">
        <label>{label}</label>
        <strong>{formatted}</strong>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={draft}
        onChange={(event) => setDraft(Number(event.target.value))}
        onMouseUp={commit}
        onTouchEnd={commit}
        onBlur={commit}
      />
      <div className="range-field-foot">
        <span>{format ? format(min) : min}</span>
        <em>{hint}</em>
        <span>{format ? format(max) : max}</span>
      </div>
    </div>
  );
}

function ttsWorkflowKind(workflow: string) {
  return getTtsWorkflow(workflow).kind;
}

function getTtsWorkflow(workflow: string) {
  return (
    ttsWorkflowOptions.find((item) => item.value === workflow) ||
    ttsWorkflowOptions[0]
  );
}

function ttsWorkflowNotice(workflowKind: string) {
  if (workflowKind === "edge") {
    return "使用云端默认配音，可调整音色、语速和音调，不读取参考音频。";
  }
  if (workflowKind === "spark") {
    return "适合需要情绪或更强表现力的配音，可调整性别、语速、音调和表现强度。";
  }
  if (workflowKind === "index") {
    return "适合固定使用老板本人音色，需要先选择一段参考音频。";
  }
  return "当前声音生成方式会使用默认参数。";
}

function voiceOptionLabel(options: Array<{ value: string; label: string }>, value: string) {
  return options.find((option) => option.value === value)?.label || "系统推荐";
}

function voicePreviewText(script: string) {
  const clean = script.replace(/\s+/g, " ").trim();
  return clean.slice(0, 80) || "你好，欢迎来到本店，今天给大家介绍一个实用建议。";
}

function scriptCharCount(value: string) {
  return value.replace(/\s/g, "").length;
}

function voiceMatchesCategory(voice: { label: string; value: string }, category: string) {
  if (category === "热门") return true;
  if (category === "男声") return /男|Yun|Yunjian|Yunxi|Yunyang/i.test(voice.label);
  if (category === "女声") return /女|Xiao|Xiaoxiao|Xiaoyi/i.test(voice.label);
  return /Yunyang|晓伊|Xiaoyi/i.test(voice.label);
}

function voiceDisplayName(label: string, index: number) {
  if (index === 0) return "系统推荐";
  return label
    .replace(/^中文\s*[·-]\s*/, "")
    .replace(/\s*\(.*?\)\s*$/, "")
    .replace(/\s*（.*?）\s*$/, "");
}

function voiceInitial(label: string) {
  const name = voiceDisplayName(label, 1);
  return name.slice(0, 1) || "声";
}

function voiceGenderLabel(label: string) {
  if (/女|Xiao|Xiaoxiao|Xiaoyi/i.test(label)) return "女声";
  if (/男|Yun|Yunjian|Yunxi|Yunyang/i.test(label)) return "男声";
  return "特色音色";
}

function getDigitalHumanWorkflow(value: string) {
  return (
    digitalHumanWorkflowOptions.find((workflow) => workflow.value === value) ||
    digitalHumanWorkflowOptions[0]
  );
}

function PortraitStep({
  session,
  portraits,
  patch,
  execute,
  busy,
  reloadAssets,
  openAssetTab,
  goToStep,
  step,
}: {
  session: IpBroadcastState;
  portraits: PortraitAsset[];
  patch: (values: Record<string, unknown>) => Promise<void>;
  execute: (stepKey: string) => Promise<void>;
  busy: boolean;
  reloadAssets: () => Promise<void>;
  openAssetTab: (tab: AssetTab) => void;
  goToStep: (step: number) => void;
  step: number;
}) {
  const [addPortraitOpen, setAddPortraitOpen] = useState(false);
  const [preview, setPreview] = useState<AssetPreview | null>(null);
  const currentWorkflow = (session.state.digital_human_workflow as string) || "";
  const workflowConfig = getDigitalHumanWorkflow(currentWorkflow);
  const compatiblePortraits = portraits.filter((portrait) =>
    workflowConfig.supportedMediaTypes.includes(portrait.media_type),
  );
  const accept = workflowConfig.supportedMediaTypes.includes("image")
    ? workflowConfig.supportedMediaTypes.includes("video")
      ? "image/*,video/*"
      : "image/*"
    : "video/*";
  const selectedPortrait = portraits.find(
    (portrait) => portrait.portrait_id === session.state.portrait_id,
  );

  useEffect(() => {
    const updates: Record<string, unknown> = {};
    if (currentWorkflow !== workflowConfig.value) {
      updates.digital_human_workflow = workflowConfig.value;
      if (!session.state.digital_human_width) {
        updates.digital_human_width = workflowConfig.defaultWidth;
      }
      if (!session.state.digital_human_height) {
        updates.digital_human_height = workflowConfig.defaultHeight;
      }
    }
    if (
      selectedPortrait &&
      !workflowConfig.supportedMediaTypes.includes(selectedPortrait.media_type)
    ) {
      updates.portrait_id = "";
      updates.portrait_path = "";
      updates.portrait_media_type = "";
    }
    if (Object.keys(updates).length) {
      void patch(updates);
    }
  }, [
    currentWorkflow,
    selectedPortrait?.portrait_id,
    selectedPortrait?.media_type,
    session.state.digital_human_width,
    session.state.digital_human_height,
    workflowConfig.defaultHeight,
    workflowConfig.defaultWidth,
    workflowConfig.value,
  ]);

  async function selectPortrait(portrait: PortraitAsset) {
    await patch({
      portrait_id: portrait.portrait_id,
      portrait_path: portrait.asset_path,
      portrait_media_type: portrait.media_type,
    });
  }

  return (
    <div>
      <div className="section-title inline-section-title">
        <span>形象库</span>
        <Button size="small" onClick={() => openAssetTab("portraits")}>
          管理形象库
        </Button>
      </div>
      <div className="asset-grid portraits">
        {compatiblePortraits.map((portrait) => (
          <section
            key={portrait.portrait_id}
            className={`asset-card portrait selectable ${
              session.state.portrait_id === portrait.portrait_id ? "selected" : ""
            }`}
            onClick={() => selectPortrait(portrait)}
          >
            {portrait.media_type === "image" ? (
              <AssetImage src={portrait.file_url} alt={portrait.name} />
            ) : (
              <div className="video-thumb">VIDEO</div>
            )}
            <strong>{portrait.name}</strong>
            <span>{portrait.media_type === "video" ? "视频形象" : "图片形象"}</span>
            <div className="asset-card-actions">
              <button
                type="button"
                className="asset-action preview"
                onClick={(event) => {
                  event.stopPropagation();
                  setPreview({
                    kind: portrait.media_type,
                    title: portrait.name,
                    src: portrait.file_url,
                  });
                }}
                disabled={!portrait.file_url}
              >
                预览
              </button>
            </div>
          </section>
        ))}
        {!compatiblePortraits.length ? (
          <div className="empty-state">
            当前出镜方式只支持
            {workflowConfig.supportedMediaTypes.includes("video") ? "视频形象" : "图片形象"}。
          </div>
        ) : null}
        <AddAssetCard
          title="添加形象"
          description={
            workflowConfig.supportedMediaTypes.includes("video")
              ? "上传视频形象，保存后自动选中"
              : "上传图片形象，保存后自动选中"
          }
          onClick={() => setAddPortraitOpen(true)}
          className="portrait"
        />
      </div>
      <SimpleAssetModal
        open={addPortraitOpen}
        title="添加数字人形象"
        description={
          workflowConfig.supportedMediaTypes.includes("video")
            ? "当前出镜方式仅支持视频形象。"
            : "当前出镜方式仅支持图片形象。"
        }
        assetNameLabel="形象名称"
        fileLabel={workflowConfig.supportedMediaTypes.includes("video") ? "视频形象" : "图片形象"}
        accept={accept}
        upload={uploadPortraitAsset}
        onClose={() => setAddPortraitOpen(false)}
        onUploaded={async (portrait) => {
          await selectPortrait(portrait);
          await reloadAssets();
          setAddPortraitOpen(false);
        }}
      />
      <AssetPreviewModal preview={preview} onClose={() => setPreview(null)} />
      <div className="grid2">
        <div>
          <label>出镜生成方式</label>
          <select
            value={workflowConfig.value}
            onChange={(event) => {
              const nextWorkflow = getDigitalHumanWorkflow(event.target.value);
              const currentPortrait = portraits.find(
                (portrait) => portrait.portrait_id === session.state.portrait_id,
              );
              patch({
                digital_human_workflow: nextWorkflow.value,
                digital_human_width: nextWorkflow.defaultWidth,
                digital_human_height: nextWorkflow.defaultHeight,
                ...(currentPortrait &&
                !nextWorkflow.supportedMediaTypes.includes(currentPortrait.media_type)
                  ? { portrait_id: "", portrait_path: "", portrait_media_type: "" }
                  : {}),
              });
            }}
          >
            {digitalHumanWorkflowOptions.map((workflow) => (
              <option key={workflow.value} value={workflow.value}>
                {workflow.label}
              </option>
            ))}
          </select>
          <p className="muted">
            当前只显示
            {workflowConfig.supportedMediaTypes.includes("video") ? "视频形象" : "图片形象"}。
          </p>
        </div>
      </div>
      {workflowConfig.supportsPrompt ? (
        <>
          <label>出镜动作描述</label>
          <textarea
            className="small-textarea"
            defaultValue={(session.state.digital_human_prompt as string) || ""}
            placeholder="例如：正视镜头，自然说话，头部稳定，口型清晰。"
            onBlur={(event) => patch({ digital_human_prompt: event.target.value })}
          />
        </>
      ) : (
        <div className="inline-hint">
          当前出镜方式不支持动作描述，系统会按默认口播动作生成。
        </div>
      )}
      <details className="advanced">
        <summary>高级出镜参数</summary>
        <div className="voice-param-grid">
          <div>
            <label>视频宽度</label>
            <input
              type="number"
              defaultValue={(session.state.digital_human_width as number) || 720}
              onBlur={(event) => patch({ digital_human_width: Number(event.target.value) })}
            />
          </div>
          <div>
            <label>视频高度</label>
            <input
              type="number"
              defaultValue={(session.state.digital_human_height as number) || 1280}
              onBlur={(event) => patch({ digital_human_height: Number(event.target.value) })}
            />
          </div>
        </div>
      </details>
      {session.state.digital_human_video_path ? (
        <div className="generated-preview-card">
          <div>
            <strong>已生成出镜视频</strong>
            <small>请预览口型、形象和画面是否正常，没有问题再进入一键成片。</small>
          </div>
          <ArtifactMediaPreview
            sessionId={session.session_id}
            artifactKey="digital_human_video"
            kind="video"
            enabled={Boolean(session.state.digital_human_video_path)}
          />
        </div>
      ) : null}
      <div className="panel-actions">
        <StepNavButtons step={step} goToStep={goToStep} />
        <div className="panel-primary-actions">
          {session.state.digital_human_video_path ? (
            <>
            <button className="primary" onClick={() => goToStep(step + 1)} disabled={busy}>
              使用当前出镜视频继续
            </button>
            <button className="secondary-action" onClick={() => execute("digital_human")} disabled={busy}>
              重新生成
            </button>
            </>
          ) : (
            <button className="primary" onClick={() => execute("digital_human")} disabled={busy}>
              {busy ? "正在生成..." : "生成出镜视频"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function PostproductionStep({
  session,
  templates,
  videos,
  bgm,
  patch,
  execute,
  busy,
  openStoryboard,
  openAssetTab,
  goToStep,
  step,
}: {
  session: IpBroadcastState;
  templates: IpTemplateAsset[];
  videos: VideoAsset[];
  bgm: BgmAsset[];
  patch: (values: Record<string, unknown>) => Promise<void>;
  execute: (stepKey: string) => Promise<void>;
  busy: boolean;
  openStoryboard: () => void;
  openAssetTab: (tab: AssetTab) => void;
  goToStep: (step: number) => void;
  step: number;
}) {
  const [templatePickerOpen, setTemplatePickerOpen] = useState(false);
  const groups = readGroups(session.state.visual_groups);
  const segments = splitSegments((session.state.final_script as string) || "");
  const videoPlan = readVideoPlan(session.state.video_plan);
  const planGroups = buildGroupsFromVideoPlan(videoPlan, videos);
  const planApplied = Boolean(session.state.video_plan_applied);
  const visualStrategy = String(session.state.business_visual_strategy || "");
  const selectedTemplate = templates.find((template) => template.template_id === session.state.template_id) || templates[0];
  async function applyRecommendedPlan() {
    await patch({
      story_segments: segments,
      visual_groups: planGroups,
      overlay_enabled: planGroups.length > 0,
      video_plan_applied: true,
    });
  }
  return (
    <div className="production-split postproduction-step-layout">
      <section className="production-main-panel">
        <div className="panel-titleline">
          <div>
            <strong>成片配置</strong>
            <span>选择画面模板、规划覆盖素材，再生成最终视频。</span>
          </div>
          <Tag>{videos.length} 个视频素材</Tag>
        </div>

        <div className="template-summary-card">
          {selectedTemplate ? (
            <>
              <AssetImage src={selectedTemplate.preview_url} alt={selectedTemplate.display_name} />
              <div>
                <label>画面模板</label>
                <strong>{selectedTemplate.display_name}</strong>
                <span>{selectedTemplate.short_description}</span>
                <small>影响封面标题、字幕样式和安全区域。</small>
              </div>
            </>
          ) : (
            <div>
              <label>画面模板</label>
              <strong>还没有可用模板</strong>
              <span>请先到画面模板库维护模板。</span>
            </div>
          )}
          <Button onClick={() => setTemplatePickerOpen(true)} disabled={!templates.length}>
            更换模板
          </Button>
        </div>

        <div className="video-plan-card">
          <header className="video-plan-header">
            <div>
              <strong>画面规划</strong>
              <p>
                {videoPlan?.status === "ready"
                  ? `系统建议：${humanVideoPlanSummary(videoPlan)}`
                  : visualStrategy || "确认文案后，系统会根据本条视频目标生成推荐画面规划。"}
              </p>
            </div>
            <Tag color={planApplied ? "success" : videoPlan?.status === "ready" ? "processing" : "default"}>
              {planApplied ? "已使用推荐方案" : videoPlan?.status === "ready" ? "可一键使用" : "等待文案"}
            </Tag>
          </header>

          {videoPlan?.segments?.length ? (
            <div className="video-plan-list">
              {videoPlan.segments.map((segment) => (
                <div key={segment.segment_id} className="video-plan-item">
                  <span>{segment.index}</span>
                  <div>
                    <strong>{humanVideoPlanStep(segment)}</strong>
                    <em>{videoPlanMaterialHint(segment, videos)}</em>
                  </div>
                  <i className={`visual-type-pill ${segment.visual_type}`}>
                    {visualTypeLabel(segment.visual_type)}
                  </i>
                </div>
              ))}
            </div>
          ) : null}

          <footer className="video-plan-footer">
            <div>
              <strong>
                {groups.length
                  ? `已配置 ${groups.length} 个覆盖组`
                  : `当前 ${segments.length} 段文案，默认全程数字人`}
              </strong>
              <small>
                {groups.length
                  ? `覆盖 ${groups.reduce((sum, group) => sum + group.segment_ids.length, 0)} 段文案。`
                  : visualStrategy || "可打开画面规划，按段选择视频素材覆盖数字人画面。"}
              </small>
            </div>
            <Space wrap>
              <Button disabled={!videoPlan || !planGroups.length || planApplied} onClick={applyRecommendedPlan}>
                按方案生成
              </Button>
              <Button onClick={openStoryboard}>{videoPlan ? "手动调整" : "打开画面规划"}</Button>
            </Space>
          </footer>
        </div>

        <PostproductionMoreSettings session={session} bgm={bgm} patch={patch} />

        <div className="summary-box subtle">
          <span>视频素材库：{videos.length} 个素材可用于画面规划。</span>
          <Button size="small" onClick={() => openAssetTab("videos")}>
            管理视频素材库
          </Button>
        </div>
      </section>

      <aside className="production-preview-panel video-preview-panel">
        <div className="panel-titleline">
          <div>
            <strong>成片预览</strong>
            <span>{session.state.final_video_path ? "最终视频已生成，请确认画面和字幕。" : "生成中和生成后都会在这里展示。"}</span>
          </div>
          <Tag color={session.state.final_video_path ? "success" : busy ? "processing" : "default"}>
            {session.state.final_video_path ? "已生成" : busy ? "生成中" : "待生成"}
          </Tag>
        </div>
        <div className="vertical-preview-shell">
          {session.state.final_video_path ? (
            <ArtifactMediaPreview
              sessionId={session.session_id}
              artifactKey="final_video"
              kind="video"
              enabled={Boolean(session.state.final_video_path)}
            />
          ) : selectedTemplate ? (
            <div className="template-preview-placeholder">
              <AssetImage src={selectedTemplate.preview_url} alt={selectedTemplate.display_name} />
              <strong>{selectedTemplate.display_name}</strong>
              <span>{selectedTemplate.short_description}</span>
            </div>
          ) : (
            <div className="preview-empty-state">选择模板后可预览大致效果</div>
          )}
          {busy ? (
            <div className="preview-progress-overlay">
              <Loader2 className="spin" size={22} />
              <strong>正在生成成片</strong>
              <span>正在合成字幕、BGM 和画面规划...</span>
            </div>
          ) : null}
        </div>
        <div className="preview-meta-list">
          <div>
            <span>模板</span>
            <strong>{selectedTemplate?.display_name || "未选择"}</strong>
          </div>
          <div>
            <span>覆盖组</span>
            <strong>{groups.length} 组</strong>
          </div>
          <div>
            <span>BGM</span>
            <strong>{session.state.bgm_path ? "已选择" : "无 BGM"}</strong>
          </div>
        </div>
      </aside>

      <div className="panel-actions">
        <StepNavButtons step={step} goToStep={goToStep} />
        <div className="panel-primary-actions">
          {session.state.final_video_path ? (
            <>
            <button className="primary" onClick={() => goToStep(step + 1)} disabled={busy}>
              查看发布素材
            </button>
            <button className="secondary-action" onClick={() => execute("postproduction")} disabled={busy}>
              重新成片
            </button>
            </>
          ) : (
            <button className="primary" onClick={() => execute("postproduction")} disabled={busy}>
              {busy ? "正在成片..." : "一键成片"}
            </button>
          )}
        </div>
      </div>
      <TemplatePickerModal
        open={templatePickerOpen}
        templates={templates}
        selectedId={(selectedTemplate?.template_id as string) || ""}
        onClose={() => setTemplatePickerOpen(false)}
        onSelect={async (template) => {
          await patch({ template_id: template.template_id });
          setTemplatePickerOpen(false);
        }}
      />
    </div>
  );
}

function PostproductionMoreSettings({
  session,
  bgm,
  patch,
}: {
  session: IpBroadcastState;
  bgm: BgmAsset[];
  patch: (values: Record<string, unknown>) => Promise<void>;
}) {
  const [bgmPickerOpen, setBgmPickerOpen] = useState(false);
  const selectedBgm = bgm.find((item) => item.path === session.state.bgm_path);
  const bgmVolume = Number.isFinite(session.state.bgm_volume as number)
    ? (session.state.bgm_volume as number)
    : 0.3;

  return (
    <section className="more-settings-card">
      <header>
        <strong>更多配置</strong>
        <span>常用开关直接调，低频参数保持轻量。</span>
      </header>
      <div className="more-toggle-row">
        <span>添加解说字幕</span>
        <Switch
          checked={(session.state.subtitle_enabled as boolean) ?? true}
          onChange={(checked) => patch({ subtitle_enabled: checked })}
        />
        <span>剪辑静音停顿</span>
        <Switch
          checked={(session.state.remove_silence as boolean) || false}
          onChange={(checked) => patch({ remove_silence: checked })}
        />
      </div>
      <div className="more-settings-grid">
        <button className="more-setting-tile clickable" onClick={() => setBgmPickerOpen(true)}>
          <span className="compact-setting-icon">♪</span>
          <div>
            <strong>背景音乐：{selectedBgm?.name || "不使用 BGM"}</strong>
          </div>
          <i>›</i>
        </button>
        <div className="bgm-volume-compact">
          <span>音乐音量</span>
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={bgmVolume}
            onChange={(event) => patch({ bgm_volume: Number(event.target.value) })}
          />
          <strong>{Math.round(bgmVolume * 100)}%</strong>
        </div>
      </div>
      <BgmPickerModal
        open={bgmPickerOpen}
        bgm={bgm}
        selectedPath={(session.state.bgm_path as string) || ""}
        onClose={() => setBgmPickerOpen(false)}
        onConfirm={async (path) => {
          await patch({ bgm_path: path });
          setBgmPickerOpen(false);
        }}
      />
    </section>
  );
}

function BgmPickerModal({
  open,
  bgm,
  selectedPath,
  onClose,
  onConfirm,
}: {
  open: boolean;
  bgm: BgmAsset[];
  selectedPath: string;
  onClose: () => void;
  onConfirm: (path: string) => Promise<void>;
}) {
  const [tab, setTab] = useState<"library" | "custom">("library");
  const [draftPath, setDraftPath] = useState(selectedPath);

  useEffect(() => {
    if (open) {
      setDraftPath(selectedPath);
      setTab("library");
    }
  }, [open, selectedPath]);

  if (!open) return null;

  const items = bgm.filter((item) => (tab === "custom" ? item.source === "custom" : item.source !== "custom"));

  return (
    <div className="modal-backdrop asset-modal-backdrop">
      <section className="modal bgm-picker-modal">
        <div className="modal-title">
          <div>
            <h2>背景音乐</h2>
            <p>试听后选择适合本条视频的背景音乐，确认后才会应用。</p>
          </div>
          <button onClick={onClose}>关闭</button>
        </div>
        <div className="bgm-tabs">
          <button className={tab === "library" ? "selected" : ""} onClick={() => setTab("library")}>
            音乐库
          </button>
          <button className={tab === "custom" ? "selected" : ""} onClick={() => setTab("custom")}>
            我上传的
          </button>
        </div>
        <div className="bgm-picker-list">
          {tab === "library" ? (
            <button
              className={`bgm-picker-item ${draftPath === "" ? "selected" : ""}`}
              onClick={() => setDraftPath("")}
            >
              <span className="choice-summary-icon">无</span>
              <span>
                <strong>不使用 BGM</strong>
                <small>只保留口播原声和字幕。</small>
              </span>
            </button>
          ) : null}
          {items.map((item) => (
            <button
              key={`${item.source}-${item.path}`}
              className={`bgm-picker-item ${draftPath === item.path ? "selected" : ""}`}
              onClick={() => setDraftPath(item.path)}
            >
              <span className="choice-summary-icon">♪</span>
              <span>
                <strong>{item.name}</strong>
                <small>{item.source === "custom" ? "我上传的音乐" : "系统音乐库"}</small>
              </span>
              <BgmAudioPreview path={item.path} />
            </button>
          ))}
          {!items.length && tab === "custom" ? (
            <div className="empty-state">还没有上传的背景音乐。本轮先支持选择已有音乐，上传入口后续接入。</div>
          ) : null}
        </div>
        <div className="modal-actions">
          <Button onClick={onClose}>取消</Button>
          <Button type="primary" onClick={() => onConfirm(draftPath)}>
            确认使用
          </Button>
        </div>
      </section>
    </div>
  );
}

function BgmAudioPreview({ path }: { path: string }) {
  return (
    <span
      className="bgm-audio-preview"
      onClick={(event) => event.stopPropagation()}
    >
      <ProtectedMedia kind="audio" src={`/api/files/${path}`} />
    </span>
  );
}

function PublishStep({
  session,
  downloadFinalVideo,
}: {
  session: IpBroadcastState;
  downloadFinalVideo: () => Promise<void>;
}) {
  const [publishLoading, setPublishLoading] = useState(false);
  const [publishResult, setPublishResult] = useState<PublishResult | null>(null);
  const publishPackage = (session.state.publish_package as Record<string, unknown>) || {};
  const platformSuggestions =
    (publishPackage.platform_suggestions as Record<string, Record<string, unknown>>) ||
    ((session.state.platform_suggestions as Record<string, Record<string, unknown>>) ?? {});
  const title = (publishPackage.title as string) || (session.state.title as string) || "";
  const coverTitle = (publishPackage.cover_title as string) || title;
  const description =
    (publishPackage.description as string) || (session.state.description as string) || "";
  const commentCta = (publishPackage.comment_cta as string) || "";
  const hashtags = ((publishPackage.hashtags as string[]) || (session.state.hashtags as string[]) || []).join(
    " ",
  );
  const script = (publishPackage.script as string) || (session.state.final_script as string) || "";
  const publishReady = Boolean(session.artifacts.final_video || session.state.final_video_path);
  const coverReady = Boolean(session.artifacts.cover || session.state.cover_path);
  const finalVideoPath = (session.state.final_video_path as string) || "";
  const coverPath = (session.state.cover_path as string) || "";
  const hashtagList =
    ((publishPackage.hashtags as string[]) || (session.state.hashtags as string[]) || []).filter(Boolean);
  const fullPackageText = [
    coverTitle ? `封面大字：${coverTitle}` : "",
    title ? `标题：${title}` : "",
    description ? `描述：${description}` : "",
    commentCta ? `评论区引导：${commentCta}` : "",
    hashtags ? `话题标签：${hashtags}` : "",
    finalVideoPath ? `最终视频路径：${finalVideoPath}` : "最终视频：请先下载最终视频后上传。",
    coverPath ? `封面路径：${coverPath}` : "封面：请先下载封面后上传。",
    script ? `口播文案：\n${script}` : "",
  ]
    .filter(Boolean)
    .join("\n\n");
  const deliveryItems = [
    { label: "视频", ready: publishReady },
    { label: "封面", ready: coverReady },
    { label: "标题", ready: Boolean(title) },
    { label: "描述", ready: Boolean(description) },
    { label: "标签", ready: Boolean(hashtags) },
    { label: "口播文案", ready: Boolean(script) },
  ];
  const preferredPlatforms = readStringArray(
    publishPackage.preferred_platforms || session.state.business_publish_platforms,
  );
  const platformEntries = Object.entries(platformSuggestions);
  const preferredPlatformEntries = preferredPlatforms.length
    ? platformEntries.filter(([platform]) => preferredPlatforms.includes(platform))
    : platformEntries;
  const otherPlatformEntries = preferredPlatforms.length
    ? platformEntries.filter(([platform]) => !preferredPlatforms.includes(platform))
    : [];
  const renderPlatformCard = ([platform, value]: [string, Record<string, unknown>]) => {
    const platformText = buildPlatformMaterialText({
      platform,
      title: String(value.title || title || ""),
      description: String(value.description || description || ""),
      hashtags,
      commentCta,
      finalVideoPath,
      coverPath,
    });
    return (
      <section key={platform} className="platform-card">
        <div className="platform-capability-head">
          <Tag color="processing">{platformLabel(platform)}</Tag>
          <Tag color={platform === "douyin" ? "success" : "default"}>{publishCapabilityLabel(platform)}</Tag>
        </div>
        <strong>{String(value.title || "") || "暂无标题建议"}</strong>
        <p>{String(value.description || "") || "暂无描述建议"}</p>
        <small>{publishCapabilityDescription(platform)}</small>
        <CopyButton text={platformText} label="复制该平台素材" disabled={!publishReady} />
      </section>
    );
  };
  async function prepareDouyinDraft() {
    if (!finalVideoPath) return;
    setPublishLoading(true);
    setPublishResult(null);
    try {
      const result = await prepareDouyinPublish({
        session_id: session.session_id,
        platform: "douyin",
        video_path: finalVideoPath,
        title,
        description,
        hashtags: hashtagList,
        cover_path: coverPath,
      });
      setPublishResult(result);
    } catch (err) {
      setPublishResult({
        status: "failed",
        platform: "douyin",
        message: formatUiError(err),
      });
    } finally {
      setPublishLoading(false);
    }
  }
  return (
    <div className="publish-workbench">
      {publishResult ? (
        <Alert
          className="step-notice"
          type={publishResult.status === "failed" ? "error" : "info"}
          showIcon
          message={publishResult.message || publishStatusLabel(publishResult.status)}
        />
      ) : null}
      {publishReady ? (
        <Alert
          className="step-notice"
          type="info"
          showIcon
          message="发布助手会打开独立浏览器窗口，使用本机登录态填写抖音草稿；最终发布仍需要你在抖音页面确认。"
          description="当前发布能力：抖音草稿助手，其他平台复制素材手动发布。这不是全平台自动发布。登录数据只保存在本机 data/publish_browser/ 目录，不会随发布素材上传。"
        />
      ) : null}

      <div className="publish-layout">
        <div className="publish-main">
          <Card className={`publish-hero ${publishReady ? "" : "pending"}`} variant="borderless">
            <div className="publish-ready-head">
              <div>
                <Typography.Title level={4}>
                  {publishReady ? "发布任务就绪" : "还不能发布"}
                </Typography.Title>
                <Typography.Text type="secondary">
                  {publishReady
                    ? "视频、文案和平台素材已整理好，确认后可打开发布助手。"
                    : "请先完成一键成片，系统会生成最终视频和发布素材。"}
                </Typography.Text>
              </div>
              <Tag color={publishReady ? "success" : "default"}>
                {publishReady ? "可发布" : "待成片"}
              </Tag>
            </div>
            <PublishDeliveryChecklist items={deliveryItems} />
          </Card>

          <Card title="发布文案" variant="borderless">
            <PublishField
              label="封面大字"
              value={coverTitle}
              minRows={1}
              singleLine
              copyLabel="复制封面大字"
              disabled={!publishReady}
            />
            <PublishField label="标题" value={title} minRows={2} copyLabel="复制标题" disabled={!publishReady} />
            <PublishField label="描述" value={description} minRows={4} copyLabel="复制描述" disabled={!publishReady} />
            <PublishField
              label="评论区引导"
              value={commentCta}
              minRows={1}
              singleLine
              copyLabel="复制引导语"
              disabled={!publishReady}
            />
            <PublishField
              label="标签"
              value={hashtags}
              minRows={1}
              singleLine
              copyLabel="复制标签"
              disabled={!publishReady}
            />
            <PublishField
              label="口播文案"
              value={script}
              minRows={6}
              copyLabel="复制文案"
              disabled={!publishReady}
              extra={
                session.artifacts.script ? (
                  <Button onClick={() => downloadArtifact(session.session_id, "script")}>
                    下载文案
                  </Button>
                ) : null
              }
            />
          </Card>

          <Card title="发布平台" variant="borderless">
            <div className="platform-grid">
              {preferredPlatformEntries.map(renderPlatformCard)}
              {!Object.keys(platformSuggestions).length ? (
                <div className="empty-state">暂无平台建议。请先完成一键成片生成发布素材。</div>
              ) : null}
            </div>
            {otherPlatformEntries.length ? (
              <details className="platform-more">
                <summary>更多平台建议</summary>
                <div className="platform-grid">{otherPlatformEntries.map(renderPlatformCard)}</div>
              </details>
            ) : null}
          </Card>
        </div>

        <aside className="publish-aside">
          <Card className="publish-preview-card" title="发布预览" variant="borderless">
            <ArtifactVideoPreview
              sessionId={session.session_id}
              artifactKey="final_video"
              enabled={publishReady}
            />
            {coverReady ? (
              <>
                <Divider />
                <Typography.Text type="secondary">封面预览</Typography.Text>
                <ArtifactMediaPreview
                  sessionId={session.session_id}
                  artifactKey="cover"
                  kind="image"
                  enabled={coverReady}
                />
              </>
            ) : null}
            <Divider />
            <div className="publish-side-actions">
              <Button
                type="primary"
                block
                disabled={!publishReady || !finalVideoPath}
                loading={publishLoading}
                onClick={prepareDouyinDraft}
              >
                打开抖音发布助手
              </Button>
              <CopyButton
                text={fullPackageText}
                label="复制整套素材"
                disabled={!publishReady}
              />
            </div>
            <Space direction="vertical" className="publish-file-actions">
              {publishReady ? (
                <Button block onClick={downloadFinalVideo}>
                  下载最终视频
                </Button>
              ) : null}
              {session.artifacts.publish_package_json ? (
                <Button block onClick={() => downloadArtifact(session.session_id, "publish_package_json")}>
                  下载发布素材 JSON
                </Button>
              ) : null}
            </Space>
            <Divider />
            <Typography.Text type="secondary">最终视频路径</Typography.Text>
            <p className="result-path">{(session.state.final_video_path as string) || "暂无最终视频"}</p>
          </Card>
        </aside>
      </div>
    </div>
  );
}

function PublishField({
  label,
  value,
  minRows,
  singleLine = false,
  extra,
  disabled = false,
  copyLabel = "复制",
}: {
  label: string;
  value: string;
  minRows: number;
  singleLine?: boolean;
  extra?: ReactNode;
  disabled?: boolean;
  copyLabel?: string;
}) {
  return (
    <section className="publish-field">
      <div className="publish-field-title">
        <strong>{label}</strong>
        <Space>
          {extra}
          <CopyButton text={value} label={copyLabel} disabled={disabled} />
        </Space>
      </div>
      {singleLine ? <input readOnly value={value} /> : <textarea readOnly value={value} rows={minRows} />}
    </section>
  );
}

function PublishDeliveryChecklist({ items }: { items: Array<{ label: string; ready: boolean }> }) {
  return (
    <section className="publish-delivery-checklist" aria-label="发布素材交付清单">
      {items.map((item) => (
        <div key={item.label} className={item.ready ? "ready" : "missing"}>
          <span>{item.label}</span>
          <Tag color={item.ready ? "success" : "default"}>{item.ready ? "已准备" : "缺失"}</Tag>
        </div>
      ))}
    </section>
  );
}

function CopyButton({
  text,
  label = "复制",
  disabled = false,
}: {
  text: string;
  label?: string;
  disabled?: boolean;
}) {
  const [status, setStatus] = useState<"idle" | "success" | "error">("idle");
  async function copyText() {
    try {
      await navigator.clipboard.writeText(text);
      setStatus("success");
    } catch {
      setStatus("error");
    }
    window.setTimeout(() => setStatus("idle"), 1800);
  }
  return (
    <Button onClick={copyText} disabled={disabled || !text} danger={status === "error"}>
      {status === "success" ? "已复制" : status === "error" ? "复制失败" : label}
    </Button>
  );
}

function platformLabel(platform: string) {
  return (
    {
      douyin: "抖音",
      xiaohongshu: "小红书",
      shipinhao: "视频号",
      kuaishou: "快手",
    }[platform] || platform
  );
}

function publishCapabilityLabel(platform: string) {
  return platform === "douyin" ? "抖音草稿助手" : "复制素材手动发布";
}

function publishCapabilityDescription(platform: string) {
  return platform === "douyin"
    ? "可打开本机浏览器填写抖音草稿，最终发布仍需人工确认。"
    : "当前不是全平台自动发布，请复制标题、描述、标签和视频素材到平台后台手动发布。";
}

function buildPlatformMaterialText({
  platform,
  title,
  description,
  hashtags,
  commentCta,
  finalVideoPath,
  coverPath,
}: {
  platform: string;
  title: string;
  description: string;
  hashtags: string;
  commentCta: string;
  finalVideoPath: string;
  coverPath: string;
}) {
  return [
    `平台：${platformLabel(platform)}`,
    `发布方式：${publishCapabilityLabel(platform)}`,
    title ? `标题：${title}` : "",
    description ? `描述：${description}` : "",
    hashtags ? `话题标签：${hashtags}` : "",
    commentCta ? `评论区引导：${commentCta}` : "",
    finalVideoPath ? `最终视频路径：${finalVideoPath}` : "最终视频：请先下载最终视频后上传。",
    coverPath ? `封面路径：${coverPath}` : "封面：请先下载封面后上传。",
  ]
    .filter(Boolean)
    .join("\n");
}

function publishStatusLabel(status: PublishResult["status"]) {
  return (
    {
      login_required: "请先在发布助手浏览器中登录平台账号。",
      uploading: "正在上传视频。",
      draft_ready: "发布草稿已准备好，请最终确认后发布。",
      failed: "发布助手执行失败。",
      cancelled: "发布助手已停止。",
    }[status] || status
  );
}

function humanGoalLabel(preset: IpPresetAsset) {
  return (
    {
      group_buying: "推一个团购套餐",
      store_visit: "拍一条门店种草",
      new_product: "介绍一个新品",
      boss_persona: "老板出镜讲经验",
      customer_case: "讲一个客户案例",
    }[preset.preset_id] || preset.display_name
  );
}

function sourceActionLabel(sourceMode: string, topicCount = 0) {
  return (
    {
      video_extract: "提取视频口播文案",
      paste: "整理为口播文案",
      industry_persona: "生成口播文案",
      ip_learning: topicCount ? "用选题生成文案" : "学习最近 5 条视频",
    }[sourceMode] || "生成口播文案"
  );
}

function completedProductionSteps(session: IpBroadcastState) {
  if (session.state.final_video_path || session.artifacts.final_video) return 5;
  if (session.state.digital_human_video_path || session.artifacts.digital_human_video) return 3;
  if (session.state.audio_path || session.artifacts.audio) return 2;
  if (session.state.final_script) return 1;
  return 0;
}

function uiStepStatus(session: IpBroadcastState, step: number) {
  const oldStatus = session.step_status || {};
  if (step === 1) {
    if (oldStatus["1"] === "error" || oldStatus["2"] === "error") return "error";
    if (oldStatus["1"] === "running" || oldStatus["2"] === "running") return "running";
    if (oldStatus["2"] === "done" || session.state.copywriting_confirmed) return "done";
    if (session.state.final_script || oldStatus["1"] === "done") return "ready";
    return oldStatus["1"] || "pending";
  }
  const oldStep = String(step + 1);
  return oldStatus[oldStep] || "pending";
}

function uiStepNotice(session: IpBroadcastState, step: number) {
  if (step === 1) {
    return session.notices["2"] || session.notices["1"];
  }
  return session.notices[String(step + 1)];
}

function humanVideoPlanSummary(plan: VideoPlan) {
  const uploadedCount = plan.segments.filter((segment) => segment.visual_type === "uploaded_video").length;
  if (!uploadedCount) return "老板全程出镜，先保证视频能快速发布";
  return "老板开头讲清楚重点，中间插入门店/产品画面，结尾回到老板提醒行动";
}

function humanVideoPlanStep(segment: VideoPlanSegment) {
  if (segment.visual_type === "uploaded_video") {
    if (segment.asset_keywords.some((keyword) => ["菜品", "套餐", "产品", "新品"].includes(keyword))) {
      return "中间插入套餐/菜品画面";
    }
    if (segment.asset_keywords.some((keyword) => ["门店", "环境", "门头"].includes(keyword))) {
      return "中间插入门店环境画面";
    }
    return "中间插入门店实拍画面";
  }
  if (segment.index === 1) return "开头老板出镜讲重点";
  return "老板出镜继续讲";
}

function videoPlanMaterialHint(segment: VideoPlanSegment, videos: VideoAsset[]) {
  if (segment.visual_type !== "uploaded_video") return "默认数字人";
  const matched = findMatchingVideoAsset(segment.asset_keywords, videos);
  if (matched) return `已找到：${matched.name}`;
  const label = segment.asset_keywords.slice(0, 2).join("/") || "门店";
  return `建议补一段${label}视频，素材名称写清楚即可`;
}

function visualTypeLabel(visualType: VisualGroup["visual_type"] | VideoPlanSegment["visual_type"]) {
  return (
    {
      digital_human: "数字人",
      uploaded_video: "素材覆盖",
      ai_video: "AI 视频",
    }[visualType] || "数字人"
  );
}

function stepStatusLabel(status: string) {
  return (
    {
      pending: "未开始",
      ready: "可执行",
      running: "进行中",
      done: "已完成",
      error: "失败",
    }[status] || status
  );
}

function stepAntdStatus(status: string): "wait" | "process" | "finish" | "error" {
  if (status === "done") return "finish";
  if (status === "error") return "error";
  if (status === "ready" || status === "running") return "process";
  return "wait";
}

function noticeKind(kind: string): "success" | "info" | "warning" | "error" {
  if (kind === "success") return "success";
  if (kind === "error") return "error";
  if (kind === "warning") return "warning";
  return "info";
}

function stepNumberForTaskKey(stepKey: string) {
  return (
    {
      source: 1,
      copywriting: 1,
      voice: 3,
      digital_human: 4,
      postproduction: 5,
      publish: 6,
    }[stepKey] || 0
  );
}

function StepNavButtons({ step, goToStep }: { step: number; goToStep: (step: number) => void }) {
  return (
    <div className="step-nav-actions">
      <button disabled={step <= 1} onClick={() => goToStep(step - 1)}>
        上一步
      </button>
      <button disabled={step >= stepTitles.length} onClick={() => goToStep(step + 1)}>
        下一步
      </button>
    </div>
  );
}

function StoryboardModal({
  session,
  videos,
  patch,
  reloadAssets,
  openAssetTab,
  onClose,
}: {
  session: IpBroadcastState;
  videos: VideoAsset[];
  patch: (values: Record<string, unknown>) => Promise<void>;
  reloadAssets: () => Promise<void>;
  openAssetTab: (tab: AssetTab) => void;
  onClose: () => void;
}) {
  const segments = splitSegments((session.state.final_script as string) || "");
  const [selected, setSelected] = useState<string[]>([]);
  const [groups, setGroups] = useState<VisualGroup[]>(readGroups(session.state.visual_groups));
  const coveredSegmentCount = groups.reduce((sum, group) => sum + group.segment_ids.length, 0);
  const selectedIndexes = selected
    .map((segmentId) => segments.find((segment) => segment.segment_id === segmentId)?.index ?? 0)
    .sort((a, b) => a - b);
  const canCreate =
    selectedIndexes.length > 0 &&
    selectedIndexes.every((index, i) => i === 0 || index === selectedIndexes[i - 1] + 1);

  function toggleSegment(segmentId: string) {
    setSelected((current) =>
      current.includes(segmentId)
        ? current.filter((item) => item !== segmentId)
        : [...current, segmentId],
    );
  }

  function createGroup() {
    if (!canCreate) return;
    setGroups((current) => [
      ...current,
      {
        group_id: `group_${Date.now()}`,
        segment_ids: selected,
        visual_type: "uploaded_video",
        prompt: "",
        uploaded_video_path: "",
        video_asset_id: "",
        status: "pending",
      },
    ]);
    setSelected([]);
  }

  function groupForSegment(segmentId: string) {
    return groups.find((group) => group.segment_ids.includes(segmentId));
  }

  async function save() {
    await patch({
      story_segments: segments,
      visual_groups: groups,
      overlay_enabled: groups.length > 0,
    });
    onClose();
  }

  return (
    <div className="modal-backdrop">
      <section className="modal large">
        <div className="modal-title">
          <div>
            <h2>画面规划</h2>
            <p>按视频播放顺序管理画面覆盖。左侧勾选连续段落，右侧设置覆盖方式。</p>
          </div>
          <button onClick={onClose}>关闭</button>
        </div>
        <div className="storyboard-summary-bar">
          <span>共 {segments.length} 段文案</span>
          <span>{groups.length ? `${groups.length} 个覆盖组` : "未创建覆盖组"}</span>
          <span>{coveredSegmentCount ? `已覆盖 ${coveredSegmentCount} 段` : "默认全程数字人"}</span>
        </div>
        <div className="storyboard-layout">
          <div className="storyboard-timeline-panel">
            <div className="storyboard-panel-title">
              <strong>视频顺序</strong>
              <small>黄色表示会用视频素材或 AI 视频覆盖数字人画面。</small>
            </div>
            {segments.length ? (
              <div className="storyboard-timeline">
                {segments.map((segment) => {
                  const group = groupForSegment(segment.segment_id);
                  const selectedSegment = selected.includes(segment.segment_id);
                  const visualType = group?.visual_type || "digital_human";
                  return (
                    <label
                      key={segment.segment_id}
                      className={`storyboard-timeline-item ${selectedSegment ? "selected" : ""}`}
                    >
                      <input
                        type="checkbox"
                        checked={selectedSegment}
                        onChange={() => toggleSegment(segment.segment_id)}
                      />
                      <span className="timeline-index">{segment.index}</span>
                      <div>
                        <header>
                          <strong>第 {segment.index} 段</strong>
                          <i className={`visual-type-pill ${visualType}`}>{visualTypeLabel(visualType)}</i>
                        </header>
                        <p>{segment.text}</p>
                        <small>
                          {group
                            ? `属于覆盖组：段落 ${group.segment_ids.join(", ")}`
                            : "未覆盖，使用数字人画面。"}
                        </small>
                      </div>
                    </label>
                  );
                })}
              </div>
            ) : (
              <div className="empty-state">暂无可拆分文案。请先在第 2 步填写最终口播文案。</div>
            )}
            <div className="storyboard-create-row">
              <button disabled={!canCreate} onClick={createGroup}>
                勾选段落成组
              </button>
              <small>{selected.length ? `已选 ${selected.length} 段` : "先勾选需要覆盖的连续段落"}</small>
            </div>
            {selected.length && !canCreate ? (
              <small className="task-error">v1 只支持连续段落成组。</small>
            ) : null}
          </div>
          <div className="storyboard-groups">
            <div className="storyboard-panel-title">
              <strong>覆盖组设置</strong>
              <small>每组可以保持数字人、选择视频素材，或填写 AI 视频提示词。</small>
            </div>
            {groups.length ? (
              groups.map((group) => (
                <GroupEditor
                  key={group.group_id}
                  group={group}
                  videos={videos}
                  reloadAssets={reloadAssets}
                  openAssetTab={openAssetTab}
                  update={(updated) =>
                    setGroups((current) =>
                      current.map((item) => (item.group_id === group.group_id ? updated : item)),
                    )
                  }
                  remove={() =>
                    setGroups((current) => current.filter((item) => item.group_id !== group.group_id))
                  }
                />
              ))
            ) : (
              <div className="empty-state">未创建覆盖组，默认全程使用数字人画面。</div>
            )}
          </div>
        </div>
        <div className="modal-actions">
          <button onClick={onClose}>取消</button>
          <button className="primary" onClick={save}>
            保存规划
          </button>
        </div>
      </section>
    </div>
  );
}

function GroupEditor({
  group,
  videos,
  reloadAssets,
  openAssetTab,
  update,
  remove,
}: {
  group: VisualGroup;
  videos: VideoAsset[];
  reloadAssets: () => Promise<void>;
  openAssetTab: (tab: AssetTab) => void;
  update: (group: VisualGroup) => void;
  remove: () => void;
}) {
  const [addVideoOpen, setAddVideoOpen] = useState(false);
  const [videoPickerOpen, setVideoPickerOpen] = useState(false);
  const selectedVideo = videos.find((item) => item.asset_id === group.video_asset_id);

  return (
    <section className="group-card">
      <div className="card-title">
        <strong>段落 {group.segment_ids.join(", ")}</strong>
        <button onClick={remove}>删除</button>
      </div>
      <label>画面类型</label>
      <select
        value={group.visual_type}
        onChange={(event) =>
          update({ ...group, visual_type: event.target.value as VisualGroup["visual_type"] })
        }
      >
        <option value="uploaded_video">视频素材覆盖</option>
        <option value="ai_video">AI 视频</option>
        <option value="digital_human">保持数字人</option>
      </select>
      {group.visual_type === "uploaded_video" ? (
        <>
          <div className="section-title inline-section-title">
            <span>视频素材</span>
            <Space size={8}>
              <Button size="small" onClick={() => setVideoPickerOpen(true)}>
                选择视频素材
              </Button>
              <Button size="small" type="primary" onClick={() => setAddVideoOpen(true)}>
                + 添加
              </Button>
              <Button size="small" onClick={() => openAssetTab("videos")}>
                管理视频素材库
              </Button>
            </Space>
          </div>
          <div className="selected-video-summary">
            {selectedVideo ? (
              <>
                {selectedVideo.thumbnail_exists ? (
                  <AssetImage src={selectedVideo.thumbnail_url} alt={selectedVideo.name} />
                ) : (
                  <div className="video-thumb">VIDEO</div>
                )}
                <div>
                  <strong>{selectedVideo.name}</strong>
                  <span>{selectedVideo.duration ? `${selectedVideo.duration}s` : selectedVideo.filename}</span>
                </div>
              </>
            ) : (
              <span>未选择视频素材。点击“选择视频素材”从素材库中选择。</span>
            )}
          </div>
          <VideoAssetPickerModal
            open={videoPickerOpen}
            videos={videos}
            selectedId={group.video_asset_id}
            onClose={() => setVideoPickerOpen(false)}
            onSelect={(video) => {
              update({
                ...group,
                video_asset_id: video.asset_id,
                uploaded_video_path: video.asset_path,
              });
              setVideoPickerOpen(false);
            }}
          />
          <SimpleAssetModal
            open={addVideoOpen}
            title="添加视频素材"
            description="起个你自己看得懂的名字，系统会根据名称帮你推荐到合适的视频里。"
            assetNameLabel="视频素材名称"
            namePlaceholder="例如：双人火锅套餐、门店环境、锅底翻滚、顾客用餐"
            fileLabel="覆盖视频"
            accept="video/*"
            upload={uploadVideoAsset}
            onClose={() => setAddVideoOpen(false)}
            onUploaded={async (video) => {
              update({
                ...group,
                video_asset_id: video.asset_id,
                uploaded_video_path: video.asset_path,
              });
              await reloadAssets();
              setAddVideoOpen(false);
            }}
          />
        </>
      ) : null}
      {group.visual_type === "ai_video" ? (
        <>
          <label>AI 视频 Prompt</label>
          <textarea
            className="small-textarea"
            value={group.prompt}
            onChange={(event) => update({ ...group, prompt: event.target.value })}
          />
        </>
      ) : null}
    </section>
  );
}

function VideoAssetPickerModal({
  open,
  videos,
  selectedId,
  onClose,
  onSelect,
}: {
  open: boolean;
  videos: VideoAsset[];
  selectedId: string;
  onClose: () => void;
  onSelect: (video: VideoAsset) => void;
}) {
  const [query, setQuery] = useState("");
  const filteredVideos = videos.filter((video) => {
    const keyword = query.trim().toLowerCase();
    if (!keyword) return true;
    return `${video.name} ${video.filename}`.toLowerCase().includes(keyword);
  });

  if (!open) return null;

  return (
    <div className="modal-backdrop asset-modal-backdrop">
      <section className="modal video-picker-modal">
        <div className="modal-title">
          <div>
            <h2>选择视频素材</h2>
            <p>按名称或文件名搜索。建议素材命名清楚，例如“锅底翻滚”“门店环境”。</p>
          </div>
          <button onClick={onClose}>关闭</button>
        </div>
        <input
          className="video-picker-search"
          placeholder="搜索视频名称或文件名"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <div className="video-picker-grid">
          {filteredVideos.map((video) => (
            <button
              key={video.asset_id}
              className={`video-picker-card ${selectedId === video.asset_id ? "selected" : ""}`}
              onClick={() => onSelect(video)}
            >
              {video.thumbnail_exists ? (
                <AssetImage src={video.thumbnail_url} alt={video.name} />
              ) : (
                <div className="video-thumb">VIDEO</div>
              )}
              <strong>{video.name}</strong>
              <span>{video.duration ? `${video.duration}s` : video.filename}</span>
            </button>
          ))}
          {!filteredVideos.length ? <div className="empty-state">没有匹配的视频素材。</div> : null}
        </div>
      </section>
    </div>
  );
}

function TemplatePickerModal({
  open,
  templates,
  selectedId,
  onClose,
  onSelect,
}: {
  open: boolean;
  templates: IpTemplateAsset[];
  selectedId: string;
  onClose: () => void;
  onSelect: (template: IpTemplateAsset) => void | Promise<void>;
}) {
  const [query, setQuery] = useState("");
  const filteredTemplates = templates.filter((template) => {
    const keyword = query.trim().toLowerCase();
    if (!keyword) return true;
    return `${template.display_name} ${template.short_description} ${template.full_description}`
      .toLowerCase()
      .includes(keyword);
  });

  if (!open) return null;

  return (
    <div className="modal-backdrop asset-modal-backdrop">
      <section className="modal template-picker-modal">
        <div className="modal-title">
          <div>
            <h2>选择画面模板</h2>
            <p>模板会影响封面标题、字幕位置和整体视觉风格。</p>
          </div>
          <button onClick={onClose}>关闭</button>
        </div>
        <input
          className="video-picker-search"
          placeholder="搜索模板名称或风格"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <div className="template-picker-grid">
          {filteredTemplates.map((template) => (
            <button
              key={template.template_id}
              className={`template-picker-card ${selectedId === template.template_id ? "selected" : ""}`}
              onClick={() => onSelect(template)}
              title={template.full_description}
            >
              <AssetImage src={template.preview_url} alt={template.display_name} />
              <div>
                <strong>{template.display_name}</strong>
                <span>{template.short_description}</span>
              </div>
              {selectedId === template.template_id ? <i>当前使用</i> : null}
            </button>
          ))}
          {!filteredTemplates.length ? <div className="empty-state">没有匹配的画面模板。</div> : null}
        </div>
      </section>
    </div>
  );
}

function AssetPreviewModal({
  preview,
  onClose,
}: {
  preview: AssetPreview | null;
  onClose: () => void;
}) {
  if (!preview) return null;

  return (
    <div className="modal-backdrop asset-modal-backdrop">
      <section className="modal asset-preview-modal">
        <div className="modal-title">
          <div>
            <h2>{preview.title}</h2>
            <p>{preview.kind === "audio" ? "音色试听" : "素材预览"}</p>
          </div>
          <button onClick={onClose}>关闭</button>
        </div>
        <div className={`asset-preview-body ${preview.kind}`}>
          {preview.kind === "audio" ? <ProtectedMedia kind="audio" src={preview.src} /> : null}
          {preview.kind === "image" ? <AssetImage src={preview.src} alt={preview.title} /> : null}
          {preview.kind === "video" ? <ProtectedMedia kind="video" src={preview.src} /> : null}
        </div>
      </section>
    </div>
  );
}

function ConfirmDeleteModal({
  pending,
  onClose,
}: {
  pending: PendingDelete | null;
  onClose: () => void;
}) {
  const [loading, setLoading] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  if (!pending) return null;

  async function confirmDelete() {
    if (!pending) return;
    setLoading(true);
    setDeleteError("");
    try {
      await pending.confirm();
      onClose();
    } catch (err) {
      setDeleteError(formatUiError(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="modal-backdrop asset-modal-backdrop">
      <section className="modal confirm-delete-modal">
        <div className="modal-title">
          <div>
            <h2>{pending.title}</h2>
            <p>删除后无法在当前素材库恢复；已生成的视频不受影响，但后续任务不能再选择这个素材。</p>
          </div>
          <button type="button" onClick={onClose}>关闭</button>
        </div>
        <div className="confirm-delete-body">
          <strong>{pending.name}</strong>
          <span>{pending.description}</span>
        </div>
        {deleteError ? <Alert type="error" showIcon message={`删除失败：${deleteError}`} /> : null}
        <div className="modal-actions">
          <Button onClick={onClose}>取消</Button>
          <Button danger type="primary" loading={loading} onClick={confirmDelete}>
            {pending.confirmLabel}
          </Button>
        </div>
      </section>
    </div>
  );
}

function AddAssetCard({
  title,
  description,
  onClick,
  className = "",
}: {
  title: string;
  description: string;
  onClick: () => void;
  className?: string;
}) {
  return (
    <button className={`asset-card add-asset-card ${className}`} onClick={onClick}>
      <span className="add-asset-icon">+</span>
      <strong>{title}</strong>
      <span>{description}</span>
    </button>
  );
}

function SimpleAssetModal<TAsset>({
  open,
  title,
  description,
  assetNameLabel,
  namePlaceholder = "可选，默认使用文件名",
  fileLabel,
  accept,
  upload,
  onClose,
  onUploaded,
  submitLabel = "保存并使用",
  successNote = "保存成功后：关闭弹窗 → 刷新素材 → 自动选中。",
  successMessage = "已保存到素材库并选中。",
}: {
  open: boolean;
  title: string;
  description: string;
  assetNameLabel: string;
  namePlaceholder?: string;
  fileLabel: string;
  accept: string;
  upload: (name: string, file: File) => Promise<TAsset>;
  onClose: () => void;
  onUploaded: (asset: TAsset) => Promise<void>;
  submitLabel?: string;
  successNote?: string;
  successMessage?: string;
}) {
  const [name, setName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function submit() {
    if (!file) return;
    setMessage("");
    setError("");
    try {
      const asset = await upload(name || file.name, file);
      await onUploaded(asset);
      setName("");
      setFile(null);
      setMessage(successMessage);
    } catch (err) {
      setError(String(err));
    }
  }

  if (!open) return null;

  return (
    <div className="modal-backdrop asset-modal-backdrop">
      <section className="modal asset-modal">
        <div className="modal-title">
          <div>
            <h2>{title}</h2>
            <p>{description}</p>
          </div>
          <button onClick={onClose}>关闭</button>
        </div>
        <div className="asset-modal-grid single-name">
          <div>
            <label>{assetNameLabel}</label>
            <input
              placeholder={namePlaceholder}
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </div>
        </div>
        <FileUploadPanel
          label={fileLabel}
          hint={assetModalHintText(title)}
          accept={accept}
          file={file}
          onChange={setFile}
        />
        <div className="asset-modal-success-note">{successNote}</div>
        {message ? <div className="notice success">{message}</div> : null}
        {error ? <div className="notice error">{error}</div> : null}
        <div className="modal-actions">
          <button onClick={onClose}>取消</button>
          <button className="primary" disabled={!file} onClick={submit}>
            {submitLabel}
          </button>
        </div>
      </section>
    </div>
  );
}

function VoiceAssetModal({
  open,
  onClose,
  onUploaded,
  submitLabel = "保存并使用",
  successNote = "保存成功后：关闭弹窗 → 刷新素材 → 自动选中。",
  successMessage = "已保存到音色库并选中。",
}: {
  open: boolean;
  onClose: () => void;
  onUploaded: (voice: VoiceAsset) => Promise<void>;
  submitLabel?: string;
  successNote?: string;
  successMessage?: string;
}) {
  const [mode, setMode] = useState<"upload" | "record">("upload");
  const [name, setName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function submitUpload() {
    if (!file) return;
    setMessage("");
    setError("");
    try {
      const voice = await uploadVoiceAsset(name || file.name, file);
      await onUploaded(voice);
      setName("");
      setFile(null);
      setMessage(successMessage);
    } catch (err) {
      setError(String(err));
    }
  }

  if (!open) return null;

  return (
    <div className="modal-backdrop asset-modal-backdrop">
      <section className="modal asset-modal">
        <div className="modal-title">
          <div>
            <h2>添加参考音色</h2>
            <p>上传或录制后保存到音色库，并自动选中。</p>
          </div>
          <button onClick={onClose}>关闭</button>
        </div>
        <div className="asset-modal-tabs">
          <button className={mode === "upload" ? "active" : ""} onClick={() => setMode("upload")}>
            从文件添加
          </button>
          <button className={mode === "record" ? "active" : ""} onClick={() => setMode("record")}>
            直接录一段
          </button>
        </div>
        {mode === "upload" ? (
          <>
            <div className="asset-modal-grid single-name">
              <div>
                <label>素材名称</label>
                <input
                  placeholder="可选，默认使用文件名"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                />
              </div>
            </div>
            <FileUploadPanel
              label="参考音频"
              hint="建议上传 30 秒以内的老板本人或品牌常用声音，背景安静、说话清晰。"
              accept="audio/*"
              file={file}
              onChange={setFile}
            />
            <div className="asset-modal-success-note">{successNote}</div>
            <div className="modal-actions">
              <button onClick={onClose}>取消</button>
              <button className="primary" disabled={!file} onClick={submitUpload}>
                {submitLabel}
              </button>
            </div>
          </>
        ) : (
          <VoiceRecorder onRecorded={onUploaded} />
        )}
        {message ? <div className="notice success">{message}</div> : null}
        {error ? <div className="notice error">{error}</div> : null}
      </section>
    </div>
  );
}

function FileUploadPanel({
  label,
  hint,
  accept,
  file,
  onChange,
}: {
  label: string;
  hint: ReactNode;
  accept: string;
  file: File | null;
  onChange: (file: File | null) => void;
}) {
  const isVideoUpload = accept.includes("video");
  const isAudioUpload = accept.includes("audio");
  const isImageUpload = accept.includes("image");
  const uploadKind = isAudioUpload ? "audio" : isImageUpload && isVideoUpload ? "mixed" : isVideoUpload ? "video" : "image";
  return (
    <div className="asset-upload-panel">
      <p className="asset-upload-rule">
        {uploadRuleText(uploadKind)}
        <span>素材规范</span>
      </p>
      <FileDropField
        accept={accept}
        label={label}
        file={file}
        onChange={onChange}
        title={file ? "已选择素材" : "点击上传"}
        description={file ? file.name : hint}
        kind={uploadKind}
      />
    </div>
  );
}

function uploadRuleText(kind: "image" | "video" | "audio" | "mixed") {
  if (kind === "audio") {
    return "支持 MP3/WAV/FLAC 音频，建议上传 30 秒以内，背景安静、说话清晰。";
  }
  if (kind === "mixed") {
    return "支持 JPG/PNG 图片或 MP4/MOV 视频，建议正面、光线稳定、脸部清晰。";
  }
  if (kind === "video") {
    return "支持 MP4/MOV 视频，建议上传门店环境、菜品特写、服务过程或顾客体验素材。";
  }
  return "支持 JPG/PNG 图片，建议正面、光线稳定、脸部清晰。";
}

function FileDropField({
  accept,
  label,
  file,
  onChange,
  title,
  description,
  kind,
}: {
  accept: string;
  label: string;
  file: File | null;
  onChange: (file: File | null) => void;
  title: string;
  description: ReactNode;
  kind: "image" | "video" | "audio" | "mixed";
}) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const inputId = useId();
  return (
    <label
      className={`file-drop-field ${file ? "has-file" : ""}`}
      htmlFor={inputId}
      role="button"
      tabIndex={0}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          inputRef.current?.click();
        }
      }}
    >
      <span className="file-drop-icon">
        {kind === "audio" ? <Mic2 size={34} /> : kind === "video" ? <Video size={34} /> : <Images size={34} />}
      </span>
      <strong>{title}</strong>
      <small>{description}</small>
      <input
        id={inputId}
        aria-label={label}
        ref={inputRef}
        type="file"
        accept={accept}
        onClick={(event) => {
          event.currentTarget.value = "";
        }}
        onChange={(event) => onChange(event.target.files?.[0] || null)}
      />
    </label>
  );
}

function AssetModalHint({ children }: { children: ReactNode }) {
  return (
    <div className="asset-modal-hint">
      <span className="asset-modal-dot" />
      <p>{children}</p>
    </div>
  );
}

function assetModalHintText(title: string) {
  if (title.includes("形象")) {
    return "建议上传正面、光线稳定、脸部清晰的图片或闭口视频。";
  }
  if (title.includes("视频")) {
    return "建议用老板自己看得懂的名字，例如“双人火锅套餐”“门店环境”。系统只按名称做轻量推荐，不做复杂分类。";
  }
  return "保存后会进入素材库，并自动选中当前素材。";
}

function VoiceRecorder({ onRecorded }: { onRecorded: (voice: VoiceAsset) => Promise<void> }) {
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const [recording, setRecording] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function startRecording() {
    setMessage("");
    setError("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      chunksRef.current = [];
      const recorder = new MediaRecorder(stream);
      recorderRef.current = recorder;
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.onstop = async () => {
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
        const file = new File([blob], `recorded_voice_${Date.now()}.webm`, {
          type: blob.type || "audio/webm",
        });
        try {
          const voice = await uploadVoiceAsset(file.name, file);
          await onRecorded(voice);
          setMessage("录音已保存到音色库并选中。");
        } catch (err) {
          setError(String(err));
        } finally {
          streamRef.current?.getTracks().forEach((track) => track.stop());
          streamRef.current = null;
          recorderRef.current = null;
          chunksRef.current = [];
          setRecording(false);
        }
      };
      recorder.start();
      setRecording(true);
    } catch (err) {
      setError(String(err));
      setRecording(false);
    }
  }

  function stopRecording() {
    recorderRef.current?.stop();
  }

  return (
    <section className="asset-record-panel">
      <span className="asset-modal-dot recording" />
      <strong>直接录制参考音</strong>
      <small>录完会保存到音色库并自动选中。</small>
      <Space wrap>
        <Button type={recording ? "default" : "primary"} onClick={recording ? stopRecording : startRecording}>
          {recording ? "停止并保存" : "开始录音"}
        </Button>
        {recording ? <Tag color="processing">录音中</Tag> : null}
      </Space>
      {message ? <div className="notice success">{message}</div> : null}
      {error ? <div className="notice error">{error}</div> : null}
    </section>
  );
}

function AssetsView({
  assets,
  activeTab,
  setActiveTab,
  reload,
}: {
  assets: AssetState;
  activeTab: AssetTab;
  setActiveTab: (tab: AssetTab) => void;
  reload: () => Promise<void>;
}) {
  const tabs: Array<{ key: AssetTab; label: string; icon: ReactNode }> = [
    { key: "voices", label: "音色库", icon: <Mic2 size={16} /> },
    { key: "portraits", label: "形象库", icon: <UserSquare2 size={16} /> },
    { key: "templates", label: "画面模板库", icon: <Images size={16} /> },
    { key: "videos", label: "视频素材库", icon: <Video size={16} /> },
    { key: "brands", label: "品牌包", icon: <Package size={16} /> },
  ];
  return (
    <section className="asset-center">
      <div className="tabs">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            className={activeTab === tab.key ? "active" : ""}
            onClick={() => setActiveTab(tab.key)}
          >
            {tab.icon} {tab.label}
          </button>
        ))}
      </div>
      {activeTab === "voices" ? <VoiceLibrary items={assets.voices} reload={reload} /> : null}
      {activeTab === "portraits" ? <PortraitLibrary items={assets.portraits} reload={reload} /> : null}
      {activeTab === "templates" ? <TemplateLibrary items={assets.templates} /> : null}
      {activeTab === "videos" ? <VideoLibrary items={assets.videos} reload={reload} /> : null}
      {activeTab === "brands" ? <BrandKitLibrary items={assets.brands} reload={reload} /> : null}
    </section>
  );
}

function VoiceLibrary({ items, reload }: { items: VoiceAsset[]; reload: () => Promise<void> }) {
  const [preview, setPreview] = useState<AssetPreview | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<PendingDelete | null>(null);
  return (
    <>
      <AssetLibraryShell
        title="音色库"
        addLabel="添加参考音色"
        onAdd={() => setAddOpen(true)}
        cards={
          <div className="asset-grid">
            {items.map((item) => (
              <section key={item.reference_id} className="asset-card">
                <Mic2 size={24} />
                <strong>{item.name}</strong>
                <span>{item.filename}</span>
                <div className="asset-card-actions">
                  <button
                    type="button"
                    className="asset-action preview"
                    onClick={() => setPreview({ kind: "audio", title: item.name, src: item.file_url })}
                    disabled={!item.file_url}
                  >
                    试听
                  </button>
                  <button
                    type="button"
                    className="asset-action danger"
                    onClick={() =>
                      setPendingDelete({
                        title: "确认删除音色",
                        name: item.name,
                        description: item.filename,
                        confirmLabel: "确认删除音色",
                        confirm: async () => {
                          await deleteVoiceAsset(item.reference_id);
                          await reload();
                        },
                      })
                    }
                  >
                    删除
                  </button>
                </div>
              </section>
            ))}
          </div>
        }
      />
      <VoiceAssetModal
        open={addOpen}
        onClose={() => setAddOpen(false)}
        onUploaded={async () => {
          await reload();
          setAddOpen(false);
        }}
        submitLabel="保存到素材库"
        successNote="保存成功后：关闭弹窗 → 刷新素材列表。"
        successMessage="已保存到音色库。"
      />
      <AssetPreviewModal preview={preview} onClose={() => setPreview(null)} />
      <ConfirmDeleteModal pending={pendingDelete} onClose={() => setPendingDelete(null)} />
    </>
  );
}

function PortraitLibrary({
  items,
  reload,
}: {
  items: PortraitAsset[];
  reload: () => Promise<void>;
}) {
  const [preview, setPreview] = useState<AssetPreview | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<PendingDelete | null>(null);
  return (
    <>
      <AssetLibraryShell
        title="形象库"
        addLabel="添加数字人形象"
        onAdd={() => setAddOpen(true)}
        cards={
          <div className="asset-grid portraits">
            {items.map((item) => (
              <section key={item.portrait_id} className="asset-card portrait">
                {item.media_type === "image" ? (
                  <AssetImage src={item.file_url} alt={item.name} />
                ) : (
                  <ProtectedMedia kind="video" src={item.file_url} />
                )}
                <strong>{item.name}</strong>
                <span>{item.media_type === "video" ? "视频形象" : "图片形象"}</span>
                <div className="asset-card-actions">
                  <button
                    type="button"
                    className="asset-action preview"
                    onClick={() =>
                      setPreview({
                        kind: item.media_type,
                        title: item.name,
                        src: item.file_url,
                      })
                    }
                    disabled={!item.file_url}
                  >
                    预览
                  </button>
                  <button
                    type="button"
                    className="asset-action danger"
                    onClick={() =>
                      setPendingDelete({
                        title: "确认删除形象",
                        name: item.name,
                        description: item.media_type === "video" ? "视频形象" : "图片形象",
                        confirmLabel: "确认删除形象",
                        confirm: async () => {
                          await deletePortraitAsset(item.portrait_id);
                          await reload();
                        },
                      })
                    }
                  >
                    删除
                  </button>
                </div>
              </section>
            ))}
          </div>
        }
      />
      <SimpleAssetModal
        open={addOpen}
        title="添加数字人形象"
        description="上传图片形象或闭口视频形象，保存后进入数字人库。"
        assetNameLabel="形象名称"
        fileLabel="图片或视频形象"
        accept="image/*,video/*"
        upload={uploadPortraitAsset}
        onClose={() => setAddOpen(false)}
        onUploaded={async () => {
          await reload();
          setAddOpen(false);
        }}
        submitLabel="保存到素材库"
        successNote="保存成功后：关闭弹窗 → 刷新素材列表。"
        successMessage="已保存到形象库。"
      />
      <AssetPreviewModal preview={preview} onClose={() => setPreview(null)} />
      <ConfirmDeleteModal pending={pendingDelete} onClose={() => setPendingDelete(null)} />
    </>
  );
}

function TemplateLibrary({ items }: { items: IpTemplateAsset[] }) {
  return (
    <section className="card wide">
      <h2>画面模板库</h2>
      <p className="muted">模板 v1 由系统内置，控制封面标题区域和视频字幕样式。</p>
      <div className="asset-grid templates">
        {items.map((item) => (
          <section key={item.template_id} className="asset-card template" title={item.full_description}>
            <AssetImage src={item.preview_url} alt={item.display_name} />
            <strong>{item.display_name}</strong>
            <span>{item.short_description}</span>
          </section>
        ))}
      </div>
    </section>
  );
}

function VideoLibrary({ items, reload }: { items: VideoAsset[]; reload: () => Promise<void> }) {
  const [addOpen, setAddOpen] = useState(false);
  const [preview, setPreview] = useState<AssetPreview | null>(null);
  const [pendingDelete, setPendingDelete] = useState<PendingDelete | null>(null);
  return (
    <>
      <AssetLibraryShell
        title="视频素材库"
        addLabel="添加视频素材"
        onAdd={() => setAddOpen(true)}
        cards={
          <div className="asset-grid videos">
            {items.map((item) => (
              <section key={item.asset_id} className="asset-card video-asset">
                {item.thumbnail_exists ? (
                  <AssetImage src={item.thumbnail_url} alt={item.name} />
                ) : (
                  <div className="video-thumb">VIDEO</div>
                )}
                <strong>{item.name}</strong>
                <span>{item.duration ? `${item.duration}s` : item.filename}</span>
                <div className="asset-card-actions">
                  <button
                    type="button"
                    className="asset-action preview"
                    onClick={() => setPreview({ kind: "video", title: item.name, src: item.file_url })}
                    disabled={!item.file_url}
                  >
                    预览
                  </button>
                  <button
                    type="button"
                    className="asset-action danger"
                    onClick={() =>
                      setPendingDelete({
                        title: "确认删除视频素材",
                        name: item.name,
                        description: item.filename,
                        confirmLabel: "确认删除视频素材",
                        confirm: async () => {
                          await deleteVideoAsset(item.asset_id);
                          await reload();
                        },
                      })
                    }
                  >
                    删除
                  </button>
                </div>
              </section>
            ))}
          </div>
        }
      />
      <SimpleAssetModal
        open={addOpen}
        title="添加视频素材"
        description="起个你自己看得懂的名字，系统会根据名称帮你推荐到合适的视频里。"
        assetNameLabel="视频素材名称"
        namePlaceholder="例如：双人火锅套餐、门店环境、锅底翻滚、顾客用餐"
        fileLabel="视频素材"
        accept="video/*"
        upload={uploadVideoAsset}
        onClose={() => setAddOpen(false)}
        onUploaded={async () => {
          await reload();
          setAddOpen(false);
        }}
        submitLabel="保存到素材库"
        successNote="保存成功后：关闭弹窗 → 刷新素材列表。"
        successMessage="已保存到视频素材库。"
      />
      <AssetPreviewModal preview={preview} onClose={() => setPreview(null)} />
      <ConfirmDeleteModal pending={pendingDelete} onClose={() => setPendingDelete(null)} />
    </>
  );
}

function BrandKitLibrary({ items, reload }: { items: BrandKit[]; reload: () => Promise<void> }) {
  const [pendingDelete, setPendingDelete] = useState<PendingDelete | null>(null);
  const [draft, setDraft] = useState<Partial<BrandKit>>({
    brand_name: "",
    primary_color: "#6D5DF6",
    secondary_color: "#0f766e",
    store_address: "",
    phone: "",
    coupon_phrase: "",
  });

  async function save() {
    await createBrandKit(draft);
    setDraft({
      brand_name: "",
      primary_color: "#6D5DF6",
      secondary_color: "#0f766e",
      store_address: "",
      phone: "",
      coupon_phrase: "",
    });
    await reload();
  }

  return (
    <section className="card wide">
      <h2>品牌包</h2>
      <p className="muted">保存企业固定品牌信息，后续可自动应用到模板、BGM 和发布素材包。</p>
      <div className="brand-form">
        <input
          placeholder="品牌/门店名称"
          value={draft.brand_name || ""}
          onChange={(event) => setDraft({ ...draft, brand_name: event.target.value })}
        />
        <input
          placeholder="品牌色"
          value={draft.primary_color || ""}
          onChange={(event) => setDraft({ ...draft, primary_color: event.target.value })}
        />
        <input
          placeholder="门店地址"
          value={draft.store_address || ""}
          onChange={(event) => setDraft({ ...draft, store_address: event.target.value })}
        />
        <input
          placeholder="电话"
          value={draft.phone || ""}
          onChange={(event) => setDraft({ ...draft, phone: event.target.value })}
        />
        <input
          placeholder="团购口令"
          value={draft.coupon_phrase || ""}
          onChange={(event) => setDraft({ ...draft, coupon_phrase: event.target.value })}
        />
        <button className="primary" disabled={!draft.brand_name} onClick={save}>
          保存品牌包
        </button>
      </div>
      <div className="asset-grid">
        {items.map((item) => (
          <section key={item.brand_id} className="asset-card">
            <strong>{item.brand_name}</strong>
            <span>{item.store_address || item.coupon_phrase || "暂无业务信息"}</span>
            <div className="swatches">
              <i style={{ background: item.primary_color }} />
              <i style={{ background: item.secondary_color }} />
            </div>
            <input
              placeholder="默认 BGM 路径"
              defaultValue={item.default_bgm_path}
              onBlur={(event) =>
                updateBrandKit(item.brand_id, { default_bgm_path: event.target.value }).then(reload)
              }
            />
            <button
              onClick={() =>
                setPendingDelete({
                  title: "确认删除品牌资料",
                  name: item.brand_name,
                  description: item.store_address || item.coupon_phrase || "暂无业务信息",
                  confirmLabel: "确认删除品牌资料",
                  confirm: async () => {
                    await deleteBrandKit(item.brand_id);
                    await reload();
                  },
                })
              }
            >
              删除
            </button>
          </section>
        ))}
      </div>
      <ConfirmDeleteModal pending={pendingDelete} onClose={() => setPendingDelete(null)} />
    </section>
  );
}

function PublishAccountsView() {
  const platforms = [
    {
      key: "douyin",
      name: "抖音",
      logo: "/platform-logos/douyin.svg",
      description: "可通过发布助手打开独立浏览器，自动填写视频、标题和标签。",
      status: <Tag color="success">可用</Tag>,
      ready: true,
    },
    {
      key: "shipinhao",
      name: "视频号",
      logo: "/platform-logos/shipinhao.svg",
      description: "后续接入桌面端发布助手，当前可在发布页复制素材手动发布。",
      status: <Tag>规划中</Tag>,
      ready: false,
    },
    {
      key: "kuaishou",
      name: "快手",
      logo: "/platform-logos/kuaishou.svg",
      description: "后续扩展自动填写能力，当前保留发布素材包。",
      status: <Tag>规划中</Tag>,
      ready: false,
    },
    {
      key: "xiaohongshu",
      name: "小红书",
      logo: "/platform-logos/xiaohongshu.svg",
      description: "后续按平台规则单独适配发布文案和素材上传。",
      status: <Tag>规划中</Tag>,
      ready: false,
    },
  ];
  return (
    <section className="card wide publish-account-page">
      <div className="card-title">
        <div>
          <h2>发布账号</h2>
          <p className="muted">管理短视频平台登录状态。当前版本先支持抖音发布助手。</p>
        </div>
        <Tag color="processing">本机登录态</Tag>
      </div>
      <div className="publish-account-grid">
        {platforms.map((platform) => (
          <section key={platform.key} className={`publish-account-card ${platform.ready ? "ready" : ""}`}>
            <div className="platform-logo">
              <img src={platform.logo} alt={`${platform.name} logo`} />
            </div>
            <div>
              <strong>{platform.name}</strong>
              <span>{platform.description}</span>
            </div>
            {platform.status}
          </section>
        ))}
      </div>
      <Alert
        type="info"
        showIcon
        message="登录数据只保存在本机"
        description="抖音发布助手使用本机 data/publish_browser/ 目录保存浏览器登录态，该目录不会提交到代码仓库。最终发布仍需你在平台页面确认。"
      />
    </section>
  );
}

function TaskCenterView() {
  const [status, setStatus] = useState("");
  const [tasks, setTasks] = useState<TaskInfo[]>([]);
  const [error, setError] = useState("");

  async function reload(nextStatus = status) {
    try {
      const items = await listTasks(nextStatus, 100);
      setTasks(items);
    } catch (err) {
      setError(String(err));
    }
  }

  useEffect(() => {
    reload();
    const timer = window.setInterval(() => reload(), 3000);
    return () => window.clearInterval(timer);
  }, [status]);

  return (
    <section className="card wide">
      <div className="card-title">
        <h2>任务记录</h2>
        <select
          value={status}
          onChange={(event) => {
            setStatus(event.target.value);
            reload(event.target.value);
          }}
        >
          <option value="">全部</option>
          <option value="running">运行中</option>
          <option value="completed">已完成</option>
          <option value="failed">失败</option>
          <option value="cancelled">已取消</option>
        </select>
      </div>
      {error ? <div className="notice error">{error}</div> : null}
      <div className="task-list">
        {tasks.map((item) => (
          <section key={item.task_id} className="task-row">
            <div>
              <strong>{item.display_name || item.task_id}</strong>
              <span>
                {item.flow_name || "任务"} · {taskStepLabel(item.step_key || "")} ·{" "}
                {taskStatusLabel(item.status)}
              </span>
              {item.error ? <small className="task-error">{item.error}</small> : null}
            </div>
            <div className="task-actions">
              {item.status === "failed" ? (
                <button onClick={() => retryTask(item.task_id).then(() => reload())}>创建重试记录</button>
              ) : null}
              {["pending", "running"].includes(item.status) ? (
                <button onClick={() => cancelTask(item.task_id).then(() => reload())}>停止</button>
              ) : null}
            </div>
          </section>
        ))}
      </div>
    </section>
  );
}

function taskStepLabel(stepKey: string) {
  return (
    {
      source: "搞定文案",
      copywriting: "搞定文案",
      voice: "配音制作",
      digital_human: "数字人出镜",
      postproduction: "一键成片",
      publish: "发布素材",
    }[stepKey] || stepKey || "-"
  );
}

function taskStatusLabel(status: TaskInfo["status"]) {
  return (
    {
      pending: "等待中",
      running: "运行中",
      completed: "已完成",
      failed: "失败",
      cancelled: "已取消",
    }[status] || status
  );
}

function AssetLibraryShell({
  title,
  addLabel,
  onAdd,
  cards,
}: {
  title: string;
  addLabel: string;
  onAdd: () => void;
  cards: ReactNode;
}) {
  return (
    <section className="card wide">
      <div className="asset-library-header">
        <h2>{title}</h2>
        <button className="primary" type="button" onClick={onAdd}>
          {addLabel}
        </button>
      </div>
      {cards}
    </section>
  );
}

function ConfigView({
  themeSkin,
  setThemeSkin,
}: {
  themeSkin: ThemeSkin;
  setThemeSkin: (skin: ThemeSkin) => void;
}) {
  const [config, setConfig] = useState<DesktopConfig | null>(null);
  const [saved, setSaved] = useState("");
  const [checkResult, setCheckResult] = useState<ConfigCheckResult | null>(null);
  const [checkingConfig, setCheckingConfig] = useState(false);

  useEffect(() => {
    getDesktopConfig().then(setConfig).catch((err) => setSaved(String(err)));
  }, []);

  if (!config) return <section className="card">加载配置中...</section>;

  async function save() {
    if (!config) return;
    const updated = await saveDesktopConfig(config);
    setConfig(updated);
    setSaved("配置已保存。需要时请重启本地服务。");
  }

  function updateConfigDraft(nextConfig: DesktopConfig) {
    setConfig(nextConfig);
    setCheckResult(null);
  }

  async function runConfigCheck() {
    if (!config) return;
    setCheckingConfig(true);
    setSaved("");
    try {
      setCheckResult(await checkDesktopConfig(config));
    } catch (err) {
      setCheckResult({
        ok: false,
        checks: [
          {
            id: "config_check",
            label: "配置检查",
            status: "missing",
            message: formatUiError(err),
          },
        ],
      });
    } finally {
      setCheckingConfig(false);
    }
  }

  return (
    <section className="config-page">
      <Card title="外观设置" variant="borderless">
        <Typography.Paragraph type="secondary">
          皮肤只影响 App 界面，不影响品牌包、视频模板和发布素材。
        </Typography.Paragraph>
        <Segmented
          block
          value={themeSkin}
          onChange={(value) => setThemeSkin(value as ThemeSkin)}
          options={Object.entries(themeSkins).map(([key, skin]) => ({
            label: skin.label,
            value: key,
          }))}
        />
        <div className="theme-card-grid">
          {Object.entries(themeSkins).map(([key, skin]) => (
            <button
              key={key}
              className={`theme-card ${themeSkin === key ? "selected" : ""}`}
              data-swatch={key}
              onClick={() => setThemeSkin(key as ThemeSkin)}
            >
              <span className="theme-preview">
                <i />
                <b />
                <em />
              </span>
              <strong>{skin.label}</strong>
              <small>{skin.description}</small>
            </button>
          ))}
        </div>
      </Card>

      <Card title="配置中心" variant="borderless">
        <Alert
          className="config-security-note"
          type="info"
          showIcon
          message="发布助手登录态保存在本机"
          description="抖音等平台的浏览器登录数据会保存在 data/publish_browser/，用于下次免登录。该目录已加入忽略规则，不应提交到代码仓库。"
        />
        <label>LLM Base URL</label>
        <input
          value={config.llm.base_url}
          onChange={(event) =>
            updateConfigDraft({ ...config, llm: { ...config.llm, base_url: event.target.value } })
          }
        />
        <label>LLM API Key</label>
        <input
          placeholder={config.llm.api_key || "请输入 API Key"}
          onChange={(event) =>
            updateConfigDraft({ ...config, llm: { ...config.llm, api_key: event.target.value } })
          }
        />
        <label>LLM Model</label>
        <input
          value={config.llm.model}
          onChange={(event) =>
            updateConfigDraft({ ...config, llm: { ...config.llm, model: event.target.value } })
          }
        />
        <label>RunningHub API Key</label>
        <input
          placeholder={config.runninghub.api_key || "请输入 RunningHub API Key"}
          onChange={(event) =>
            updateConfigDraft({
              ...config,
              runninghub: { ...config.runninghub, api_key: event.target.value },
            })
          }
        />
        <label>RunningHub Instance Type</label>
        <input
          value={config.runninghub.instance_type}
          onChange={(event) =>
            updateConfigDraft({
              ...config,
              runninghub: { ...config.runninghub, instance_type: event.target.value },
            })
          }
        />
        <div className="config-check-actions">
          <Button onClick={runConfigCheck} loading={checkingConfig}>
            检查当前配置
          </Button>
          <span>配置项已填写，尚未验证服务账号是否可用。</span>
        </div>
        {checkResult ? (
          <div className="config-check-list">
            {checkResult.checks.map((item) => (
              <CheckRow key={item.id} item={item} className="config-check-row" />
            ))}
          </div>
        ) : null}
        <Button type="primary" onClick={save}>
          保存配置
        </Button>
        {saved ? <Alert className="step-notice" type="success" showIcon message={saved} /> : null}
      </Card>
    </section>
  );
}

function DiagnosticsView() {
  const [diagnostics, setDiagnostics] = useState<DesktopDiagnostics | null>(null);
  useEffect(() => {
    getDiagnostics().then(setDiagnostics);
  }, []);
  return (
    <section className="card wide">
      <h2>启动自检</h2>
      <div className="diagnostic-check-list">
        {diagnostics?.checks.map((item) => (
          <CheckRow key={item.id} item={item} className="diagnostic-check-row" />
        ))}
      </div>
    </section>
  );
}

function CheckRow({ item, className }: { item: DiagnosticCheck; className: string }) {
  return (
    <section className={className}>
      <Tag color={item.status === "ok" ? "success" : item.status === "warning" ? "warning" : "error"}>
        {item.status === "ok" ? "正常" : item.status === "warning" ? "待验证" : "待处理"}
      </Tag>
      <strong>{item.label}</strong>
      <span>{item.message}</span>
    </section>
  );
}

function AssetImage({
  src,
  alt,
  fallback = false,
}: {
  src: string;
  alt: string;
  fallback?: boolean;
}) {
  const [resolved, setResolved] = useState("");
  useEffect(() => {
    if (!src || fallback) return;
    let current = "";
    assetBlobUrl(src).then((url) => {
      current = url;
      setResolved(url);
    });
    return () => {
      if (current) URL.revokeObjectURL(current);
    };
  }, [fallback, src]);
  if (fallback || !src) {
    return (
      <div className="template-demo">
        <strong>标题区</strong>
        <span>字幕区</span>
      </div>
    );
  }
  return <img src={resolved || src} alt={alt} />;
}

function ProtectedMedia({ src, kind }: { src: string; kind: "audio" | "video" }) {
  const [resolved, setResolved] = useState("");
  useEffect(() => {
    if (!src) return;
    let current = "";
    assetBlobUrl(src).then((url) => {
      current = url;
      setResolved(url);
    });
    return () => {
      if (current) URL.revokeObjectURL(current);
    };
  }, [src]);
  if (kind === "audio") return <audio controls src={resolved} />;
  return <video controls src={resolved} />;
}

function ArtifactMediaPreview({
  sessionId,
  artifactKey,
  kind,
  enabled,
}: {
  sessionId: string;
  artifactKey: string;
  kind: "audio" | "video" | "image";
  enabled: boolean;
}) {
  const [resolved, setResolved] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    if (!enabled) {
      setResolved("");
      setError("");
      return;
    }
    let current = "";
    artifactBlobUrl(sessionId, artifactKey)
      .then((url) => {
        current = url;
        setResolved(url);
        setError("");
      })
      .catch((err) => {
        setError(formatUiError(err));
      });
    return () => {
      if (current) URL.revokeObjectURL(current);
    };
  }, [artifactKey, enabled, sessionId]);

  if (!enabled) return null;
  if (error) return <span className="generated-preview-error">预览加载失败，可重新生成后再试。</span>;
  if (!resolved) return <span className="generated-preview-loading">正在加载预览...</span>;
  if (kind === "image") return <img className="artifact-image-preview" src={resolved} alt="生成封面预览" />;
  return kind === "audio" ? <audio controls src={resolved} /> : <video controls src={resolved} />;
}

function ArtifactVideoPreview({
  sessionId,
  artifactKey,
  enabled,
}: {
  sessionId: string;
  artifactKey: string;
  enabled: boolean;
}) {
  const [resolved, setResolved] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    if (!enabled) {
      setResolved("");
      setError("");
      return;
    }
    let current = "";
    artifactBlobUrl(sessionId, artifactKey)
      .then((url) => {
        current = url;
        setResolved(url);
        setError("");
      })
      .catch((err) => {
        setError(formatUiError(err));
      });
    return () => {
      if (current) URL.revokeObjectURL(current);
    };
  }, [artifactKey, enabled, sessionId]);

  if (!enabled) {
    return (
      <div className="video-preview-shell placeholder">
        <Video size={36} />
        <span>等待成片</span>
      </div>
    );
  }
  if (error) {
    return (
      <div className="video-preview-shell placeholder">
        <AlertCircle size={28} />
        <span>视频预览加载失败，可直接下载检查</span>
      </div>
    );
  }
  return (
    <div className="artifact-video-preview">
      {resolved ? <video controls src={resolved} /> : <span>正在加载视频预览...</span>}
    </div>
  );
}

function stepHint(step: number) {
  return [
    "先选本条视频目标和素材来源，再确认最终口播稿；回车分段会用于画面规划。",
    "选择系统默认配音，或用老板参考音频做声音克隆。",
    "按出镜生成方式选择兼容形象，再生成出镜视频。",
    "选择画面模板，需要插入门店/菜品视频时再打开画面规划。",
    "确认视频、文案、平台和发布方式，打开抖音发布助手。",
  ][step - 1];
}

function splitSegments(script: string): StorySegment[] {
  return script
    .split(/\n+/)
    .map((text) => text.trim())
    .filter(Boolean)
    .map((text, index) => ({
      segment_id: String(index + 1),
      index: index + 1,
      text,
    }));
}

function readGroups(value: unknown): VisualGroup[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is VisualGroup => {
    return Boolean(item && typeof item === "object" && "group_id" in item);
  });
}

function readVideoPlan(value: unknown): VideoPlan | null {
  if (!value || typeof value !== "object") return null;
  const plan = value as Partial<VideoPlan>;
  if (!Array.isArray(plan.segments) || !plan.segments.length) return null;
  return {
    goal: String(plan.goal || ""),
    status: String(plan.status || "empty"),
    summary: String(plan.summary || ""),
    visual_strategy: String(plan.visual_strategy || ""),
    segments: plan.segments.map((segment, index) => {
      const item = segment as Partial<VideoPlanSegment>;
      return {
        segment_id: String(item.segment_id || index + 1),
        index: Number(item.index || index + 1),
        text: String(item.text || ""),
        visual_type: (item.visual_type || "digital_human") as VideoPlanSegment["visual_type"],
        label: String(item.label || "老板出镜"),
        asset_keywords: readStringArray(item.asset_keywords),
        prompt: String(item.prompt || ""),
        reason: String(item.reason || ""),
      };
    }),
  };
}

function buildGroupsFromVideoPlan(plan: VideoPlan | null, videos: VideoAsset[]): VisualGroup[] {
  if (!plan) return [];
  return plan.segments
    .filter((segment) => segment.visual_type === "uploaded_video")
    .map((segment) => {
      const matched = findMatchingVideoAsset(segment.asset_keywords, videos);
      return {
        group_id: `plan_group_${segment.segment_id}`,
        segment_ids: [segment.segment_id],
        visual_type: "uploaded_video",
        prompt: segment.prompt,
        uploaded_video_path: matched?.asset_path || "",
        video_asset_id: matched?.asset_id || "",
        status: "recommended",
      };
    });
}

function findMatchingVideoAsset(keywords: string[], videos: VideoAsset[]) {
  if (!keywords.length) return null;
  return (
    videos.find((video) => {
      const text = `${video.name} ${video.filename}`.toLowerCase();
      return keywords.some((keyword) => text.includes(keyword.toLowerCase()));
    }) || null
  );
}

function readStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => String(item)).filter(Boolean);
}
