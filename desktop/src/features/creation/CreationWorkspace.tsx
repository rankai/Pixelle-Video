import { useEffect, useMemo, useState } from "react";
import { Alert, Button, Card, Empty, Input, List, Select, Space, Tag, Typography } from "antd";
import {
  AppRun,
  ArtifactVersion,
  ContentProject,
  createAppRun,
  createContentProject,
  archiveContentProject,
  appendArtifactVersion,
  createArtifactHandoff,
  cancelAppRun,
  completeAppRun,
  downloadAppArtifactFile,
  executeAppRun,
  getCurrentContextSnapshot,
  listArtifactVersions,
  listAppRuns,
  listContentProjects,
  retryAppRun,
  updateContentProject,
} from "../../api";

type Props = {
  appId?: string;
  appVersion?: string;
};

type CopyVariantDraft = {
  version_name?: string;
  angle?: string;
  hook?: string;
  body?: string;
  cta?: string;
  full_text?: string;
  word_count?: number;
  estimated_seconds?: number;
  [key: string]: unknown;
};

type TitleCandidateDraft = {
  title?: string;
  angle?: string;
  objective?: string;
  length?: number;
  [key: string]: unknown;
};

type StructuredArtifactDraft = {
  schema_version?: number;
  artifact_type?: string;
  variants?: CopyVariantDraft[];
  candidates?: TitleCandidateDraft[];
  [key: string]: unknown;
};

function asStructuredDraft(value: unknown): StructuredArtifactDraft | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const draft = value as StructuredArtifactDraft;
  return draft.artifact_type === "copywriting" || draft.artifact_type === "title_set" ? draft : null;
}

function codePointLength(value: string): number {
  return Array.from(value).length;
}

const stateLabels: Record<AppRun["state"], string> = {
  draft: "草稿",
  queued: "排队中",
  running: "执行中",
  needs_review: "待审核",
  completed: "已完成",
  failed: "失败",
  cancelled: "已取消",
};

