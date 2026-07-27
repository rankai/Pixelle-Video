import {
  AlertCircle,
  CheckCircle2,
  Clapperboard,
  Home,
  Image as ImageIcon,
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
import { lazy, Suspense, useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";
import {
  artifactBlobUrl,
  assetBlobUrl,
  cancelTask,
  checkDesktopConfig,
  createBrandKit,
  createSession,
  deleteBrandKit,
  deleteImageAsset,
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
  listImageAssets,
  listIpPresetAssets,
  listIpTemplateAssets,
  listPortraitAssets,
  listTasks,
  listVideoAssets,
  listVoiceAssets,
  PortraitAsset,
  ImageAsset,
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
  uploadImageAsset,
  uploadVideoAsset,
  uploadVoiceAsset,
  BgmAsset,
  PublishResult,
  PublishPlatform,
  VideoAsset,
  VoiceAsset,
  AssetLibraryV2Item,
  LibraryItemV2,
  archiveMediaAssetV2,
  listLibraryItemsV2,
  listMediaAssetsV2,
  reconcileSessionResourceUsageV2,
  uploadMediaAssetV2,
} from "./api";
import { featureFlags } from "./featureFlags";
import { createAntdTheme, readStoredThemeSkin, themeSkins, type ThemeSkin } from "./theme";
import { AssetCenterV2 } from "./features/assets/components/AssetCenterV2";
import { AssetPickerDialog } from "./features/assets/components/AssetPickerDialog";
import { ApplicationCenterView } from "./features/app-center/ApplicationCenterView";
import { DigitalHumanApplicationView } from "./features/app-center/DigitalHumanApplicationView";
import { CreationWorkspace } from "./features/creation/CreationWorkspace";
import { PublishCenterView } from "./features/publishing/PublishCenterView";
import { useHashRouter } from "./features/app-center/AppShell";

const PublishWorkspace = lazy(() => import("./features/publishing/PublishWorkspace"));
const DashboardView = lazy(() => import("./features/dashboard/DashboardView"));

type View = "apps" | "home" | "application_workflow" | "ip" | "digital_human_app" | "assets" | "publish_accounts" | "tasks" | "config" | "diagnostics";
type AssetTab = "videos" | "images" | "voices" | "portraits" | "templates" | "brands";
type NavKey =
  | "apps"
  | "home"
  | "ip"
  | "assets"
  | "publish_accounts"
  | "tasks"
  | "config";

type AssetState = {
  voices: VoiceAsset[];
  portraits: PortraitAsset[];
  templates: IpTemplateAsset[];
  presets: IpPresetAsset[];
  videos: VideoAsset[];
  images: ImageAsset[];
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
  visual_type: "digital_human" | "ai_video" | "uploaded_video" | "uploaded_image";
  prompt: string;
  uploaded_video_path: string;
  video_asset_id: string;
  uploaded_image_path: string;
  image_asset_id: string;
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

type SubtitleStyleDraft = {
  font_size: number;
  margin_v: number;
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
  "文案与分段",
  "配音",
  "出镜",
  "成片",
  "发布",
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

const IPB_SESSION_STORAGE_KEY = "pixelle_ipb_session_id";
const IPB_TASK_STORAGE_KEY = "pixelle_ipb_task_id";

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
  description: string;
  supportedMediaTypes: PortraitMediaType[];
  supportsPrompt: boolean;
  defaultWidth?: number;
  defaultHeight?: number;
}> = [
  {
    value: "workflows/runninghub/digital_combination.json",
    label: "标准图片出镜",
    description: "上传老板照片生成自然口播视频；速度稳定，动作默认。",
    supportedMediaTypes: ["image"],
    supportsPrompt: false,
    defaultWidth: 720,
    defaultHeight: 1280,
  },
  {
    value: "workflows/runninghub/digital_talk_image_prompt.json",
    label: "可控图片出镜",
    description: "上传老板照片生成口播视频，可用动作描述控制镜头表现。",
    supportedMediaTypes: ["image"],
    supportsPrompt: true,
    defaultWidth: 720,
    defaultHeight: 1280,
  },
  {
    value: "workflows/runninghub/digital_talk_fast_720p.json",
    label: "快速可控出镜",
    description: "上传老板照片快速生成口播视频，适合先看效果再精修。",
    supportedMediaTypes: ["image"],
    supportsPrompt: true,
    defaultWidth: 720,
    defaultHeight: 1280,
  },
  {
    value: "workflows/runninghub/digital_lip_sync_video.json",
    label: "真人视频改口型",
    description: "上传老板真人视频，只替换口型和声音，保留原视频动作。",
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
  images: [],
  brands: [],
  bgm: [],
};

const navItems: MenuProps["items"] = [
  { key: "home", icon: <Home size={16} />, label: "工作台" },
  ...(featureFlags.appCenterShell ? [{ key: "apps", icon: <Images size={16} />, label: "应用中心" }] : []),
  { key: "ip", icon: <Video size={16} />, label: "口播剪辑" },
  { type: "divider" },
  { key: "assets", icon: <Package size={16} />, label: "企业资产库" },
  { type: "divider" },
  { key: "publish_accounts", icon: <Share2 size={16} />, label: "发布中心" },
  { key: "tasks", icon: <CheckCircle2 size={16} />, label: "任务记录" },
  { key: "config", icon: <Settings size={16} />, label: "系统设置" },
];

function viewTitle(view: View, assetTab: AssetTab) {
  if (view === "apps") return "应用中心";
  if (view === "application_workflow") return "应用流程";
  if (view === "ip") return "口播剪辑";
  if (view === "digital_human_app") return "数字人口播视频";
  if (view === "assets") return `企业资产库 · ${{ videos: "视频", images: "图片", voices: "音色", portraits: "数字人", templates: "模板", brands: "品牌" }[assetTab]}`;
  return { home: "企业视频工作台", publish_accounts: "发布中心", tasks: "任务记录", config: "系统设置", diagnostics: "启动自检" }[view] || "Pixelle Video";
}

function viewDescription(view: View) {
  if (view === "apps") return "发现可扩展的文案、标题、图文和视频应用。";
  if (view === "application_workflow") return "按应用完成输入、生成、审核和交接。";
  if (view === "ip") return "文案、配音、出镜、成片和发布，一条生产线完成。";
  if (view === "digital_human_app") return "从项目或可信内容进入数字人口播应用，发布前保留人工确认。";
  if (view === "assets") return "集中管理可在不同项目中复用的企业视频资产。";
  if (view === "publish_accounts") return "自动填充平台信息，最终发布由人工确认。";
  return "管理企业视频资产、生产任务与发布交付。";
}

function autoAdvanceStepAfter(stepKey?: string) {
  return (
    {
      source: 1,
      postproduction: 5,
    }[stepKey || ""] || 0
  );
}

function uiStepForApiStep(apiStep?: number) {
  if (!apiStep || apiStep <= 2) return 1;
  return Math.min(apiStep - 1, 5);
}

function uiStepForTask(stepKey: string) {
  return (
    {
      source: 1,
      copywriting: 1,
      voice: 2,
      digital_human: 3,
      postproduction: 4,
      publish: 5,
    }[stepKey] || 0
  );
}

function viewForPath(pathname: string): View {
  const basePath = pathname.split("?", 1)[0];
  if (basePath === "/" || basePath === "/apps") return "apps";
  if (["/apps/marketing-copy", "/apps/viral-titles", "/apps/douyin-carousel"].includes(basePath)) return "application_workflow";
  if (basePath === "/ip") return "ip";
  if (basePath === "/apps/digital-human-video") return "digital_human_app";
  if (basePath === "/assets") return "assets";
  if (basePath === "/publish") return "publish_accounts";
  if (basePath === "/tasks") return "tasks";
  if (basePath === "/config" || basePath === "/settings") return "config";
  if (basePath === "/runs") return "tasks";
  if (basePath === "/projects") return "home";
  if (basePath === "/diagnostics") return "diagnostics";
  return "home";
}

function pathForView(view: View): string {
  return {
    apps: "/apps",
    home: "/home",
    application_workflow: "/apps",
    ip: "/ip",
    digital_human_app: "/apps/digital-human-video",
    assets: "/assets",
    publish_accounts: "/publish",
    tasks: "/tasks",
    config: "/config",
    diagnostics: "/diagnostics",
  }[view];
}

export function StudioApp() {
  const router = useHashRouter();
  const [view, setView] = useState<View>(() => (router ? viewForPath(router.pathname) : "home"));
  const [assetTab, setAssetTab] = useState<AssetTab>("videos");
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
  const [creationAppId, setCreationAppId] = useState(() => appIdForPath(router?.pathname || "") || "builtin.marketing-copy");
  const [creationSourceArtifactVersionId, setCreationSourceArtifactVersionId] = useState("");

  function appIdForPath(pathname: string): string | null {
    const basePath = pathname.split("?", 1)[0];
    return {
      "/apps/marketing-copy": "builtin.marketing-copy",
      "/apps/viral-titles": "builtin.viral-titles",
      "/apps/douyin-carousel": "builtin.douyin-carousel",
    }[basePath] || null;
  }

  useEffect(() => {
    if (!router) return;
    setView(viewForPath(router.pathname));
    const routedAppId = appIdForPath(router.pathname);
    if (routedAppId) setCreationAppId(routedAppId);
  }, [router?.pathname]);

  useEffect(() => {
    // The application-center route must not create a legacy IP session as a
    // side effect. Legacy recovery remains explicit when the old workflow is
    // opened, preserving the historical StudioApp behavior there.
    if (view === "apps" || view === "application_workflow" || view === "digital_human_app") return;
    recoverAppState().catch((err) => setAppError(formatUiError(err)));
  }, [view]);

  function setThemeSkin(skin: ThemeSkin) {
    window.localStorage.setItem("pixelle_desktop_theme_skin", skin);
    setThemeSkinState(skin);
  }

  async function restoreOrCreateSession() {
    const storedSessionId = window.localStorage.getItem(IPB_SESSION_STORAGE_KEY);
    if (storedSessionId) {
      try {
        const restored = await getSession(storedSessionId);
        setSession(restored);
        setActiveStep(uiStepForApiStep(restored.current_step));
        await restoreCurrentTask(restored.session_id);
        return;
      } catch {
        window.localStorage.removeItem(IPB_SESSION_STORAGE_KEY);
        window.localStorage.removeItem(IPB_TASK_STORAGE_KEY);
      }
    }
    const created = await createSession();
    window.localStorage.setItem(IPB_SESSION_STORAGE_KEY, created.session_id);
    window.localStorage.removeItem(IPB_TASK_STORAGE_KEY);
    setSession(created);
    setActiveStep(1);
  }

  async function restoreCurrentTask(sessionId: string) {
    const storedTaskId = window.localStorage.getItem(IPB_TASK_STORAGE_KEY);
    if (!storedTaskId) return;
    try {
      const restoredTask = await getTask(storedTaskId);
      if (restoredTask.session_id && restoredTask.session_id !== sessionId) {
        window.localStorage.removeItem(IPB_TASK_STORAGE_KEY);
        return;
      }
      setTask(restoredTask);
      const restoredStep = uiStepForTask(restoredTask.step_key || "");
      if (restoredStep) setActiveStep(restoredStep);
      if (["completed", "failed", "cancelled"].includes(restoredTask.status)) {
        window.localStorage.removeItem(IPB_TASK_STORAGE_KEY);
        setBusy(false);
      } else {
        setBusy(true);
      }
    } catch {
      window.localStorage.removeItem(IPB_TASK_STORAGE_KEY);
    }
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
          window.localStorage.removeItem(IPB_TASK_STORAGE_KEY);
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
    const [presets, legacyBgm] = await Promise.all([listIpPresetAssets(), listBgm()]);
    const bgm = featureFlags.assetCenterV2
      ? (await listLibraryItemsV2("audio")).items.map(mapV2BgmAsset)
      : legacyBgm.bgm_files;
    const [voices, portraits, templates, brands, videos, images] = featureFlags.assetCenterV2
      ? await Promise.all([
          listLibraryItemsV2("voice"),
          listLibraryItemsV2("digital_human"),
          listLibraryItemsV2("template"),
          listLibraryItemsV2("brand"),
          listMediaAssetsV2("video"),
          listMediaAssetsV2("image"),
        ]).then(([voiceItems, portraitItems, templateItems, brandItems, videoItems, imageItems]) => [
          { items: voiceItems.items.map(mapV2VoiceAsset) },
          { items: portraitItems.items.map(mapV2PortraitAsset) },
          { items: templateItems.items.map(mapV2TemplateAsset) },
          { items: brandItems.items.map(mapV2BrandKit) },
          { items: videoItems.items.map(mapV2VideoAsset) },
          { items: imageItems.items.map(mapV2ImageAsset) },
        ] as const)
      : await Promise.all([
          listVoiceAssets(),
          listPortraitAssets(),
          listIpTemplateAssets(),
          listBrandKits(),
          listVideoAssets(),
          listImageAssets(),
        ]);
    setAssets({
      voices: voices.items,
      portraits: portraits.items,
      templates: templates.items,
      presets: presets.items,
      videos: videos.items,
      images: images.items,
      brands: brands.items,
      bgm,
    });
  }

  async function execute(stepKey: string) {
    if (!session || configSaving) return;
    setBusy(true);
    setWorkflowError("");
    setTask(null);
    try {
      const result = await runStep(session.session_id, stepKey);
      window.localStorage.setItem(IPB_TASK_STORAGE_KEY, result.task_id);
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
      window.localStorage.removeItem(IPB_TASK_STORAGE_KEY);
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
      if (featureFlags.assetCenterV2) {
        const nextState = updated.state as Record<string, unknown>;
        const references: Array<{ resource_kind: string; resource_id: string; step: string; purpose: string; slot_id: string }> = [];
        if (nextState.tts_ref_audio_id) references.push({ resource_kind: "voice", resource_id: String(nextState.tts_ref_audio_id), step: "voice", purpose: "reference", slot_id: "voice-reference" });
        if (nextState.portrait_id) references.push({ resource_kind: "digital_human", resource_id: String(nextState.portrait_id), step: "digital_human", purpose: "portrait", slot_id: "digital-human" });
        if (nextState.digital_human_scene_id) references.push({ resource_kind: "digital_human_scene", resource_id: String(nextState.digital_human_scene_id), step: "digital_human", purpose: "scene", slot_id: "digital-human-scene" });
        if (nextState.brand_kit_id) references.push({ resource_kind: "brand", resource_id: String(nextState.brand_kit_id), step: "postproduction", purpose: "brand_kit", slot_id: "brand" });
        if (nextState.template_id) references.push({ resource_kind: "template", resource_id: String(nextState.template_id), step: "postproduction", purpose: "template", slot_id: "template" });
        const groups = Array.isArray(nextState.visual_groups) ? nextState.visual_groups : [];
        groups.forEach((group, index) => {
          if (!group || typeof group !== "object") return;
          const value = group as Record<string, unknown>;
          if (value.visual_type === "uploaded_video" && value.video_asset_id) references.push({ resource_kind: "video", resource_id: String(value.video_asset_id), step: "postproduction", purpose: "overlay_video", slot_id: String(value.group_id || `overlay-${index + 1}`) });
          if (value.visual_type === "uploaded_image" && value.image_asset_id) references.push({ resource_kind: "image", resource_id: String(value.image_asset_id), step: "postproduction", purpose: "overlay_image", slot_id: String(value.group_id || `overlay-${index + 1}`) });
        });
        void reconcileSessionResourceUsageV2(currentSessionId, references).catch(() => undefined);
      }
    } finally {
      setConfigSaving(false);
    }
  }

  function openAssetTab(tab: AssetTab) {
    setAssetTab(tab);
    navigateToView("assets");
  }

  function openView(nextView: View) {
    if (nextView === "ip") {
      setActiveStep(1);
    }
    navigateToView(nextView);
  }

  function navigateToView(nextView: View) {
    setView(nextView);
    router?.navigate(pathForView(nextView));
  }

  function openPublishCenter(packageId?: string) {
    setView("publish_accounts");
    router?.navigate(packageId ? `/publish?package_id=${encodeURIComponent(packageId)}` : "/publish");
  }

  function openNavItem(key: NavKey) {
    openView(key);
  }

  function selectedNavKey(): string {
    if (view === "digital_human_app" || view === "application_workflow") return "apps";
    if (view === "assets") return "assets";
    return view;
  }

  async function startNewIpSession() {
    setBusy(false);
    setTask(null);
    setWorkflowError("");
    const created = await createSession();
    window.localStorage.setItem(IPB_SESSION_STORAGE_KEY, created.session_id);
    window.localStorage.removeItem(IPB_TASK_STORAGE_KEY);
    setSession(created);
    setActiveStep(1);
    navigateToView("ip");
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
              <span>企业视频工作台</span>
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
                {viewTitle(view, assetTab)}
              </Typography.Title>
              <Typography.Text type="secondary">
                {viewDescription(view)}
              </Typography.Text>
            </div>
            <Tag color="default">本机安全模式</Tag>
          </Layout.Header>
          <Layout.Content className="app-content">
            {appError ? (
              <Alert
                className="global-alert"
                type="error"
                showIcon
                title={appError}
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

            {view === "apps" ? (
              <ApplicationCenterView onOpenApp={(application) => {
                setCreationAppId(application.appId);
                if (application.routePath && router) router.navigate(application.routePath);
                else navigateToView("home");
              }} />
            ) : null}

            {view === "digital_human_app" ? (
              <DigitalHumanApplicationView onBack={() => navigateToView("apps")} />
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
                    onOpenPublishCenter={openPublishCenter}
                    goToStep={setActiveStep}
                  />
                </section>

                {storyboardOpen ? (
                  <StoryboardModal
                    session={session}
                    videos={assets.videos}
                    images={assets.images}
                    patch={patch}
                    reloadAssets={reloadAssets}
                    openAssetTab={openAssetTab}
                    onClose={() => setStoryboardOpen(false)}
                  />
                ) : null}
              </section>
            ) : null}

      {view === "application_workflow" ? (
        <Suspense fallback={<div className="workspace-loading">正在加载应用流程…</div>}>
          <CreationWorkspace
            appId={creationAppId}
            focused
            initialSourceArtifactVersionId={creationSourceArtifactVersionId}
            onBack={() => { setCreationSourceArtifactVersionId(""); navigateToView("apps"); }}
            onOpenApp={(nextAppId, sourceVersionId) => {
              setCreationAppId(nextAppId);
              setCreationSourceArtifactVersionId(sourceVersionId || "");
              router?.navigate(nextAppId === "builtin.douyin-carousel" ? "/apps/douyin-carousel" : "/apps");
            }}
          />
        </Suspense>
      ) : null}

      {view === "home" ? (
        <Suspense fallback={<div className="workspace-loading">正在加载企业视频工作台…</div>}>
          {featureFlags.appCenterShell ? <CreationWorkspace appId={creationAppId} /> : null}
          <DashboardView
            assets={{
              videos: assets.videos.length,
              images: assets.images.length,
              voices: assets.voices.length,
              portraits: assets.portraits.length,
              templates: assets.templates.length,
              brands: assets.brands.length,
            }}
            onStart={() => startNewIpSession().catch((err) => setAppError(formatUiError(err)))}
            onAssets={() => navigateToView("assets")}
            onAssetTab={openAssetTab}
            onConfig={() => navigateToView("config")}
            onDiagnostics={() => navigateToView("diagnostics")}
            onTasks={() => navigateToView("tasks")}
            onPublish={() => navigateToView("publish_accounts")}
          />
        </Suspense>
      ) : null}

      {view === "assets" ? (
        featureFlags.assetCenterV2 && featureFlags.assetCenterSmbUx ? (
          <AssetCenterV2
            onUse={(item, sceneId) => {
              navigateToView("ip");
              if (!session) return;
              const values: Record<string, unknown> =
                item.kind === "voice"
                  ? { tts_ref_audio_id: item.resource_id, tts_ref_audio_path: item.file_url || "" }
                  : item.kind === "audio"
                    ? { bgm_asset_id: item.resource_id, bgm_path: item.file_url || "", brand_bgm_asset_id: "" }
                  : item.kind === "digital_human"
                      ? { portrait_id: item.resource_id, portrait_path: item.file_url || "", portrait_media_type: item.summary.media_type || "image", digital_human_scene_id: sceneId || item.summary.default_scene_id || "" }
                      : item.kind === "template"
                      ? { template_id: item.resource_id }
                      : item.kind === "brand"
                        ? { brand_kit_id: item.resource_id, brand_bgm_asset_id: String(item.brand?.default_bgm_asset_id || "") }
                        : {};
              if (Object.keys(values).length) void patch(values);
            }}
          />
        ) : (
          <AssetsView
            assets={assets}
            activeTab={assetTab}
            setActiveTab={setAssetTab}
            reload={reloadAssets}
            assetCenterV2={featureFlags.assetCenterV2}
          />
        )
      ) : null}
      {view === "publish_accounts" ? <PublishCenterView /> : null}
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
    assets.voices.length +
    assets.portraits.length +
    assets.templates.length +
    assets.videos.length +
    assets.images.length +
    assets.brands.length;
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
        <MetricCard label="图片素材" value={assets.images.length} />
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
          {task.error ? <Alert type="error" showIcon title={task.error} /> : null}
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
    needs_review: "warning",
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
  onOpenPublishCenter,
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
  onOpenPublishCenter: (packageId?: string) => void;
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
        <Suspense fallback={<div className="workspace-loading">正在加载发布工作区…</div>}>
          <PublishWorkspace session={session} downloadFinalVideo={downloadFinalVideo} onOpenPublishCenter={onOpenPublishCenter} />
        </Suspense>
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
        title={isTaskFailed ? task?.error || "任务执行失败" : error}
      />
    );
  }

  if (isTaskCancelled) {
    return (
      <Alert
        className="step-notice"
        type="warning"
        showIcon
        title="已停止当前生产任务，已有素材不会被清空。"
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
      title={notice.message}
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
  const [brandV2PickerOpen, setBrandV2PickerOpen] = useState(false);
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
                      title="已生成候选选题，请选择 1 个再生成文案。"
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
            {featureFlags.assetCenterV2 ? (
              <div className="inline-asset-picker">
                <button type="button" onClick={() => setBrandV2PickerOpen(true)}>
                  {selectedBrand?.brand_name || (session.state.brand_kit_id ? `已选品牌包 · ${String(session.state.brand_kit_id).slice(0, 14)}` : "选择品牌包")}
