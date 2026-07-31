import { useEffect, useMemo, useRef, useState } from "react";
import { Alert, Button, Card, Input, List, Modal, Select, Space, Tag, Typography } from "antd";
import {
  AppRun,
  ArtifactVersion,
  ContentProject,
  ContextSnapshot,
  GenerationCarouselResultItem,
  GenerationRecordBlock,
  GenerationTextResultItem,
  GenerationVideoResultItem,
  createAppRun,
  createPublishPackageV2,
  createProjectArtifact,
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
  listStylePresets,
  retryAppRun,
  retryCarouselPage,
  recordAppEvent,
  updateContentProject,
  listProjectArtifacts,
} from "../../api";
import { AssetPickerDialog } from "../assets/components/AssetPickerDialog";
import type { LibraryItemV2, StylePreset } from "../../api";
import { featureFlags } from "../../featureFlags";
import { AppWorkbenchShell, type WorkbenchViewState } from "../app-workbench/AppWorkbenchShell";
import { ProjectBriefEditor } from "../app-workbench/ProjectBriefEditor";
import { ProjectBriefDisclosure } from "../app-workbench/ProjectBriefDisclosure";
import { ProjectContextSelector } from "../app-workbench/ProjectContextSelector";
import {
  BrandProjectContextPanel,
  BrandProjectCreateDialog,
} from "../app-workbench/BrandProjectContext";
import { StylePresetPicker, type StyleSource } from "../app-workbench/StylePresetPicker";
import { HandoffActions, VersionSwitcher } from "../app-workbench/ArtifactActions";
import { ProjectGenerationHistory } from "../app-workbench/ProjectGenerationHistory";

type Props = {
  appId?: string;
  appVersion?: string;
  focused?: boolean;
  onBack?: () => void;
  onOpenApp?: (appId: string, sourceArtifactVersionId?: string) => void;
  onOpenPublishCenter?: (packageId: string) => void;
  initialSourceArtifactVersionId?: string;
  workbenchV2?: boolean;
  textAppsV2?: boolean;
  carouselAppsV2?: boolean;
  brandProjectV1?: boolean;
  resultHistoryV1?: boolean;
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

function parseGenerationTextItemId(itemId: string) {
  const segments = itemId.split(":");
  const indexText = segments.pop();
  const artifactVersionId = segments.pop();
  const artifactId = segments.join(":");
  const itemIndex = Number(indexText) - 1;
  if (
    !artifactId
    || !artifactVersionId
    || !Number.isInteger(itemIndex)
    || itemIndex < 0
  ) {
    throw new Error("这条历史结果暂时无法操作，请刷新后重试");
  }
  return { artifactId, artifactVersionId, itemIndex };
}

async function sha256Fingerprint(value: string): Promise<string> {
  const digest = await window.crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(value),
  );
  return `sha256:${Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("")}`;
}

const stateLabels: Record<AppRun["state"], string> = {
  draft: "草稿",
  queued: "排队中",
  running: "执行中",
  needs_review: "请确认",
  completed: "已完成",
  failed: "失败",
  cancelled: "已取消",
};

const APP_COPY: Record<string, { name: string; description: string; eyebrow: string }> = {
  "builtin.marketing-copy": { name: "门店营销文案", description: "把本次主推和卖点，变成一段可以直接使用的营销文案。", eyebrow: "文案创作" },
  "builtin.viral-titles": { name: "爆款标题", description: "为一段内容生成多个标题，挑一个最适合发布的。", eyebrow: "文案创作" },
  "builtin.douyin-carousel": { name: "抖音图文", description: "把一段内容和门店图片，变成可以直接发布的抖音图文。", eyebrow: "图文创作" },
};

const MARKETING_BENEFIT_SUGGESTIONS = [
  "新品",
  "限时优惠",
  "到店",
  "直播",
  "节日",
  "送礼",
  "折扣",
  "预约",
  "复购",
];

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

function truncateSourceText(value: string, maxLength = 36): string {
  const normalized = value.replace(/\s+/g, " ").trim();
  return normalized.length > maxLength ? `${normalized.slice(0, maxLength)}…` : normalized;
}

function parseCarouselAssetRef(ref: string): { assetId: string; revisionId: string } {
  const normalized = ref.replace(/^asset:/, "");
  const [assetId, revisionId = ""] = normalized.split("@", 2);
  return { assetId, revisionId };
}

function carouselAssetRef(item: LibraryItemV2): string {
  const assetId = item.asset_id || item.resource_id;
  const revisionId = item.revision?.revision_id;
  return `asset:${assetId}${revisionId ? `@${revisionId}` : ""}`;
}

function carouselAssetDescription(ref: string, items: LibraryItemV2[]) {
  const { assetId } = parseCarouselAssetRef(ref);
  const asset = items.find((item) => (item.asset_id || item.resource_id) === assetId);
  const dimensions = asset?.summary
    ? [asset.summary.width, asset.summary.height].filter((value) => Number(value) > 0).join("×")
    : "";
  const metadataBasis = [
    asset?.name || "已选图片",
    asset?.tags?.filter(Boolean).join("、") || "",
    dimensions,
  ].filter(Boolean).join("；");
  return {
    asset_ref: ref,
    name: asset?.name || "已选图片",
    description: asset?.description?.trim() || "",
    description_status: asset?.description?.trim() ? "provided" : "generate_on_demand",
    metadata_basis: metadataBasis,
  };
}

const CAROUSEL_ERROR_COPY: Record<string, string> = {
  ASSET_REF_REQUIRED: "至少选择一张可用图片后再生成。",
  ASSET_NOT_FOUND: "有图片资产已缺失或版本不可用，请重新选择。",
  FONT_MISSING: "当前模板字体不可用，请检查本机字体资源后重试。",
  TEXT_OVERFLOW: "有页面文字过多，请缩短文案后单独重渲染该页。",
  PAGE_COUNT_NOT_ALLOWED: "图文页数只能选择 3、5 或 8 页。",
  STRUCTURED_OUTPUT_INVALID: "分页计划不符合图文规则，请检查来源内容后重试。",
  LLM_PROVIDER_FAILED: "大模型分页规划失败，请检查当前模型配置。",
};

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

function contextFactTexts(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => item && typeof item === "object" ? String((item as Record<string, unknown>).text || "").trim() : "")
    .filter(Boolean);
}

function projectBriefFromContext(payload: Record<string, unknown> | null | undefined): Record<string, unknown> {
  const brief = payload?.project_brief;
  return brief && typeof brief === "object" && !Array.isArray(brief)
    ? brief as Record<string, unknown>
    : payload || {};
}

function supportsApplicationContext(snapshot: ContextSnapshot | null): boolean {
  return Boolean(snapshot && (snapshot.schema_version === 2 || snapshot.schema_version === 3));
}