export function CreationWorkspace({ appId = "builtin.marketing-copy", appVersion = "1.0.0" }: Props) {
  const [projects, setProjects] = useState<ContentProject[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [name, setName] = useState("");
  const [goal, setGoal] = useState("");
  const [runs, setRuns] = useState<AppRun[]>([]);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState("");
  const [contextPayload, setContextPayload] = useState<Record<string, unknown> | null>(null);
  const [versionCounts, setVersionCounts] = useState<Record<string, number>>({});
  const [versionDrafts, setVersionDrafts] = useState<Record<string, string>>({});
  const [structuredDrafts, setStructuredDrafts] = useState<Record<string, StructuredArtifactDraft | null>>({});
  const [latestArtifactVersions, setLatestArtifactVersions] = useState<Record<string, ArtifactVersion | null>>({});
  const [productOrService, setProductOrService] = useState("");
  const [contentFormat, setContentFormat] = useState("oral");
  const [lengthBucket, setLengthBucket] = useState("short_15s");
  const [platform, setPlatform] = useState("douyin");
  const [objective, setObjective] = useState("click");
  const [count, setCount] = useState(5);
  const [topic, setTopic] = useState("");
  const selected = useMemo(() => projects.find((project) => project.project_id === selectedId) || null, [projects, selectedId]);
  const isTitlesApp = appId === "builtin.viral-titles";
  const isCarouselApp = appId === "builtin.douyin-carousel";
  const [carouselSourceVersionId, setCarouselSourceVersionId] = useState("");
  const [carouselAssetRefs, setCarouselAssetRefs] = useState("");
  const [carouselPageCount, setCarouselPageCount] = useState(3);

  function resetCarouselDraft() {
    setCarouselSourceVersionId("");
    setCarouselAssetRefs("");
    setCarouselPageCount(3);
  }

  function restoreCarouselDraft(nextRuns: AppRun[]) {
    if (!isCarouselApp) {
      resetCarouselDraft();
      return;
    }
    const latest = [...nextRuns]
      .filter((run) => run.app_id === appId && run.input_payload && typeof run.input_payload === "object")
      .sort((left, right) => right.created_at.localeCompare(left.created_at))
      .find((run) => {
        const payload = run.input_payload;
        const sourceIds = Array.isArray(payload.source_artifact_version_ids)
          ? payload.source_artifact_version_ids.filter((value): value is string => typeof value === "string" && value.trim().length > 0)
          : [];
        const assetRefs = Array.isArray(payload.asset_refs)
          ? payload.asset_refs.filter((value): value is string => typeof value === "string" && value.trim().length > 0)
          : [];
        return sourceIds.length > 0 && assetRefs.length > 0 && [3, 5, 8].includes(Number(payload.page_count));
      });
    if (!latest) {
      resetCarouselDraft();
      return;
    }
    const payload = latest.input_payload;
    const sourceIds = Array.isArray(payload.source_artifact_version_ids)
      ? payload.source_artifact_version_ids.filter((value): value is string => typeof value === "string" && value.trim().length > 0)
      : [];
    const assetRefs = Array.isArray(payload.asset_refs)
      ? payload.asset_refs.filter((value): value is string => typeof value === "string" && value.trim().length > 0)
      : [];
    setCarouselSourceVersionId(sourceIds[0] || "");
    setCarouselAssetRefs(assetRefs.join(", "));
    setCarouselPageCount(Number(payload.page_count) as 3 | 5 | 8);
  }

  async function reload(forceSelect = false) {
    try {
      const next = await listContentProjects();
      setProjects(next);
      const first = next[0];
      if (first && (forceSelect || !selectedId)) {
        setSelectedId(first.project_id);
        setName(first.name);
        setGoal(first.primary_goal);
        const [nextRuns, snapshot] = await Promise.all([listAppRuns(first.project_id), getCurrentContextSnapshot(first.project_id)]);
        setRuns(nextRuns);
        restoreCarouselDraft(nextRuns);
        setContextPayload(snapshot?.payload || null);
      }
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "创作项目加载失败");
    }
  }

  useEffect(() => {
    void reload();
  }, []);

  useEffect(() => {
    if (!isCarouselApp) resetCarouselDraft();
  }, [appId, isCarouselApp]);

  useEffect(() => {
    if (!selectedId || !runs.some((run) => ["queued", "running"].includes(run.state))) return;
    const timer = window.setInterval(() => {
      void listAppRuns(selectedId).then(setRuns).catch(() => undefined);
    }, 1500);
    return () => window.clearInterval(timer);
  }, [selectedId, runs]);

  async function selectProject(project: ContentProject) {
    if (dirty && !window.confirm("当前项目有未保存修改，确定切换吗？")) return;
    resetCarouselDraft();
    setSelectedId(project.project_id);
    setName(project.name);
    setGoal(project.primary_goal);
    setDirty(false);
    const [nextRuns, snapshot] = await Promise.all([listAppRuns(project.project_id), getCurrentContextSnapshot(project.project_id)]);
    setRuns(nextRuns);
    restoreCarouselDraft(nextRuns);
    setContextPayload(snapshot?.payload || null);
  }

  async function saveDraft() {
    try {
      const project = selected
        ? await updateContentProject(selected.project_id, { name, primary_goal: goal })
        : await createContentProject({ name, primary_goal: goal });
      setProjects((current) => [project, ...current.filter((item) => item.project_id !== project.project_id)]);
      setSelectedId(project.project_id);
      setContextPayload(null);
      setDirty(false);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "项目保存失败");
    }
  }

  async function createDraftRun() {
    if (!selected) return;
    try {
      const input_payload = isCarouselApp
        ? {
            goal,
            page_count: carouselPageCount,
            source_artifact_version_ids: [carouselSourceVersionId.trim()],
            asset_refs: carouselAssetRefs.split(/[\s,，]+/).map((item) => item.trim()).filter(Boolean),
          }
        : isTitlesApp
          ? { platform, objective, count, topic }
          : { goal, product_or_service: productOrService, content_format: contentFormat, length_bucket: lengthBucket };
      await createAppRun({
        project_id: selected.project_id,
        app_id: appId,
        app_version: appVersion,
        input_payload,
        idempotency_key: `${selected.project_id}-${Date.now()}`,
        context_snapshot_id: selected.current_context_snapshot_id,
      });
      setRuns(await listAppRuns(selected.project_id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "运行草稿创建失败");
    }
  }

  async function actOnRun(run: AppRun) {
    try {
      if (run.state === "draft") await executeAppRun(run.app_run_id);
      else if (run.state === "failed") {
        await retryAppRun(run.app_run_id);
        await executeAppRun(run.app_run_id);
      } else if (run.state === "needs_review") await completeAppRun(run.app_run_id);
      else if (run.state === "queued" || run.state === "running") await cancelAppRun(run.app_run_id);
      if (selected) setRuns(await listAppRuns(selected.project_id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "运行操作失败");
    }
  }

  async function archiveSelected() {
    if (!selected) return;
    try {
      await archiveContentProject(selected.project_id);
      setSelectedId("");
      setRuns([]);
      setContextPayload(null);
      await reload(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "项目归档失败");
    }
  }

  async function inspectArtifact(artifactId: string) {
    try {
      const versions = await listArtifactVersions(artifactId);
      const latest = versions[versions.length - 1];
      setVersionCounts((current) => ({ ...current, [artifactId]: versions.length }));
      setLatestArtifactVersions((current) => ({ ...current, [artifactId]: latest || null }));
      const structured = asStructuredDraft(latest?.content);
      setStructuredDrafts((current) => ({ ...current, [artifactId]: structured }));
      setVersionDrafts((current) => ({ ...current, [artifactId]: JSON.stringify(structured || latest?.content || {}, null, 2) }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "版本加载失败");
    }
  }

  async function downloadCarouselPackage(artifactId: string, version: ArtifactVersion) {
    const zipRef = version.file_refs.find((fileRef) => fileRef.kind === "zip" || fileRef.mime_type === "application/zip");
    if (!zipRef || typeof zipRef.file_key !== "string") {
      setError("图文包 ZIP 不存在");
      return;
    }
    try {
      const blob = await downloadAppArtifactFile(artifactId, zipRef.file_key);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = zipRef.file_key;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "图文包下载失败");
    }
  }

  async function copyCarouselPublishCopy(version: ArtifactVersion) {
    const content = version.content || {};
    const hashtags = Array.isArray(content.hashtags) ? content.hashtags.map(String).join(" ") : "";
    const text = [String(content.title || ""), String(content.description || ""), hashtags].filter(Boolean).join("\n");
    if (!text || !navigator.clipboard) {
      setError("当前环境不支持复制发布文案");
      return;
    }
    try {
      await navigator.clipboard.writeText(text);
    } catch (err) {
      setError(err instanceof Error ? err.message : "发布文案复制失败");
    }
  }

  function syncStructuredDraft(artifactId: string, next: StructuredArtifactDraft) {
    setStructuredDrafts((current) => ({ ...current, [artifactId]: next }));
    setVersionDrafts((current) => ({ ...current, [artifactId]: JSON.stringify(next, null, 2) }));
  }

  function updateCopyVariant(artifactId: string, index: number, field: "hook" | "body" | "cta", value: string) {
    const draft = structuredDrafts[artifactId];
    if (!draft?.variants?.[index]) return;
    const variants = [...draft.variants];
    const current = { ...variants[index], [field]: value };
    const fullText = `${String(current.hook || "")}${String(current.body || "")}${String(current.cta || "")}`;
    const wordCount = codePointLength(fullText);
    variants[index] = { ...current, full_text: fullText, word_count: wordCount, estimated_seconds: Math.ceil(wordCount / 4) };
    syncStructuredDraft(artifactId, { ...draft, variants });
  }

  function updateTitleCandidate(artifactId: string, index: number, value: string) {
    const draft = structuredDrafts[artifactId];
    if (!draft?.candidates?.[index]) return;
    const candidates = [...draft.candidates];
    candidates[index] = { ...candidates[index], title: value, length: codePointLength(value) };
    syncStructuredDraft(artifactId, { ...draft, candidates });
  }

  async function saveEditedArtifact(artifactId: string) {
    try {
      const content = JSON.parse(versionDrafts[artifactId] || "{}");
      await appendArtifactVersion(artifactId, content, "edited");
      await inspectArtifact(artifactId);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "编辑版本保存失败");
    }
  }

  async function handoffToTitles(run: AppRun, artifactId: string) {
    if (!selected) return;
    try {
      const versions = await listArtifactVersions(artifactId);
      const latest = versions[versions.length - 1];
      if (!latest) throw new Error("暂无可交接的产物版本");
      const target = await createAppRun({
        project_id: selected.project_id,
        app_id: "builtin.viral-titles",
        app_version: "1.0.0",
        input_payload: { platform: "douyin", objective: "click", count: 5, source_artifact_version_id: latest.artifact_version_id },
        idempotency_key: `${run.app_run_id}-title-handoff-${latest.artifact_version_id}`,
        context_snapshot_id: selected.current_context_snapshot_id,
      });
      await createArtifactHandoff({
        project_id: selected.project_id,
        source_artifact_id: artifactId,
        source_artifact_version_id: latest.artifact_version_id,
        target_app_id: target.app_id,
        target_app_version: target.app_version,
        artifact_version_ids: [latest.artifact_version_id],
        target_run_id: target.app_run_id,
      });
      setRuns(await listAppRuns(selected.project_id));
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "文案交接标题失败");
    }
  }

  return (
    <Card title="我的创作" className="creation-workspace">
      {error && <Alert type="error" showIcon message={error} />}
      <div className="creation-workspace__grid">
        <Card size="small" title="项目" extra={<Button size="small" onClick={() => { setSelectedId(""); setName(""); setGoal(""); resetCarouselDraft(); setDirty(true); }}>新建</Button>}>
          {projects.length ? (
            <List
              size="small"
              dataSource={projects}
              renderItem={(project) => <List.Item onClick={() => void selectProject(project)} className={project.project_id === selectedId ? "creation-project--selected" : "creation-project"}>
                <Typography.Text strong>{project.name}</Typography.Text>
                <Tag>{project.status === "active" ? "进行中" : "已归档"}</Tag>
              </List.Item>}
            />
          ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有创作项目" />}
        </Card>
        <Card size="small" title={selected ? "项目草稿" : "新建项目"}>
          <Space direction="vertical" size="middle" style={{ width: "100%" }}>
            <Input value={name} placeholder="项目名称" onChange={(event) => { setName(event.target.value); setDirty(true); }} />
            <Input.TextArea value={goal} placeholder="本次营销目标" rows={4} onChange={(event) => { setGoal(event.target.value); setDirty(true); }} />
            {isCarouselApp ? (
              <>
                <Input aria-label="图文来源 ArtifactVersion" value={carouselSourceVersionId} placeholder="来源 ArtifactVersion ID" onChange={(event) => setCarouselSourceVersionId(event.target.value)} />
                <Input.TextArea aria-label="图文资产引用" value={carouselAssetRefs} placeholder="已登记图片引用，例如 asset:xxx，可填写多个" rows={3} onChange={(event) => setCarouselAssetRefs(event.target.value)} />
                <Select aria-label="图文页数" value={carouselPageCount} options={[3, 5, 8].map((value) => ({ value, label: `${value} 页` }))} onChange={setCarouselPageCount} />
                <Typography.Text type="secondary">图文只使用已登记的 asset:&lt;id&gt;，不接受本地绝对路径；分页文案由既有大模型配置生成，可在产物版本中编辑。</Typography.Text>
              </>
            ) : isTitlesApp ? (
              <>
                <Select aria-label="标题平台" value={platform} options={[{ value: "douyin", label: "抖音" }, { value: "xiaohongshu", label: "小红书" }, { value: "shipinhao", label: "视频号" }, { value: "kuaishou", label: "快手" }]} onChange={setPlatform} />
                <Select aria-label="标题目标" value={objective} options={[{ value: "click", label: "点击" }, { value: "store_visit", label: "到店" }, { value: "inquiry", label: "咨询" }, { value: "completion", label: "完播" }, { value: "save", label: "收藏" }]} onChange={setObjective} />
                <Select aria-label="标题数量" value={count} options={[5, 6, 7, 8, 9, 10].map((value) => ({ value, label: `${value} 个候选` }))} onChange={setCount} />
                <Input.TextArea value={topic} placeholder="标题主题（只能填写一种来源）" rows={3} onChange={(event) => setTopic(event.target.value)} />
              </>
            ) : (
              <>
                <Input value={productOrService} placeholder="产品或服务" onChange={(event) => setProductOrService(event.target.value)} />
                <Space>
                  <Select aria-label="文案形式" value={contentFormat} options={[{ value: "oral", label: "口播" }, { value: "carousel", label: "图文" }, { value: "general", label: "通用" }]} onChange={setContentFormat} />
                  <Select aria-label="文案时长" value={lengthBucket} options={[{ value: "short_15s", label: "15 秒" }, { value: "medium_30s", label: "30 秒" }, { value: "long_60s", label: "60 秒" }]} onChange={setLengthBucket} />
                </Space>
              </>
            )}
            <Space>
              <Button type="primary" disabled={!name.trim() || !goal.trim()} onClick={() => void saveDraft()}>保存草稿</Button>
              <Button disabled={!selected || (isCarouselApp ? !carouselSourceVersionId.trim() || !carouselAssetRefs.trim() : isTitlesApp ? !topic.trim() : !productOrService.trim())} onClick={() => void createDraftRun()}>创建运行草稿</Button>
              <Button danger disabled={!selected} onClick={() => void archiveSelected()}>归档项目</Button>
            </Space>
          </Space>
        </Card>
      </div>
      {selected && contextPayload && <Alert type="info" showIcon message="已恢复项目上下文快照" description={JSON.stringify(contextPayload)} />}
      {selected && <Card size="small" title="运行记录" style={{ marginTop: 16 }}>
        <List size="small" dataSource={runs} locale={{ emptyText: "暂无运行" }} renderItem={(run) => <List.Item actions={run.state !== "completed" && run.state !== "cancelled" ? [<Button size="small" onClick={() => void actOnRun(run)}>{run.state === "needs_review" ? "确认完成" : run.state === "queued" || run.state === "running" ? "取消" : run.state === "failed" ? "重试" : "执行"}</Button>] : undefined}>
          <Space direction="vertical" size={2}>
            <Space size="small"><Typography.Text>{run.app_id}</Typography.Text><Tag color={run.state === "failed" ? "error" : run.state === "completed" ? "success" : run.state === "cancelled" ? "default" : "processing"}>{stateLabels[run.state]}</Tag></Space>
            {run.output_artifact_ids.map((artifactId) => {
              const structured = structuredDrafts[artifactId];
              const latestVersion = latestArtifactVersions[artifactId];
              const isCarouselPackage = latestVersion?.content?.artifact_type === "carousel_package";
              return <Space key={artifactId} direction="vertical" size="small" style={{ width: "100%" }}>
                <Space size="small"><Typography.Text type="secondary">产物 {artifactId}</Typography.Text><Button size="small" type="link" onClick={() => void inspectArtifact(artifactId)}>查看版本</Button>{versionCounts[artifactId] !== undefined && <Tag>{versionCounts[artifactId]} 个版本</Tag>}{isCarouselPackage && latestVersion && <><Button size="small" onClick={() => void downloadCarouselPackage(artifactId, latestVersion)}>下载图文包</Button><Button size="small" onClick={() => void copyCarouselPublishCopy(latestVersion)}>复制发布文案</Button></>}{run.app_id === "builtin.marketing-copy" && <Button size="small" type="link" onClick={() => void handoffToTitles(run, artifactId)}>交给爆款标题</Button>}</Space>
                {structured?.artifact_type === "copywriting" && structured.variants?.map((variant, index) => <Card key={`variant-${index}`} size="small" title={`文案版本 ${index + 1}`}>
                  <Space direction="vertical" style={{ width: "100%" }}>
                    <Input aria-label={`文案版本${index + 1}开头`} value={String(variant.hook || "")} onChange={(event) => updateCopyVariant(artifactId, index, "hook", event.target.value)} />
                    <Input.TextArea aria-label={`文案版本${index + 1}正文`} value={String(variant.body || "")} rows={3} onChange={(event) => updateCopyVariant(artifactId, index, "body", event.target.value)} />
                    <Input aria-label={`文案版本${index + 1}行动号召`} value={String(variant.cta || "")} onChange={(event) => updateCopyVariant(artifactId, index, "cta", event.target.value)} />
                    <Typography.Text type="secondary">合成正文：{String(variant.full_text || "")}（{String(variant.word_count || 0)} 字，约 {String(variant.estimated_seconds || 0)} 秒）</Typography.Text>
                  </Space>
                </Card>)}
                {structured?.artifact_type === "title_set" && structured.candidates?.map((candidate, index) => <Input key={`candidate-${index}`} aria-label={`标题候选${index + 1}`} value={String(candidate.title || "")} onChange={(event) => updateTitleCandidate(artifactId, index, event.target.value)} addonAfter={`${String(candidate.length || 0)} 字`} />)}
                {versionDrafts[artifactId] !== undefined && <><Input.TextArea aria-label={`产物 ${artifactId} 编辑内容`} value={versionDrafts[artifactId]} rows={5} onChange={(event) => setVersionDrafts((current) => ({ ...current, [artifactId]: event.target.value }))} /><Button size="small" onClick={() => void saveEditedArtifact(artifactId)}>保存编辑版本</Button></>}
              </Space>;
            })}
          </Space>
        </List.Item>} />
      </Card>}
    </Card>
  );
}

export default CreationWorkspace;
