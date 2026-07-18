import { Button, Progress, Tag } from "antd";
import {
  ArrowRight,
  CheckCircle2,
  CircleAlert,
  Clapperboard,
  Image,
  Mic2,
  Package,
  Plus,
  Search,
  Send,
  Sparkles,
  UserSquare2,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { getDesktopConfig, listTasks, type DesktopConfig, type TaskInfo } from "../../api";

type AssetTab = "videos" | "images" | "voices" | "portraits" | "templates" | "brands";

export type DashboardAssetSummary = {
  videos: number;
  images: number;
  voices: number;
  portraits: number;
  templates: number;
  brands: number;
};

export function DashboardView({
  assets,
  onStart,
  onAssets,
  onAssetTab,
  onConfig,
  onDiagnostics,
  onTasks,
  onPublish,
}: {
  assets: DashboardAssetSummary;
  onStart: () => void;
  onAssets: () => void;
  onAssetTab: (tab: AssetTab) => void;
  onConfig: () => void;
  onDiagnostics: () => void;
  onTasks: () => void;
  onPublish: () => void;
}) {
  const [tasks, setTasks] = useState<TaskInfo[]>([]);
  const [config, setConfig] = useState<DesktopConfig | null>(null);
  const [query, setQuery] = useState("");

  useEffect(() => {
    Promise.all([listTasks("", 100), getDesktopConfig()]).then(([nextTasks, nextConfig]) => {
      setTasks(nextTasks);
      setConfig(nextConfig);
    }).catch(() => undefined);
  }, []);

  const filteredTasks = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return tasks;
    return tasks.filter((task) =>
      [task.display_name, task.flow_name, task.step_key, task.task_id]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(normalized)),
    );
  }, [query, tasks]);
  const latestTask = tasks[0];
  const queue = tasks.filter((task) => ["pending", "running", "failed"].includes(task.status)).slice(0, 3);
  const configReady = isConfigured(config?.llm.api_key) && isConfigured(config?.runninghub.api_key);
  const productionReady = configReady && assets.voices > 0 && assets.portraits > 0 && assets.templates > 0;
  const stage = taskStage(latestTask?.step_key);
  const completion = latestTask?.progress?.percentage ?? (latestTask?.status === "completed" ? 100 : Math.max(8, stage * 20));

  return (
    <section className="dashboard-v2">
      <header className="dashboard-commandbar">
        <div>
          <h1>今天从哪条视频开始？</h1>
          <p>把企业资产、口播生产和平台发布集中在一个工作台。</p>
        </div>
        <div className="dashboard-actions">
          <Button icon={<Package size={15} />} onClick={onAssets}>导入资产</Button>
          <Button type="primary" icon={<Plus size={16} />} onClick={onStart}>新建口播视频</Button>
        </div>
      </header>

      <div className="dashboard-main-grid">
        <main className="dashboard-primary">
          <section className="continue-project-panel">
            <div className="continue-project-head">
              <div>
                <span className="section-kicker">继续上次项目</span>
                <h2>{latestTask?.display_name || latestTask?.flow_name || "创建第一条企业口播"}</h2>
                <p>{latestTask?.progress?.message || "从文案到发布，用一条清晰的生产线完成。"}</p>
              </div>
              <Button type="primary" onClick={onStart}>
                {latestTask ? "继续生产" : "开始制作"}<ArrowRight size={15} />
              </Button>
            </div>
            <div className="project-progress-rail" aria-label="项目生产进度">
              {["文案", "配音", "出镜", "成片", "发布"].map((label, index) => (
                <div key={label} className={index + 1 < stage ? "done" : index + 1 === stage ? "active" : ""}>
                  <i>{index + 1 < stage ? <CheckCircle2 size={14} /> : index + 1}</i>
                  <span>{label}</span>
                </div>
              ))}
            </div>
            <Progress percent={Math.round(completion)} showInfo={false} />
          </section>

          <section className="project-list-panel">
            <div className="panel-title-row">
              <div>
                <h2>最近项目</h2>
                <p>按生产进度继续工作，不必重新寻找任务。</p>
              </div>
              <div className="project-search">
                <Search size={15} />
                <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索项目" />
              </div>
            </div>
            <div className="project-table" role="table" aria-label="最近项目">
              <div className="project-table-head" role="row">
                <span>项目</span><span>当前阶段</span><span>状态</span><span>更新时间</span><span />
              </div>
              {filteredTasks.slice(0, 6).map((task) => (
                <div className="project-table-row" role="row" key={task.task_id}>
                  <div className="project-name-cell">
                    <span className="project-thumb"><Clapperboard size={17} /></span>
                    <div><strong>{task.display_name || task.flow_name || "口播视频"}</strong><small>{shortId(task.task_id)}</small></div>
                  </div>
                  <span>{stepLabel(task.step_key)}</span>
                  <span><Tag color={statusColor(task.status)}>{statusLabel(task.status)}</Tag></span>
                  <span>{formatDate(task.created_at)}</span>
                  <button type="button" onClick={onStart}>打开 <ArrowRight size={13} /></button>
                </div>
              ))}
              {!filteredTasks.length ? <div className="dashboard-empty">还没有项目，先创建一条口播视频。</div> : null}
            </div>
            <Button className="view-all-projects" onClick={onTasks}>查看全部任务</Button>
          </section>
        </main>

        <aside className="dashboard-rail">
          <section className="queue-panel">
            <div className="panel-title-row compact"><h2>生产队列</h2><button type="button" onClick={onTasks}>全部</button></div>
            <div className="queue-list">
              {queue.map((task) => (
                <button type="button" key={task.task_id} onClick={onTasks}>
                  <span className={`queue-status ${task.status}`} />
                  <div><strong>{task.display_name || task.flow_name || "生产任务"}</strong><small>{task.progress?.message || stepLabel(task.step_key)}</small></div>
                  <em>{task.status === "running" ? `${Math.round(task.progress?.percentage || 0)}%` : statusLabel(task.status)}</em>
                </button>
              ))}
              {!queue.length ? <div className="queue-empty"><Sparkles size={18} /><span>当前没有等待任务</span></div> : null}
            </div>
          </section>

          <section className="asset-overview-panel">
            <div className="panel-title-row compact"><h2>企业资产</h2><button type="button" onClick={onAssets}>管理</button></div>
            <div className="asset-overview-list">
              <AssetRow icon={<Clapperboard />} label="视频" value={assets.videos} onClick={() => onAssetTab("videos")} />
              <AssetRow icon={<Image />} label="图片" value={assets.images} onClick={() => onAssetTab("images")} />
              <AssetRow icon={<Mic2 />} label="音色" value={assets.voices} onClick={() => onAssetTab("voices")} />
              <AssetRow icon={<UserSquare2 />} label="数字人" value={assets.portraits} onClick={() => onAssetTab("portraits")} />
              <AssetRow icon={<Package />} label="品牌包" value={assets.brands} onClick={() => onAssetTab("brands")} />
            </div>
          </section>

          <section className="readiness-panel">
            <div className="readiness-title">
              {productionReady ? <CheckCircle2 size={18} /> : <CircleAlert size={18} />}
              <div><strong>{productionReady ? "生产环境已就绪" : "还有准备项未完成"}</strong><span>{productionReady ? "可以生成并准备发布" : "补齐配置后生产更稳定"}</span></div>
            </div>
            <div className="readiness-actions">
              <button type="button" onClick={onConfig}>系统设置</button>
              <button type="button" onClick={onDiagnostics}>启动自检</button>
              <button type="button" onClick={onPublish}><Send size={14} /> 发布账号</button>
            </div>
          </section>
        </aside>
      </div>
    </section>
  );
}

