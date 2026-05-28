import {
  AlertCircle,
  CheckCircle2,
  Images,
  Loader2,
  Mic2,
  MonitorStop,
  Package,
  Settings,
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
  Tabs,
  Tag,
  Typography,
} from "antd";
import type { MenuProps } from "antd";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  assetBlobUrl,
  cancelTask,
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
  listBrandKits,
  listIpPresetAssets,
  listIpTemplateAssets,
  listPortraitAssets,
  listTasks,
  listVideoAssets,
  listVoiceAssets,
  PortraitAsset,
  BrandKit,
  DesktopConfig,
  IpBroadcastState,
  IpPresetAsset,
  IpTemplateAsset,
  retryTask,
  runStep,
  saveDesktopConfig,
  TaskInfo,
  updateBrandKit,
  updateSessionConfig,
  uploadPortraitAsset,
  uploadVideoAsset,
  uploadVoiceAsset,
  VideoAsset,
  VoiceAsset,
} from "./api";
import { createAntdTheme, readStoredThemeSkin, themeSkins, type ThemeSkin } from "./theme";

type View = "ip" | "assets" | "tasks" | "config" | "diagnostics";
type AssetTab = "voices" | "portraits" | "templates" | "videos" | "brands";

type AssetState = {
  voices: VoiceAsset[];
  portraits: PortraitAsset[];
  templates: IpTemplateAsset[];
  presets: IpPresetAsset[];
  videos: VideoAsset[];
  brands: BrandKit[];
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

const stepTitles = [
  "素材来源",
  "文案确认",
  "声音生成",
  "数字人视频",
  "一键成片",
  "视频发布",
];

const sourceModeLabels: Record<string, string> = {
  video_extract: "视频提取",
  paste: "粘贴脚本",
  industry_persona: "行业+人设",
  ip_learning: "IP学习",
};

const emptyAssets: AssetState = {
  voices: [],
  portraits: [],
  templates: [],
  presets: [],
  videos: [],
  brands: [],
};

const navItems: MenuProps["items"] = [
  { key: "ip", icon: <Video size={16} />, label: "IP口播" },
  { key: "assets", icon: <Package size={16} />, label: "素材资产" },
  { key: "tasks", icon: <CheckCircle2 size={16} />, label: "任务中心" },
  { key: "config", icon: <Settings size={16} />, label: "配置" },
  { key: "diagnostics", icon: <CheckCircle2 size={16} />, label: "诊断" },
];

export function App() {
  const [view, setView] = useState<View>("ip");
  const [assetTab, setAssetTab] = useState<AssetTab>("voices");
  const [themeSkin, setThemeSkinState] = useState<ThemeSkin>(() => readStoredThemeSkin());
  const [assets, setAssets] = useState<AssetState>(emptyAssets);
  const [session, setSession] = useState<IpBroadcastState | null>(null);
  const [activeStep, setActiveStep] = useState(1);
  const [task, setTask] = useState<TaskInfo | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [storyboardOpen, setStoryboardOpen] = useState(false);

  useEffect(() => {
    restoreOrCreateSession().catch((err) => setError(String(err)));
    reloadAssets().catch((err) => setError(String(err)));
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
        setActiveStep(restored.current_step || 1);
        return;
      } catch {
        window.localStorage.removeItem("pixelle_ipb_session_id");
      }
    }
    const created = await createSession();
    window.localStorage.setItem("pixelle_ipb_session_id", created.session_id);
    setSession(created);
    setActiveStep(created.current_step || 1);
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
          setActiveStep(fresh.current_step || activeStep);
          if (latestTask.status === "failed") setError(latestTask.error || "任务执行失败");
        }
      } catch (err) {
        setBusy(false);
        setError(String(err));
      }
    }, 1500);
    return () => window.clearInterval(timer);
  }, [activeStep, session, task]);

  const completedPercent = useMemo(() => {
    if (!session) return 0;
    return Math.round((session.completed_steps / 6) * 100);
  }, [session]);

  async function reloadAssets() {
    const [voices, portraits, templates, presets, videos, brands] = await Promise.all([
      listVoiceAssets(),
      listPortraitAssets(),
      listIpTemplateAssets(),
      listIpPresetAssets(),
      listVideoAssets(),
      listBrandKits(),
    ]);
    setAssets({
      voices: voices.items,
      portraits: portraits.items,
      templates: templates.items,
      presets: presets.items,
      videos: videos.items,
      brands: brands.items,
    });
  }

  async function execute(stepKey: string) {
    if (!session) return;
    setBusy(true);
    setError("");
    setTask(null);
    try {
      const result = await runStep(session.session_id, stepKey);
      setTask({ task_id: result.task_id, status: "pending" });
    } catch (err) {
      setBusy(false);
      setError(String(err));
    }
  }

  async function stopCurrentTask() {
    if (!task) return;
    try {
      await cancelTask(task.task_id);
      setBusy(false);
      setTask({ ...task, status: "cancelled" });
    } catch (err) {
      setError(String(err));
    }
  }

  async function patch(values: Record<string, unknown>) {
    if (!session) return;
    const updated = await updateSessionConfig(session.session_id, values);
    setSession(updated);
  }

  async function downloadFinalVideo() {
    if (!session) return;
    try {
      await downloadArtifact(session.session_id, "final_video");
    } catch (err) {
      setError(String(err));
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
            selectedKeys={[view]}
            items={navItems}
            onClick={(item) => setView(item.key as View)}
          />
        </Layout.Sider>
        <Layout>
          <Layout.Header className="app-header">
            <div>
              <Typography.Title level={3}>老板 IP 口播智能体</Typography.Title>
              <Typography.Text type="secondary">桌面版 v1：工作台生产，资产库独立维护。</Typography.Text>
            </div>
            <Tag color="processing">{themeSkins[themeSkin].label}</Tag>
          </Layout.Header>
          <Layout.Content className="app-content">
            {error ? (
              <Alert
                className="global-alert"
                type="error"
                showIcon
                message={error}
                icon={<AlertCircle size={16} />}
              />
            ) : null}

      {view === "ip" && session ? (
        <section className="workspace">
          <ProductionConsole
            session={session}
            task={task}
            busy={busy}
            completedPercent={completedPercent}
            onContinue={() => execute(session.next_action.key)}
            onStop={stopCurrentTask}
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
              busy={busy}
              openStoryboard={() => setStoryboardOpen(true)}
              downloadFinalVideo={downloadFinalVideo}
            />
          </section>

          <BottomActionBar
            session={session}
            activeStep={activeStep}
            busy={busy}
            setActiveStep={setActiveStep}
            execute={execute}
          />

          {storyboardOpen ? (
            <StoryboardModal
              session={session}
              videos={assets.videos}
              patch={patch}
              onClose={() => setStoryboardOpen(false)}
            />
          ) : null}
        </section>
      ) : null}

      {view === "assets" ? (
        <AssetsView
          assets={assets}
          activeTab={assetTab}
          setActiveTab={setAssetTab}
          reload={reloadAssets}
        />
      ) : null}
      {view === "tasks" ? <TaskCenterView /> : null}
      {view === "config" ? <ConfigView themeSkin={themeSkin} setThemeSkin={setThemeSkin} /> : null}
      {view === "diagnostics" ? <DiagnosticsView /> : null}
          </Layout.Content>
        </Layout>
      </Layout>
    </ConfigProvider>
  );
}