export function CreationWorkspace({
  appId = "builtin.marketing-copy",
  appVersion = "1.0.0",
  focused = false,
  onBack,
  onOpenApp,
  onOpenPublishCenter,
  initialSourceArtifactVersionId = "",
  workbenchV2 = featureFlags.appWorkbenchV2,
  textAppsV2 = featureFlags.appWorkbenchTextV2,
  carouselAppsV2 = featureFlags.appWorkbenchCarouselV2,
  brandProjectV1 = featureFlags.brandProjectBoundaryV1,
  resultHistoryV1 = featureFlags.appResultHistoryV1,
}: Props) {
  const [projects, setProjects] = useState<ContentProject[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [name, setName] = useState("");
  const [goal, setGoal] = useState("");
  const [runs, setRuns] = useState<AppRun[]>([]);
  const [dirty, setDirty] = useState(false);
  const [contextDirty, setContextDirty] = useState(false);
  const [projectDetailsOpen, setProjectDetailsOpen] = useState(false);
  const [projectCreateOpen, setProjectCreateOpen] = useState(false);
  const [projectCreateBusy, setProjectCreateBusy] = useState(false);
  const [newProjectName, setNewProjectName] = useState("");
  const [newProjectGoal, setNewProjectGoal] = useState("");
  const [error, setError] = useState("");
  const [contextPayload, setContextPayload] = useState<Record<string, unknown> | null>(null);
  const [contextSnapshot, setContextSnapshot] = useState<ContextSnapshot | null>(null);
  const projectRequestSequence = useRef(0);
  const [versionCounts, setVersionCounts] = useState<Record<string, number>>({});
  const [versionDrafts, setVersionDrafts] = useState<Record<string, string>>({});
  const [structuredDrafts, setStructuredDrafts] = useState<Record<string, StructuredArtifactDraft | null>>({});
  const [latestArtifactVersions, setLatestArtifactVersions] = useState<Record<string, ArtifactVersion | null>>({});
  const [artifactVersionLists, setArtifactVersionLists] = useState<Record<string, ArtifactVersion[]>>({});
  const selectedTitleVersionInFlight = useRef(new Map<string, Promise<ArtifactVersion>>());
  const [selectedTitleArtifactIds, setSelectedTitleArtifactIds] = useState<Record<string, string>>({});
  const [productOrService, setProductOrService] = useState("");
  const [marketingGoal, setMarketingGoal] = useState("");
  const [benefitTagsText, setBenefitTagsText] = useState("");
  const [contentFormat, setContentFormat] = useState("oral");
  const [lengthBucket, setLengthBucket] = useState("short_15s");
  const [platform, setPlatform] = useState("douyin");
  const [objective, setObjective] = useState("click");
  const [count, setCount] = useState(6);
  const [topic, setTopic] = useState("");
  const [titleKeywordsText, setTitleKeywordsText] = useState("");
  const textWorkbenchV2 = workbenchV2
    && textAppsV2
    && ["builtin.marketing-copy", "builtin.viral-titles"].includes(appId);
  const [stylePresets, setStylePresets] = useState<StylePreset[]>([]);
  const [styleSource, setStyleSource] = useState<StyleSource>("preset");
  const [selectedStyleId, setSelectedStyleId] = useState("");
  const [customStyleText, setCustomStyleText] = useState("");
  const [titleSourceMode, setTitleSourceMode] = useState<"artifact" | "topic" | "text">(
    initialSourceArtifactVersionId ? "artifact" : "topic",
  );
  const [titleSourceText, setTitleSourceText] = useState("");
  const [titleSourceArtifacts, setTitleSourceArtifacts] = useState<Awaited<ReturnType<typeof listProjectArtifacts>>>([]);
  const [titleSourceArtifactId, setTitleSourceArtifactId] = useState("");
  const [titleSourceVersions, setTitleSourceVersions] = useState<ArtifactVersion[]>([]);
  const [titleSourceVersionId, setTitleSourceVersionId] = useState(initialSourceArtifactVersionId);
  const [sourceRouteBlocked, setSourceRouteBlocked] = useState(false);
  const [actionNotice, setActionNotice] = useState("");
  const restoredTextRunKey = useRef("");
  const selected = useMemo(() => projects.find((project) => project.project_id === selectedId) || null, [projects, selectedId]);
  const isTitlesApp = appId === "builtin.viral-titles";
  const isCarouselApp = appId === "builtin.douyin-carousel";
  const carouselWorkbenchV2 = workbenchV2 && carouselAppsV2 && isCarouselApp;
  const styleWorkbenchV2 = textWorkbenchV2 || carouselWorkbenchV2;
  const [carouselSourceVersionId, setCarouselSourceVersionId] = useState("");
  const [carouselSourceArtifactId, setCarouselSourceArtifactId] = useState("");
  const [carouselSourceArtifacts, setCarouselSourceArtifacts] = useState<Awaited<ReturnType<typeof listProjectArtifacts>>>([]);
  const [carouselSourceVersions, setCarouselSourceVersions] = useState<ArtifactVersion[]>([]);
  const [carouselSourceDateRange, setCarouselSourceDateRange] = useState<CarouselSourceDateRange>("all");
  const [carouselAssetRefs, setCarouselAssetRefs] = useState<string[]>([]);
  const [carouselAssetItems, setCarouselAssetItems] = useState<LibraryItemV2[]>([]);
  const [assetPickerOpen, setAssetPickerOpen] = useState(false);
  const [carouselPageCount, setCarouselPageCount] = useState(3);
  const [carouselTemplateId, setCarouselTemplateId] = useState("template:clean-01");
  const [carouselCoverHook, setCarouselCoverHook] = useState("");
  const [carouselCta, setCarouselCta] = useState("");
  const [carouselPublishDescription, setCarouselPublishDescription] = useState("");
  const [carouselHashtagsText, setCarouselHashtagsText] = useState("");
  const [carouselPageDrafts, setCarouselPageDrafts] = useState<Record<string, { text: string; asset_refs: string[] }>>({});
  const [carouselPreviewUrls, setCarouselPreviewUrls] = useState<Record<string, string>>({});
  const [carouselPageBusy, setCarouselPageBusy] = useState("");

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
  const titleSourceArtifact = useMemo(
    () => titleSourceArtifacts.find((artifact) => artifact.artifact_id === titleSourceArtifactId) || null,
    [titleSourceArtifactId, titleSourceArtifacts],
  );
  const titleSourceVersionUpdateAvailable = Boolean(
    initialSourceArtifactVersionId
      && titleSourceArtifact?.current_version_id
      && titleSourceArtifact.current_version_id !== initialSourceArtifactVersionId,
  );
  const carouselSourceVersionUpdateAvailable = Boolean(
    initialSourceArtifactVersionId
      && selectedSourceArtifact?.current_version_id
      && selectedSourceArtifact.current_version_id !== initialSourceArtifactVersionId,
  );
  const projectSellingPoints = useMemo(
    () => {
      const payload = contextSnapshot?.payload;
      const brief = payload?.project_brief && typeof payload.project_brief === "object"
        ? payload.project_brief as Record<string, unknown>
        : payload;
      return contextFactTexts(brief?.selling_points);
    },
    [contextSnapshot],
  );
  const selectedBenefitTags = useMemo(
    () => benefitTagsText
      .split(/[\n,，]/)
      .map((item) => item.trim())
      .filter(Boolean),
    [benefitTagsText],
  );

  function toggleBenefitTag(tag: string) {
    const next = new Set(selectedBenefitTags);
    if (next.has(tag)) next.delete(tag);
    else next.add(tag);
    setBenefitTagsText(Array.from(next).join("，"));
  }

  function resetCarouselDraft() {
    setSourceRouteBlocked(false);
    setCarouselSourceVersionId("");
    setCarouselSourceArtifactId("");
    setCarouselSourceVersions([]);
    setCarouselSourceDateRange("all");
    setCarouselAssetRefs([]);
    setCarouselPageCount(3);
    setCarouselTemplateId("template:clean-01");
    setCarouselCoverHook("");
    setCarouselCta("");
    setCarouselPublishDescription("");
    setCarouselHashtagsText("");
    setCarouselPageDrafts({});
    setCarouselPreviewUrls((current) => {
      Object.values(current).forEach((url) => URL.revokeObjectURL(url));
      return {};
    });
  }

  function resetTextAppDraft() {
    setSourceRouteBlocked(false);
    restoredTextRunKey.current = "";
    setProductOrService("");
    setMarketingGoal("");
    setBenefitTagsText("");
    setContentFormat("oral");
    setLengthBucket("short_15s");
    setPlatform("douyin");
    setObjective("click");
    setCount(6);
    setTopic("");
    setTitleKeywordsText("");
    setTitleSourceMode(initialSourceArtifactVersionId ? "artifact" : "topic");
    setTitleSourceText("");
    setTitleSourceArtifactId("");
    setTitleSourceVersions([]);
    setTitleSourceVersionId(initialSourceArtifactVersionId);
    setSelectedTitleArtifactIds({});
    setStyleSource("preset");
    setCustomStyleText("");
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
        const brief = Number(payload.schema_version) === 2 && payload.task_brief && typeof payload.task_brief === "object"
          ? payload.task_brief as Record<string, unknown>
          : payload;
        const sourceIds = Array.isArray(payload.source_artifact_version_ids)
          ? payload.source_artifact_version_ids.filter((value): value is string => typeof value === "string" && value.trim().length > 0)
          : [];
        const assetRefs = Array.isArray(brief.asset_refs)
          ? brief.asset_refs.filter((value): value is string => typeof value === "string" && value.trim().length > 0)
          : [];
        return sourceIds.length > 0 && assetRefs.length > 0 && [3, 5, 8].includes(Number(brief.page_count));
      });
    if (!latest) {
      resetCarouselDraft();
      return;
    }
    const payload = latest.input_payload;
    const brief = Number(payload.schema_version) === 2 && payload.task_brief && typeof payload.task_brief === "object"
      ? payload.task_brief as Record<string, unknown>
      : payload;
    const sourceIds = Array.isArray(payload.source_artifact_version_ids)
      ? payload.source_artifact_version_ids.filter((value): value is string => typeof value === "string" && value.trim().length > 0)
      : [];
    const assetRefs = Array.isArray(brief.asset_refs)
      ? brief.asset_refs.filter((value): value is string => typeof value === "string" && value.trim().length > 0)
      : [];
    setCarouselSourceVersionId(sourceIds[0] || "");
    setCarouselAssetRefs(assetRefs);
    setCarouselPageCount(Number(brief.page_count) as 3 | 5 | 8);
    if (Number(payload.schema_version) === 2) {
      setCarouselTemplateId(String(brief.template_id || "template:clean-01"));
      setCarouselCoverHook(String(brief.cover_hook || ""));
      setCarouselCta(String(brief.cta || ""));
      setCarouselPublishDescription(String(brief.publish_description || ""));
      setCarouselHashtagsText(Array.isArray(brief.hashtags) ? brief.hashtags.map(String).join("，") : "");
      const style = payload.style_ref && typeof payload.style_ref === "object"
        ? payload.style_ref as Record<string, unknown>
        : null;
      const custom = payload.custom_style_reference && typeof payload.custom_style_reference === "object"
        ? payload.custom_style_reference as Record<string, unknown>
        : null;
      if (style?.style_id) {
        setStyleSource("preset");
        setSelectedStyleId(String(style.style_id));
        setCustomStyleText("");
      } else if (custom?.text) {
        setStyleSource("custom");
        setCustomStyleText(String(custom.text));
      }
    }
  }

  async function reload(forceSelect = false) {
    const requestSequence = ++projectRequestSequence.current;
    try {
      const next = await listContentProjects();
      if (requestSequence !== projectRequestSequence.current) return;
      setProjects(next);
      const first = next[0];
      if (first && (forceSelect || !selectedId)) {
        setSelectedId(first.project_id);
        setName(first.name);
        setGoal(first.primary_goal);
        setMarketingGoal(first.primary_goal);
        const [nextRuns, snapshot] = await Promise.all([listAppRuns(first.project_id), getCurrentContextSnapshot(first.project_id)]);
        if (requestSequence !== projectRequestSequence.current) return;
        setRuns(nextRuns);
        restoreCarouselDraft(nextRuns);
        setContextPayload(snapshot?.payload || null);
        setContextSnapshot(snapshot);
        setContextDirty(false);
        if (brandProjectV1 && snapshot?.schema_version === 3) setProjectDetailsOpen(true);
      }
      setError("");
    } catch (err) {
      if (requestSequence !== projectRequestSequence.current) return;
      setError(err instanceof Error ? err.message : "创作项目加载失败");
    }
  }

  useEffect(() => {
    void reload();
  }, []);

  useEffect(() => {
    if (!styleWorkbenchV2) {
      setStylePresets([]);
      setSelectedStyleId("");
      return;
    }
    let active = true;
    void listStylePresets(appId)
      .then(({ items }) => {
        if (!active) return;
        setStylePresets(items);
        setSelectedStyleId((current) => (
          items.some((item) => item.style_id === current)
            ? current
            : items[0]?.style_id || ""
        ));
      })
      .catch((loadError) => {
        if (active) setError(loadError instanceof Error ? loadError.message : "风格目录加载失败");
      });
    return () => {
      active = false;
    };
  }, [appId, styleWorkbenchV2]);

  useEffect(() => {
    if (!textWorkbenchV2 || !selectedId) return;
    const latest = [...runs]
      .filter((run) => run.project_id === selectedId && run.app_id === appId)
      .sort((left, right) => right.created_at.localeCompare(left.created_at))[0];
    if (!latest || restoredTextRunKey.current === latest.app_run_id) return;
    const payload = latest.input_payload && typeof latest.input_payload === "object"
      ? latest.input_payload
      : {};
    if (Number(payload.schema_version) !== 2) return;
    const brief = payload.task_brief && typeof payload.task_brief === "object"
      ? payload.task_brief as Record<string, unknown>
      : {};
    const style = payload.style_ref && typeof payload.style_ref === "object"
      ? payload.style_ref as Record<string, unknown>
      : null;
    const custom = payload.custom_style_reference && typeof payload.custom_style_reference === "object"
      ? payload.custom_style_reference as Record<string, unknown>
      : null;
    if (style?.style_id) {
      setStyleSource("preset");
      setSelectedStyleId(String(style.style_id));
      setCustomStyleText("");
    } else if (custom?.text) {
      setStyleSource("custom");
      setCustomStyleText(String(custom.text));
    }
    if (isTitlesApp) {
      setPlatform(String(brief.platform || "douyin"));
      setObjective(String(brief.objective || "click"));
      const nextCount = Number(brief.count || 6);
      if (nextCount === 6) setCount(6);
      setTopic(String(brief.topic || ""));
      setTitleSourceText(String(brief.source_text || ""));
      setTitleKeywordsText(Array.isArray(brief.keywords) ? brief.keywords.map(String).join("，") : "");
      const sourceIds = Array.isArray(payload.source_artifact_version_ids)
        ? payload.source_artifact_version_ids.filter((item): item is string => typeof item === "string")
        : [];
      if (sourceIds[0]) {
        setTitleSourceMode("artifact");
        setTitleSourceVersionId(sourceIds[0]);
      } else if (brief.source_text) {
        setTitleSourceMode("text");
      } else {
        setTitleSourceMode("topic");
      }
    } else {
      setProductOrService(String(brief.offer_name || ""));
      setMarketingGoal(String(brief.marketing_goal || brief.goal || goal || ""));
      setBenefitTagsText(Array.isArray(brief.benefit_tags) ? brief.benefit_tags.map(String).join("，") : "");
      setContentFormat(String(brief.content_format || "oral"));
      setLengthBucket(String(brief.length_bucket || "short_15s"));
    }
    restoredTextRunKey.current = latest.app_run_id;
  }, [appId, isTitlesApp, runs, selectedId, textWorkbenchV2]);

  useEffect(() => {
    if (!textWorkbenchV2 || isTitlesApp || productOrService.trim()) return;
    const brief = projectBriefFromContext(contextSnapshot?.payload);
    const offer = brief.offer;
    if (!offer || typeof offer !== "object") return;
    const offerName = String((offer as Record<string, unknown>).name || "").trim();
    if (offerName) setProductOrService(offerName);
    if (!marketingGoal.trim()) {
      const nextGoal = String(brief.marketing_goal || goal || "").trim();
      if (nextGoal) setMarketingGoal(nextGoal);
    }
  }, [contextSnapshot, goal, isTitlesApp, marketingGoal, productOrService, textWorkbenchV2]);

  useEffect(() => {
    if (!textWorkbenchV2 || !isTitlesApp || !selectedId) {
      setTitleSourceArtifacts([]);
      setTitleSourceVersions([]);
      return;
    }
    let active = true;
    if (sourceRouteBlocked) return;
    void listProjectArtifacts(selectedId)
      .then(async (items) => {
        if (!active) return;
        const eligible = items.filter((item) => item.artifact_type === "copywriting" && item.status !== "archived");
        setTitleSourceArtifacts(eligible);
        const matching = initialSourceArtifactVersionId
          ? (await Promise.all(eligible.map(async (item) => {
              try {
                const versions = await listArtifactVersions(item.artifact_id);
                return versions.some((version) => version.artifact_version_id === initialSourceArtifactVersionId) ? item : null;
              } catch {
                return null;
              }
            }))).find((item): item is typeof eligible[number] => Boolean(item))
          : eligible.find((item) => item.artifact_id === titleSourceArtifactId) || eligible[0];
        if (!active) return;
        if (initialSourceArtifactVersionId && !matching) {
          setTitleSourceArtifactId("");
          setTitleSourceVersionId("");
          setTitleSourceMode("artifact");
          setSourceRouteBlocked(true);
          setError("带入的标题来源版本不存在或已归档；已安全停手，请重新选择来源版本。 ");
          return;
        }
        const preferredArtifact = matching || eligible[0];
        setTitleSourceArtifactId(preferredArtifact?.artifact_id || "");
        if (preferredArtifact) setTitleSourceMode("artifact");
      })
      .catch((loadError) => {
        if (active) setError(loadError instanceof Error ? loadError.message : "标题来源加载失败");
      });
    return () => {
      active = false;
    };
  }, [initialSourceArtifactVersionId, isTitlesApp, selectedId, sourceRouteBlocked, textWorkbenchV2]);

  useEffect(() => {
    if (!textWorkbenchV2 || !isTitlesApp || !titleSourceArtifactId || sourceRouteBlocked) {
      setTitleSourceVersions([]);
      if (!titleSourceArtifactId) setTitleSourceVersionId("");
      return;
    }
    let active = true;
    void listArtifactVersions(titleSourceArtifactId)
      .then((items) => {
        if (!active) return;
        setTitleSourceVersions(items);
        setTitleSourceVersionId((current) => {
          const preferred = items.find((item) => item.artifact_version_id === initialSourceArtifactVersionId)
            || items.find((item) => item.artifact_version_id === current)
            || items[items.length - 1];
          return preferred?.artifact_version_id || "";
        });
      })
      .catch((loadError) => {
        if (active) setError(loadError instanceof Error ? loadError.message : "标题来源版本加载失败");
      });
    return () => {
      active = false;
    };
  }, [initialSourceArtifactVersionId, isTitlesApp, sourceRouteBlocked, textWorkbenchV2, titleSourceArtifactId]);

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
    if (sourceRouteBlocked) return;
    void listProjectArtifacts(selectedId)
      .then(async (items) => {
        if (!active) return;
        const eligible = items.filter((item) => ["copywriting", "selected_title", "title_set"].includes(item.artifact_type) && item.status !== "archived");
        setCarouselSourceArtifacts(eligible);
        const matching = initialSourceArtifactVersionId
          ? (await Promise.all(eligible.map(async (item) => {
              try {
                const versions = await listArtifactVersions(item.artifact_id);
                return versions.some((version) => version.artifact_version_id === initialSourceArtifactVersionId) ? item : null;
              } catch {
                return null;
              }
            }))).find((item): item is typeof eligible[number] => Boolean(item))
          : eligible.find((item) => item.artifact_id === carouselSourceArtifactId)
            || eligible.find((item) => item.current_version_id === carouselSourceVersionId)
            || eligible[0];
        if (!active) return;
        if (initialSourceArtifactVersionId && !matching) {
          setCarouselSourceArtifactId("");
          setCarouselSourceVersionId("");
          setSourceRouteBlocked(true);
          setError("带入的图文来源版本不存在或已归档；已安全停手，请重新选择来源版本。 ");
          return;
        }
        if (!carouselSourceArtifactId || matching?.artifact_id !== carouselSourceArtifactId) setCarouselSourceArtifactId(matching?.artifact_id || "");
      })
      .catch((err) => { if (active) setError(err instanceof Error ? err.message : "来源产物加载失败"); });
    return () => { active = false; };
  }, [initialSourceArtifactVersionId, isCarouselApp, selectedId, sourceRouteBlocked]);

  useEffect(() => {
    if (!isCarouselApp || !carouselSourceArtifactId || sourceRouteBlocked) {
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
  }, [carouselSourceArtifactId, initialSourceArtifactVersionId, isCarouselApp, sourceRouteBlocked]);

  useEffect(() => {
    if (!isCarouselApp || !selectedId || !carouselSourceArtifactId || sourceRouteBlocked) return;
    if (!visibleSourceArtifacts.some((artifact) => artifact.artifact_id === carouselSourceArtifactId)) {
      const next = visibleSourceArtifacts[0];
      setCarouselSourceArtifactId(next?.artifact_id || "");
      setCarouselSourceVersionId("");
    }
  }, [carouselSourceArtifactId, isCarouselApp, selectedId, sourceRouteBlocked, visibleSourceArtifacts]);

  // Project/run restoration and artifact loading resolve independently. If a
  // restored draft clears the selection after artifacts arrive, re-select the
  // best source once the list is available instead of leaving the picker blank.
  useEffect(() => {
    if (!isCarouselApp || !selectedId || carouselSourceArtifactId || sourceRouteBlocked || !carouselSourceArtifacts.length) return;
    const matching = carouselSourceArtifacts.find((artifact) => artifact.current_version_id === initialSourceArtifactVersionId)
      || carouselSourceArtifacts.find((artifact) => artifact.current_version_id === carouselSourceVersionId)
      || carouselSourceArtifacts[0];
    if (matching) setCarouselSourceArtifactId(matching.artifact_id);
  }, [carouselSourceArtifactId, carouselSourceArtifacts, carouselSourceVersionId, initialSourceArtifactVersionId, isCarouselApp, selectedId, sourceRouteBlocked]);

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

  useEffect(() => {
    if (
      !workbenchV2
      || (resultHistoryV1 && (textWorkbenchV2 || carouselWorkbenchV2))
    ) return;
    const artifactIds = runs
      .filter((run) => run.app_id === appId)
      .flatMap((run) => run.output_artifact_ids);
    artifactIds.forEach((artifactId) => {
      if (!latestArtifactVersions[artifactId]) void inspectArtifact(artifactId);
    });
  }, [
    appId,
    latestArtifactVersions,
    resultHistoryV1,
    runs,
    carouselWorkbenchV2,
    textWorkbenchV2,
    workbenchV2,
  ]);

  async function selectProject(project: ContentProject) {
    if ((dirty || contextDirty) && !window.confirm("当前项目有未保存修改（项目资料草稿已保存在本机），确定切换吗？")) return;
    const requestSequence = ++projectRequestSequence.current;
    resetCarouselDraft();
    resetTextAppDraft();
    setSelectedId(project.project_id);
    setName(project.name);
    setGoal(project.primary_goal);
    setMarketingGoal(project.primary_goal);
    setContextPayload(null);
    setContextSnapshot(null);
    setDirty(false);
    setContextDirty(false);
    setProjectDetailsOpen(false);
    setError("");
    try {
      const [nextRuns, snapshot] = await Promise.all([listAppRuns(project.project_id), getCurrentContextSnapshot(project.project_id)]);
      if (requestSequence !== projectRequestSequence.current) return;
      setRuns(nextRuns);
      restoreCarouselDraft(nextRuns);
      setContextPayload(snapshot?.payload || null);
      setContextSnapshot(snapshot);
      if (brandProjectV1 && snapshot?.schema_version === 3) setProjectDetailsOpen(true);
    } catch (loadError) {
      if (requestSequence !== projectRequestSequence.current) return;
      setError(loadError instanceof Error ? loadError.message : "项目上下文加载失败");
    }
  }

  function beginNewProject() {
    if ((dirty || contextDirty) && !window.confirm("当前项目有未保存修改（项目资料草稿已保存在本机），确定新建项目吗？")) return;
    projectRequestSequence.current += 1;
    resetCarouselDraft();
    resetTextAppDraft();
    setSelectedId("");
    setName("");
    setGoal("");
    setMarketingGoal("");
    setRuns([]);
    setContextPayload(null);
    setContextSnapshot(null);
    setDirty(false);
    setContextDirty(false);
    setProjectDetailsOpen(false);
    setError("");
    window.requestAnimationFrame(() => document.getElementById("creation-project-name")?.focus());
  }

  async function persistProject(): Promise<ContentProject> {
    const existingProject = selected;
    const project = selected
      ? await updateContentProject(selected.project_id, { name, primary_goal: goal })
      : await createContentProject({ name, primary_goal: goal });
    setProjects((current) => [project, ...current.filter((item) => item.project_id !== project.project_id)]);
    setSelectedId(project.project_id);
    if (!existingProject) {
      setContextPayload(null);
      setContextSnapshot(null);
      setContextDirty(false);
    }
    setDirty(false);
    setError("");
    return project;
  }

  async function saveDraft() {
    try {
      await persistProject();
    } catch (err) {
      setError(err instanceof Error ? err.message : "项目保存失败");
    }
  }

  async function createProjectFromDialog() {
    const nextName = newProjectName.trim();
    const nextGoal = newProjectGoal.trim();
    if (!nextName || !nextGoal) return;
    setProjectCreateBusy(true);
    try {
      const created = await createContentProject({ name: nextName, primary_goal: nextGoal });
      setProjects((current) => [created, ...current.filter((item) => item.project_id !== created.project_id)]);
      setSelectedId(created.project_id);
      setName(created.name);
      setGoal(created.primary_goal);
      setMarketingGoal(created.primary_goal);
      setRuns([]);
      setContextPayload(null);
      setContextSnapshot(null);
      setDirty(false);
      setContextDirty(false);
      setProjectDetailsOpen(false);
      setProjectCreateOpen(false);
      setNewProjectName("");
      setNewProjectGoal("");
      setError("");
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : "项目创建失败");
    } finally {
      setProjectCreateBusy(false);
    }
  }

  function handleBrandProjectCreated(created: ContentProject) {
    setProjects((current) => [created, ...current.filter((item) => item.project_id !== created.project_id)]);
    setSelectedId(created.project_id);
    setName(created.name);
    setGoal(created.primary_goal);
    setMarketingGoal(created.primary_goal);
    setRuns([]);
    setContextPayload(null);
    setContextSnapshot(null);
    setDirty(false);
    setContextDirty(false);
    setProjectDetailsOpen(true);
    setProjectCreateOpen(false);
    setNewProjectName("");
    setNewProjectGoal("");
    setError("");
    void getCurrentContextSnapshot(created.project_id)
      .then((snapshot) => {
        setContextSnapshot(snapshot);
        setContextPayload(snapshot?.payload || null);
      })
      .catch((loadError) => setError(loadError instanceof Error ? loadError.message : "项目上下文加载失败"));
  }

  async function reloadSelectedProjectContext() {
    if (!selectedId) return;
    const [nextProjects, snapshot] = await Promise.all([
      listContentProjects(),
      getCurrentContextSnapshot(selectedId),
    ]);
    setProjects(nextProjects);
    const nextProject = nextProjects.find((item) => item.project_id === selectedId);
    if (nextProject) {
      setName(nextProject.name);
      setGoal(nextProject.primary_goal);
      setMarketingGoal(nextProject.primary_goal);
    }
    setContextSnapshot(snapshot);
    setContextPayload(snapshot?.payload || null);
    setContextDirty(false);
  }

  async function buildRunInputPayload() {
    if (carouselWorkbenchV2) {
      if (!selected || !contextSnapshot || !supportsApplicationContext(contextSnapshot)) {
        throw new Error("请先保存完整的 v2 项目资料");
      }
      const style = stylePresets.find((item) => item.style_id === selectedStyleId);
      const customText = customStyleText.trim();
      return {
        schema_version: 2,
        app_id: appId,
        input_schema_ref: "douyin-carousel-input.v2",
        project_id: selected.project_id,
        context_snapshot_id: contextSnapshot.context_snapshot_id,
        task_brief: {
          goal: goal.trim(),
          page_count: carouselPageCount,
          template_id: carouselTemplateId,
          asset_refs: carouselAssetRefs,
          asset_descriptions: carouselAssetRefs.map((ref) => carouselAssetDescription(ref, carouselAssetItems)),
          cover_hook: carouselCoverHook.trim(),
          cta: carouselCta.trim(),
          publish_description: carouselPublishDescription.trim(),
          hashtags: carouselHashtagsText
            .split(/[\n,，#]/)
            .map((item) => item.trim())
            .filter(Boolean),
        },
        style_ref: styleSource === "preset" && style
          ? { style_id: style.style_id, version: style.version }
          : null,
        custom_style_reference: styleSource === "custom" && customText
          ? {
              text: customText,
              content_fingerprint: await sha256Fingerprint(customText),
              facts_imported: false,
            }
          : null,
        source_artifact_version_ids: [carouselSourceVersionId.trim()],
      };
    }
    if (textWorkbenchV2) {
      if (!selected || !contextSnapshot || !supportsApplicationContext(contextSnapshot)) {
        throw new Error("请先保存完整的 v2 项目资料");
      }
      const style = stylePresets.find((item) => item.style_id === selectedStyleId);
      const customText = customStyleText.trim();
      const style_ref = styleSource === "preset" && style
        ? { style_id: style.style_id, version: style.version }
        : null;
      const custom_style_reference = styleSource === "custom" && customText
        ? {
            text: customText,
            content_fingerprint: await sha256Fingerprint(customText),
            facts_imported: false,
          }
        : null;
      const common = {
        schema_version: 2,
        app_id: appId,
        project_id: selected.project_id,
        context_snapshot_id: contextSnapshot.context_snapshot_id,
        style_ref,
        custom_style_reference,
      };
      if (isTitlesApp) {
        return {
          ...common,
          input_schema_ref: "viral-titles-input.v2",
          task_brief: {
            platform,
            objective,
            count,
            topic: titleSourceMode === "topic" ? topic.trim() : null,
            source_text: titleSourceMode === "text" ? titleSourceText.trim() : null,
            keywords: titleKeywordsText
              .split(/[\n,，]/)
              .map((item) => item.trim())
              .filter(Boolean),
          },
          source_artifact_version_ids: titleSourceMode === "artifact" && titleSourceVersionId
            ? [titleSourceVersionId]
            : [],
        };
      }
      const context = projectBriefFromContext(contextSnapshot.payload);
      const offer = context.offer && typeof context.offer === "object"
        ? context.offer as Record<string, unknown>
        : {};
      const audience = context.audience && typeof context.audience === "object"
        ? context.audience as Record<string, unknown>
        : {};
      const sellingPoints = Array.isArray(context.selling_points) ? context.selling_points : [];
      const requiredFacts = Array.isArray(context.required_facts) ? context.required_facts : [];
      return {
        ...common,
        input_schema_ref: "marketing-copy-input.v2",
        task_brief: {
          marketing_goal: marketingGoal.trim(),
          offer_name: productOrService.trim() || String(offer.name || ""),
          selling_point_fact_ids: sellingPoints
            .map((item) => item && typeof item === "object" ? String((item as Record<string, unknown>).fact_id || "") : "")
            .filter(Boolean),
          benefit_tags: benefitTagsText
            .split(/[\n,，]/)
            .map((item) => item.trim())
            .filter(Boolean),
          benefit_text: benefitTagsText.trim(),
          audience: String(audience.primary || ""),
          must_include: requiredFacts
            .map((item) => item && typeof item === "object" ? String((item as Record<string, unknown>).text || "") : "")
            .filter(Boolean),
        },
        source_artifact_version_ids: [],
      };
    }
    return isCarouselApp
      ? {
          goal,
          page_count: carouselPageCount,
          source_artifact_version_ids: [carouselSourceVersionId.trim()],
          asset_refs: carouselAssetRefs,
          asset_descriptions: carouselAssetRefs.map((ref) => carouselAssetDescription(ref, carouselAssetItems)),
        }
      : isTitlesApp
        ? { platform, objective, count, topic }
        : { goal, product_or_service: productOrService, content_format: contentFormat, length_bucket: lengthBucket };
  }

  async function startGeneration() {
    try {
      const project = selected && !dirty ? selected : await persistProject();
      const input_payload = await buildRunInputPayload();
      const run = await createAppRun({
        project_id: project.project_id,
        app_id: appId,
        app_version: textWorkbenchV2 || carouselWorkbenchV2 ? "1.1.0" : appVersion,
        input_payload,
        idempotency_key: `${project.project_id}-${Date.now()}`,
        context_snapshot_id: project.current_context_snapshot_id,
      });
      await executeAppRun(run.app_run_id);
      setRuns(await listAppRuns(project.project_id));
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "应用生成启动失败");
    }
  }

  function handleContextSaved(snapshot: ContextSnapshot) {
    setContextSnapshot(snapshot);
    setContextPayload(snapshot.payload);
    setContextDirty(false);
    setProjects((current) => current.map((project) => (
      project.project_id === snapshot.project_id
        ? { ...project, current_context_snapshot_id: snapshot.context_snapshot_id }
        : project
    )));
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
    if ((dirty || contextDirty) && !window.confirm("当前项目有未保存修改。归档后项目将从列表移除，本机项目资料草稿也会删除，确定继续吗？")) return;
    const archivedProjectId = selected.project_id;
    try {
      await archiveContentProject(archivedProjectId);
      window.localStorage.removeItem(`pixelle.app-workbench.context-draft.v2:${archivedProjectId}`);
      setSelectedId("");
      setName("");
      setGoal("");
      setRuns([]);
      setContextPayload(null);
      setContextSnapshot(null);
      setDirty(false);
      setContextDirty(false);
      await reload(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "项目归档失败");
    }
  }

  async function inspectArtifact(artifactId: string) {
    try {
      const versions = await listArtifactVersions(artifactId);
      setArtifactVersionLists((current) => ({ ...current, [artifactId]: versions }));
      const latest = versions[versions.length - 1];
      setVersionCounts((current) => ({ ...current, [artifactId]: versions.length }));
      setLatestArtifactVersions((current) => ({ ...current, [artifactId]: latest || null }));
      const structured = asStructuredDraft(latest?.content);
      setStructuredDrafts((current) => ({ ...current, [artifactId]: structured }));
      setVersionDrafts((current) => ({ ...current, [artifactId]: JSON.stringify(structured || latest?.content || {}, null, 2) }));
      if (latest?.content?.artifact_type === "carousel_page") {
        const text = String(latest.content.text || "");
        const assetRefs = Array.isArray(latest.content.asset_refs)
          ? latest.content.asset_refs.map(String)
          : [];
        setCarouselPageDrafts((current) => ({
          ...current,
          [artifactId]: { text, asset_refs: assetRefs },
        }));
        const imageRef = latest.file_refs.find((fileRef) => fileRef.kind === "image" || fileRef.mime_type === "image/png");
        if (imageRef && typeof imageRef.file_key === "string") {
          const blob = await downloadAppArtifactFile(artifactId, imageRef.file_key);
          const url = URL.createObjectURL(blob);
          setCarouselPreviewUrls((current) => {
            if (current[artifactId]) URL.revokeObjectURL(current[artifactId]);
            return { ...current, [artifactId]: url };
          });
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "版本加载失败");
    }
  }

  async function selectArtifactVersion(artifactId: string, versionId: string) {
    const versions = artifactVersionLists[artifactId] || [];
    const selectedVersion = versions.find((version) => version.artifact_version_id === versionId);
    if (!selectedVersion) return;
    setLatestArtifactVersions((current) => ({ ...current, [artifactId]: selectedVersion }));
    setStructuredDrafts((current) => ({ ...current, [artifactId]: asStructuredDraft(selectedVersion.content) }));
    setVersionDrafts((current) => ({ ...current, [artifactId]: JSON.stringify(asStructuredDraft(selectedVersion.content) || selectedVersion.content || {}, null, 2) }));
    setActionNotice(`已切换到结果 v${selectedVersion.version_number}；交接将使用此固定版本。`);
  }

  async function saveAndRenderCarouselPage(artifactId: string) {
    const draft = carouselPageDrafts[artifactId];
    if (!draft?.text.trim() || !draft.asset_refs.length) {
      setError("页面文案和图片都不能为空");
      return;
    }
    setCarouselPageBusy(artifactId);
    try {
      const response = await retryCarouselPage(artifactId, {
        text: draft.text.trim(),
        asset_refs: draft.asset_refs,
      });
      setLatestArtifactVersions((current) => ({
        ...current,
        [artifactId]: response.page_artifact_version,
        [response.package_artifact_version.artifact_id]: response.package_artifact_version,
      }));
      await inspectArtifact(artifactId);
      setActionNotice("当前页已生成新版本，其他页面保持不变；旧发布包已安全失效。");
      setError("");
    } catch (renderError) {
      setError(renderError instanceof Error ? renderError.message : "当前页重渲染失败");
    } finally {
      setCarouselPageBusy("");
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

  async function downloadCarouselImages(artifactId: string, version: ArtifactVersion) {
    const imageRefs = version.file_refs.filter((fileRef) => fileRef.kind === "image" || fileRef.mime_type === "image/png");
    if (!imageRefs.length) {
      setError("图文包中没有可下载的页面图片");
      return;
    }
    try {
      for (const fileRef of imageRefs) {
        if (typeof fileRef.file_key !== "string") continue;
        const blob = await downloadAppArtifactFile(artifactId, fileRef.file_key);
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = fileRef.file_key;
        anchor.click();
        URL.revokeObjectURL(url);
      }
      setActionNotice(`已准备 ${imageRefs.length} 张图文页面图片。`);
    } catch (downloadError) {
      setError(downloadError instanceof Error ? downloadError.message : "页面图片下载失败");
    }
  }

  async function handoffCarouselToPublishing(artifactId: string, version: ArtifactVersion) {
    if (!selected || !onOpenPublishCenter) return;
    try {
      const packageData = await createPublishPackageV2({
        project_id: selected.project_id,
        artifact_version_ids: [version.artifact_version_id],
      });
      onOpenPublishCenter(packageData.package_id);
      setActionNotice("图文包已固定交给发布中心；平台与账号将在发布中心选择，最终发布仍由你人工确认。");
      setError("");
    } catch (handoffError) {
      setError(handoffError instanceof Error ? handoffError.message : "交给发布中心失败");
    }
  }

  function syncStructuredDraft(artifactId: string, next: StructuredArtifactDraft) {
    setStructuredDrafts((current) => ({ ...current, [artifactId]: next }));
    setVersionDrafts((current) => ({ ...current, [artifactId]: JSON.stringify(next, null, 2) }));
  }

  function updateCopyVariant(artifactId: string, index: number, field: "hook" | "body" | "cta" | "full_text", value: string) {
    const draft = structuredDrafts[artifactId];
    if (!draft?.variants?.[index]) return;
    const variants = [...draft.variants];
    if (field === "full_text") {
      variants[index] = { full_text: value };
    } else {
      const current = { ...variants[index], [field]: value };
      const fullText = `${String(current.hook || "")}${String(current.body || "")}${String(current.cta || "")}`;
      variants[index] = draft.schema_version === 2
        ? { full_text: fullText }
        : {
            ...current,
            full_text: fullText,
            word_count: codePointLength(fullText),
            estimated_seconds: Math.ceil(codePointLength(fullText) / 4),
          };
    }
    syncStructuredDraft(artifactId, { ...draft, variants });
  }

  function updateTitleCandidate(artifactId: string, index: number, value: string) {
    const draft = structuredDrafts[artifactId];
    if (!draft?.candidates?.[index]) return;
    const candidates = [...draft.candidates];
    candidates[index] = draft.schema_version === 2
      ? { title: value }
      : { ...candidates[index], title: value, length: codePointLength(value) };
    syncStructuredDraft(artifactId, { ...draft, candidates });
  }

  function sourceRunForArtifact(artifactId: string) {
    return runs.find((run) => run.output_artifact_ids.includes(artifactId)) || null;
  }

  async function sourceRunForHandoffArtifact(artifactId: string) {
    const direct = sourceRunForArtifact(artifactId);
    if (direct) {
      if (direct.archived_at) {
        throw new Error("来源运行记录不存在，已停止交接；请重新选择有效结果。 ");
      }
      return direct;
    }
    if (!selected) throw new Error("当前项目不存在，无法交接来源产物。 ");
    const summaries = await listProjectArtifacts(selected.project_id);
    const summary = summaries.find((item) => item.artifact_id === artifactId);
    if (!summary || summary.status === "archived" || !summary.source_app_run_id) {
      throw new Error("来源运行记录不存在，已停止交接；请重新选择有效结果。 ");
    }
    const persistedRuns = runs.some((run) => run.app_run_id === summary.source_app_run_id)
      ? runs
      : await listAppRuns(selected.project_id);
    const sourceRun = persistedRuns.find((run) => run.app_run_id === summary.source_app_run_id);
    if (!sourceRun || sourceRun.archived_at) {
      throw new Error("来源运行记录不存在，已停止交接；请重新选择有效结果。 ");
    }
    return sourceRun;
  }

  async function resolveHandoffVersion(artifactId: string) {
    if (!selected) throw new Error("当前项目不存在，无法交接来源产物。 ");
    const summaries = await listProjectArtifacts(selected.project_id);
    const summary = summaries.find((item) => item.artifact_id === artifactId);
    if (!summary || summary.project_id !== selected.project_id || summary.status === "archived") {
      throw new Error("来源产物不存在、已归档或不属于当前项目；已安全停手，请重新选择来源。 ");
    }
    const versions = await listArtifactVersions(artifactId);
    const selectedVersion = latestArtifactVersions[artifactId];
    if (selectedVersion) {
      const matching = versions.find((version) => version.artifact_version_id === selectedVersion.artifact_version_id);
      if (!matching) throw new Error("当前选择的结果版本已不存在，请刷新版本列表后再交接。 ");
      return matching;
    }
    const latest = versions[versions.length - 1];
    if (!latest) throw new Error("暂无可交接的产物版本");
    return latest;
  }

  async function recordResultInteraction(
    artifactId: string,
    eventType: "result.copied" | "result.selected" | "result.liked" | "result.disliked",
    itemIndex: number,
    summary: string,
  ) {
    const sourceRun = sourceRunForArtifact(artifactId);
    const version = latestArtifactVersions[artifactId];
    if (!sourceRun) return;
    await recordAppEvent(sourceRun.app_run_id, eventType, {
      artifact_id: artifactId,
      ...(version ? { artifact_version_id: version.artifact_version_id } : {}),
      item_index: itemIndex,
      summary,
    });
  }

  async function copyResultItem(artifactId: string, itemIndex: number, value: string, summary: string) {
    if (!navigator.clipboard || !value.trim()) {
      setError("当前环境不支持复制此结果");
      return;
    }
    try {
      await navigator.clipboard.writeText(value);
      await recordResultInteraction(artifactId, "result.copied", itemIndex, summary);
      setActionNotice("已复制到剪贴板。");
      setError("");
    } catch (copyError) {
      setError(copyError instanceof Error ? copyError.message : "结果复制失败");
    }
  }

  async function setPrimaryResult(artifactId: string, itemIndex: number) {
    const draft = structuredDrafts[artifactId];
    const sourceRun = sourceRunForArtifact(artifactId);
    if (!draft || !sourceRun || !selected) {
      return;
    }
    try {
      if (draft.artifact_type === "copywriting" && draft.variants?.[itemIndex]) {
        const variants = [...draft.variants];
        const [selectedVariant] = variants.splice(itemIndex, 1);
        const next = { ...draft, variants: [selectedVariant, ...variants] };
        const saved = await appendArtifactVersion(artifactId, next, "edited");
        await inspectArtifact(artifactId);
        await recordAppEvent(sourceRun.app_run_id, "result.selected", {
          artifact_id: artifactId,
          artifact_version_id: saved.artifact_version_id,
          item_index: itemIndex,
          summary: "设为主文案",
        });
        setActionNotice("已设为主文案并保存为新版本。");
      } else if (draft.artifact_type === "title_set" && draft.candidates?.[itemIndex]) {
        const saved = await createSelectedTitleVersion(artifactId, itemIndex, draft, sourceRun);
        setSelectedTitleArtifactIds((current) => ({ ...current, [artifactId]: saved.artifact_id }));
        await recordAppEvent(sourceRun.app_run_id, "result.selected", {
          artifact_id: saved.artifact_id,
          artifact_version_id: saved.artifact_version_id,
          item_index: itemIndex,
          summary: "设为主标题",
        });
        setActionNotice("已生成可继续交付的主标题版本。");
      }
      setError("");
    } catch (selectError) {
      setError(selectError instanceof Error ? selectError.message : "主结果保存失败");
    }
  }

  async function createSelectedTitleVersion(
    artifactId: string,
    itemIndex: number,
    draft: StructuredArtifactDraft,
    sourceRun: AppRun,
    sourceVersionIdOverride?: string,
  ): Promise<ArtifactVersion> {
    if (!selected || draft.artifact_type !== "title_set" || !draft.candidates?.[itemIndex]) {
      throw new Error("请选择一个可用标题");
    }
    const candidate = draft.candidates[itemIndex];
    const sourceTitleVersionId = (
      sourceVersionIdOverride
      || latestArtifactVersions[artifactId]?.artifact_version_id
      || ""
    );
    const key = `${artifactId}:${sourceTitleVersionId || "latest"}:${itemIndex}`;
    const inFlight = selectedTitleVersionInFlight.current.get(key);
    if (inFlight) return inFlight;
    const operation = (async () => {
      if (sourceTitleVersionId) {
        const selectedTitleArtifacts = (await listProjectArtifacts(selected.project_id))
          .filter((artifact) => artifact.artifact_type === "selected_title" && artifact.status !== "archived");
        const existingMatches = await Promise.all(selectedTitleArtifacts.map(async (artifact) => {
          try {
            const history = await listArtifactVersions(artifact.artifact_id);
            return history.find((version) => (
              version.content?.source_title_set_artifact_id === artifactId
                && version.content?.source_title_set_version_id === sourceTitleVersionId
                && Number(version.content?.selected_index) === itemIndex
            )) || null;
          } catch {
            return null;
          }
        }));
        const existing = existingMatches.find((version): version is ArtifactVersion => Boolean(version));
        if (existing) return existing;
      }
      const selectedArtifact = await createProjectArtifact(selected.project_id, {
        artifact_type: "selected_title",
        name: String(candidate.title || "主标题"),
        source_app_run_id: sourceRun.app_run_id,
      });
      const schemaVersion = draft.schema_version === 2 ? 2 : 1;
      return appendArtifactVersion(selectedArtifact.artifact_id, {
        schema_version: schemaVersion,
        artifact_type: "selected_title",
        title: String(candidate.title || ""),
        ...(schemaVersion === 1 && candidate.angle ? { angle: String(candidate.angle) } : {}),
        source_title_set_artifact_id: artifactId,
        source_title_set_version_id: sourceTitleVersionId || null,
        selected_index: itemIndex,
      }, "edited");
    })();
    selectedTitleVersionInFlight.current.set(key, operation);
    try {
      return await operation;
    } finally {
      selectedTitleVersionInFlight.current.delete(key);
    }
  }

  async function resolveHistoryTextItem(
    record: GenerationRecordBlock,
    item: GenerationTextResultItem,
  ) {
    const { artifactId, artifactVersionId, itemIndex } = parseGenerationTextItemId(item.item_id);
    const versions = await listArtifactVersions(artifactId);
    const exactVersion = versions.find(
      (version) => version.artifact_version_id === artifactVersionId,
    );
    const draft = asStructuredDraft(exactVersion?.content);
    const sourceRun = runs.find((run) => run.app_run_id === record.app_run_id);
    if (!exactVersion || !draft || !sourceRun || sourceRun.project_id !== record.project_id) {
      throw new Error("这条历史结果已发生变化，请刷新后重试");
    }
    return { artifactId, artifactVersionId, itemIndex, exactVersion, draft, sourceRun };
  }

  async function copyHistoryTextItem(
    record: GenerationRecordBlock,
    item: GenerationTextResultItem,
  ) {
    if (!navigator.clipboard || !item.text.trim()) {
      throw new Error("当前环境不支持复制此结果");
    }
    const resolved = await resolveHistoryTextItem(record, item);
    await navigator.clipboard.writeText(item.text);
    await recordAppEvent(record.app_run_id, "result.copied", {
      artifact_id: resolved.artifactId,
      artifact_version_id: resolved.artifactVersionId,
      item_index: resolved.itemIndex,
      summary: item.kind === "title" ? "复制标题" : "复制文案",
    });
    setActionNotice("已复制到剪贴板。");
    setError("");
  }

  async function selectHistoryTextItem(
    record: GenerationRecordBlock,
    item: GenerationTextResultItem,
  ) {
    if (!selected || selected.project_id !== record.project_id) {
      throw new Error("当前项目已切换，请刷新后再采用");
    }
    const resolved = await resolveHistoryTextItem(record, item);
    if (
      resolved.draft.artifact_type === "copywriting"
      && resolved.draft.variants?.[resolved.itemIndex]
    ) {
      const variants = [...resolved.draft.variants];
      const [selectedVariant] = variants.splice(resolved.itemIndex, 1);
      const saved = await appendArtifactVersion(
        resolved.artifactId,
        { ...resolved.draft, variants: [selectedVariant, ...variants] },
        "edited",
      );
      await recordAppEvent(record.app_run_id, "result.selected", {
        artifact_id: resolved.artifactId,
        artifact_version_id: saved.artifact_version_id,
        item_index: resolved.itemIndex,
        summary: "设为主文案",
      });
      setActionNotice("已采用这条文案。");
    } else if (
      resolved.draft.artifact_type === "title_set"
      && resolved.draft.candidates?.[resolved.itemIndex]
    ) {
      const saved = await createSelectedTitleVersion(
        resolved.artifactId,
        resolved.itemIndex,
        resolved.draft,
        resolved.sourceRun,
        resolved.artifactVersionId,
      );
      setSelectedTitleArtifactIds((current) => ({ ...current, [resolved.artifactId]: saved.artifact_id }));
      await recordAppEvent(record.app_run_id, "result.selected", {
        artifact_id: saved.artifact_id,
        artifact_version_id: saved.artifact_version_id,
        item_index: resolved.itemIndex,
        summary: "设为主标题",
      });
      setActionNotice("已采用这个标题。");
    } else {
      throw new Error("这条历史结果不支持采用");
    }
    await inspectArtifact(resolved.artifactId);
    setError("");
  }

  async function editHistoryTextItem(
    record: GenerationRecordBlock,
    item: GenerationTextResultItem,
    nextText: string,
  ) {
    const resolved = await resolveHistoryTextItem(record, item);
    let nextDraft: StructuredArtifactDraft;
    if (
      resolved.draft.artifact_type === "copywriting"
      && resolved.draft.variants?.[resolved.itemIndex]
    ) {
      const variants = [...resolved.draft.variants];
      variants[resolved.itemIndex] = resolved.draft.schema_version === 2
        ? { full_text: nextText }
        : {
            ...variants[resolved.itemIndex],
            hook: "",
            body: nextText,
            cta: "",
            full_text: nextText,
            word_count: codePointLength(nextText),
            estimated_seconds: Math.ceil(codePointLength(nextText) / 4),
          };
      nextDraft = { ...resolved.draft, variants };
    } else if (
      resolved.draft.artifact_type === "title_set"
      && resolved.draft.candidates?.[resolved.itemIndex]
    ) {
      const candidates = [...resolved.draft.candidates];
      candidates[resolved.itemIndex] = resolved.draft.schema_version === 2
        ? { title: nextText }
        : {
            ...candidates[resolved.itemIndex],
            title: nextText,
            length: codePointLength(nextText),
          };
      nextDraft = { ...resolved.draft, candidates };
    } else {
      throw new Error("这条历史结果不支持编辑");
    }
    const saved = await appendArtifactVersion(resolved.artifactId, nextDraft, "edited");
    await recordAppEvent(record.app_run_id, "result.edited", {
      artifact_id: resolved.artifactId,
      artifact_version_id: saved.artifact_version_id,
      item_index: resolved.itemIndex,
      summary: item.kind === "title" ? "编辑标题" : "编辑文案",
    });
    await inspectArtifact(resolved.artifactId);
    setActionNotice("修改已保存，原版本仍会保留。");
    setError("");
  }

  async function publishHistoryMedia(
    record: GenerationRecordBlock,
    item: GenerationCarouselResultItem | GenerationVideoResultItem,
  ) {
    if (!selected || selected.project_id !== record.project_id || !onOpenPublishCenter) {
      throw new Error("当前项目无法交给发布中心");
    }
    const versionIds = item.artifact_version_ids;
    if (!versionIds.length) {
      throw new Error("成品资料不完整，暂时无法交给发布中心");
    }
    const packageData = await createPublishPackageV2({
      project_id: selected.project_id,
      artifact_version_ids: versionIds,
    });
    onOpenPublishCenter(packageData.package_id);
    setActionNotice(
      "成品已固定交给发布中心；平台与账号将在发布中心选择，最终发布仍由你人工确认。",
    );
    setError("");
  }

  async function sendResultFeedback(
    artifactId: string,
    itemIndex: number,
    liked: boolean,
  ) {
    try {
      await recordResultInteraction(
        artifactId,
        liked ? "result.liked" : "result.disliked",
        itemIndex,
        liked ? "用户喜欢" : "用户不喜欢",
      );
      setActionNotice(liked ? "已记录喜欢。" : "已记录不喜欢。");
      setError("");
    } catch (feedbackError) {
      setError(feedbackError instanceof Error ? feedbackError.message : "反馈记录失败");
    }
  }

  async function saveEditedArtifact(artifactId: string) {
    try {
      const content = JSON.parse(versionDrafts[artifactId] || "{}");
      const saved = await appendArtifactVersion(artifactId, content, "edited");
      const sourceRun = runs.find((run) => run.output_artifact_ids.includes(artifactId));
      if (sourceRun) {
        await recordAppEvent(sourceRun.app_run_id, "result.edited", {
          artifact_id: artifactId,
          artifact_version_id: saved.artifact_version_id,
          summary: "保存编辑版本",
        });
      }
      await inspectArtifact(artifactId);
      setActionNotice("已保存为新的结果版本，旧版本保持不变。");
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "编辑版本保存失败");
    }
  }

  async function handoffToTitles(run: AppRun, artifactId: string) {
    if (!selected) return;
    try {
      const latest = await resolveHandoffVersion(artifactId);
      if (textWorkbenchV2) {
        await recordAppEvent(run.app_run_id, "handoff.started", {
          artifact_id: artifactId,
          artifact_version_id: latest.artifact_version_id,
          target_app_id: "builtin.viral-titles",
          summary: "交给爆款标题",
        });
        await createArtifactHandoff({
          project_id: selected.project_id,
          source_artifact_id: artifactId,
          source_artifact_version_id: latest.artifact_version_id,
          target_app_id: "builtin.viral-titles",
          target_app_version: "1.1.0",
          artifact_version_ids: [latest.artifact_version_id],
          mapping_version: 2,
        });
        await recordAppEvent(run.app_run_id, "handoff.completed", {
          artifact_id: artifactId,
          artifact_version_id: latest.artifact_version_id,
          target_app_id: "builtin.viral-titles",
          summary: "已带入标题工作台",
        });
        onOpenApp?.("builtin.viral-titles", latest.artifact_version_id);
        setActionNotice("文案版本已固定带入爆款标题；确认标题输入后再生成。");
        setError("");
        return;
      }
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
    if (!onOpenApp || !selected) return;
    try {
      const latest = await resolveHandoffVersion(artifactId);
      const sourceRun = await sourceRunForHandoffArtifact(artifactId);
      if (sourceRun) {
        await createArtifactHandoff({
          project_id: selected.project_id,
          source_artifact_id: artifactId,
          source_artifact_version_id: latest.artifact_version_id,
          target_app_id: "builtin.douyin-carousel",
          target_app_version: "1.1.0",
          artifact_version_ids: [latest.artifact_version_id],
          mapping_version: 2,
        });
        await recordAppEvent(sourceRun.app_run_id, "handoff.completed", {
          artifact_id: artifactId,
          artifact_version_id: latest.artifact_version_id,
          target_app_id: "builtin.douyin-carousel",
          summary: "文案已固定带入抖音图文",
        });
      }
      onOpenApp("builtin.douyin-carousel", latest.artifact_version_id);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "打开抖音图文失败");
    }
  }

  async function openDigitalHumanFromArtifact(artifactId: string) {
    if (!onOpenApp || !selected) return;
    try {
      const latest = await resolveHandoffVersion(artifactId);
      const sourceRun = await sourceRunForHandoffArtifact(artifactId);
      if (sourceRun) {
        await createArtifactHandoff({
          project_id: selected.project_id,
          source_artifact_id: artifactId,
          source_artifact_version_id: latest.artifact_version_id,
          target_app_id: "builtin.digital-human-video",
          target_app_version: "1.1.0",
          artifact_version_ids: [latest.artifact_version_id],
          mapping_version: 2,
        });
        await recordAppEvent(sourceRun.app_run_id, "handoff.completed", {
          artifact_id: artifactId,
          artifact_version_id: latest.artifact_version_id,
          target_app_id: "builtin.digital-human-video",
          summary: "文案已固定带入数字人",
        });
      }
      onOpenApp("builtin.digital-human-video", latest.artifact_version_id);
      setActionNotice("文案版本已固定带入数字人口播；请补充形象与交付字段后再生成。 ");
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "打开数字人口播失败");
    }
  }

  const appCopy = APP_COPY[appId] || APP_COPY["builtin.marketing-copy"];
  const generationLabel = isCarouselApp ? "生成抖音图文" : isTitlesApp ? "生成爆款标题" : "生成营销文案";
  const textStyleMissing = textWorkbenchV2 && (
    styleSource === "preset" ? !selectedStyleId : !customStyleText.trim()
  );
  const carouselStyleMissing = carouselWorkbenchV2 && (
    styleSource === "preset" ? !selectedStyleId : !customStyleText.trim()
  );
  const textContextMissing = textWorkbenchV2 && !supportsApplicationContext(contextSnapshot);
  const carouselContextMissing = carouselWorkbenchV2 && !supportsApplicationContext(contextSnapshot);
  const titleV2SourceMissing = textWorkbenchV2 && isTitlesApp && (
    titleSourceMode === "artifact"
      ? !titleSourceVersionId
      : titleSourceMode === "topic"
        ? !topic.trim()
        : !titleSourceText.trim()
  );
  const appInputMissing = isCarouselApp
    ? !selected
      || !carouselSourceVersionId.trim()
      || carouselAssetRefs.length === 0
      || carouselStyleMissing
      || carouselContextMissing
    : isTitlesApp
      ? (textWorkbenchV2 ? titleV2SourceMissing || textStyleMissing || textContextMissing : !topic.trim())
      : textWorkbenchV2
        ? !(marketingGoal.trim() && (productOrService.trim() || String((projectBriefFromContext(contextSnapshot?.payload).offer as Record<string, unknown> | undefined)?.name || "").trim()))
          || textStyleMissing || textContextMissing
        : !productOrService.trim();
  const relevantRuns = workbenchV2 ? runs.filter((run) => run.app_id === appId) : runs;
  const latestRun = [...relevantRuns]
    .sort((left, right) => right.updated_at.localeCompare(left.updated_at))[0] || null;
  const visibleRuns = workbenchV2
    ? (latestRun ? [latestRun] : [])
    : relevantRuns;
  const resultState: WorkbenchViewState = !latestRun
    ? "empty"
    : latestRun.state === "failed" || latestRun.state === "cancelled"
      ? "failed"
      : latestRun.state === "needs_review"
        ? "needs_review"
        : latestRun.state === "completed"
          ? "saved"
          : "running";
  const legacyRunPanel = selected ? (
    <div className="creation-workbench-results">
      <List size="small" dataSource={visibleRuns} locale={{ emptyText: workbenchV2 ? "当前应用暂无运行" : "暂无运行" }} renderItem={(run) => <List.Item actions={run.state !== "completed" && run.state !== "cancelled" ? [<Button size="small" onClick={() => void actOnRun(run)}>{run.state === "needs_review" ? "确认完成" : run.state === "queued" || run.state === "running" ? "取消" : run.state === "failed" ? "重试" : "执行"}</Button>] : undefined}>
        <Space orientation="vertical" size={2} style={{ width: "100%" }}>
          {!workbenchV2 ? <Space size="small"><Typography.Text>{appCopy.name}</Typography.Text><Tag color={run.state === "failed" ? "error" : run.state === "completed" ? "success" : run.state === "cancelled" ? "default" : "processing"}>{stateLabels[run.state]}</Tag></Space> : null}
          {run.state === "failed" ? <Alert type="error" showIcon message={CAROUSEL_ERROR_COPY[run.error_code || ""] || "本次生成失败，输入仍保留，可检查后按原输入重试。"} /> : null}
          {run.output_artifact_ids.map((artifactId) => {
            const structured = structuredDrafts[artifactId];
            const latestVersion = latestArtifactVersions[artifactId];
            const isCarouselPackage = latestVersion?.content?.artifact_type === "carousel_package";
            const isCarouselPlan = latestVersion?.content?.artifact_type === "carousel_plan";
            const isCarouselPage = latestVersion?.content?.artifact_type === "carousel_page";
            const isCarouselArtifact = isCarouselPackage || isCarouselPlan || isCarouselPage;
            const carouselPageAssetRef = isCarouselPage
              ? carouselPageDrafts[artifactId]?.asset_refs?.[0] || ""
              : "";
            const carouselPageAssetOptions = Array.from(new Set(
              [...carouselAssetRefs, carouselPageAssetRef].filter(Boolean),
            )).map((ref) => {
              const { assetId, revisionId } = parseCarouselAssetRef(ref);
              const asset = carouselAssetItems.find((item) => (item.asset_id || item.resource_id) === assetId);
              return {
                value: ref,
                label: asset?.name || (revisionId ? "已选项目图片" : "项目图片"),
              };
            });
            const validationFacts = latestVersion?.content?.validation_facts;
            const validationInput = validationFacts && typeof validationFacts === "object"
              ? (validationFacts as Record<string, unknown>).input
              : null;
            const styleRef = validationInput && typeof validationInput === "object"
              ? (validationInput as Record<string, unknown>).style_ref
              : null;
            const styleId = styleRef && typeof styleRef === "object"
              ? String((styleRef as Record<string, unknown>).style_id || "")
              : "";
            const styleName = stylePresets.find((item) => item.style_id === styleId)?.name || styleId;
            const missingFacts = Array.isArray(latestVersion?.content?.missing_facts) ? latestVersion?.content?.missing_facts : [];
            const riskFlags = Array.isArray(latestVersion?.content?.risk_flags) ? latestVersion?.content?.risk_flags : [];
            return <Space key={artifactId} orientation="vertical" size="small" style={{ width: "100%" }}>
              <div className="creation-result-toolbar">
                <div className="creation-result-title">
                  <Typography.Text strong>{isCarouselPackage ? (workbenchV2 ? "本次图文" : "图文成品") : isCarouselPlan ? "分页内容" : isCarouselPage ? `第 ${String(latestVersion?.content?.page_index || "")} 页` : "本次内容"}</Typography.Text>
                  {styleName ? <Tag color="purple">{styleName}</Tag> : null}
                </div>
                <div className="creation-result-actions">
                  {!workbenchV2 ? (
                    <VersionSwitcher
                      versions={artifactVersionLists[artifactId] || []}
                      value={latestVersion?.artifact_version_id}
                      onChange={(versionId) => void selectArtifactVersion(artifactId, versionId)}
                    />
                  ) : null}
                  {isCarouselPackage && latestVersion ? (
                    <HandoffActions actions={[
                      ...(onOpenPublishCenter ? [{ key: "publish", label: "交给发布中心", primary: true, onClick: () => void handoffCarouselToPublishing(artifactId, latestVersion) }] : []),
                      { key: "images", label: "下载图片", onClick: () => void downloadCarouselImages(artifactId, latestVersion) },
                      { key: "zip", label: "下载全部", onClick: () => void downloadCarouselPackage(artifactId, latestVersion) },
                      { key: "copy", label: "复制发布文案", onClick: () => void copyCarouselPublishCopy(latestVersion) },
                      ...(!workbenchV2 ? [{ key: "versions", label: "查看版本", onClick: () => void inspectArtifact(artifactId) }] : []),
                    ]} />
                  ) : !workbenchV2 ? (
                    <HandoffActions actions={[
                      { key: "versions", label: "查看版本", onClick: () => void inspectArtifact(artifactId) },
                    ]} />
                  ) : null}
                  {run.app_id === "builtin.marketing-copy" ? <HandoffActions actions={[
                    { key: "titles", label: "交给爆款标题", primary: true, onClick: () => void handoffToTitles(run, artifactId) },
                    ...(onOpenApp ? [{ key: "carousel", label: "制作抖音图文", onClick: () => void openCarouselFromArtifact(artifactId) }, { key: "digital-human", label: "制作数字人", onClick: () => void openDigitalHumanFromArtifact(artifactId) }] : []),
                  ]} /> : null}
                  {run.app_id === "builtin.viral-titles" && selectedTitleArtifactIds[artifactId] && onOpenApp ? <HandoffActions actions={[
                    { key: "carousel", label: "制作抖音图文", onClick: () => void openCarouselFromArtifact(selectedTitleArtifactIds[artifactId]) },
                    { key: "digital-human", label: "制作数字人", onClick: () => void openDigitalHumanFromArtifact(selectedTitleArtifactIds[artifactId]) },
                  ]} /> : null}
                </div>
              </div>
              {missingFacts.length || riskFlags.length ? <details className="creation-result-note">
                <summary>内容检查（可选）</summary>
                {missingFacts.length ? <div>
                  <Typography.Text strong>想更准确时可以补充</Typography.Text>
                  <Typography.Paragraph type="secondary">{missingFacts.map((item) => {
                    if (!item || typeof item !== "object") return String(item);
                    const fact = item as Record<string, unknown>;
                    return [fact.field, fact.reason].filter(Boolean).map(String).join("：");
                  }).filter(Boolean).join("；")}</Typography.Paragraph>
                </div> : null}
                {riskFlags.length ? <div>
                  <Typography.Text strong>发布前建议看一眼</Typography.Text>
                  <Typography.Paragraph type="secondary">{riskFlags.map((item) => {
                    if (!item || typeof item !== "object") return String(item);
                    const risk = item as Record<string, unknown>;
                    return [risk.code, risk.reason].filter(Boolean).map(String).join("：");
                  }).filter(Boolean).join("；")}</Typography.Paragraph>
                </div> : null}
              </details> : null}
              {structured?.artifact_type === "copywriting" && structured.variants?.map((variant, index) => workbenchV2 ? (
                <Card
                  key={`variant-${index}`}
                  size="small"
                  className={`creation-result-option-card creation-result-option-card--compact${index === 0 ? " is-selected" : ""}`}
                  title={<Space wrap><span>文案 {index + 1}</span>{index === 0 ? <Tag color="purple">已选</Tag> : null}</Space>}
                >
                  <Typography.Paragraph className="creation-result-copy-preview">
                    {String(variant.full_text || [variant.hook, variant.body, variant.cta].filter(Boolean).join(""))}
                  </Typography.Paragraph>
                  <div className="creation-result-option-footer">
                    <Typography.Text type="secondary">可直接复制、修改或采用</Typography.Text>
                    <HandoffActions actions={[
                      { key: "select", label: index === 0 ? "已选用" : "选用这版", primary: index !== 0, disabled: index === 0, onClick: () => void setPrimaryResult(artifactId, index) },
                      { key: "copy", label: "复制文案", onClick: () => void copyResultItem(artifactId, index, String(variant.full_text || ""), `文案版本 ${index + 1}`) },
                    ]} />
                  </div>
                  <details className="creation-result-inline-editor">
                    <summary>修改这版</summary>
                    <Space orientation="vertical" style={{ width: "100%" }}>
                      <Input.TextArea
                        aria-label={`文案${index + 1}`}
                        value={String(variant.full_text || "")}
                        rows={5}
                        maxLength={5000}
                        showCount
                        onChange={(event) => updateCopyVariant(artifactId, index, "full_text", event.target.value)}
                      />
                    </Space>
                  </details>
                </Card>
              ) : (
                <Card key={`variant-${index}`} size="small" className="creation-result-option-card" title={<Space wrap><span>文案方案 {index + 1}</span>{variant.angle ? <Tag>{String(variant.angle)}</Tag> : null}{index === 0 ? <Tag color="purple">正在使用</Tag> : null}</Space>}>
                  <Space orientation="vertical" style={{ width: "100%" }}>
                    <Input aria-label={`文案版本${index + 1}开头`} value={String(variant.hook || "")} onChange={(event) => updateCopyVariant(artifactId, index, "hook", event.target.value)} />
                    <Input.TextArea aria-label={`文案版本${index + 1}正文`} value={String(variant.body || "")} rows={3} onChange={(event) => updateCopyVariant(artifactId, index, "body", event.target.value)} />
                    <Input aria-label={`文案版本${index + 1}行动号召`} value={String(variant.cta || "")} onChange={(event) => updateCopyVariant(artifactId, index, "cta", event.target.value)} />
                    <Typography.Text type="secondary">合成正文：{String(variant.full_text || "")}（{String(variant.word_count || 0)} 字，约 {String(variant.estimated_seconds || 0)} 秒）</Typography.Text>
                    <HandoffActions actions={[
                      { key: "select", label: index === 0 ? "当前使用" : "使用这版", primary: index !== 0, disabled: index === 0, onClick: () => void setPrimaryResult(artifactId, index) },
                      { key: "copy", label: "复制文案", onClick: () => void copyResultItem(artifactId, index, String(variant.full_text || ""), `文案版本 ${index + 1}`) },
                      { key: "like", label: "这个不错", onClick: () => void sendResultFeedback(artifactId, index, true) },
                      { key: "dislike", label: "不太合适", onClick: () => void sendResultFeedback(artifactId, index, false) },
                    ]} />
                  </Space>
                </Card>
              ))}
              {structured?.artifact_type === "title_set" && structured.candidates?.map((candidate, index) => <Card key={`candidate-${index}`} size="small" className="creation-result-option-card" title={`标题 ${index + 1}`}>
                <Space orientation="vertical" style={{ width: "100%" }}>
                  <Input aria-label={`标题候选${index + 1}`} value={String(candidate.title || "")} onChange={(event) => updateTitleCandidate(artifactId, index, event.target.value)} addonAfter={`${codePointLength(String(candidate.title || ""))} 字`} />
                  <HandoffActions actions={[
                    { key: "select", label: "使用这个标题", primary: true, onClick: () => void setPrimaryResult(artifactId, index) },
                    { key: "copy", label: "复制标题", onClick: () => void copyResultItem(artifactId, index, String(candidate.title || ""), `标题候选 ${index + 1}`) },
                  ]} />
                </Space>
              </Card>)}
              {isCarouselPlan && latestVersion ? (
                <div className="carousel-plan-result" aria-label="图文分页计划">
                  {(Array.isArray(latestVersion.content?.page_outline) ? latestVersion.content.page_outline : []).map((item, index) => {
                    const page = item && typeof item === "object" ? item as Record<string, unknown> : {};
                    return <div key={`outline-${index}`}><strong>第 {String(page.page_index || index + 1)} 页</strong><span>{String(page.purpose || "内容页")}</span></div>;
                  })}
                </div>
              ) : null}
              {isCarouselPage && latestVersion ? (
                <Card size="small" className="carousel-page-result-card">
                  <div className="carousel-page-result">
                    <div className="carousel-page-preview">
                      {carouselPreviewUrls[artifactId]
                        ? <img src={carouselPreviewUrls[artifactId]} alt={`图文第 ${String(latestVersion.content?.page_index || "")} 页预览`} />
                        : <Typography.Text type="secondary">正在载入真实页面预览…</Typography.Text>}
                    </div>
                    <Space orientation="vertical" size="small" style={{ width: "100%" }}>
                      <Input.TextArea
                        aria-label={`图文第${String(latestVersion.content?.page_index || "")}页文案`}
                        rows={5}
                        maxLength={480}
                        showCount
                        value={carouselPageDrafts[artifactId]?.text || ""}
                        onChange={(event) => setCarouselPageDrafts((current) => ({
                          ...current,
                          [artifactId]: {
                            text: event.target.value,
                            asset_refs: current[artifactId]?.asset_refs || [],
                          },
                        }))}
                      />
                      <Select
                        aria-label={`图文第${String(latestVersion.content?.page_index || "")}页图片`}
                        value={carouselPageAssetRef || undefined}
                        options={carouselPageAssetOptions}
                        onChange={(value) => setCarouselPageDrafts((current) => ({
                          ...current,
                          [artifactId]: {
                            text: current[artifactId]?.text || "",
                            asset_refs: [value],
                          },
                        }))}
                      />
                      <Button
                        type="primary"
                        loading={carouselPageBusy === artifactId}
                        onClick={() => void saveAndRenderCarouselPage(artifactId)}
                      >
                        保存本页
                      </Button>
                    </Space>
                  </div>
                </Card>
              ) : null}
              {structured && versionDrafts[artifactId] !== undefined ? (
                <Button size="small" onClick={() => void saveEditedArtifact(artifactId)}>{workbenchV2 ? "保存修改" : "保存本次编辑"}</Button>
              ) : null}
              {!structured && !isCarouselArtifact && versionDrafts[artifactId] !== undefined ? <><Input.TextArea aria-label={`产物 ${artifactId} 编辑内容`} value={versionDrafts[artifactId]} rows={5} onChange={(event) => setVersionDrafts((current) => ({ ...current, [artifactId]: event.target.value }))} /><Button size="small" onClick={() => void saveEditedArtifact(artifactId)}>保存编辑版本</Button></> : null}
            </Space>;
          })}
        </Space>
      </List.Item>} />
    </div>
  ) : (
    <div className="creation-workbench-empty">
      <Typography.Title level={4}>先选择或新建项目</Typography.Title>
      <Typography.Paragraph type="secondary">项目确定后，这里会显示生成进度、内容结果和下一步操作。</Typography.Paragraph>
    </div>
  );
  const historyRefreshKey = runs
    .map((run) => (
      `${run.app_run_id}:${run.state}:${run.state_version}:${run.updated_at}:${run.output_artifact_ids.join(",")}`
    ))
    .join("|");
  const runPanel = resultHistoryV1
    && (textWorkbenchV2 || carouselWorkbenchV2)
    && selected ? (
    <ProjectGenerationHistory
      projectId={selected.project_id}
      appId={appId as GenerationRecordBlock["app_id"]}
      refreshKey={historyRefreshKey}
      onCopy={copyHistoryTextItem}
      onSelect={selectHistoryTextItem}
      onEdit={editHistoryTextItem}
      onRunAction={async (record) => {
        const run = runs.find((item) => item.app_run_id === record.app_run_id);
        if (!run) throw new Error("这次生成状态已更新，请刷新后重试");
        await actOnRun(run);
      }}
      onPublish={onOpenPublishCenter ? publishHistoryMedia : undefined}
    />
  ) : legacyRunPanel;
  const primaryActions = (
    <div className="creation-primary-actions">
      <Button block size="large" type="primary" disabled={!name.trim() || !goal.trim() || appInputMissing || contextDirty} onClick={() => void startGeneration()}>{generationLabel}</Button>
      {!workbenchV2 ? <details className="creation-project-actions">
        <summary>项目操作</summary>
        <Space wrap size="small">
          <Button size="small" disabled={!name.trim() || !goal.trim()} onClick={() => void saveDraft()}>保存项目</Button>
          <Button size="small" danger disabled={!selected} onClick={() => void archiveSelected()}>归档项目</Button>
        </Space>
      </details> : null}
    </div>
  );
  const workspace = (
    <Card title={focused ? "开始创作" : "我的创作"} className="creation-workspace">
      {error && <Alert type="error" showIcon message={error} />}
      {actionNotice && <Alert type="success" showIcon closable message={actionNotice} onClose={() => setActionNotice("")} />}
      <ProjectContextSelector
        projects={projects}
        value={selectedId}
        onChange={(projectId) => {
          const project = projects.find((item) => item.project_id === projectId);
          if (project) void selectProject(project);
        }}
        onCreate={() => {
          if (!workbenchV2) {
            beginNewProject();
            return;
          }
          setNewProjectName("");
          setNewProjectGoal("");
          setProjectCreateOpen(true);
        }}
        onEdit={() => setProjectDetailsOpen(true)}
      />
      <Card size="small" title={focused ? undefined : selected ? "本次要做什么" : "新建创作项目"} className="creation-input-card">
          <Space orientation="vertical" size="middle" className="creation-input-stack">
            {selected && !workbenchV2 ? (
              <details className="creation-project-disclosure">
                <summary>
                  <span>
                    <Typography.Text strong>{selected.name}</Typography.Text>
                    <Typography.Text type="secondary">{goal || "还没有填写本次目标"}</Typography.Text>
                  </span>
                  <Typography.Text type="secondary">编辑</Typography.Text>
                </summary>
                <div className="creation-project-disclosure__body">
                  <Input id="creation-project-name" value={name} placeholder="项目名称" onChange={(event) => { setName(event.target.value); setDirty(true); }} />
                  <Input.TextArea value={goal} placeholder="本次营销目标" rows={3} onChange={(event) => { setGoal(event.target.value); setDirty(true); }} />
                </div>
              </details>
            ) : !selected && !workbenchV2 ? (
              <>
                <Input id="creation-project-name" value={name} placeholder="项目名称" onChange={(event) => { setName(event.target.value); setDirty(true); }} />
                <Input.TextArea value={goal} placeholder="本次营销目标" rows={3} onChange={(event) => { setGoal(event.target.value); setDirty(true); }} />
              </>
            ) : null}
            {workbenchV2 && brandProjectV1 && selected ? (
              <BrandProjectContextPanel
                project={selected}
                snapshot={contextSnapshot}
                open={contextSnapshot?.schema_version === 3 && projectDetailsOpen}
                onOpen={() => setProjectDetailsOpen(true)}
                onClose={() => setProjectDetailsOpen(false)}
                onSaved={handleContextSaved}
                onReload={reloadSelectedProjectContext}
                onDirtyChange={setContextDirty}
              />
            ) : workbenchV2 && selected && contextSnapshot?.schema_version !== 2 ? (
              <ProjectBriefDisclosure ready={false}>
                <ProjectBriefEditor
                  projectId={selected.project_id}
                  projectName={selected.name}
                  snapshot={contextSnapshot}
                  onSaved={handleContextSaved}
                  onDirtyChange={setContextDirty}
                />
              </ProjectBriefDisclosure>
            ) : null}
            {workbenchV2 && selected && contextSnapshot?.schema_version === 2 && projectDetailsOpen ? (
              <section className="project-details-editor" aria-label="编辑当前项目信息">
                <div className="project-details-editor__heading">
                  <Typography.Text strong>编辑项目信息</Typography.Text>
                  <Button size="small" onClick={() => setProjectDetailsOpen(false)}>完成</Button>
                </div>
                <ProjectBriefEditor
                  projectId={selected.project_id}
                  projectName={selected.name}
                  snapshot={contextSnapshot}
                  onSaved={handleContextSaved}
                  onDirtyChange={setContextDirty}
                />
              </section>
            ) : null}
            {isCarouselApp ? (
              <>
                <label className="creation-select-field">
                  <span>本次使用哪段内容？</span>
                  <Select
                    aria-label="本次使用内容"
                    placeholder="选择已有文案或标题"
                    value={carouselSourceArtifactId || undefined}
                    options={visibleSourceArtifacts.map((artifact) => {
                      const currentVersion = carouselSourceVersions.find((version) => version.artifact_id === artifact.artifact_id);
                      const preview = currentVersion ? truncateSourceText(sourceContentPreview(currentVersion.content), 32) : "";
                      return {
                        value: artifact.artifact_id,
                        label: preview || artifact.name,
                      };
                    })}
                    onChange={(value) => { setSourceRouteBlocked(false); setCarouselSourceArtifactId(value); setCarouselSourceVersionId(""); }}
                    notFoundContent="当前项目还没有可用文案或标题"
                  />
                </label>
                {selectedSourceVersion ? <div className="creation-source-summary" aria-label="图文来源摘要">
                  <Typography.Text type="secondary">已带入：{truncateSourceText(sourceContentPreview(selectedSourceVersion.content), 96)}</Typography.Text>
                </div> : null}
                {initialSourceArtifactVersionId && carouselSourceVersionId === initialSourceArtifactVersionId ? (
                  <Alert
                    type={carouselSourceVersionUpdateAvailable ? "warning" : "info"}
                    showIcon
                    message={carouselSourceVersionUpdateAvailable ? "这段内容后来有过更新" : "已带入上一步选择的内容"}
                    description={carouselSourceVersionUpdateAvailable
                      ? "本次仍使用你刚才确认的内容；重新选择即可使用最新内容。"
                      : "系统会保存本次使用的内容，后续编辑不会影响这次图文。"}
                  />
                ) : null}
                {carouselWorkbenchV2 ? (
                  <>
                    <Input
                      aria-label="图文封面钩子"
                      value={carouselCoverHook}
                      placeholder="封面主标题（可选，不填会自动生成）"
                      maxLength={80}
                      showCount
                      onChange={(event) => setCarouselCoverHook(event.target.value)}
                    />
                  </>
                ) : null}
                <div className="creation-carousel-assets" aria-label="图文图片资产">
                  <Space wrap>
                    {carouselAssetRefs.map((ref) => {
                      const { assetId, revisionId } = parseCarouselAssetRef(ref);
                      const asset = carouselAssetItems.find((item) => (item.asset_id || item.resource_id) === assetId);
                      return <Tag key={ref} closable onClose={() => setCarouselAssetRefs((current) => current.filter((item) => item !== ref))}>{asset?.name || (revisionId ? "已选项目图片" : "已选图片")}</Tag>;
                    })}
                    <Button type="dashed" onClick={() => setAssetPickerOpen(true)}>选择图片资产</Button>
                  </Space>
                  {!carouselAssetRefs.length ? <Typography.Text type="secondary">请选择 1–20 张企业图片。</Typography.Text> : null}
                </div>
                {!carouselWorkbenchV2 ? <label className="creation-select-field">
                  <span>图文页数</span>
                  <Select aria-label="图文页数" value={carouselPageCount} options={[3, 5, 8].map((value) => ({ value, label: `${value} 页` }))} onChange={setCarouselPageCount} />
                </label> : null}
                {carouselWorkbenchV2 ? (
                  <details className="carousel-more-settings">
                    <summary>更多配置</summary>
                    <Space orientation="vertical" size="middle" style={{ width: "100%" }}>
                      <div className="creation-select-grid">
                        <label className="creation-select-field">
                          <span>图文页数</span>
                          <Select aria-label="图文页数" value={carouselPageCount} options={[3, 5, 8].map((value) => ({ value, label: `${value} 页` }))} onChange={setCarouselPageCount} />
                        </label>
                        <label className="creation-select-field">
                          <span>页面样式</span>
                          <Select
                            aria-label="图文模板"
                            value={carouselTemplateId}
                            options={[
                              { value: "template:clean-01", label: "简洁信息卡 · 3:4" },
                              { value: "template:cover-focus-01", label: "封面聚焦 · 3:4" },
                              { value: "template:action-card-01", label: "行动引导 · 3:4" },
                            ]}
                            onChange={setCarouselTemplateId}
                          />
                        </label>
                      </div>
                      <label className="creation-select-field">
                        <span>查找更早内容</span>
                        <Select
                          aria-label="图文来源时间筛选"
                          value={carouselSourceDateRange}
                          options={CAROUSEL_SOURCE_DATE_OPTIONS}
                          onChange={setCarouselSourceDateRange}
                        />
                      </label>
                      <Input
                        aria-label="图文行动号召"
                        value={carouselCta}
                        placeholder="例如：收藏这份清单，到店前再看一遍"
                        maxLength={120}
                        showCount
                        onChange={(event) => setCarouselCta(event.target.value)}
                      />
                      <Input.TextArea
                        aria-label="图文发布描述"
                        value={carouselPublishDescription}
                        placeholder="可选：发布描述；留空时从来源内容提取"
                        rows={3}
                        maxLength={2000}
                        showCount
                        onChange={(event) => setCarouselPublishDescription(event.target.value)}
                      />
                      <Input
                        aria-label="图文话题"
                        value={carouselHashtagsText}
                        placeholder="可选：咖啡，门店探店"
                        maxLength={300}
                        onChange={(event) => setCarouselHashtagsText(event.target.value)}
                      />
                    </Space>
                  </details>
                ) : null}
                <Typography.Text type="secondary">图片来自企业资产库，生成后可以逐页调整文案和图片。</Typography.Text>
              </>
            ) : isTitlesApp ? (
              <>
                {textWorkbenchV2 ? (
                  <>
                    <div className="creation-source-choice" role="tablist" aria-label="标题内容来源">
                      {([
                        { value: "artifact", label: "已有文案" },
                        { value: "topic", label: "写个主题" },
                        { value: "text", label: "粘贴内容" },
                      ] as const).map((item) => (
                        <button
                          key={item.value}
                          type="button"
                          role="tab"
                          aria-selected={titleSourceMode === item.value}
                          onClick={() => {
                            setSourceRouteBlocked(false);
                            setTitleSourceMode(item.value);
                          }}
                        >
                          {item.label}
                        </button>
                      ))}
                    </div>
                    {titleSourceMode === "artifact" ? (
                      <>
                        <label className="creation-select-field">
                          <span>本次根据哪段内容生成？</span>
                          <Select
                            aria-label="标题来源文案"
                            value={titleSourceArtifactId || undefined}
                            placeholder="从已有文案中选择"
                            options={titleSourceArtifacts.map((artifact) => {
                              const currentVersion = titleSourceVersions.find((version) => version.artifact_id === artifact.artifact_id);
                              return {
                                value: artifact.artifact_id,
                                label: currentVersion
                                  ? truncateSourceText(sourceContentPreview(currentVersion.content), 38)
                                  : artifact.name,
                              };
                            })}
                            onChange={(value) => {
                              setSourceRouteBlocked(false);
                              setTitleSourceArtifactId(value);
                              setTitleSourceVersionId("");
                            }}
                            notFoundContent="当前项目还没有可用文案"
                          />
                        </label>
                        {initialSourceArtifactVersionId && titleSourceVersionId === initialSourceArtifactVersionId ? (
                          <Alert
                            type={titleSourceVersionUpdateAvailable ? "warning" : "info"}
                            showIcon
                            message={titleSourceVersionUpdateAvailable ? "这段文案后来有过更新" : "已带入上一步选择的文案"}
                            description={titleSourceVersionUpdateAvailable
                              ? "本次仍使用你刚才确认的内容；重新选择文案即可使用最新内容。"
                              : "系统会保存本次使用的内容，后续编辑不会影响这次生成。"}
                          />
                        ) : null}
                      </>
                    ) : titleSourceMode === "topic" ? (
                      <Input.TextArea aria-label="标题主题" value={topic} placeholder="例如：午后咖啡套餐" rows={3} onChange={(event) => setTopic(event.target.value)} />
                    ) : (
                      <Input.TextArea aria-label="标题自定义原文" value={titleSourceText} placeholder="粘贴希望提炼标题的原文" rows={5} maxLength={5000} showCount onChange={(event) => setTitleSourceText(event.target.value)} />
                    )}
                  </>
                ) : null}
                <div className="creation-select-grid">
                  <label className="creation-select-field">
                    <span>发布平台</span>
                    <Select aria-label="标题平台" value={platform} options={[{ value: "douyin", label: "抖音" }, { value: "xiaohongshu", label: "小红书" }, { value: "shipinhao", label: "视频号" }, { value: "kuaishou", label: "快手" }]} onChange={setPlatform} />
                  </label>
                  <label className="creation-select-field">
                    <span>营销目标</span>
                    <Select aria-label="标题目标" value={objective} options={[{ value: "click", label: "点击" }, { value: "store_visit", label: "到店" }, { value: "inquiry", label: "咨询" }, { value: "completion", label: "完播" }, { value: "save", label: "收藏" }]} onChange={setObjective} />
                  </label>
                </div>
                {textWorkbenchV2 ? (
                  <details className="carousel-more-settings">
                    <summary>更多选项</summary>
                    <Space orientation="vertical" size="middle" style={{ width: "100%" }}>
                      <label className="creation-select-field">
                        <span>生成几个标题</span>
                        <Select aria-label="标题数量" value={6} options={[{ value: 6, label: "6 个" }]} disabled />
                      </label>
                      <Input.TextArea
                        aria-label="标题关键词"
                        value={titleKeywordsText}
                        placeholder="可选：想覆盖的关键词"
                        rows={2}
                        maxLength={200}
                        showCount
                        onChange={(event) => setTitleKeywordsText(event.target.value)}
                      />
                    </Space>
                  </details>
                ) : null}
                {!textWorkbenchV2 ? <Input.TextArea value={topic} placeholder="标题主题（只能填写一种来源）" rows={3} onChange={(event) => setTopic(event.target.value)} /> : null}
              </>
            ) : (
              <>
                {textWorkbenchV2 ? (
                  <label className="creation-select-field">
                    <span>这次想达成什么？</span>
                    <Input.TextArea
                      aria-label="营销目标"
                      value={marketingGoal}
                      placeholder="例如：吸引附近上班族下午到店"
                      rows={2}
                      maxLength={500}
                      showCount
                      onChange={(event) => setMarketingGoal(event.target.value)}
                    />
                  </label>
                ) : null}
                <label className="creation-select-field">
                  <span>本次主推 *</span>
                  <Input
                    aria-label="本次主推"
                    value={productOrService}
                    placeholder="选择项目后会自动带入商品或服务"
                    onChange={(event) => setProductOrService(event.target.value)}
                  />
                </label>
                {projectSellingPoints.length ? (
                  <section className="creation-quick-tags" aria-label="项目卖点">
                    <Typography.Text strong>项目卖点</Typography.Text>
                    <div className="creation-quick-tags__list">
                      {projectSellingPoints.map((item) => <span key={item}>{item}</span>)}
                    </div>
                  </section>
                ) : null}
                {textWorkbenchV2 ? (
                  <section className="creation-quick-tags">
                    <Typography.Text strong>这次想强调什么？ <small>可选</small></Typography.Text>
                    <Input.TextArea
                      aria-label="营销利益点"
                      value={benefitTagsText}
                      placeholder="也可以输入自己的营销信息"
                      rows={2}
                      maxLength={200}
                      showCount
                      onChange={(event) => setBenefitTagsText(event.target.value)}
                    />
                    <div className="creation-quick-tags__list">
                      {MARKETING_BENEFIT_SUGGESTIONS.map((item) => (
                        <button
                          key={item}
                          type="button"
                          aria-pressed={selectedBenefitTags.includes(item)}
                          onClick={() => toggleBenefitTag(item)}
                        >
                          {item}
                        </button>
                      ))}
                    </div>
                  </section>
                ) : null}
                {!textWorkbenchV2 ? <details className="carousel-more-settings">
                  <summary>更多选项</summary>
                  <div className="creation-select-grid">
                    <label className="creation-select-field">
                      <span>文案形式</span>
                      <Select aria-label="文案形式" value={contentFormat} options={[{ value: "oral", label: "口播" }, { value: "carousel", label: "图文" }, { value: "general", label: "通用" }]} onChange={setContentFormat} />
                    </label>
                    <label className="creation-select-field">
                      <span>文案时长</span>
                      <Select aria-label="文案时长" value={lengthBucket} options={[{ value: "short_15s", label: "15 秒" }, { value: "medium_30s", label: "30 秒" }, { value: "long_60s", label: "60 秒" }]} onChange={setLengthBucket} />
                    </label>
                  </div>
                </details> : null}
              </>
            )}
            {styleWorkbenchV2 ? (
              <StylePresetPicker
                presets={stylePresets}
                source={styleSource}
                selectedStyleId={selectedStyleId}
                customText={customStyleText}
                onSourceChange={setStyleSource}
                onStyleChange={setSelectedStyleId}
                onCustomTextChange={setCustomStyleText}
              />
            ) : null}
            {!focused || !workbenchV2 ? primaryActions : null}
            {contextDirty ? <Typography.Text type="warning">请先保存或放弃项目资料草稿，再开始生成。</Typography.Text> : null}
            {textContextMissing ? <Typography.Text type="warning">请先补全并保存项目信息，再开始生成。</Typography.Text> : null}
            {textStyleMissing ? <Typography.Text type="warning">请选择风格，或填写自定义风格参考。</Typography.Text> : null}
            {carouselContextMissing ? <Typography.Text type="warning">请先补全并保存项目信息，再开始生成图文。</Typography.Text> : null}
            {carouselStyleMissing ? <Typography.Text type="warning">请选择图文风格，或填写本次自定义风格参考。</Typography.Text> : null}
          </Space>
      </Card>
      {brandProjectV1 ? (
        <BrandProjectCreateDialog
          open={projectCreateOpen}
          busy={projectCreateBusy}
          onCancel={() => setProjectCreateOpen(false)}
          onCreated={handleBrandProjectCreated}
        />
      ) : <Modal
        open={projectCreateOpen}
        title="新建项目"
        okText="创建并完善资料"
        cancelText="取消"
        confirmLoading={projectCreateBusy}
        okButtonProps={{ disabled: !newProjectName.trim() || !newProjectGoal.trim() }}
        onOk={() => void createProjectFromDialog()}
        onCancel={() => {
          if (projectCreateBusy) return;
          setProjectCreateOpen(false);
        }}
      >
        <Space orientation="vertical" size="middle" style={{ width: "100%" }}>
          <Typography.Paragraph type="secondary">
            项目保存门店或品牌的长期资料；创建后可供所有内容应用重复使用。
          </Typography.Paragraph>
          <label className="creation-select-field">
            <span>项目名称</span>
            <Input
              aria-label="新项目名称"
              value={newProjectName}
              placeholder="例如：街角咖啡工作日下午茶"
              onChange={(event) => setNewProjectName(event.target.value)}
            />
          </label>
          <label className="creation-select-field">
            <span>主要营销目标</span>
            <Input.TextArea
              aria-label="新项目营销目标"
              value={newProjectGoal}
              placeholder="例如：吸引附近上班族到店"
              rows={3}
              onChange={(event) => setNewProjectGoal(event.target.value)}
            />
          </label>
        </Space>
      </Modal>}
      {!workbenchV2 && selected && contextPayload && <Alert type="info" showIcon message="已恢复项目上下文快照" description={JSON.stringify(contextPayload)} />}
      {!workbenchV2 ? runPanel : null}
      {isCarouselApp ? <AssetPickerDialog
        open={assetPickerOpen}
        kind="image"
        selectionMode="multiple"
        selectedIds={carouselAssetRefs.map((ref) => {
          const { assetId } = parseCarouselAssetRef(ref);
          return carouselAssetItems.find((item) => (item.asset_id || item.resource_id) === assetId)?.resource_id || assetId;
        })}
        onClose={() => setAssetPickerOpen(false)}
        onSelect={() => undefined}
        onSelectMany={(items: LibraryItemV2[]) => {
          setCarouselAssetItems(items);
          setCarouselAssetRefs(items.map(carouselAssetRef));
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
  if (workbenchV2) {
    const inputLabel = isCarouselApp ? "图文设置" : isTitlesApp ? "标题设置" : "文案设置";
    const resultLabel = isCarouselApp ? "图文成品" : isTitlesApp ? "标题候选" : "文案结果";
    return (
      <AppWorkbenchShell
        eyebrow={appCopy.eyebrow}
        title={appCopy.name}
        description={appCopy.description}
        onBack={onBack}
        input={workspace}
        inputFooter={primaryActions}
        result={runPanel}
        resultState={resultState}
        inputLabel={inputLabel}
        resultLabel={resultLabel}
      />
    );
  }
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
