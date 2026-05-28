import { AlertCircle, CheckCircle2, Loader2, Settings, Video } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  createSession,
  downloadArtifact,
  getDesktopConfig,
  getDiagnostics,
  getSession,
  getTask,
  DesktopConfig,
  IpBroadcastState,
  runStep,
  saveDesktopConfig,
  updateSessionConfig,
} from "./api";

type View = "ip" | "config" | "diagnostics";

const stepTitles = [
  "素材来源",
  "文案确认",
  "声音生成",
  "数字人视频",
  "一键成片",
  "视频发布",
];

export function App() {
  const [view, setView] = useState<View>("ip");
  const [session, setSession] = useState<IpBroadcastState | null>(null);
  const [taskId, setTaskId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    createSession().then(setSession).catch((err) => setError(String(err)));
  }, []);

  useEffect(() => {
    if (!taskId || !session) return;
    const timer = window.setInterval(async () => {
      try {
        const task = await getTask(taskId);
        if (task.status === "completed" || task.status === "failed" || task.status === "cancelled") {
          setBusy(false);
          setTaskId("");
          const fresh = await getSession(session.session_id);
          setSession(fresh);
          if (task.status === "failed") setError(task.error || "任务执行失败");
        }
      } catch (err) {
        setBusy(false);
        setTaskId("");
        setError(String(err));
      }
    }, 1500);
    return () => window.clearInterval(timer);
  }, [taskId, session]);

  const completedPercent = useMemo(() => {
    if (!session) return 0;
    return Math.round((session.completed_steps / 6) * 100);
  }, [session]);

  async function execute(stepKey: string) {
    if (!session) return;
    setBusy(true);
    setError("");
    try {
      const result = await runStep(session.session_id, stepKey);
      setTaskId(result.task_id);
    } catch (err) {
      setBusy(false);
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
    <main className="app-shell">
      <header className="topbar">
        <div>
          <h1>老板 IP 口播智能体</h1>
          <p>桌面版 v1：专注文案、配音、数字人和一键成片。</p>
        </div>
        <nav>
          <button className={view === "ip" ? "active" : ""} onClick={() => setView("ip")}>
            <Video size={16} /> IP口播
          </button>
          <button className={view === "config" ? "active" : ""} onClick={() => setView("config")}>
            <Settings size={16} /> 配置
          </button>
          <button
            className={view === "diagnostics" ? "active" : ""}
            onClick={() => setView("diagnostics")}
          >
            <CheckCircle2 size={16} /> 诊断
          </button>
        </nav>
      </header>

      {error ? (
        <div className="notice error">
          <AlertCircle size={16} /> {error}
        </div>
      ) : null}

      {view === "ip" && session ? (
        <>
          <section className="console">
            <div>
              <strong>生产主控台</strong>
              <p>{session.next_action.description}</p>
              <div className="progress">
                <span style={{ width: `${completedPercent}%` }} />
              </div>
              <small>
                进度：{session.completed_steps}/6
                {session.missing_requirements.length
                  ? ` · ${session.missing_requirements.join(" · ")}`
                  : ""}
              </small>
            </div>
            <button
              className="primary"
              disabled={busy || session.next_action.disabled}
              onClick={() => execute(session.next_action.key)}
            >
              {busy ? <Loader2 className="spin" size={16} /> : null}
              一键继续：{session.next_action.label}
            </button>
          </section>

          <section className="columns">
            <div className="column">
              <StepCard step={1} session={session}>
                <label>素材文本</label>
                <textarea
                  defaultValue={(session.state.source_text as string) || ""}
                  onBlur={(event) => patch({ source_mode: "paste", source_text: event.target.value })}
                  placeholder="粘贴口播文案或视频提取后的文本..."
                />
                <button onClick={() => execute("source")} disabled={busy}>
                  生成口播文案
                </button>
              </StepCard>
              <StepCard step={2} session={session}>
                <label>最终口播文案</label>
                <textarea
                  defaultValue={(session.state.final_script as string) || ""}
                  onBlur={(event) => patch({ final_script: event.target.value })}
                />
                <div className="grid2">
                  <input
                    placeholder="写作风格"
                    defaultValue={(session.state.style_prompt as string) || ""}
                    onBlur={(event) => patch({ style_prompt: event.target.value })}
                  />
                  <input
                    type="number"
                    defaultValue={(session.state.word_count as number) || 200}
                    onBlur={(event) => patch({ word_count: Number(event.target.value) })}
                  />
                </div>
                <button onClick={() => execute("copywriting")} disabled={busy}>
                  AI 改写/优化文案
                </button>
              </StepCard>
            </div>

            <div className="column">
              <StepCard step={3} session={session}>
                <div className="grid2">
                  <input
                    placeholder="音色"
                    defaultValue={(session.state.tts_voice as string) || "zh-CN-YunjianNeural"}
                    onBlur={(event) => patch({ tts_voice: event.target.value })}
                  />
                  <input
                    type="number"
                    step="0.1"
                    defaultValue={(session.state.tts_speed as number) || 1.2}
                    onBlur={(event) => patch({ tts_speed: Number(event.target.value) })}
                  />
                </div>
                <button onClick={() => execute("voice")} disabled={busy}>
                  生成语音
                </button>
              </StepCard>
              <StepCard step={4} session={session}>
                <input
                  placeholder="形象文件路径（v1 调试入口）"
                  defaultValue={(session.state.portrait_path as string) || ""}
                  onBlur={(event) => patch({ portrait_path: event.target.value })}
                />
                <input
                  placeholder="数字人工作流"
                  defaultValue={(session.state.digital_human_workflow as string) || ""}
                  onBlur={(event) => patch({ digital_human_workflow: event.target.value })}
                />
                <button onClick={() => execute("digital_human")} disabled={busy}>
                  生成数字人视频
                </button>
              </StepCard>
            </div>

            <div className="column">
              <StepCard step={5} session={session}>
                <input
                  placeholder="画面模板"
                  defaultValue={(session.state.template_id as string) || "boss_clean"}
                  onBlur={(event) => patch({ template_id: event.target.value })}
                />
                <button onClick={() => execute("postproduction")} disabled={busy}>
                  一键成片
                </button>
              </StepCard>
              <StepCard step={6} session={session}>
                <p className="result-path">{(session.state.final_video_path as string) || "暂无最终视频"}</p>
                {session.artifacts.final_video ? (
                  <button className="download" onClick={downloadFinalVideo}>
                    下载最终视频
                  </button>
                ) : null}
              </StepCard>
            </div>
          </section>
        </>
      ) : null}

      {view === "config" ? <ConfigView /> : null}
      {view === "diagnostics" ? <DiagnosticsView /> : null}
    </main>
  );
}

function StepCard({
  step,
  session,
  children,
}: {
  step: number;
  session: IpBroadcastState;
  children: React.ReactNode;
}) {
  const status = session.step_status[String(step)] || "pending";
  const notice = session.notices[String(step)];
  return (
    <section className="card">
      <div className="card-title">
        <strong>
          {step}. {stepTitles[step - 1]}
        </strong>
        <span className={`badge ${status}`}>{status}</span>
      </div>
      {children}
      {notice ? <div className={`notice ${notice.kind}`}>{notice.message}</div> : null}
    </section>
  );
}

function ConfigView() {
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
    <section className="card wide">
      <h2>配置中心</h2>
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
      <button className="primary" onClick={save}>
        保存配置
      </button>
      {saved ? <div className="notice success">{saved}</div> : null}
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