function ProductionConsole({
  session,
  task,
  busy,
  completedPercent,
  onContinue,
  onStop,
}: {
  session: IpBroadcastState;
  task: TaskInfo | null;
  busy: boolean;
  completedPercent: number;
  onContinue: () => void;
  onStop: () => void;
}) {
  const taskStatus = task
    ? `当前任务：${taskStatusLabel(task.status)} · ${task.task_id.slice(0, 8)}`
    : "当前无任务";
  return (
    <Card className="console" variant="borderless">
      <div className="console-main">
        <Space align="center" size={10}>
          <Typography.Title level={4}>生产主控台</Typography.Title>
          <Tag color={session.completed_steps >= 6 ? "success" : "processing"}>
            {session.completed_steps}/6 已完成
          </Tag>
        </Space>
        <Typography.Paragraph type="secondary">{session.next_action.description}</Typography.Paragraph>
        <Progress percent={completedPercent} showInfo={false} />
        <Typography.Text type="secondary">
          {session.missing_requirements.length
            ? `缺失项：${session.missing_requirements.join(" · ")}`
            : "关键素材已准备好。"}
        </Typography.Text>
      </div>
      <div className="task-panel">
        <Tag>{taskStatus}</Tag>
        {task?.progress?.message ? (
          <Typography.Text type="secondary">{task.progress.message}</Typography.Text>
        ) : null}
        {task?.error ? <Typography.Text type="danger">{task.error}</Typography.Text> : null}
        <Space>
          {busy && task ? (
            <Button onClick={onStop} icon={<MonitorStop size={16} />}>
              停止
            </Button>
          ) : null}
          <Button
            type="primary"
            disabled={busy || session.next_action.disabled}
            onClick={onContinue}
            icon={busy ? <Loader2 className="spin" size={16} /> : undefined}
          >
            一键继续：{session.next_action.label}
          </Button>
        </Space>
      </div>
    </Card>
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
          const status = session.step_status[String(step)] || "pending";
          return {
            title,
            description: stepStatusLabel(status),
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
  openStoryboard,
  downloadFinalVideo,
}: {
  step: number;
  session: IpBroadcastState;
  assets: AssetState;
  patch: (values: Record<string, unknown>) => Promise<void>;
  execute: (stepKey: string) => Promise<void>;
  busy: boolean;
  openStoryboard: () => void;
  downloadFinalVideo: () => Promise<void>;
}) {
  const notice = session.notices[String(step)];
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
        <SourceStep
          session={session}
          presets={assets.presets}
          brands={assets.brands}
          patch={patch}
          execute={execute}
          busy={busy}
        />
      ) : null}
      {step === 2 ? <CopywritingStep session={session} patch={patch} execute={execute} busy={busy} /> : null}
      {step === 3 ? (
        <VoiceStep session={session} voices={assets.voices} patch={patch} execute={execute} busy={busy} />
      ) : null}
      {step === 4 ? (
        <PortraitStep
          session={session}
          portraits={assets.portraits}
          patch={patch}
          execute={execute}
          busy={busy}
        />
      ) : null}
      {step === 5 ? (
        <PostproductionStep
          session={session}
          templates={assets.templates}
          videos={assets.videos}
          patch={patch}
          execute={execute}
          busy={busy}
          openStoryboard={openStoryboard}
        />
      ) : null}
      {step === 6 ? (
        <PublishStep session={session} downloadFinalVideo={downloadFinalVideo} />
      ) : null}
      {notice ? (
        <Alert className="step-notice" type={noticeKind(notice.kind)} showIcon message={notice.message} />
      ) : null}
    </Card>
  );
}

