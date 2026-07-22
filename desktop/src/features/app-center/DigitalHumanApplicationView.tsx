import { Alert, Button, Card, Input, Tag, Typography } from "antd";
import { useEffect, useMemo, useState } from "react";
import {
  acceptIpBroadcastAppRun,
  cancelIpBroadcastAppRun,
  createContentProject,
  createIpBroadcastAppRun,
  executeIpBroadcastAppRun,
  getIpBroadcastAppRun,
  listApplications,
  listArtifactVersions,
  listContentProjects,
  listProjectArtifacts,
  retryIpBroadcastAppRun,
  type ArtifactSummary,
  type ArtifactVersion,
  type ContentProject,
  type IpBroadcastAppRun,
} from "../../api";
import { featureFlags } from "../../featureFlags";

const STORAGE_KEY = "pixelle_ip_broadcast_app_state_v1";
const PENDING_STORAGE_KEY = "pixelle_ip_broadcast_app_pending_v1";
const APP_ID = "builtin.digital-human-video";
const APP_VERSION = "1.0.0";
type SourceMode = "blank_project" | "copywriting" | "selected_title";

type StoredPointer = {
  route: "/apps/digital-human-video";
  project_id: string;
  app_run_id: string;
  session_id: string;
  source_mode: SourceMode;
  source_revision: string;
  context_snapshot_id: string | null;
};

type StoredPending = {
  route: "/apps/digital-human-video";
  project_id: string;
  source_mode: SourceMode;
  source_artifact_id: string | null;
  idempotency_key: string;
  input_payload: Record<string, unknown>;
};

function readStoredPointer(): StoredPointer | null {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const value = JSON.parse(raw) as Partial<StoredPointer>;
    if (value.route !== "/apps/digital-human-video" || !value.project_id || !value.app_run_id || !value.session_id || !value.source_mode || !value.source_revision) return null;
    if (!(["blank_project", "copywriting", "selected_title"] as string[]).includes(value.source_mode)) return null;
    return {
      route: "/apps/digital-human-video",
      project_id: value.project_id,
      app_run_id: value.app_run_id,
      session_id: value.session_id,
      source_mode: value.source_mode,
      source_revision: value.source_revision,
      context_snapshot_id: value.context_snapshot_id || null,
    } as StoredPointer;
  } catch {
    return null;
  }
}

function writeStoredPointer(run: IpBroadcastAppRun, sourceMode: SourceMode) {
  const pointer: StoredPointer = {
    route: "/apps/digital-human-video",
    project_id: run.project_id,
    app_run_id: run.app_run_id,
    session_id: run.session_id,
    source_mode: sourceMode,
    source_revision: run.source_revision,
    context_snapshot_id: run.context_snapshot_id || null,
  };
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(pointer));
}

function clearStoredPointer() {
  window.localStorage.removeItem(STORAGE_KEY);
}

function readStoredPending(): StoredPending | null {
  try {
    const raw = window.localStorage.getItem(PENDING_STORAGE_KEY);
    if (!raw) return null;
    const value = JSON.parse(raw) as Partial<StoredPending>;
    if (value.route !== "/apps/digital-human-video" || !value.project_id || !value.source_mode || !value.idempotency_key || !value.input_payload || typeof value.input_payload !== "object") return null;
    if (!(Object.keys(value.input_payload).every((key) => ["project_id", "source_mode", "goal", "source_artifact_version_ids", "selected_variant_index"].includes(key)))) return null;
    if (value.input_payload.project_id !== value.project_id || value.input_payload.source_mode !== value.source_mode) return null;
    if (value.source_artifact_id !== null && typeof value.source_artifact_id !== "string") return null;
    return value as StoredPending;
  } catch {
    return null;
  }
}

function writeStoredPending(projectId: string, sourceMode: SourceMode, sourceArtifactId: string | null, idempotencyKey: string, inputPayload: Record<string, unknown>) {
  const pending: StoredPending = {
    route: "/apps/digital-human-video",
    project_id: projectId,
    source_mode: sourceMode,
    source_artifact_id: sourceArtifactId,
    idempotency_key: idempotencyKey,
    input_payload: inputPayload,
  };
  window.localStorage.setItem(PENDING_STORAGE_KEY, JSON.stringify(pending));
}

function clearStoredPending() {
  window.localStorage.removeItem(PENDING_STORAGE_KEY);
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : String(error);
}

function randomIdempotencyKey(projectId: string) {
  const suffix = typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return `desktop-digital-human:${projectId}:${suffix}`;
}

function artifactLabel(artifact: ArtifactSummary) {
  return `${artifact.name} · ${artifact.artifact_type}`;
}