function AssetRow({ icon, label, value, onClick }: { icon: React.ReactElement; label: string; value: number; onClick: () => void }) {
  return <button type="button" onClick={onClick}><i>{icon}</i><span>{label}</span><strong>{value}</strong><ArrowRight size={13} /></button>;
}

function isConfigured(value?: string) {
  const key = (value || "").trim().toLowerCase();
  return Boolean(key && key !== "请输入 api key" && !key.includes("your-api-key"));
}

function taskStage(step?: string) {
  return { source: 1, copywriting: 1, voice: 2, digital_human: 3, postproduction: 4, publish: 5 }[step || ""] || 1;
}

function stepLabel(step?: string) {
  return { source: "文案", copywriting: "文案", voice: "配音", digital_human: "数字人出镜", postproduction: "一键成片", publish: "发布" }[step || ""] || "待开始";
}

function statusLabel(status: TaskInfo["status"]) {
  return { pending: "等待中", running: "进行中", completed: "已完成", failed: "需处理", cancelled: "已停止" }[status];
}

function statusColor(status: TaskInfo["status"]) {
  return { pending: "default", running: "processing", completed: "success", failed: "error", cancelled: "default" }[status];
}

function formatDate(value?: string) {
  if (!value) return "刚刚";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value.slice(0, 10) : date.toLocaleDateString("zh-CN", { month: "2-digit", day: "2-digit" });
}

function shortId(value: string) {
  return value.length > 10 ? `#${value.slice(-6)}` : `#${value}`;
}

export default DashboardView;