function SourceStep({
  session,
  presets,
  brands,
  patch,
  execute,
  busy,
}: {
  session: IpBroadcastState;
  presets: IpPresetAsset[];
  brands: BrandKit[];
  patch: (values: Record<string, unknown>) => Promise<void>;
  execute: (stepKey: string) => Promise<void>;
  busy: boolean;
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
  async function applyPreset(presetId: string) {
    const preset = presets.find((item) => item.preset_id === presetId);
    if (!preset) {
      await patch({ business_preset_id: "" });
      return;
    }
    await patch({
      business_preset_id: preset.preset_id,
      word_count: preset.recommended_word_count,
      style_prompt: preset.default_style_prompt,
      template_id: preset.default_template_id,
      subtitle_enabled: preset.default_subtitle_enabled,
    });
  }
  const sourceActions: Record<string, string> = {
    video_extract: "提取视频口播文案",
    paste: "整理为口播文案",
    industry_persona: "生成口播文案",
    ip_learning: ipTopics.length ? "用选题生成文案" : "学习最近 5 条视频",
  };
  return (
    <div>
      <div className="grid2">
        <div>
          <label>业务预设</label>
          <select
            value={(session.state.business_preset_id as string) || ""}
            onChange={(event) => applyPreset(event.target.value)}
          >
            <option value="">不使用预设</option>
            {presets.map((preset) => (
              <option key={preset.preset_id} value={preset.preset_id}>
                {preset.display_name}
              </option>
            ))}
          </select>
          {selectedPreset ? (
            <small className="muted">{selectedPreset.recommended_visual_strategy}</small>
          ) : null}
        </div>
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
                  没有现成素材时，用行业、人设和卖点直接生成第一版口播文案。
                </Typography.Paragraph>
                <div className="grid2">
                  <div>
                    <label>视频类型</label>
                    <select
                      value={(session.state.video_type as string) || "口播文案"}
                      onChange={(event) =>
                        patch({ source_mode: "industry_persona", video_type: event.target.value })
                      }
                    >
                      {["口播文案", "种草带货", "干货教程", "故事分享", "情绪表达", "品牌推广"].map(
                        (item) => (
                          <option key={item} value={item}>
                            {item}
                          </option>
                        ),
                      )}
                    </select>
                  </div>
                  <div>
                    <label>文案类型</label>
                    <select
                      value={(session.state.copy_type as string) || "人设型"}
                      onChange={(event) =>
                        patch({ source_mode: "industry_persona", copy_type: event.target.value })
                      }
                    >
                      {["人设型", "干货型", "情绪共鸣型", "痛点解决型", "促销转化型"].map((item) => (
                        <option key={item} value={item}>
                          {item}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
                <label>行业与人设</label>
                <textarea
                  className="small-textarea"
                  defaultValue={(session.state.industry_persona as string) || ""}
                  onBlur={(event) =>
                    patch({ source_mode: "industry_persona", industry_persona: event.target.value })
                  }
                  placeholder="例如：火锅店老板，十年重庆火锅经验，熟悉牛油锅底和本地客群"
                />
                <div className="grid2">
                  <div>
                    <label>核心卖点</label>
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
                    <label>目标客户</label>
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
                <label>活动/转化口令</label>
                <input
                  defaultValue={(session.state.conversion_phrase as string) || ""}
                  onBlur={(event) =>
                    patch({ source_mode: "industry_persona", conversion_phrase: event.target.value })
                  }
                  placeholder="例如：到店报口令打九折"
                />
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
                ) : null}
              </div>
            ),
          },
        ]}
      />
      <div className="panel-actions">
        <Button type="primary" onClick={() => execute("source")} disabled={busy}>
          {sourceActions[sourceMode] || "生成口播文案"}
        </Button>
      </div>
    </div>
  );
}