function latestVersion(versions: ArtifactVersion[]) {
  return [...versions].sort((left, right) => right.version_number - left.version_number)[0] || null;
}

export function DigitalHumanApplicationView({
  onBack,
  allowLocalExecute = false,
  desktopEnabled = featureFlags.digitalHumanInAppCenter,
}: {
  onBack: () => void;
  allowLocalExecute?: boolean;
  desktopEnabled?: boolean;
}) {
  const [projects, setProjects] = useState<ContentProject[]>([]);
  const [projectId, setProjectId] = useState("");
  const [artifacts, setArtifacts] = useState<ArtifactSummary[]>([]);
  const [versions, setVersions] = useState<ArtifactVersion[]>([]);
  const [sourceMode, setSourceMode] = useState<SourceMode>("blank_project");
  const [goal, setGoal] = useState("");
  const [artifactId, setArtifactId] = useState("");
  const [versionId, setVersionId] = useState("");
  const [variantIndex, setVariantIndex] = useState(0);
  const [run, setRun] = useState<IpBroadcastAppRun | null>(null);
  const [pending, setPending] = useState<StoredPending | null>(null);
  const [loading, setLoading] = useState(true);
  const [backendReady, setBackendReady] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const selectedArtifactType = sourceMode === "copywriting" ? "copywriting" : "selected_title";
  const sourceArtifacts = useMemo(
    () => artifacts.filter((artifact) => artifact.artifact_type === selectedArtifactType && artifact.status !== "archived"),
    [artifacts, selectedArtifactType],
  );
  const selectedVersion = versions.find((version) => version.artifact_version_id === versionId) || null;
  const variants = Array.isArray(selectedVersion?.content?.variants) ? selectedVersion.content.variants : [];
  const canStart = Boolean(
    projectId.trim() &&
      (sourceMode === "blank_project"
        ? goal.trim()
        : artifactId && versionId && (sourceMode !== "copywriting" || variants[variantIndex])),
  );

  useEffect(() => {
    if (!desktopEnabled) {
      setLoading(false);
      return;
    }
    let active = true;
    const pointer = readStoredPointer();
    const pendingSubmission = readStoredPending();
    async function load() {
      try {
        const directory = await listApplications();
        const manifest = directory.apps.find((item) => item.app_id === APP_ID);
        if (!manifest || !manifest.enabled || manifest.readiness.status !== "ready") {
          if (active) {
            setBackendReady(false);
            setLoading(false);
          }
          return;
        }
        const loadedProjects = await listContentProjects();
        if (!active) return;
        setBackendReady(true);
        setProjects(loadedProjects);
        if (pointer) {
          setProjectId(pointer.project_id);
          setSourceMode(pointer.source_mode);
          try {
            const restored = await getIpBroadcastAppRun(pointer.app_run_id, pointer.project_id);
            if (!active) return;
            if (
              restored.project_id !== pointer.project_id ||
              restored.session_id !== pointer.session_id ||
              restored.source_revision !== pointer.source_revision ||
              (restored.context_snapshot_id || null) !== pointer.context_snapshot_id
            ) {
              clearStoredPointer();
              setNotice("历史运行绑定校验未通过，已安全清理本地指针；不会覆盖或复用不同来源。 ");
              return;
            }
            setRun(restored);
            setNotice("已从上次安全停手位置恢复；未创建新的运行或会话。 ");
          } catch (restoreError) {
            if (!active) return;
            clearStoredPointer();
            setNotice(`历史运行不可恢复，已清理本地指针：${errorMessage(restoreError)}`);
          }
        } else if (pendingSubmission) {
          setPending(pendingSubmission);
          setProjectId(pendingSubmission.project_id);
          setSourceMode(pendingSubmission.source_mode);
          const payload = pendingSubmission.input_payload;
          if (pendingSubmission.source_mode === "blank_project" && typeof payload.goal === "string") setGoal(payload.goal);
          const sourceVersion = Array.isArray(payload.source_artifact_version_ids) ? payload.source_artifact_version_ids[0] : null;
          if (typeof sourceVersion === "string") setVersionId(sourceVersion);
          if (typeof payload.selected_variant_index === "number" && Number.isInteger(payload.selected_variant_index) && payload.selected_variant_index >= 0) {
            setVariantIndex(payload.selected_variant_index);
          }
          if (pendingSubmission.source_artifact_id) setArtifactId(pendingSubmission.source_artifact_id);
          setNotice("上次提交尚未收到确认；点击创建应用运行将复用同一幂等键，不会随机创建第二个运行。 ");
        } else if (loadedProjects[0]) {
          setProjectId(loadedProjects[0].project_id);
        }
        setError("");
      } catch (loadError) {
        if (active) setError(errorMessage(loadError));
      } finally {
        if (active) setLoading(false);
      }
    }
    void load();
    return () => {
      active = false;
    };
  }, [desktopEnabled]);

  useEffect(() => {
    if (!desktopEnabled) return;
    if (!projectId) {
      setArtifacts([]);
      return;
    }
    let active = true;
    listProjectArtifacts(projectId)
      .then((items) => {
        if (active) {
          setArtifacts(items);
          if (!items.length) {
            setArtifactId("");
            setVersionId("");
            setVersions([]);
          }
        }
      })
      .catch((loadError) => {
        if (active) setError(errorMessage(loadError));
      });
    return () => {
      active = false;
    };
  }, [desktopEnabled, projectId]);

  useEffect(() => {
    if (!desktopEnabled || !pending?.source_artifact_id) return;
    if (sourceArtifacts.some((artifact) => artifact.artifact_id === pending.source_artifact_id) && artifactId !== pending.source_artifact_id) {
      setArtifactId(pending.source_artifact_id);
    }
  }, [artifactId, desktopEnabled, pending, sourceArtifacts]);

  useEffect(() => {
    if (!desktopEnabled) return;
    if (!artifacts.length) return;
    const pendingArtifact = pending?.source_artifact_id
      ? sourceArtifacts.find((artifact) => artifact.artifact_id === pending.source_artifact_id)
      : null;
    if (pending?.source_artifact_id && !pendingArtifact) {
      setArtifactId("");
      setVersionId("");
      setVersions([]);
      setError("待确认提交引用的来源产物不存在或已归档；已安全停手，请重新选择来源后创建。 ");
      return;
    }
    const selected = pendingArtifact && !artifactId
      ? pendingArtifact
      : sourceArtifacts.find((artifact) => artifact.artifact_id === artifactId) || sourceArtifacts[0];
    if (!selected) {
      setArtifactId("");
      setVersionId("");
      return;
    }
    if (selected.artifact_id !== artifactId) {
      setArtifactId(selected.artifact_id);
      return;
    }
    let active = true;
    listArtifactVersions(selected.artifact_id)
      .then((items) => {
        if (!active) return;
        setVersions(items);
        const pendingVersion = pending?.project_id === projectId && pending.source_mode === sourceMode && Array.isArray(pending.input_payload.source_artifact_version_ids)
          ? pending.input_payload.source_artifact_version_ids[0]
          : null;
        setVersionId(typeof pendingVersion === "string" && items.some((item) => item.artifact_version_id === pendingVersion)
          ? pendingVersion
          : selected.current_version_id && items.some((item) => item.artifact_version_id === selected.current_version_id)
          ? selected.current_version_id
          : latestVersion(items)?.artifact_version_id || "");
      })
      .catch((loadError) => {
        if (active) setError(errorMessage(loadError));
      });
    return () => {
      active = false;
    };
  }, [artifactId, artifacts, desktopEnabled, pending, projectId, sourceMode, sourceArtifacts]);

  async function createProject() {
    const name = window.prompt("项目名称", "数字人口播灰度项目")?.trim();
    if (!name) return;
    setBusy(true);
    setError("");
    try {
      const created = await createContentProject({ name, primary_goal: "制作一条门店数字人口播视频" });
      setProjects((current) => [created, ...current]);
      setProjectId(created.project_id);
      setNotice("项目已创建；请先选择来源，再显式创建应用运行。 ");
    } catch (createError) {
      setError(errorMessage(createError));
    } finally {
      setBusy(false);
    }
  }

  async function createRun() {
    const inputPayload: Record<string, unknown> = {
      project_id: projectId,
      source_mode: sourceMode,
    };
    if (sourceMode === "blank_project") inputPayload.goal = goal.trim();
    if (sourceMode !== "blank_project") {
      inputPayload.source_artifact_version_ids = [versionId];
      if (sourceMode === "copywriting") inputPayload.selected_variant_index = variantIndex;
    }
    const pendingMatches = pending && pending.project_id === projectId && pending.source_mode === sourceMode && JSON.stringify(pending.input_payload) === JSON.stringify(inputPayload);
    if (!canStart && !pendingMatches) return;
    const idempotencyKey = pendingMatches ? pending.idempotency_key : randomIdempotencyKey(projectId);
    // Persist before POST: if the process dies after the server commits but
    // before the response reaches the UI, the next explicit click replays the
    // same idempotency key instead of creating a second AppRun.
    writeStoredPending(projectId, sourceMode, artifactId || pending?.source_artifact_id || null, idempotencyKey, inputPayload);
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const created = await createIpBroadcastAppRun({
        project_id: projectId,
        input_payload: inputPayload,
        idempotency_key: idempotencyKey,
      });
      setRun(created);
      writeStoredPointer(created, sourceMode);
      clearStoredPending();
      setPending(null);
      setNotice("应用运行已创建；当前只等待本地隔离执行或人工确认，不会自动触发外部平台动作。 ");
    } catch (createError) {
      setError(errorMessage(createError));
    } finally {
      setBusy(false);
    }
  }

  async function refreshRun() {
    if (!run) return;
    setBusy(true);
    try {
      const refreshed = await getIpBroadcastAppRun(run.app_run_id, run.project_id);
      setRun(refreshed);
      writeStoredPointer(refreshed, sourceMode);
    } catch (refreshError) {
      setError(errorMessage(refreshError));
    } finally {
      setBusy(false);
    }
  }

  async function mutateRun(action: "execute" | "cancel" | "retry" | "accept") {
    if (!run) return;
    if (action === "execute" && !allowLocalExecute) {
      setError("当前桌面入口不允许执行隔离 seam；请使用受控测试证据。 ");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const next = action === "execute"
        ? await executeIpBroadcastAppRun(run.app_run_id)
        : action === "cancel"
          ? await cancelIpBroadcastAppRun(run.app_run_id)
          : action === "retry"
            ? await retryIpBroadcastAppRun(run.app_run_id)
            : await acceptIpBroadcastAppRun(run.app_run_id);
      setRun(next);
      writeStoredPointer(next, sourceMode);
      setNotice(action === "accept" ? "已显式接收当前结果；未触发最终平台发布。 " : "运行状态已更新。 ");
    } catch (actionError) {
      setError(errorMessage(actionError));
    } finally {
      setBusy(false);
    }
  }

  function changeSourceMode(next: SourceMode) {
    setSourceMode(next);
    setArtifactId("");
    setVersionId("");
    setVersions([]);
    setVariantIndex(0);
    setError("");
    if (pending && pending.source_mode !== next) {
      clearStoredPending();
      setPending(null);
      setNotice("已切换来源类型；原待确认提交不再匹配，下一次创建将生成新的幂等键。 ");
    }
  }

  function changeProject(nextProjectId: string) {
    if (nextProjectId === projectId) return;
    setProjectId(nextProjectId);
    setArtifactId("");
    setVersionId("");
    setVersions([]);
    if (pending && pending.project_id !== nextProjectId) {
      clearStoredPending();
      setPending(null);
    }
    if (run && run.project_id !== nextProjectId) {
      setRun(null);
      clearStoredPointer();
      setNotice("已切换到其他项目；旧运行指针已清理，请显式创建或恢复当前项目运行。 ");
    }
  }

  function changeArtifact(nextArtifactId: string) {
    setArtifactId(nextArtifactId);
    setVersionId("");
    setVersions([]);
    if (pending && pending.source_artifact_id !== nextArtifactId) {
      clearStoredPending();
      setPending(null);
      setNotice("已切换来源产物；原待确认提交不再匹配，下一次创建将生成新的幂等键。 ");
    }
  }

  if (!desktopEnabled) {
    return (
      <section className="digital-human-app-workspace" aria-label="数字人口播应用">
        <Alert type="warning" showIcon message="数字人口播应用尚未进入桌面灰度" description="请返回应用中心；旧版口播入口仍可使用。" />
        <Button onClick={onBack}>返回应用中心</Button>
      </section>
    );
  }

  if (backendReady === false) {
    return (
      <section className="digital-human-app-workspace" aria-label="数字人口播应用">
        <Alert type="warning" showIcon message="数字人口播应用暂不可用" description="后端 Registry 未开启或 readiness 尚未通过；旧版口播入口仍可使用。" />
        <Button onClick={onBack}>返回应用中心</Button>
      </section>
    );
  }

  return (
    <section className="digital-human-app-workspace" aria-label="数字人口播应用">
      <div className="digital-human-app-heading">
        <div>
          <Typography.Text type="secondary">APPLICATION · {APP_ID}</Typography.Text>
          <Typography.Title level={2}>数字人口播视频</Typography.Title>
          <Typography.Paragraph type="secondary">
            从项目、可信文案或选定标题进入统一运行链路。当前桌面灰度只负责本地状态与人工确认，不会自动发布。
          </Typography.Paragraph>
        </div>
        <SpaceButtons onBack={onBack} />
      </div>

      {error ? <Alert type="error" showIcon message="应用运行未完成" description={error} /> : null}
      {notice ? <Alert type="info" showIcon message={notice} /> : null}

      <Card title="1 · 选择项目与来源" className="digital-human-app-card">
        <div className="digital-human-app-field">
          <label htmlFor="digital-human-project">内容项目</label>
          <div className="digital-human-app-inline">
            <select id="digital-human-project" value={projectId} onChange={(event) => changeProject(event.target.value)} disabled={loading || busy}>
              <option value="">请选择项目</option>
              {projects.map((project) => <option key={project.project_id} value={project.project_id}>{project.name}</option>)}
            </select>
            <Button size="small" onClick={() => void createProject()} disabled={busy}>新建项目</Button>
          </div>
        </div>
        <div className="digital-human-app-source-tabs" role="tablist" aria-label="口播来源">
          {(["blank_project", "copywriting", "selected_title"] as SourceMode[]).map((mode) => (
            <button key={mode} type="button" role="tab" aria-selected={sourceMode === mode} onClick={() => changeSourceMode(mode)}>
              {mode === "blank_project" ? "空白项目" : mode === "copywriting" ? "已有文案" : "选定标题"}
            </button>
          ))}
        </div>
        {sourceMode === "blank_project" ? (
          <Input.TextArea aria-label="制作目标" rows={3} value={goal} onChange={(event) => setGoal(event.target.value)} placeholder="例如：为新店开业制作一条 30 秒口播视频" />
        ) : (
          <div className="digital-human-app-source-selects">
            <select aria-label="来源产物" value={artifactId} onChange={(event) => changeArtifact(event.target.value)} disabled={!projectId || busy}>
              <option value="">请选择{sourceMode === "copywriting" ? "文案" : "标题"}产物</option>
              {sourceArtifacts.map((artifact) => <option key={artifact.artifact_id} value={artifact.artifact_id}>{artifactLabel(artifact)}</option>)}
            </select>
            {sourceMode === "copywriting" ? (
              <select aria-label="文案变体" value={String(variantIndex)} onChange={(event) => setVariantIndex(Number(event.target.value))} disabled={!versions.length || busy}>
                {variants.map((variant, index) => <option key={index} value={index}>变体 {index + 1} · {typeof variant === "object" && variant && "title" in variant ? String(variant.title) : "可选文案"}</option>)}
              </select>
            ) : null}
          </div>
        )}
        <div className="digital-human-app-actions">
          <Button type="primary" onClick={() => void createRun()} disabled={!canStart || busy} loading={busy}>创建应用运行</Button>
          <Tag color="default">v{APP_VERSION}</Tag>
        </div>
      </Card>

      <Card title="2 · 运行状态与安全停手" className="digital-human-app-card">
        {run ? (
          <div className="digital-human-app-run" aria-label="应用运行状态">
            <div className="digital-human-app-run-meta">
              <span>AppRun：<code>{run.app_run_id}</code></span>
              <span>Session：<code>{run.session_id}</code></span>
              <Tag color={run.state === "completed" ? "success" : run.state === "needs_review" ? "warning" : "processing"}>{run.state}</Tag>
            </div>
            <Typography.Paragraph type="secondary">{run.projection.when || "状态已读取"} · {run.projection.task_status || "pending"}</Typography.Paragraph>
            {run.error_code ? <Alert type="warning" showIcon message={run.error_code} /> : null}
            <div className="digital-human-app-actions">
              <Button onClick={() => void refreshRun()} disabled={busy}>刷新状态</Button>
              <Button onClick={() => void mutateRun("cancel")} disabled={busy || ["completed", "cancelled"].includes(run.state)}>取消</Button>
              <Button onClick={() => void mutateRun("retry")} disabled={busy || !["failed", "cancelled"].includes(run.state)}>重试</Button>
              {allowLocalExecute ? <Button onClick={() => void mutateRun("execute")} disabled={busy || ["completed", "cancelled"].includes(run.state)}>运行本地隔离 seam</Button> : null}
              <Button type="primary" onClick={() => void mutateRun("accept")} disabled={busy || run.state !== "needs_review"}>确认接收结果</Button>
            </div>
            <Typography.Text type="secondary">确认接收只完成本地人工交接，不代表抖音发布。</Typography.Text>
          </div>
        ) : (
          <Typography.Text type="secondary">尚未创建运行。创建后将持久化安全指针，并在重启时优先读取已有运行。</Typography.Text>
        )}
      </Card>
    </section>
  );
}

function SpaceButtons({ onBack }: { onBack: () => void }) {
  return <Button onClick={onBack}>返回应用中心</Button>;
}
