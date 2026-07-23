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
  listLibraryItemsV2,
  listContentProjects,
  retryAppRun,
  updateContentProject,
  listProjectArtifacts,
} from "../../api";
import { AssetPickerDialog } from "../assets/components/AssetPickerDialog";
import type { LibraryItemV2 } from "../../api";

type Props = {
  appId?: string;
  appVersion?: string;
  focused?: boolean;
  onBack?: () => void;
  onOpenApp?: (appId: string, sourceArtifactVersionId?: string) => void;
  initialSourceArtifactVersionId?: string;
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

const APP_COPY: Record<string, { name: string; description: string; eyebrow: string }> = {
  "builtin.marketing-copy": { name: "门店营销文案", description: "生成可编辑的门店营销文案，并交给标题、图文或数字人口播。", eyebrow: "CONTENT APP · COPYWRITING" },
  "builtin.viral-titles": { name: "爆款标题", description: "围绕平台和经营目标生成多角度标题候选，选择后继续创作。", eyebrow: "CONTENT APP · TITLES" },
  "builtin.douyin-carousel": { name: "抖音图文", description: "选择文案和企业图片，生成可下载的抖音图文包与发布文案。", eyebrow: "CONTENT APP · CAROUSEL" },
};

type CarouselSourceDateRange = "all" | "7d" | "30d" | "90d";

const CAROUSEL_SOURCE_DATE_OPTIONS: Array<{ value: CarouselSourceDateRange; label: string }> = [
  { value: "all", label: "全部时间" },
  { value: "7d", label: "最近 7 天" },
  { value: "30d", label: "最近 30 天" },
  { value: "90d", label: "最近 90 天" },
];

function isWithinDateRange(value: string, range: CarouselSourceDateRange): boolean {
  if (range === "all") return true;
  const timestamp = Date.parse(value);
  if (Number.isNaN(timestamp)) return false;
  const days = Number(range.slice(0, -1));
  return timestamp >= Date.now() - days * 24 * 60 * 60 * 1000;
}

function formatSourceDate(value: string): string {
  return /^\d{4}-\d{2}-\d{2}/.test(value) ? value.slice(0, 10) : "时间未知";
}

function truncateSourceText(value: string, maxLength = 36): string {
  const normalized = value.replace(/\s+/g, " ").trim();
  return normalized.length > maxLength ? `${normalized.slice(0, maxLength)}…` : normalized;
}

function sourceContentPreview(content: Record<string, unknown> | null | undefined): string {
  if (!content) return "暂无文案摘要";
  const artifactType = String(content.artifact_type || "");
  if (artifactType === "selected_title") return String(content.title || "暂无标题摘要");
  if (artifactType === "title_set") {
    const candidates = Array.isArray(content.candidates) ? content.candidates : [];
    const first = candidates[0];
    return first && typeof first === "object" ? String((first as Record<string, unknown>).title || "暂无标题摘要") : "暂无标题摘要";
  }
  if (artifactType === "copywriting") {
    const variants = Array.isArray(content.variants) ? content.variants : [];
    const first = variants[0];
    if (first && typeof first === "object") {
      const variant = first as Record<string, unknown>;
      return String(variant.full_text || [variant.hook, variant.body, variant.cta].filter(Boolean).join("") || "暂无文案摘要");
    }
  }
  return String(content.text || content.title || "暂无文案摘要");
}

export function CreationWorkspace({
  appId = "builtin.marketing-copy",
  appVersion = "1.0.0",
  focused = false,
  onBack,
  onOpenApp,
  initialSourceArtifactVersionId = "",
}: Props) {
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
  const [carouselSourceArtifactId, setCarouselSourceArtifactId] = useState("");
  const [carouselSourceArtifacts, setCarouselSourceArtifacts] = useState<Awaited<ReturnType<typeof listProjectArtifacts>>>([]);
  const [carouselSourceVersions, setCarouselSourceVersions] = useState<ArtifactVersion[]>([]);
  const [carouselSourceDateRange, setCarouselSourceDateRange] = useState<CarouselSourceDateRange>("all");
  const [carouselAssetRefs, setCarouselAssetRefs] = useState<string[]>([]);
  const [carouselAssetItems, setCarouselAssetItems] = useState<LibraryItemV2[]>([]);
  const [assetPickerOpen, setAssetPickerOpen] = useState(false);
  const [carouselPageCount, setCarouselPageCount] = useState(3);

  const sourceRunById = useMemo(() => new Map(runs.map((run) => [run.app_run_id, run])), [runs]);
  const recentlyUsedSourceVersionIds = useMemo(() => {
    const ids = new Set<string>();
    runs.filter((run) => run.app_id === "builtin.douyin-carousel").forEach((run) => {
      const sourceIds = run.input_payload?.source_artifact_version_ids;
      if (Array.isArray(sourceIds)) sourceIds.forEach((id) => typeof id === "string" && ids.add(id));
    });
    return ids;
  }, [runs]);
  const visibleSourceArtifacts = useMemo(
    () => carouselSourceArtifacts.filter((artifact) => isWithinDateRange(artifact.updated_at || artifact.created_at, carouselSourceDateRange)),
    [carouselSourceArtifacts, carouselSourceDateRange],
  );
  const visibleSourceVersions = useMemo(
    () => carouselSourceVersions.filter((version) => isWithinDateRange(version.created_at, carouselSourceDateRange)),
    [carouselSourceVersions, carouselSourceDateRange],
  );
  const selectedSourceArtifact = useMemo(
    () => carouselSourceArtifacts.find((artifact) => artifact.artifact_id === carouselSourceArtifactId) || null,
    [carouselSourceArtifacts, carouselSourceArtifactId],
  );
  const selectedSourceVersion = useMemo(
    () => carouselSourceVersions.find((version) => version.artifact_version_id === carouselSourceVersionId) || null,
    [carouselSourceVersions, carouselSourceVersionId],
  );
  const selectedSourceRun = selectedSourceArtifact?.source_app_run_id ? sourceRunById.get(selectedSourceArtifact.source_app_run_id) : null;

  function resetCarouselDraft() {
    setCarouselSourceVersionId("");
    setCarouselSourceArtifactId("");
    setCarouselSourceVersions([]);
    setCarouselSourceDateRange("all");
    setCarouselAssetRefs([]);
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
    setCarouselAssetRefs(assetRefs);
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
    if (!isCarouselApp || !selectedId) {
      setCarouselSourceArtifacts([]);
      setCarouselSourceVersions([]);
      return;
    }
    let active = true;
    void listProjectArtifacts(selectedId)
      .then((items) => {
        if (!active) return;
        const eligible = items.filter((item) => ["copywriting", "selected_title", "title_set"].includes(item.artifact_type) && item.status !== "archived");
        setCarouselSourceArtifacts(eligible);
        if (!eligible.some((item) => item.artifact_id === carouselSourceArtifactId)) {
          const matching = eligible.find((item) => item.current_version_id === initialSourceArtifactVersionId)
            || eligible.find((item) => item.current_version_id === carouselSourceVersionId)
            || eligible[0];
          setCarouselSourceArtifactId(matching?.artifact_id || "");
        }
      })
      .catch((err) => { if (active) setError(err instanceof Error ? err.message : "来源产物加载失败"); });
    return () => { active = false; };
  }, [initialSourceArtifactVersionId, isCarouselApp, selectedId]);

  useEffect(() => {
    if (!isCarouselApp || !carouselSourceArtifactId) {
      setCarouselSourceVersions([]);
      return;
    }
    let active = true;
    void listArtifactVersions(carouselSourceArtifactId)
      .then((items) => {
        if (!active) return;
        setCarouselSourceVersions(items);
        const preferred = items.find((item) => item.artifact_version_id === initialSourceArtifactVersionId)
          || items.find((item) => item.artifact_version_id === carouselSourceVersionId)
          || items.find((item) => item.artifact_version_id === carouselSourceArtifacts.find((artifact) => artifact.artifact_id === carouselSourceArtifactId)?.current_version_id)
          || items[items.length - 1];
        setCarouselSourceVersionId(preferred?.artifact_version_id || "");
      })
      .catch((err) => { if (active) setError(err instanceof Error ? err.message : "来源产物版本加载失败"); });
    return () => { active = false; };
  }, [carouselSourceArtifactId, initialSourceArtifactVersionId, isCarouselApp]);

  useEffect(() => {
    if (!isCarouselApp || !selectedId || !carouselSourceArtifactId) return;
    if (!visibleSourceArtifacts.some((artifact) => artifact.artifact_id === carouselSourceArtifactId)) {
      const next = visibleSourceArtifacts[0];
      setCarouselSourceArtifactId(next?.artifact_id || "");
      setCarouselSourceVersionId("");
    }
  }, [carouselSourceArtifactId, isCarouselApp, selectedId, visibleSourceArtifacts]);

  // Project/run restoration and artifact loading resolve independently. If a
  // restored draft clears the selection after artifacts arrive, re-select the
  // best source once the list is available instead of leaving the picker blank.
  useEffect(() => {
    if (!isCarouselApp || !selectedId || carouselSourceArtifactId || !carouselSourceArtifacts.length) return;
    const matching = carouselSourceArtifacts.find((artifact) => artifact.current_version_id === initialSourceArtifactVersionId)
      || carouselSourceArtifacts.find((artifact) => artifact.current_version_id === carouselSourceVersionId)
      || carouselSourceArtifacts[0];
    if (matching) setCarouselSourceArtifactId(matching.artifact_id);
  }, [carouselSourceArtifactId, carouselSourceArtifacts, carouselSourceVersionId, initialSourceArtifactVersionId, isCarouselApp, selectedId]);

  useEffect(() => {
    if (!isCarouselApp || !carouselSourceVersions.length) return;
    if (!visibleSourceVersions.some((version) => version.artifact_version_id === carouselSourceVersionId)) {
      setCarouselSourceVersionId(visibleSourceVersions[visibleSourceVersions.length - 1]?.artifact_version_id || "");
    }
  }, [carouselSourceVersionId, carouselSourceVersions, isCarouselApp, visibleSourceVersions]);

  useEffect(() => {
    if (!isCarouselApp) {
      setCarouselAssetItems([]);
      return;
    }
    let active = true;
    void listLibraryItemsV2("image")
      .then((result) => {
        if (active) setCarouselAssetItems(result.items);
      })
      .catch(() => {
        // The picker remains the source of truth. Existing runs can still be
        // restored even if the optional name lookup is temporarily offline.
      });
    return () => { active = false; };
  }, [isCarouselApp]);

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
            asset_refs: carouselAssetRefs,
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

  async function openCarouselFromArtifact(artifactId: string) {
    if (!onOpenApp) return;
    try {
      const versions = await listArtifactVersions(artifactId);
      const latest = versions[versions.length - 1];
      if (!latest) throw new Error("暂无可交接的文案版本");
      onOpenApp("builtin.douyin-carousel", latest.artifact_version_id);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "打开抖音图文失败");
    }
  }

  const appCopy = APP_COPY[appId] || APP_COPY["builtin.marketing-copy"];
  const workspace = (
    <Card title={focused ? "1 · 配置输入与项目" : "我的创作"} className="creation-workspace">
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
                <Space wrap className="creation-source-toolbar">
                  <Select
                    aria-label="图文来源时间筛选"
                    value={carouselSourceDateRange}
                    options={CAROUSEL_SOURCE_DATE_OPTIONS}
                    onChange={setCarouselSourceDateRange}
                  />
                  <Typography.Text type="secondary">显示 {visibleSourceArtifacts.length} 个来源</Typography.Text>
                </Space>
                <Select
                  aria-label="图文来源产物"
                  placeholder="选择文案或标题产物"
                  value={carouselSourceArtifactId || undefined}
                  options={visibleSourceArtifacts.map((artifact) => {
                    const sourceRun = artifact.source_app_run_id ? sourceRunById.get(artifact.source_app_run_id) : null;
                    const sourceGoal = typeof sourceRun?.input_payload?.goal === "string" ? ` · 目标：${truncateSourceText(sourceRun.input_payload.goal, 24)}` : "";
                    const recentlyUsed = artifact.current_version_id && recentlyUsedSourceVersionIds.has(artifact.current_version_id) ? " · 最近使用" : "";
                    return {
                      value: artifact.artifact_id,
                      label: `${artifact.name} · ${artifact.artifact_type === "copywriting" ? "文案" : "标题"} · ${formatSourceDate(artifact.updated_at || artifact.created_at)}${sourceGoal}${recentlyUsed}`,
                    };
                  })}
                  onChange={(value) => { setCarouselSourceArtifactId(value); setCarouselSourceVersionId(""); }}
                  notFoundContent="当前项目暂无可用文案或标题"
                />
                <Select
                  aria-label="图文来源版本"
                  placeholder="选择产物版本"
                  value={carouselSourceVersionId || undefined}
                  options={visibleSourceVersions.map((version) => ({
                    value: version.artifact_version_id,
                    label: `版本 ${version.version_number} · ${formatSourceDate(version.created_at)} · ${truncateSourceText(sourceContentPreview(version.content), 28)}${recentlyUsedSourceVersionIds.has(version.artifact_version_id) ? " · 最近使用" : ""}`,
                  }))}
                  onChange={setCarouselSourceVersionId}
                  disabled={!visibleSourceVersions.length}
                />
                {selectedSourceVersion ? <div className="creation-source-summary" aria-label="图文来源摘要">
                  <Space wrap size={[6, 4]}>
                    <Tag>生成于 {formatSourceDate(selectedSourceVersion.created_at)}</Tag>
                    {selectedSourceRun && typeof selectedSourceRun.input_payload?.goal === "string" ? <Tag>营销目标：{truncateSourceText(selectedSourceRun.input_payload.goal, 30)}</Tag> : null}
                    {recentlyUsedSourceVersionIds.has(selectedSourceVersion.artifact_version_id) ? <Tag color="blue">最近使用</Tag> : null}
                  </Space>
                  <Typography.Text type="secondary">文案摘要：{truncateSourceText(sourceContentPreview(selectedSourceVersion.content), 96)}</Typography.Text>
                </div> : null}
                <div className="creation-carousel-assets" aria-label="图文图片资产">
                  <Space wrap>
                    {carouselAssetRefs.map((ref) => {
                      const assetId = ref.replace(/^asset:/, "");
                      const asset = carouselAssetItems.find((item) => (item.asset_id || item.resource_id) === assetId);
                      return <Tag key={ref} closable onClose={() => setCarouselAssetRefs((current) => current.filter((item) => item !== ref))}>{asset?.name || "已选图片"}</Tag>;
                    })}
                    <Button type="dashed" onClick={() => setAssetPickerOpen(true)}>选择图片资产</Button>
                  </Space>
                  {!carouselAssetRefs.length ? <Typography.Text type="secondary">请选择 1–20 张企业图片；系统会自动生成 asset 引用。</Typography.Text> : null}
                </div>
                <Select aria-label="图文页数" value={carouselPageCount} options={[3, 5, 8].map((value) => ({ value, label: `${value} 页` }))} onChange={setCarouselPageCount} />
                <Typography.Text type="secondary">图文只使用企业资产库中的图片；分页文案由既有大模型配置生成，可在产物版本中编辑。</Typography.Text>
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
              <Button disabled={!selected || (isCarouselApp ? !carouselSourceVersionId.trim() || carouselAssetRefs.length === 0 : isTitlesApp ? !topic.trim() : !productOrService.trim())} onClick={() => void createDraftRun()}>创建运行草稿</Button>
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
                <Space size="small"><Typography.Text type="secondary">产物 {artifactId}</Typography.Text><Button size="small" type="link" onClick={() => void inspectArtifact(artifactId)}>查看版本</Button>{versionCounts[artifactId] !== undefined && <Tag>{versionCounts[artifactId]} 个版本</Tag>}{isCarouselPackage && latestVersion && <><Button size="small" onClick={() => void downloadCarouselPackage(artifactId, latestVersion)}>下载图文包</Button><Button size="small" onClick={() => void copyCarouselPublishCopy(latestVersion)}>复制发布文案</Button></>}{run.app_id === "builtin.marketing-copy" && <Button size="small" type="link" onClick={() => void handoffToTitles(run, artifactId)}>交给爆款标题</Button>}{run.app_id === "builtin.marketing-copy" && onOpenApp && <Button size="small" type="link" onClick={() => void openCarouselFromArtifact(artifactId)}>制作抖音图文</Button>}</Space>
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
      {isCarouselApp ? <AssetPickerDialog
        open={assetPickerOpen}
        kind="image"
        selectionMode="multiple"
        selectedIds={carouselAssetRefs.map((ref) => {
          const assetId = ref.replace(/^asset:/, "");
          return carouselAssetItems.find((item) => (item.asset_id || item.resource_id) === assetId)?.resource_id || assetId;
        })}
        onClose={() => setAssetPickerOpen(false)}
        onSelect={() => undefined}
        onSelectMany={(items: LibraryItemV2[]) => {
          setCarouselAssetItems(items);
          setCarouselAssetRefs(items.map((item) => `asset:${item.asset_id || item.resource_id}`));
          setAssetPickerOpen(false);
        }}
        context={{
          session_id: selectedId || "app-center",
          step: "carousel",
          purpose: "抖音图文图片",
          slot_id: "carousel-images",
          allowed_kinds: ["image"],
          // Asset Library V2 exposes the stable picker capability `use` for
          // regular images; carousel is an application workflow, not an
          // asset capability. Requiring the old capability name made every
          // real image appear incompatible in production.
          required_capabilities: ["use"],
          selection_mode: "multiple",
        }}
      /> : null}
    </Card>
  );

  if (!focused) return workspace;
  return (
    <section className="creation-workflow-page" aria-label={`${appCopy.name}应用流程`}>
      <div className="creation-workflow-header">
        <div>
          <Typography.Text className="creation-workflow-eyebrow">{appCopy.eyebrow}</Typography.Text>
          <Typography.Title level={2}>{appCopy.name}</Typography.Title>
          <Typography.Paragraph type="secondary">{appCopy.description}</Typography.Paragraph>
        </div>
        <Button onClick={onBack}>返回应用中心</Button>
      </div>
      {workspace}
    </section>
  );
}

export default CreationWorkspace;