function CopywritingStep({
  session,
  patch,
  execute,
  busy,
}: {
  session: IpBroadcastState;
  patch: (values: Record<string, unknown>) => Promise<void>;
  execute: (stepKey: string) => Promise<void>;
  busy: boolean;
}) {
  return (
    <div>
      <label>最终口播文案</label>
      <textarea
        className="script-editor"
        defaultValue={(session.state.final_script as string) || ""}
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
      <div className="panel-actions">
        <button className="primary" onClick={() => execute("copywriting")} disabled={busy}>
          AI 改写/优化文案
        </button>
      </div>
    </div>
  );
}

function VoiceStep({
  session,
  voices,
  patch,
  execute,
  busy,
}: {
  session: IpBroadcastState;
  voices: VoiceAsset[];
  patch: (values: Record<string, unknown>) => Promise<void>;
  execute: (stepKey: string) => Promise<void>;
  busy: boolean;
}) {
  return (
    <div>
      <div className="grid2">
        <div>
          <label>推理模式</label>
          <select
            value={(session.state.tts_inference_mode as string) || "local"}
            onChange={(event) => patch({ tts_inference_mode: event.target.value })}
          >
            <option value="local">local Edge TTS</option>
            <option value="comfyui">ComfyUI / RunningHub</option>
          </select>
        </div>
        <div>
          <label>语速</label>
          <input
            type="number"
            step="0.1"
            defaultValue={(session.state.tts_speed as number) || 1.2}
            onBlur={(event) => patch({ tts_speed: Number(event.target.value) })}
          />
        </div>
      </div>
      <label>音色库</label>
      <div className="asset-grid compact">
        {voices.length ? (
          voices.map((voice) => (
            <button
              key={voice.reference_id}
              className={`asset-card selectable ${
                session.state.tts_ref_audio_path === voice.asset_path ? "selected" : ""
              }`}
              onClick={() =>
                patch({
                  tts_ref_audio_id: voice.reference_id,
                  tts_ref_audio_path: voice.asset_path,
                })
              }
            >
              <Mic2 size={20} />
              <strong>{voice.name}</strong>
              <span>{voice.filename}</span>
            </button>
          ))
        ) : (
          <div className="empty-state">暂无参考音色。请到素材资产 &gt; 音色库维护。</div>
        )}
      </div>
      <div className="grid2">
        <div>
          <label>Edge 音色</label>
          <input
            defaultValue={(session.state.tts_voice as string) || "zh-CN-YunjianNeural"}
            onBlur={(event) => patch({ tts_voice: event.target.value })}
          />
        </div>
        <div>
          <label>TTS 工作流</label>
          <input
            defaultValue={(session.state.tts_workflow as string) || ""}
            onBlur={(event) => patch({ tts_workflow: event.target.value })}
            placeholder="runninghub/tts_edge.json"
          />
        </div>
      </div>
      <div className="panel-actions">
        <button className="primary" onClick={() => execute("voice")} disabled={busy}>
          生成语音
        </button>
      </div>
    </div>
  );
}

function PortraitStep({
  session,
  portraits,
  patch,
  execute,
  busy,
}: {
  session: IpBroadcastState;
  portraits: PortraitAsset[];
  patch: (values: Record<string, unknown>) => Promise<void>;
  execute: (stepKey: string) => Promise<void>;
  busy: boolean;
}) {
  return (
    <div>
      <label>形象库</label>
      <div className="asset-grid portraits">
        {portraits.length ? (
          portraits.map((portrait) => (
            <button
              key={portrait.portrait_id}
              className={`asset-card portrait selectable ${
                session.state.portrait_id === portrait.portrait_id ? "selected" : ""
              }`}
              onClick={() =>
                patch({
                  portrait_id: portrait.portrait_id,
                  portrait_path: portrait.asset_path,
                  portrait_media_type: portrait.media_type,
                })
              }
            >
              {portrait.media_type === "image" ? (
                <AssetImage src={portrait.file_url} alt={portrait.name} />
              ) : (
                <div className="video-thumb">VIDEO</div>
              )}
              <strong>{portrait.name}</strong>
              <span>{portrait.media_type === "video" ? "视频形象" : "图片形象"}</span>
            </button>
          ))
        ) : (
          <div className="empty-state">暂无数字人形象。请到素材资产 &gt; 形象库维护。</div>
        )}
      </div>
      <div className="grid2">
        <div>
          <label>数字人工作流</label>
          <select
            value={(session.state.digital_human_workflow as string) || ""}
            onChange={(event) => patch({ digital_human_workflow: event.target.value })}
          >
            <option value="workflows/runninghub/digital_combination.json">
              旧版数字人组合工作流
            </option>
            <option value="workflows/runninghub/digital_human_ai_app.json">
              AI 应用数字人口播
            </option>
            <option value="workflows/runninghub/digital_human_fast_ai_app.json">
              AI 应用快速版
            </option>
            <option value="workflows/runninghub/digital_human_lipsync_ai_app.json">
              视频改口型
            </option>
          </select>
        </div>
        <div>
          <label>宽高</label>
          <div className="inline-inputs">
            <input
              type="number"
              defaultValue={(session.state.digital_human_width as number) || 720}
              onBlur={(event) => patch({ digital_human_width: Number(event.target.value) })}
            />
            <input
              type="number"
              defaultValue={(session.state.digital_human_height as number) || 1280}
              onBlur={(event) => patch({ digital_human_height: Number(event.target.value) })}
            />
          </div>
        </div>
      </div>
      <label>口播动作提示词</label>
      <textarea
        className="small-textarea"
        defaultValue={(session.state.digital_human_prompt as string) || ""}
        onBlur={(event) => patch({ digital_human_prompt: event.target.value })}
      />
      <div className="panel-actions">
        <button className="primary" onClick={() => execute("digital_human")} disabled={busy}>
          生成数字人视频
        </button>
      </div>
    </div>
  );
}

function PostproductionStep({
  session,
  templates,
  videos,
  patch,
  execute,
  busy,
  openStoryboard,
}: {
  session: IpBroadcastState;
  templates: IpTemplateAsset[];
  videos: VideoAsset[];
  patch: (values: Record<string, unknown>) => Promise<void>;
  execute: (stepKey: string) => Promise<void>;
  busy: boolean;
  openStoryboard: () => void;
}) {
  const groups = readGroups(session.state.visual_groups);
  const segments = splitSegments((session.state.final_script as string) || "");
  return (
    <div>
      <label>画面模板</label>
      <div className="asset-grid templates">
        {templates.map((template) => (
          <button
            key={template.template_id}
            className={`asset-card template selectable ${
              session.state.template_id === template.template_id ? "selected" : ""
            }`}
            onClick={() => patch({ template_id: template.template_id })}
            title={template.full_description}
          >
            <AssetImage src={template.preview_url} alt={template.display_name} />
            <strong>{template.display_name}</strong>
            <span>{template.short_description}</span>
          </button>
        ))}
      </div>

      <div className="summary-box">
        <div>
          <strong>画面规划</strong>
          <p>
            {groups.length
              ? `已配置 ${groups.length} 个覆盖组，覆盖 ${groups.reduce(
                  (sum, group) => sum + group.segment_ids.length,
                  0,
                )} 段文案。`
              : `当前 ${segments.length} 段文案，未配置覆盖组，默认全程数字人。`}
          </p>
          <small>可选择视频素材、AI 视频 prompt，保存后由第 5 步读取规划。</small>
        </div>
        <button onClick={openStoryboard}>打开画面规划</button>
      </div>

      <details className="advanced" open={false}>
        <summary>高级成片设置</summary>
        <div className="grid2">
          <label className="checkline">
            <input
              type="checkbox"
              defaultChecked={(session.state.subtitle_enabled as boolean) ?? true}
              onChange={(event) => patch({ subtitle_enabled: event.target.checked })}
            />
            开启字幕
          </label>
          <label className="checkline">
            <input
              type="checkbox"
              defaultChecked={(session.state.remove_silence as boolean) || false}
              onChange={(event) => patch({ remove_silence: event.target.checked })}
            />
            去静音
          </label>
          <div>
            <label>BGM 路径</label>
            <input
              defaultValue={(session.state.bgm_path as string) || ""}
              onBlur={(event) => patch({ bgm_path: event.target.value })}
              placeholder="可选"
            />
          </div>
          <div>
            <label>BGM 音量</label>
            <input
              type="number"
              step="0.1"
              defaultValue={(session.state.bgm_volume as number) || 0.3}
              onBlur={(event) => patch({ bgm_volume: Number(event.target.value) })}
            />
          </div>
        </div>
      </details>

      <div className="summary-box subtle">
        <span>视频素材库：{videos.length} 个素材可用于画面规划。</span>
      </div>

      <div className="panel-actions">
        <button className="primary" onClick={() => execute("postproduction")} disabled={busy}>
          一键成片
        </button>
      </div>
    </div>
  );
}

function PublishStep({
  session,
  downloadFinalVideo,
}: {
  session: IpBroadcastState;
  downloadFinalVideo: () => Promise<void>;
}) {
  const publishPackage = (session.state.publish_package as Record<string, unknown>) || {};
  const platformSuggestions =
    (publishPackage.platform_suggestions as Record<string, Record<string, unknown>>) ||
    ((session.state.platform_suggestions as Record<string, Record<string, unknown>>) ?? {});
  const title = (publishPackage.title as string) || (session.state.title as string) || "";
  const description =
    (publishPackage.description as string) || (session.state.description as string) || "";
  const hashtags = ((publishPackage.hashtags as string[]) || (session.state.hashtags as string[]) || []).join(
    " ",
  );
  const script = (publishPackage.script as string) || (session.state.final_script as string) || "";
  return (
    <div className="publish-workbench">
      <Card className="publish-hero" variant="borderless">
        <div>
          <Typography.Title level={4}>发布素材包已准备好</Typography.Title>
          <Typography.Text type="secondary">
            建议先下载最终视频，再按平台复制标题、描述和标签。
          </Typography.Text>
        </div>
        <Space wrap>
          {session.artifacts.final_video ? (
            <Button type="primary" onClick={downloadFinalVideo}>
              下载最终视频
            </Button>
          ) : null}
          <CopyButton text={[title, description, hashtags].filter(Boolean).join("\n")} label="复制全部" />
          {session.artifacts.publish_package_json ? (
            <Button onClick={() => downloadArtifact(session.session_id, "publish_package_json")}>
              下载 JSON
            </Button>
          ) : null}
        </Space>
      </Card>

      <div className="publish-layout">
        <div className="publish-main">
          <Card title="通用发布信息" variant="borderless">
            <PublishField label="标题" value={title} minRows={2} />
            <PublishField label="描述" value={description} minRows={4} />
            <PublishField label="标签" value={hashtags} minRows={1} singleLine />
            <PublishField
              label="口播文案"
              value={script}
              minRows={6}
              extra={
                session.artifacts.script ? (
                  <Button onClick={() => downloadArtifact(session.session_id, "script")}>
                    下载文案
                  </Button>
                ) : null
              }
            />
          </Card>

          <Card title="平台建议" variant="borderless">
            <div className="platform-grid">
              {Object.entries(platformSuggestions).map(([platform, value]) => {
                const platformText = `${String(value.title || "")}\n${String(value.description || "")}`;
                return (
                  <section key={platform} className="platform-card">
                    <Tag color="processing">{platformLabel(platform)}</Tag>
                    <strong>{String(value.title || "") || "暂无标题建议"}</strong>
                    <p>{String(value.description || "") || "暂无描述建议"}</p>
                    <CopyButton text={platformText} label="复制该平台素材" />
                  </section>
                );
              })}
              {!Object.keys(platformSuggestions).length ? (
                <div className="empty-state">暂无平台建议。请先完成一键成片生成发布素材。</div>
              ) : null}
            </div>
          </Card>
        </div>

        <aside className="publish-aside">
          <Card title="视频与文件" variant="borderless">
            <div className="video-preview-shell">
              <Video size={36} />
              <span>视频预览</span>
            </div>
            <Divider />
            <Typography.Text type="secondary">最终视频路径</Typography.Text>
            <p className="result-path">{(session.state.final_video_path as string) || "暂无最终视频"}</p>
            <Space direction="vertical" className="publish-file-actions">
              {session.artifacts.final_video ? (
                <Button type="primary" block onClick={downloadFinalVideo}>
                  下载最终视频
                </Button>
              ) : null}
              {session.artifacts.publish_package_json ? (
                <Button block onClick={() => downloadArtifact(session.session_id, "publish_package_json")}>
                  下载发布素材 JSON
                </Button>
              ) : null}
            </Space>
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
}: {
  label: string;
  value: string;
  minRows: number;
  singleLine?: boolean;
  extra?: ReactNode;
}) {
  return (
    <section className="publish-field">
      <div className="publish-field-title">
        <strong>{label}</strong>
        <Space>
          {extra}
          <CopyButton text={value} />
        </Space>
      </div>
      {singleLine ? <input readOnly value={value} /> : <textarea readOnly value={value} rows={minRows} />}
    </section>
  );
}

function CopyButton({ text, label = "复制" }: { text: string; label?: string }) {
  return (
    <Button onClick={() => navigator.clipboard.writeText(text)} disabled={!text}>
      {label}
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

function BottomActionBar({
  session,
  activeStep,
  busy,
  setActiveStep,
  execute,
}: {
  session: IpBroadcastState;
  activeStep: number;
  busy: boolean;
  setActiveStep: (step: number) => void;
  execute: (stepKey: string) => Promise<void>;
}) {
  const currentKey = Object.entries({
    source: 1,
    copywriting: 2,
    voice: 3,
    digital_human: 4,
    postproduction: 5,
    publish: 6,
  }).find(([, step]) => step === activeStep)?.[0];
  return (
    <section className="actionbar">
      <button disabled={activeStep <= 1} onClick={() => setActiveStep(activeStep - 1)}>
        上一步
      </button>
      <button disabled={activeStep >= 6} onClick={() => setActiveStep(activeStep + 1)}>
        下一步
      </button>
      {currentKey ? (
        <button className="primary" disabled={busy} onClick={() => execute(currentKey)}>
          执行当前步骤
        </button>
      ) : null}
      <button
        disabled={busy || session.next_action.disabled}
        onClick={() => execute(session.next_action.key)}
      >
        一键继续：{session.next_action.label}
      </button>
    </section>
  );
}

function StoryboardModal({
  session,
  videos,
  patch,
  onClose,
}: {
  session: IpBroadcastState;
  videos: VideoAsset[];
  patch: (values: Record<string, unknown>) => Promise<void>;
  onClose: () => void;
}) {
  const segments = splitSegments((session.state.final_script as string) || "");
  const [selected, setSelected] = useState<string[]>([]);
  const [groups, setGroups] = useState<VisualGroup[]>(readGroups(session.state.visual_groups));
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
            <p>勾选连续段落成组，为每组选择覆盖视频或 AI 视频提示词。</p>
          </div>
          <button onClick={onClose}>关闭</button>
        </div>
        <div className="storyboard-layout">
          <div className="storyboard-segments">
            <h3>文案段落</h3>
            {segments.length ? (
              segments.map((segment) => (
                <label key={segment.segment_id} className="segment-row">
                  <input
                    type="checkbox"
                    checked={selected.includes(segment.segment_id)}
                    onChange={() => toggleSegment(segment.segment_id)}
                  />
                  <span>{segment.index}</span>
                  <em>{segment.text}</em>
                </label>
              ))
            ) : (
              <div className="empty-state">暂无可拆分文案。请先在第 2 步填写最终口播文案。</div>
            )}
            <button disabled={!canCreate} onClick={createGroup}>
              勾选段落成组
            </button>
            {selected.length && !canCreate ? (
              <small className="task-error">v1 只支持连续段落成组。</small>
            ) : null}
          </div>
          <div className="storyboard-groups">
            <h3>覆盖组</h3>
            {groups.length ? (
              groups.map((group) => (
                <GroupEditor
                  key={group.group_id}
                  group={group}
                  videos={videos}
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
  update,
  remove,
}: {
  group: VisualGroup;
  videos: VideoAsset[];
  update: (group: VisualGroup) => void;
  remove: () => void;
}) {
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
          <label>视频素材</label>
          <select
            value={group.video_asset_id}
            onChange={(event) => {
              const video = videos.find((item) => item.asset_id === event.target.value);
              update({
                ...group,
                video_asset_id: event.target.value,
                uploaded_video_path: video?.asset_path || "",
              });
            }}
          >
            <option value="">请选择视频素材</option>
            {videos.map((video) => (
              <option key={video.asset_id} value={video.asset_id}>
                {video.name}
              </option>
            ))}
          </select>
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
  return (
    <AssetLibraryShell
      title="音色库"
      accept="audio/*"
      upload={uploadVoiceAsset}
      onUploaded={reload}
      cards={
        <div className="asset-grid">
          {items.map((item) => (
            <section key={item.reference_id} className="asset-card">
              <Mic2 size={24} />
              <strong>{item.name}</strong>
              <span>{item.filename}</span>
              <ProtectedMedia kind="audio" src={item.file_url} />
              <button onClick={() => deleteVoiceAsset(item.reference_id).then(reload)}>删除</button>
            </section>
          ))}
        </div>
      }
    />
  );
}

function PortraitLibrary({
  items,
  reload,
}: {
  items: PortraitAsset[];
  reload: () => Promise<void>;
}) {
  return (
    <AssetLibraryShell
      title="形象库"
      accept="image/*,video/*"
      upload={uploadPortraitAsset}
      onUploaded={reload}
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
              <button onClick={() => deletePortraitAsset(item.portrait_id).then(reload)}>删除</button>
            </section>
          ))}
        </div>
      }
    />
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
  return (
    <AssetLibraryShell
      title="视频素材库"
      accept="video/*"
      upload={uploadVideoAsset}
      onUploaded={reload}
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
              <button onClick={() => deleteVideoAsset(item.asset_id).then(reload)}>删除</button>
            </section>
          ))}
        </div>
      }
    />
  );
}

function BrandKitLibrary({ items, reload }: { items: BrandKit[]; reload: () => Promise<void> }) {
  const [draft, setDraft] = useState<Partial<BrandKit>>({
    brand_name: "",
    primary_color: "#1f6feb",
    secondary_color: "#0f766e",
    store_address: "",
    phone: "",
    coupon_phrase: "",
  });

  async function save() {
    await createBrandKit(draft);
    setDraft({
      brand_name: "",
      primary_color: "#1f6feb",
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
            <button onClick={() => deleteBrandKit(item.brand_id).then(reload)}>删除</button>
          </section>
        ))}
      </div>
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
        <h2>任务中心</h2>
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
                <button onClick={() => retryTask(item.task_id).then(() => reload())}>重试</button>
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
      source: "素材来源",
      copywriting: "文案确认",
      voice: "声音生成",
      digital_human: "数字人视频",
      postproduction: "一键成片",
      publish: "视频发布",
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
  accept,
  upload,
  onUploaded,
  cards,
}: {
  title: string;
  accept: string;
  upload: (name: string, file: File) => Promise<unknown>;
  onUploaded: () => Promise<void>;
  cards: ReactNode;
}) {
  const [name, setName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [message, setMessage] = useState("");

  async function submit() {
    if (!file) return;
    await upload(name || file.name, file);
    setName("");
    setFile(null);
    setMessage("保存成功");
    await onUploaded();
  }

  return (
    <section className="card wide">
      <h2>{title}</h2>
      <div className="upload-row">
        <input placeholder="素材名称" value={name} onChange={(event) => setName(event.target.value)} />
        <input type="file" accept={accept} onChange={(event) => setFile(event.target.files?.[0] || null)} />
        <button className="primary" disabled={!file} onClick={submit}>
          保存素材
        </button>
      </div>
      {message ? <div className="notice success">{message}</div> : null}
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
        <label>LLM Base URL</label>
        <input
          value={config.llm.base_url}
          onChange={(event) =>
            setConfig({ ...config, llm: { ...config.llm, base_url: event.target.value } })
          }
        />
        <label>LLM API Key</label>
        <input
          placeholder={config.llm.api_key || "请输入 API Key"}
          onChange={(event) =>
            setConfig({ ...config, llm: { ...config.llm, api_key: event.target.value } })
          }
        />
        <label>LLM Model</label>
        <input
          value={config.llm.model}
          onChange={(event) =>
            setConfig({ ...config, llm: { ...config.llm, model: event.target.value } })
          }
        />
        <label>RunningHub API Key</label>
        <input
          placeholder={config.runninghub.api_key || "请输入 RunningHub API Key"}
          onChange={(event) =>
            setConfig({
              ...config,
              runninghub: { ...config.runninghub, api_key: event.target.value },
            })
          }
        />
        <label>RunningHub Instance Type</label>
        <input
          value={config.runninghub.instance_type}
          onChange={(event) =>
            setConfig({
              ...config,
              runninghub: { ...config.runninghub, instance_type: event.target.value },
            })
          }
        />
        <Button type="primary" onClick={save}>
          保存配置
        </Button>
        {saved ? <Alert className="step-notice" type="success" showIcon message={saved} /> : null}
      </Card>
    </section>
  );
}

function DiagnosticsView() {
  const [diagnostics, setDiagnostics] = useState<Record<string, unknown> | null>(null);
  useEffect(() => {
    getDiagnostics().then(setDiagnostics);
  }, []);
  return (
    <section className="card wide">
      <h2>启动自检</h2>
      <pre>{JSON.stringify(diagnostics, null, 2)}</pre>
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

function stepHint(step: number) {
  return [
    "先准备素材文本，快速生成可编辑文案。",
    "确认最终口播稿，回车分段会用于画面规划。",
    "从音色库选择参考音色，或使用默认 Edge TTS。",
    "从形象库选择数字人形象，再生成口播视频。",
    "选择画面模板，打开画面规划，最后一键合成。",
    "下载视频，复制标题、描述和标签。",
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
