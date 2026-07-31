import { Alert, Button, Card, Checkbox, Input, Tag, Typography } from "antd";
import { useEffect, useMemo, useState } from "react";
import {
  acceptIpBroadcastAppRun,
  cancelIpBroadcastAppRun,
  createContentProject,
  createIpBroadcastAppRun,
  createPublishPackageV2,
  downloadArtifact,
  executeIpBroadcastAppRun,
  getCurrentContextSnapshot,
  getIpBroadcastAppRun,
  listApplications,
  listArtifactVersions,
  listContentProjects,
  listProjectArtifacts,
  prepareIpBroadcastSpokenScript,
  prepareIpBroadcastRetryPlan,
  retryIpBroadcastAppRun,
  type ArtifactSummary,
  type ArtifactVersion,
  type ContentProject,
  type ContextSnapshot,
  type GenerationRecordBlock,
  type GenerationVideoResultItem,
  type IpBroadcastAppRun,
} from "../../api";
import { featureFlags } from "../../featureFlags";
import { AssetPickerDialog } from "../assets/components/AssetPickerDialog";
import type { LibraryItemV2 } from "../../api";
import { type DigitalHumanMode } from "./DigitalHumanModeTabs";
import { DigitalHumanResultPanel } from "./DigitalHumanResultPanel";
import { AppWorkbenchShell, type WorkbenchViewState } from "../app-workbench/AppWorkbenchShell";
import { ProjectBriefEditor } from "../app-workbench/ProjectBriefEditor";
import { ProjectBriefDisclosure } from "../app-workbench/ProjectBriefDisclosure";
import { ProjectContextSelector } from "../app-workbench/ProjectContextSelector";
import { ProjectGenerationHistory } from "../app-workbench/ProjectGenerationHistory";
import {
  BrandProjectContextPanel,
  BrandProjectCreateDialog,
} from "../app-workbench/BrandProjectContext";

const STORAGE_KEY = "pixelle_ip_broadcast_app_state_v1";
const PENDING_STORAGE_KEY = "pixelle_ip_broadcast_app_pending_v1";
const APP_ID = "builtin.digital-human-video";
const APP_VERSION = "1.1.0";
const APP_SCHEMA_VERSION = 2;
type SourceMode = "blank_project" | "copywriting" | "generated_marketing_copy" | "selected_title";
type PortraitDetails = { width?: number; height?: number; durationMs?: number; quality?: string };

const runStateLabels: Record<string, string> = {
  draft: "草稿",
  queued: "排队中",
  running: "生成中",
  needs_review: "待人工确认",
  completed: "已完成",
  failed: "失败",
  cancelled: "已取消",
};

const projectionLabels: Record<string, string> = {
  new_or_not_enqueued: "尚未执行",
  queued_for_execution: "等待执行",
  step_running: "正在生成",
  user_must_edit_or_confirm: "等待人工确认",
  waiting_for_login: "等待登录",
  waiting_for_human: "等待人工处理",
};

const taskStatusLabels: Record<string, string> = {
  pending: "待执行",
  running: "执行中",
  needs_review: "待确认",
  completed: "已完成",
  failed: "失败",
  cancelled: "已取消",
};

type VoiceResolutionSource = "run_override" | "digital_human_default" | "system_default";

type VoiceDisplaySnapshot = {
  profile_id?: string;
  name: string;
  resolution_source: VoiceResolutionSource;
};

type StoredPointer = {
  route: "/apps/digital-human-video";
  project_id: string;
  app_run_id: string;
  session_id: string;
  source_mode: SourceMode;
  source_revision: string;
  context_snapshot_id: string | null;
  source_artifact_id?: string;
  source_version_id?: string;
  copy_source_artifact_id?: string;
  copy_source_version_id?: string;
  selected_variant_index?: number;
  goal?: string;
  portrait_id?: string;
  digital_human_scene_id?: string;
  digital_human_mode?: DigitalHumanMode;
  digital_human_asset_revision_id?: string;
  digital_human_media_type?: "image" | "video";
  voice_profile_id?: string;
  voice_snapshot_profile_id?: string;
  voice_snapshot_name?: string;
  voice_resolution_source?: VoiceResolutionSource;
  publish_title?: string;
  publish_description?: string;
  cover_title?: string;
  hashtags?: string[];
  subtitle_enabled?: boolean;
  selling_points?: string;
  spoken_script?: string;
};

type StoredPending = {
  route: "/apps/digital-human-video";
  project_id: string;
  source_mode: SourceMode;
  source_artifact_id: string | null;
  idempotency_key: string;
  input_payload: Record<string, unknown>;
  context_snapshot_id: string | null;
  voice_snapshot?: VoiceDisplaySnapshot;
  phase?: "create" | "execute";
  app_run_id?: string;
};

function readStoredPointer(): StoredPointer | null {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const value = JSON.parse(raw) as Partial<StoredPointer>;
    if (value.route !== "/apps/digital-human-video" || !value.project_id || !value.app_run_id || !value.session_id || !value.source_mode || !value.source_revision) return null;
    if (!(["blank_project", "copywriting", "generated_marketing_copy", "selected_title"] as string[]).includes(value.source_mode)) return null;
    return {
      route: "/apps/digital-human-video",
      project_id: value.project_id,
      app_run_id: value.app_run_id,
      session_id: value.session_id,
      source_mode: value.source_mode,
      source_revision: value.source_revision,
      context_snapshot_id: value.context_snapshot_id || null,
      source_artifact_id: typeof value.source_artifact_id === "string" ? value.source_artifact_id : undefined,
      source_version_id: typeof value.source_version_id === "string" ? value.source_version_id : undefined,
      copy_source_artifact_id: typeof value.copy_source_artifact_id === "string" ? value.copy_source_artifact_id : undefined,
      copy_source_version_id: typeof value.copy_source_version_id === "string" ? value.copy_source_version_id : undefined,
      selected_variant_index: typeof value.selected_variant_index === "number" ? value.selected_variant_index : undefined,
      goal: typeof value.goal === "string" ? value.goal : undefined,
      portrait_id: typeof value.portrait_id === "string" ? value.portrait_id : undefined,
      digital_human_scene_id: typeof value.digital_human_scene_id === "string" ? value.digital_human_scene_id : undefined,
      digital_human_mode: value.digital_human_mode === "image_talking" || value.digital_human_mode === "video_lipsync" ? value.digital_human_mode : undefined,
      digital_human_asset_revision_id: typeof value.digital_human_asset_revision_id === "string" ? value.digital_human_asset_revision_id : undefined,
      digital_human_media_type: value.digital_human_media_type === "image" || value.digital_human_media_type === "video" ? value.digital_human_media_type : undefined,
      voice_profile_id: typeof value.voice_profile_id === "string" ? value.voice_profile_id : undefined,
      voice_snapshot_profile_id: typeof value.voice_snapshot_profile_id === "string" ? value.voice_snapshot_profile_id : undefined,
      voice_snapshot_name: typeof value.voice_snapshot_name === "string" ? value.voice_snapshot_name : undefined,
      voice_resolution_source: value.voice_resolution_source === "run_override" || value.voice_resolution_source === "digital_human_default" || value.voice_resolution_source === "system_default"
        ? value.voice_resolution_source
        : undefined,
      publish_title: typeof value.publish_title === "string" ? value.publish_title : undefined,
      publish_description: typeof value.publish_description === "string" ? value.publish_description : undefined,
      cover_title: typeof value.cover_title === "string" ? value.cover_title : undefined,
      hashtags: Array.isArray(value.hashtags) && value.hashtags.every((item) => typeof item === "string") ? value.hashtags : undefined,
      subtitle_enabled: typeof value.subtitle_enabled === "boolean" ? value.subtitle_enabled : undefined,
      selling_points: typeof value.selling_points === "string" ? value.selling_points : undefined,
      spoken_script: typeof value.spoken_script === "string" ? value.spoken_script : undefined,
    } as StoredPointer;
  } catch {
    return null;
  }
}

function writeStoredPointer(
  run: IpBroadcastAppRun,
  sourceMode: SourceMode,
  inputPayload?: Record<string, unknown>,
  voiceSnapshot?: VoiceDisplaySnapshot | null,
) {
  const sourceVersionIds = Array.isArray(inputPayload?.source_artifact_version_ids) ? inputPayload.source_artifact_version_ids : [];
  const contentSource = inputPayload?.content_source && typeof inputPayload.content_source === "object" ? inputPayload.content_source as Record<string, unknown> : null;
  const digitalHuman = inputPayload?.digital_human && typeof inputPayload.digital_human === "object" ? inputPayload.digital_human as Record<string, unknown> : null;
  const sourceVersionId = typeof contentSource?.title_artifact_version_id === "string" && contentSource.title_artifact_version_id
    ? contentSource.title_artifact_version_id
    : typeof sourceVersionIds[0] === "string" && sourceVersionIds[0]
    ? sourceVersionIds[0]
    : typeof contentSource?.source_artifact_version_id === "string" && contentSource.source_artifact_version_id
      ? contentSource.source_artifact_version_id
      : "";
  const copySourceVersionId = typeof contentSource?.source_artifact_version_id === "string" ? contentSource.source_artifact_version_id : "";
  const selectedVariantIndex = typeof inputPayload?.selected_variant_index === "number"
    ? inputPayload.selected_variant_index
    : typeof contentSource?.selected_variant_index === "number" ? contentSource.selected_variant_index : undefined;
  const portraitId = typeof inputPayload?.portrait_id === "string" && inputPayload.portrait_id
    ? inputPayload.portrait_id
    : typeof digitalHuman?.portrait_id === "string" && digitalHuman.portrait_id ? digitalHuman.portrait_id : "";
  const sceneId = typeof inputPayload?.digital_human_scene_id === "string" && inputPayload.digital_human_scene_id
    ? inputPayload.digital_human_scene_id
    : typeof digitalHuman?.scene_id === "string" && digitalHuman.scene_id ? digitalHuman.scene_id : "";
  const mode = inputPayload?.digital_human_mode === "image_talking" || inputPayload?.digital_human_mode === "video_lipsync"
    ? inputPayload.digital_human_mode
    : digitalHuman?.mode === "image_talking" || digitalHuman?.mode === "video_lipsync" ? digitalHuman.mode : undefined;
  const assetRevisionId = typeof inputPayload?.digital_human_asset_revision_id === "string" && inputPayload.digital_human_asset_revision_id
    ? inputPayload.digital_human_asset_revision_id
    : typeof digitalHuman?.asset_revision_id === "string" && digitalHuman.asset_revision_id ? digitalHuman.asset_revision_id : "";
  const mediaType = inputPayload?.digital_human_media_type === "image" || inputPayload?.digital_human_media_type === "video"
    ? inputPayload.digital_human_media_type
    : mode === "video_lipsync" ? "video" : mode === "image_talking" ? "image" : undefined;
  const delivery = inputPayload?.delivery && typeof inputPayload.delivery === "object" ? inputPayload.delivery as Record<string, unknown> : null;
  const voiceProfileId = typeof inputPayload?.voice_profile_id === "string"
    ? inputPayload.voice_profile_id
    : "";
  const publishTitle = typeof inputPayload?.publish_title === "string" ? inputPayload.publish_title : typeof delivery?.publish_title === "string" ? delivery.publish_title : "";
  const publishDescription = typeof inputPayload?.publish_description === "string" ? inputPayload.publish_description : typeof delivery?.publish_description === "string" ? delivery.publish_description : "";
  const coverTitle = typeof inputPayload?.cover_title === "string" ? inputPayload.cover_title : typeof delivery?.cover_title === "string" ? delivery.cover_title : "";
  const hashtags = Array.isArray(inputPayload?.hashtags) ? inputPayload.hashtags : Array.isArray(delivery?.hashtags) ? delivery.hashtags : [];
  const subtitleEnabled = typeof delivery?.subtitle_enabled === "boolean" ? delivery.subtitle_enabled : true;
  const sellingPoints = typeof inputPayload?.selling_points === "string"
    ? inputPayload.selling_points
    : typeof contentSource?.selling_points === "string" ? contentSource.selling_points : "";
  const goal = typeof inputPayload?.goal === "string" && inputPayload.goal
    ? inputPayload.goal
    : contentSource?.mode === "custom_script" && typeof contentSource.script === "string" && contentSource.script
      ? contentSource.script
      : "";
  const spokenScript = typeof contentSource?.spoken_script === "string" ? contentSource.spoken_script : "";
  const pointer: StoredPointer = {
    route: "/apps/digital-human-video",
    project_id: run.project_id,
    app_run_id: run.app_run_id,
    session_id: run.session_id,
    source_mode: sourceMode,
    source_revision: run.source_revision,
    context_snapshot_id: run.context_snapshot_id || null,
    ...(typeof inputPayload?.source_artifact_id === "string" && inputPayload.source_artifact_id ? { source_artifact_id: inputPayload.source_artifact_id } : {}),
    ...(sourceVersionId ? { source_version_id: sourceVersionId } : {}),
    ...(copySourceVersionId && sourceVersionId !== copySourceVersionId ? { copy_source_version_id: copySourceVersionId } : {}),
    ...(typeof selectedVariantIndex === "number" ? { selected_variant_index: selectedVariantIndex } : {}),
    ...(goal ? { goal } : {}),
    ...(portraitId ? { portrait_id: portraitId } : {}),
    ...(sceneId ? { digital_human_scene_id: sceneId } : {}),
    ...(mode ? { digital_human_mode: mode } : {}),
    ...(assetRevisionId ? { digital_human_asset_revision_id: assetRevisionId } : {}),
    ...(mediaType ? { digital_human_media_type: mediaType } : {}),
    ...(voiceProfileId ? { voice_profile_id: voiceProfileId } : {}),
    ...(voiceSnapshot?.profile_id ? { voice_snapshot_profile_id: voiceSnapshot.profile_id } : {}),
    ...(voiceSnapshot?.name ? { voice_snapshot_name: voiceSnapshot.name } : {}),
    ...(voiceSnapshot?.resolution_source ? { voice_resolution_source: voiceSnapshot.resolution_source } : {}),
    ...(publishTitle ? { publish_title: publishTitle } : {}),
    ...(publishDescription ? { publish_description: publishDescription } : {}),
    ...(coverTitle ? { cover_title: coverTitle } : {}),
    ...(hashtags.length ? { hashtags } : {}),
    subtitle_enabled: subtitleEnabled,
    ...(sellingPoints ? { selling_points: sellingPoints } : {}),
    ...(spokenScript ? { spoken_script: spokenScript } : {}),
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
    if (!(Object.keys(value.input_payload).every((key) => ["project_id", "source_mode", "goal", "source_artifact_version_ids", "selected_variant_index", "portrait_id", "digital_human_scene_id", "schema_version", "app_version", "content_source", "digital_human", "voice_profile_id", "delivery", "publish_title", "publish_description", "cover_title", "hashtags", "spoken_script"].includes(key)))) return null;
    if (value.input_payload.project_id !== value.project_id || (value.input_payload.source_mode && value.input_payload.source_mode !== value.source_mode)) return null;
    if (value.source_artifact_id !== null && typeof value.source_artifact_id !== "string") return null;
    if (value.phase !== undefined && value.phase !== "create" && value.phase !== "execute") return null;
    if (value.app_run_id !== undefined && typeof value.app_run_id !== "string") return null;
    if (value.context_snapshot_id !== undefined && value.context_snapshot_id !== null && typeof value.context_snapshot_id !== "string") return null;
    if (value.voice_snapshot !== undefined) {
      if (!value.voice_snapshot || typeof value.voice_snapshot !== "object") return null;
      if (typeof value.voice_snapshot.name !== "string") return null;
      if (!["run_override", "digital_human_default", "system_default"].includes(value.voice_snapshot.resolution_source)) return null;
      if (value.voice_snapshot.profile_id !== undefined && typeof value.voice_snapshot.profile_id !== "string") return null;
    }
    return {
      ...value,
      context_snapshot_id: value.context_snapshot_id || null,
      phase: value.phase || "create",
    } as StoredPending;
  } catch {
    return null;
  }
}

function writeStoredPending(
  projectId: string,
  sourceMode: SourceMode,
  sourceArtifactId: string | null,
  idempotencyKey: string,
  inputPayload: Record<string, unknown>,
  contextSnapshotId: string | null,
  phase: "create" | "execute" = "create",
  appRunId?: string,
  voiceSnapshot?: VoiceDisplaySnapshot,
) {
  const pending: StoredPending = {
    route: "/apps/digital-human-video",
    project_id: projectId,
    source_mode: sourceMode,
    source_artifact_id: sourceArtifactId,
    idempotency_key: idempotencyKey,
    input_payload: inputPayload,
    context_snapshot_id: contextSnapshotId,
    ...(voiceSnapshot ? { voice_snapshot: voiceSnapshot } : {}),
    phase,
    ...(appRunId ? { app_run_id: appRunId } : {}),
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
  return artifact.name;
}

function latestVersion(versions: ArtifactVersion[]) {
  return [...versions].sort((left, right) => right.version_number - left.version_number)[0] || null;
}

export function DigitalHumanApplicationView({
  onBack,
  onOpenApp,
  onOpenPublishCenter,
  initialSourceArtifactVersionId = "",
  allowLocalExecute = false,
  desktopEnabled = featureFlags.digitalHumanInAppCenter && featureFlags.digitalHumanDualModeV2,
  workbenchV2 = featureFlags.appWorkbenchV2,
  brandProjectV1 = featureFlags.brandProjectBoundaryV1,
  resultHistoryV1 = featureFlags.appResultHistoryV1,
}: {
  onBack: () => void;
  onOpenApp?: (appId: string, sourceArtifactVersionId?: string) => void;
  onOpenPublishCenter?: (packageId: string) => void;
  initialSourceArtifactVersionId?: string;
  allowLocalExecute?: boolean;
  desktopEnabled?: boolean;
  workbenchV2?: boolean;
  brandProjectV1?: boolean;
  resultHistoryV1?: boolean;
}) {
  const [projects, setProjects] = useState<ContentProject[]>([]);
  const [projectId, setProjectId] = useState("");
  const [contextSnapshot, setContextSnapshot] = useState<ContextSnapshot | null>(null);
  const [contextDirty, setContextDirty] = useState(false);
  const [projectDetailsOpen, setProjectDetailsOpen] = useState(false);
  const [projectCreateOpen, setProjectCreateOpen] = useState(false);
  const [artifacts, setArtifacts] = useState<ArtifactSummary[]>([]);
  const [versions, setVersions] = useState<ArtifactVersion[]>([]);
  const [sourceMode, setSourceMode] = useState<SourceMode>("blank_project");
  const [goal, setGoal] = useState("");
  const [spokenScript, setSpokenScript] = useState("");
  const [spokenScriptPrepared, setSpokenScriptPrepared] = useState(false);
  const [sellingPoints, setSellingPoints] = useState("");
  const [artifactId, setArtifactId] = useState("");
  const [copyArtifactId, setCopyArtifactId] = useState("");
  const [copyVersions, setCopyVersions] = useState<ArtifactVersion[]>([]);
  const [copyVersionId, setCopyVersionId] = useState("");
  const [pinnedSourceArtifactId, setPinnedSourceArtifactId] = useState("");
  const [pinnedSourceVersionId, setPinnedSourceVersionId] = useState("");
  const [sourceRecoveryBlocked, setSourceRecoveryBlocked] = useState(false);
  const [versionId, setVersionId] = useState("");
  const [variantIndex, setVariantIndex] = useState(0);
  const [publishTitle, setPublishTitle] = useState("");
  const [publishDescription, setPublishDescription] = useState("");
  const [coverTitle, setCoverTitle] = useState("");
  const [hashtagsText, setHashtagsText] = useState("");
  const [subtitleEnabled, setSubtitleEnabled] = useState(true);
  const [portraitId, setPortraitId] = useState("");
  const [portraitSceneId, setPortraitSceneId] = useState("");
  const [portraitAssetRevisionId, setPortraitAssetRevisionId] = useState("");
  const [portraitMediaType, setPortraitMediaType] = useState<"image" | "video" | "">("");
  const [portraitName, setPortraitName] = useState("");
  const [portraitDetails, setPortraitDetails] = useState<PortraitDetails>({});
  const [digitalHumanMode, setDigitalHumanMode] = useState<DigitalHumanMode>("image_talking");
  const [portraitPickerOpen, setPortraitPickerOpen] = useState(false);
  const [voicePickerOpen, setVoicePickerOpen] = useState(false);
  const [voiceOverrideId, setVoiceOverrideId] = useState("");
  const [voiceOverrideName, setVoiceOverrideName] = useState("");
  const [portraitDefaultVoiceId, setPortraitDefaultVoiceId] = useState("");
  const [portraitDefaultVoiceName, setPortraitDefaultVoiceName] = useState("");
  const [runVoiceSnapshot, setRunVoiceSnapshot] = useState<VoiceDisplaySnapshot | null>(null);
  const [run, setRun] = useState<IpBroadcastAppRun | null>(null);
  const [pending, setPending] = useState<StoredPending | null>(null);
  const [loading, setLoading] = useState(true);
  const [backendReady, setBackendReady] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [retryRootCause, setRetryRootCause] = useState("");
  const [retryReason, setRetryReason] = useState("");

  function clearSpokenScriptPreparation() {
    setSpokenScript("");
    setSpokenScriptPrepared(false);
  }

  const selectedArtifactType = sourceMode === "blank_project" || sourceMode === "selected_title" ? "selected_title" : "copywriting";
  const sourceArtifacts = useMemo(
    () => artifacts.filter((artifact) => artifact.artifact_type === selectedArtifactType && artifact.status !== "archived"),
    [artifacts, selectedArtifactType],
  );
  const selectedVersion = versions.find((version) => version.artifact_version_id === versionId) || null;
  const selectedProject = projects.find((project) => project.project_id === projectId) || null;
  const variants = Array.isArray(selectedVersion?.content?.variants) ? selectedVersion.content.variants : [];
  const selectedCopyVersion = copyVersions.find((version) => version.artifact_version_id === copyVersionId) || null;
  const copyVariants = Array.isArray(selectedCopyVersion?.content?.variants) ? selectedCopyVersion.content.variants : [];
  const pinnedSourceArtifact = sourceArtifacts.find((artifact) => artifact.artifact_id === pinnedSourceArtifactId) || null;
  const sourceUpdateAvailable = Boolean(
    pinnedSourceVersionId && pinnedSourceArtifact?.current_version_id && pinnedSourceArtifact.current_version_id !== pinnedSourceVersionId,
  );
  const projectSellingPointSuggestions = useMemo(() => {
    const payload = contextSnapshot?.payload;
    const brief = payload?.project_brief && typeof payload.project_brief === "object"
      ? payload.project_brief as Record<string, unknown>
      : payload;
    const value = brief?.selling_points;
    if (!Array.isArray(value)) return [];
    return value
      .map((item) => item && typeof item === "object" ? String((item as Record<string, unknown>).text || "").trim() : "")
      .filter(Boolean);
  }, [contextSnapshot]);
  const canStart = Boolean(
    projectId.trim() &&
      (sourceMode === "blank_project"
        ? goal.trim()
        : sourceMode === "selected_title"
          ? artifactId && versionId && copyArtifactId && copyVersionId && copyVariants[variantIndex]
          : artifactId && versionId && variants[variantIndex]) &&
      portraitId && portraitSceneId && portraitAssetRevisionId &&
      !contextDirty &&
      !sourceRecoveryBlocked,
  );
  const selectedVoiceSnapshot: VoiceDisplaySnapshot = voiceOverrideId
    ? { profile_id: voiceOverrideId, name: voiceOverrideName || "本次自定义声音", resolution_source: "run_override" }
    : portraitDefaultVoiceId
      ? { profile_id: portraitDefaultVoiceId, name: portraitDefaultVoiceName || "人物默认声音", resolution_source: "digital_human_default" }
      : { name: "系统推荐男声", resolution_source: "system_default" };
  const displayedVoiceName = run ? runVoiceSnapshot?.name || "生成时固定声音" : selectedVoiceSnapshot.name;
  const displayedVoiceProfileId = run ? runVoiceSnapshot?.profile_id || "" : selectedVoiceSnapshot.profile_id || "";
  const displayedVoiceDescription = run
    ? runVoiceSnapshot?.resolution_source === "run_override"
      ? "本次运行固定的自定义声音"
      : runVoiceSnapshot?.resolution_source === "digital_human_default"
        ? "本次运行固定的人物默认声音"
        : runVoiceSnapshot?.resolution_source === "system_default"
          ? "本次运行使用系统推荐男声"
          : "历史任务已固定声音；当前页面不重新推断"
    : voiceOverrideId
      ? "仅本次使用，不修改人物默认声音"
      : portraitDefaultVoiceId
        ? "跟随当前数字人默认声音"
        : "当前人物未绑定声音，本次使用系统推荐男声";

  useEffect(() => {
    if (run?.state !== "failed") return;
    setRetryRootCause((current) => current || run.error_code || "上次执行失败");
    setRetryReason((current) => current || "复用固定输入重新执行一次");
  }, [run?.state, run?.error_code]);

  useEffect(() => {
    if (!desktopEnabled || !projectId) {
      setContextSnapshot(null);
      return;
    }
    let active = true;
    void getCurrentContextSnapshot(projectId)
      .then((snapshot) => {
        if (active) {
          setContextSnapshot(snapshot);
          if (brandProjectV1 && snapshot?.schema_version === 3) setProjectDetailsOpen(true);
        }
      })
      .catch((loadError) => {
        if (active) setError(errorMessage(loadError));
      });
    return () => {
      active = false;
    };
  }, [brandProjectV1, desktopEnabled, projectId]);

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
          if (pointer.goal) setGoal(pointer.goal);
          if (pointer.spoken_script) {
            setSpokenScript(pointer.spoken_script);
            setSpokenScriptPrepared(true);
          }
          if (pointer.selling_points) setSellingPoints(pointer.selling_points);
          if (pointer.source_artifact_id) {
            setArtifactId(pointer.source_artifact_id);
            setPinnedSourceArtifactId(pointer.source_artifact_id);
          }
          if (pointer.source_version_id) setVersionId(pointer.source_version_id);
          if (pointer.source_version_id) setPinnedSourceVersionId(pointer.source_version_id);
          if (pointer.copy_source_artifact_id) setCopyArtifactId(pointer.copy_source_artifact_id);
          if (pointer.copy_source_version_id) setCopyVersionId(pointer.copy_source_version_id);
          if (pointer.publish_title) setPublishTitle(pointer.publish_title);
          if (pointer.publish_description) setPublishDescription(pointer.publish_description);
          if (pointer.cover_title) setCoverTitle(pointer.cover_title);
          if (pointer.hashtags) setHashtagsText(pointer.hashtags.join(" "));
          if (typeof pointer.subtitle_enabled === "boolean") setSubtitleEnabled(pointer.subtitle_enabled);
          if (typeof pointer.selected_variant_index === "number" && Number.isInteger(pointer.selected_variant_index) && pointer.selected_variant_index >= 0) {
            setVariantIndex(pointer.selected_variant_index);
          }
          if (pointer.portrait_id) {
            setPortraitId(pointer.portrait_id);
            setPortraitName("已选择数字人");
          }
          if (pointer.digital_human_scene_id) setPortraitSceneId(pointer.digital_human_scene_id);
          if (pointer.digital_human_asset_revision_id) setPortraitAssetRevisionId(pointer.digital_human_asset_revision_id);
          if (pointer.digital_human_media_type) setPortraitMediaType(pointer.digital_human_media_type);
          if (pointer.digital_human_mode) {
            setDigitalHumanMode(pointer.digital_human_mode);
            if (!pointer.digital_human_media_type) setPortraitMediaType(pointer.digital_human_mode === "video_lipsync" ? "video" : "image");
          }
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
            if (pointer.voice_resolution_source) {
              const restoredVoiceSnapshot: VoiceDisplaySnapshot = {
                ...(pointer.voice_snapshot_profile_id ? { profile_id: pointer.voice_snapshot_profile_id } : {}),
                name: pointer.voice_snapshot_name || (pointer.voice_resolution_source === "system_default" ? "系统推荐男声" : "生成时固定声音"),
                resolution_source: pointer.voice_resolution_source,
              };
              setRunVoiceSnapshot(restoredVoiceSnapshot);
              if (restoredVoiceSnapshot.resolution_source === "run_override" && restoredVoiceSnapshot.profile_id) {
                setVoiceOverrideId(restoredVoiceSnapshot.profile_id);
                setVoiceOverrideName(restoredVoiceSnapshot.name);
              }
            } else if (pointer.voice_profile_id) {
              // Backward compatibility for pointers written before the canonical
              // display snapshot existed. Never infer an avatar default as the
              // system fallback.
              setRunVoiceSnapshot({
                profile_id: pointer.voice_profile_id,
                name: "本次自定义声音",
                resolution_source: "run_override",
              });
              setVoiceOverrideId(pointer.voice_profile_id);
              setVoiceOverrideName("本次自定义声音");
            }
            setRun(restored);
            clearStoredPending();
            setPending(null);
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
          const v2Content = payload.content_source && typeof payload.content_source === "object" ? payload.content_source as Record<string, unknown> : null;
          if (typeof v2Content?.spoken_script === "string") {
            setSpokenScript(v2Content.spoken_script);
            setSpokenScriptPrepared(true);
          }
          if (pendingSubmission.source_mode === "blank_project") {
            const pendingGoal = typeof payload.goal === "string"
              ? payload.goal
              : v2Content?.mode === "custom_script" && typeof v2Content.script === "string" ? v2Content.script : "";
            if (pendingGoal) setGoal(pendingGoal);
          }
          if (typeof v2Content?.selling_points === "string") setSellingPoints(v2Content.selling_points);
          const sourceVersion = typeof v2Content?.source_artifact_version_id === "string"
            ? v2Content.source_artifact_version_id
            : Array.isArray(payload.source_artifact_version_ids) ? payload.source_artifact_version_ids[0] : null;
          const titleVersion = typeof v2Content?.title_artifact_version_id === "string" ? v2Content.title_artifact_version_id : null;
          if (pendingSubmission.source_mode === "selected_title" && typeof titleVersion === "string") {
            setVersionId(titleVersion);
            if (typeof sourceVersion === "string") setCopyVersionId(sourceVersion);
          } else if (typeof sourceVersion === "string") {
            setVersionId(sourceVersion);
          }
          const pendingVariantIndex = typeof v2Content?.selected_variant_index === "number" ? v2Content.selected_variant_index : payload.selected_variant_index;
          if (typeof pendingVariantIndex === "number" && Number.isInteger(pendingVariantIndex) && pendingVariantIndex >= 0) {
            setVariantIndex(pendingVariantIndex);
          }
          if (typeof payload.portrait_id === "string") {
            setPortraitId(payload.portrait_id);
            setPortraitName("已选择数字人");
          }
          if (typeof payload.digital_human_scene_id === "string") setPortraitSceneId(payload.digital_human_scene_id);
          const pendingHuman = payload.digital_human && typeof payload.digital_human === "object" ? payload.digital_human as Record<string, unknown> : null;
          if (pendingHuman?.mode === "image_talking" || pendingHuman?.mode === "video_lipsync") {
            setDigitalHumanMode(pendingHuman.mode);
            setPortraitMediaType(pendingHuman.mode === "video_lipsync" ? "video" : "image");
          }
          if (typeof pendingHuman?.portrait_id === "string") { setPortraitId(pendingHuman.portrait_id); setPortraitName("已选择数字人"); }
          if (typeof pendingHuman?.scene_id === "string") setPortraitSceneId(pendingHuman.scene_id);
          if (typeof pendingHuman?.asset_revision_id === "string") setPortraitAssetRevisionId(pendingHuman.asset_revision_id);
          if (typeof payload.voice_profile_id === "string") {
            setVoiceOverrideId(payload.voice_profile_id);
            setVoiceOverrideName("本次自定义声音");
          }
          if (pendingSubmission.voice_snapshot?.resolution_source === "digital_human_default" && pendingSubmission.voice_snapshot.profile_id) {
            setPortraitDefaultVoiceId(pendingSubmission.voice_snapshot.profile_id);
            setPortraitDefaultVoiceName(pendingSubmission.voice_snapshot.name);
          }
          if (pendingSubmission.source_artifact_id) setArtifactId(pendingSubmission.source_artifact_id);
          const pendingDelivery = payload.delivery && typeof payload.delivery === "object" ? payload.delivery as Record<string, unknown> : null;
          if (typeof pendingDelivery?.publish_title === "string") setPublishTitle(pendingDelivery.publish_title);
          if (typeof pendingDelivery?.publish_description === "string") setPublishDescription(pendingDelivery.publish_description);
          if (typeof pendingDelivery?.cover_title === "string") setCoverTitle(pendingDelivery.cover_title);
          if (Array.isArray(pendingDelivery?.hashtags)) setHashtagsText(pendingDelivery.hashtags.filter((item): item is string => typeof item === "string").join(" "));
          if (typeof pendingDelivery?.subtitle_enabled === "boolean") setSubtitleEnabled(pendingDelivery.subtitle_enabled);
          setNotice("上次提交尚未收到确认；点击开始生成将复用同一幂等键，不会随机创建第二个运行。 ");
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
      .then(async (items) => {
        if (!active) return;
        setArtifacts(items);
        if (!items.length) {
          setArtifactId("");
          setVersionId("");
          setVersions([]);
          return;
        }
        if (initialSourceArtifactVersionId && !run && !pending && !pinnedSourceVersionId) {
          const candidates = items.filter((item) => ["copywriting", "selected_title"].includes(item.artifact_type) && item.status !== "archived");
          const matches = await Promise.all(candidates.map(async (item) => {
            try {
              const itemVersions = await listArtifactVersions(item.artifact_id);
              return itemVersions.some((version) => version.artifact_version_id === initialSourceArtifactVersionId) ? item : null;
            } catch {
              return null;
            }
          }));
          if (!active) return;
          const match = matches.find((item): item is typeof candidates[number] => Boolean(item));
          if (!match) {
            setArtifactId("");
            setVersionId("");
            setVersions([]);
            setSourceRecoveryBlocked(true);
            setError("带入的数字人来源版本不存在或已归档；已安全停手，请重新选择来源版本。 ");
            return;
          }
          setSourceMode(match.artifact_type === "selected_title" ? "selected_title" : "copywriting");
          setArtifactId(match.artifact_id);
          setPinnedSourceArtifactId(match.artifact_id);
          setVersionId(initialSourceArtifactVersionId);
          setPinnedSourceVersionId(initialSourceArtifactVersionId);
          setNotice("已带入上游固定版本；上游后续修改不会热更新本次数字人输入。 ");
        }
      })
      .catch((loadError) => {
        if (active) setError(errorMessage(loadError));
      });
    return () => {
      active = false;
    };
  }, [desktopEnabled, initialSourceArtifactVersionId, pending, pinnedSourceVersionId, projectId, run]);

  useEffect(() => {
    if (!desktopEnabled || !pending?.source_artifact_id) return;
    if (sourceArtifacts.some((artifact) => artifact.artifact_id === pending.source_artifact_id) && artifactId !== pending.source_artifact_id) {
      setArtifactId(pending.source_artifact_id);
    }
  }, [artifactId, desktopEnabled, pending, sourceArtifacts]);

  useEffect(() => {
    if (!desktopEnabled) return;
    if (sourceRecoveryBlocked) return;
    if (!artifacts.length && !pinnedSourceArtifactId) return;
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
    const pinnedArtifact = pinnedSourceArtifactId
      ? sourceArtifacts.find((artifact) => artifact.artifact_id === pinnedSourceArtifactId)
      : null;
    if (pinnedSourceArtifactId && !pinnedArtifact) {
      clearStoredPointer();
      setPinnedSourceArtifactId("");
      setRun(null);
      setRunVoiceSnapshot(null);
      setArtifactId("");
      setVersionId("");
      setVersions([]);
      setSourceRecoveryBlocked(true);
      setError("历史运行引用的来源产物不存在或已归档；已安全停手，请重新选择来源。 ");
      return;
    }
    const selected = pinnedArtifact || (pendingArtifact && !artifactId
      ? pendingArtifact
      : sourceArtifacts.find((artifact) => artifact.artifact_id === artifactId) || sourceArtifacts[0]);
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
        if (sourceRecoveryBlocked) return;
        setVersions(items);
        const pendingVersion = pending?.project_id === projectId && pending.source_mode === sourceMode && Array.isArray(pending.input_payload.source_artifact_version_ids)
          ? pending.input_payload.source_artifact_version_ids[0]
          : null;
        if (pendingVersion && !items.some((item) => item.artifact_version_id === pendingVersion)) {
          clearStoredPending();
          setPending(null);
          setVersionId("");
          setSourceRecoveryBlocked(true);
          setError("待确认提交引用的来源版本不存在或已归档；已安全停手，请重新选择来源后创建。 ");
          return;
        }
        if (pinnedSourceVersionId && !items.some((item) => item.artifact_version_id === pinnedSourceVersionId)) {
          clearStoredPointer();
          setPinnedSourceVersionId("");
          setRun(null);
          setRunVoiceSnapshot(null);
          setVersionId("");
          setSourceRecoveryBlocked(true);
          setError("历史运行引用的来源版本不存在或已归档；已安全停手，请重新选择来源。 ");
          return;
        }
        const pinnedVersion = items.some((item) => item.artifact_version_id === pinnedSourceVersionId) ? pinnedSourceVersionId : null;
        const nextVersionId = typeof pendingVersion === "string" && items.some((item) => item.artifact_version_id === pendingVersion)
          ? pendingVersion
          : pinnedVersion
          ? pinnedVersion
          : selected.current_version_id && items.some((item) => item.artifact_version_id === selected.current_version_id)
          ? selected.current_version_id
          : latestVersion(items)?.artifact_version_id || "";
        if (versionId && nextVersionId !== versionId && !pendingVersion) clearSpokenScriptPreparation();
        setVersionId(nextVersionId);
      })
      .catch((loadError) => {
        if (active) setError(errorMessage(loadError));
      });
    return () => {
      active = false;
    };
  }, [artifactId, artifacts, desktopEnabled, pending, pinnedSourceArtifactId, pinnedSourceVersionId, projectId, sourceMode, sourceArtifacts, sourceRecoveryBlocked, versionId]);

  useEffect(() => {
    if (!desktopEnabled || sourceMode !== "selected_title" || !projectId) {
      setCopyVersions([]);
      return;
    }
    const copyArtifacts = artifacts.filter((artifact) => artifact.artifact_type === "copywriting" && artifact.status !== "archived");
    const selected = copyArtifacts.find((artifact) => artifact.artifact_id === copyArtifactId) || copyArtifacts[0];
    if (!selected) {
      setCopyArtifactId("");
      setCopyVersionId("");
      setCopyVersions([]);
      return;
    }
    if (selected.artifact_id !== copyArtifactId) {
      setCopyArtifactId(selected.artifact_id);
      return;
    }
    let active = true;
    listArtifactVersions(selected.artifact_id)
      .then((items) => {
        if (!active) return;
        setCopyVersions(items);
        const pendingContent = pending?.input_payload.content_source && typeof pending.input_payload.content_source === "object"
          ? pending.input_payload.content_source as Record<string, unknown>
          : null;
        const pendingVersion = pendingContent?.mode === "title_plus_copywriting" && typeof pendingContent.source_artifact_version_id === "string"
          ? pendingContent.source_artifact_version_id
          : null;
        const nextCopyVersionId = typeof pendingVersion === "string" && items.some((item) => item.artifact_version_id === pendingVersion)
          ? pendingVersion
          : selected.current_version_id && items.some((item) => item.artifact_version_id === selected.current_version_id)
            ? selected.current_version_id
            : latestVersion(items)?.artifact_version_id || "";
        if (copyVersionId && nextCopyVersionId !== copyVersionId && !pendingVersion) clearSpokenScriptPreparation();
        setCopyVersionId(nextCopyVersionId);
      })
      .catch((loadError) => {
        if (active) setError(errorMessage(loadError));
      });
    return () => {
      active = false;
    };
  }, [artifacts, copyArtifactId, copyVersionId, desktopEnabled, pending, projectId, sourceMode]);

  async function createProject() {
    if (brandProjectV1) {
      setProjectCreateOpen(true);
      return;
    }
    const name = window.prompt("项目名称", "数字人口播灰度项目")?.trim();
    if (!name) return;
    setBusy(true);
    setError("");
    try {
      const created = await createContentProject({ name, primary_goal: "制作一条门店数字人口播视频" });
      setProjects((current) => [created, ...current]);
      setProjectId(created.project_id);
      setContextSnapshot(null);
      setContextDirty(false);
      setProjectDetailsOpen(false);
      setNotice("项目已创建；请先选择来源，再点击开始生成。 ");
    } catch (createError) {
      setError(errorMessage(createError));
    } finally {
      setBusy(false);
    }
  }

  function handleBrandProjectCreated(created: ContentProject) {
    setProjects((current) => [created, ...current.filter((item) => item.project_id !== created.project_id)]);
    setProjectId(created.project_id);
    setContextSnapshot(null);
    setContextDirty(false);
    setProjectDetailsOpen(true);
    setProjectCreateOpen(false);
    setNotice("项目已创建；请完善本次项目信息。");
    void getCurrentContextSnapshot(created.project_id)
      .then(setContextSnapshot)
      .catch((loadError) => setError(errorMessage(loadError)));
  }

  async function reloadSelectedProjectContext() {
    if (!projectId) return;
    const [nextProjects, snapshot] = await Promise.all([
      listContentProjects(),
      getCurrentContextSnapshot(projectId),
    ]);
    setProjects(nextProjects);
    setContextSnapshot(snapshot);
    setContextDirty(false);
  }

  function buildInputPayload(includeSpokenScript: boolean): Record<string, unknown> {
    const sellingPointsPayload = sellingPoints.trim() ? { selling_points: sellingPoints.trim() } : {};
    const contentSource: Record<string, unknown> = sourceMode === "blank_project"
      ? { mode: "custom_script", script: goal.trim(), ...sellingPointsPayload }
      : sourceMode === "selected_title"
        ? { mode: "title_plus_copywriting", title_artifact_version_id: versionId, source_artifact_version_id: copyVersionId, selected_variant_index: variantIndex, ...sellingPointsPayload }
        : { mode: sourceMode === "generated_marketing_copy" ? "generated_marketing_copy" : "copywriting_artifact", source_artifact_version_id: versionId, selected_variant_index: variantIndex, ...sellingPointsPayload };
    if (includeSpokenScript && spokenScript.trim()) contentSource.spoken_script = spokenScript.trim();
    const delivery: Record<string, unknown> = { subtitle_preset: "readable_v2", subtitle_enabled: subtitleEnabled };
    if (publishTitle.trim()) delivery.publish_title = publishTitle.trim();
    if (publishDescription.trim()) delivery.publish_description = publishDescription.trim();
    if (coverTitle.trim()) delivery.cover_title = coverTitle.trim();
    const hashtags = hashtagsText.split(/[\s,，#]+/).map((item) => item.trim()).filter(Boolean);
    if (hashtags.length) delivery.hashtags = hashtags;
    return {
      schema_version: APP_SCHEMA_VERSION,
      app_version: APP_VERSION,
      project_id: projectId,
      content_source: contentSource,
      digital_human: {
        mode: digitalHumanMode,
        portrait_id: portraitId,
        scene_id: portraitSceneId,
        asset_revision_id: portraitAssetRevisionId,
        workflow_profile: digitalHumanMode === "video_lipsync" ? "natural" : "stable",
      },
      ...(voiceOverrideId ? { voice_profile_id: voiceOverrideId } : {}),
      delivery,
    };
  }

  async function startGeneration() {
    const coverLines = coverTitle.trim().split(/\r?\n/);
    if (coverTitle.trim() && (coverTitle.trim().length > 24 || coverLines.length > 2 || coverLines.some((line) => line.length > 12))) {
      setError("封面标题最多 24 个字、最多两行且每行最多 12 个字。 ");
      return;
    }
    if (sourceMode === "selected_title" && (!versionId || !copyVersionId)) {
      setError("选定标题必须绑定一份完整文案版本后才能生成。 ");
      return;
    }
    if (spokenScriptPrepared && !spokenScript.trim()) {
      setError("最终口播稿不能为空；请补充内容或重新整理口播稿。 ");
      return;
    }
    const sourcePayload = buildInputPayload(false);
    if (!spokenScriptPrepared) {
      setBusy(true);
      setError("");
      setNotice("");
      try {
        const prepared = await prepareIpBroadcastSpokenScript({
          project_id: projectId,
          input_payload: sourcePayload,
          context_snapshot_id: selectedProject?.current_context_snapshot_id || null,
        });
        setSpokenScript(prepared.spoken_script);
        setSpokenScriptPrepared(true);
        if (pending && !Object.prototype.hasOwnProperty.call(
          pending.input_payload.content_source && typeof pending.input_payload.content_source === "object"
            ? pending.input_payload.content_source
            : {},
          "spoken_script",
        )) {
          clearStoredPending();
          setPending(null);
          setNotice("已重新整理口播稿；之前未确认的提交不会复用旧来源。请确认口播稿后继续。 ");
          return;
        }
        setNotice("口播稿已整理完成，请检查并编辑；确认后再次点击即可生成视频。 ");
      } catch (prepareError) {
        setError(errorMessage(prepareError));
      } finally {
        setBusy(false);
      }
      return;
    }
    const inputPayload = buildInputPayload(true);
    const pendingDelivery = pending?.input_payload.delivery && typeof pending.input_payload.delivery === "object"
      ? pending.input_payload.delivery as Record<string, unknown>
      : {};
    const comparablePendingPayload = pending
      ? { ...pending.input_payload, delivery: { subtitle_preset: "readable_v2", subtitle_enabled: true, ...pendingDelivery } }
      : null;
    const pendingMatches = pending && pending.project_id === projectId && pending.source_mode === sourceMode && JSON.stringify(comparablePendingPayload) === JSON.stringify(inputPayload);
    if (!canStart && !pendingMatches) return;
    const voiceSnapshot = pendingMatches && pending.voice_snapshot ? pending.voice_snapshot : selectedVoiceSnapshot;
    const idempotencyKey = pendingMatches ? pending.idempotency_key : randomIdempotencyKey(projectId);
    const contextSnapshotId = pendingMatches
      ? pending.context_snapshot_id
      : selectedProject?.current_context_snapshot_id || null;
    // Persist before POST: if the process dies after the server commits but
    // before the response reaches the UI, the next explicit click replays the
    // same idempotency key instead of creating a second AppRun.
    writeStoredPending(projectId, sourceMode, artifactId || pending?.source_artifact_id || null, idempotencyKey, inputPayload, contextSnapshotId, "create", undefined, voiceSnapshot);
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const created = await createIpBroadcastAppRun({
        project_id: projectId,
        input_payload: inputPayload,
        idempotency_key: idempotencyKey,
        context_snapshot_id: contextSnapshotId,
      });
      setRunVoiceSnapshot(voiceSnapshot);
      setRun(created);
      writeStoredPointer(created, sourceMode, { ...inputPayload, source_artifact_id: artifactId || pending?.source_artifact_id || "" }, voiceSnapshot);
      writeStoredPending(projectId, sourceMode, artifactId || pending?.source_artifact_id || null, idempotencyKey, inputPayload, contextSnapshotId, "execute", created.app_run_id, voiceSnapshot);
      setPending({
        route: "/apps/digital-human-video",
        project_id: projectId,
        source_mode: sourceMode,
        source_artifact_id: artifactId || pending?.source_artifact_id || null,
        idempotency_key: idempotencyKey,
        input_payload: inputPayload,
        context_snapshot_id: contextSnapshotId,
        voice_snapshot: voiceSnapshot,
        phase: "execute",
        app_run_id: created.app_run_id,
      });
      const started = await executeIpBroadcastAppRun(created.app_run_id);
      setRun(started);
      writeStoredPointer(started, sourceMode, { ...inputPayload, source_artifact_id: artifactId || pending?.source_artifact_id || "" }, voiceSnapshot);
      clearStoredPending();
      setPending(null);
      setNotice("已开始生成，将在运行状态区回读 TTS/数字人进度；最终发布仍需人工确认。 ");
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
      writeStoredPointer(refreshed, sourceMode, {
        ...buildInputPayload(true),
        goal,
        source_artifact_id: artifactId,
        source_artifact_version_ids: versionId ? [versionId] : [],
      }, runVoiceSnapshot);
    } catch (refreshError) {
      setError(errorMessage(refreshError));
    } finally {
      setBusy(false);
    }
  }

  async function mutateRun(action: "execute" | "cancel" | "retry" | "accept") {
    if (!run) return;
    if (action === "execute" && run.state === "failed") {
      setError("失败运行必须先提交受控重试计划，不能直接开始生成。 ");
      return;
    }
    if (action === "execute" && !portraitId) {
      setError("请先选择数字人形象，再生成真实视频。 ");
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
      if (action === "execute") {
        clearStoredPending();
        setPending(null);
      }
      writeStoredPointer(next, sourceMode, {
        ...buildInputPayload(true),
        goal,
        source_artifact_id: artifactId,
        source_artifact_version_ids: versionId ? [versionId] : [],
      }, runVoiceSnapshot);
      setNotice(action === "accept" ? "已显式接收当前结果；未触发最终平台发布。 " : "运行状态已更新。 ");
    } catch (actionError) {
      setError(errorMessage(actionError));
    } finally {
      setBusy(false);
    }
  }

  async function retryWithPlan() {
    if (!run || run.state !== "failed") return;
    if (!retryRootCause.trim() || !retryReason.trim()) {
      setError("请先填写失败原因和本次重试理由。 ");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await prepareIpBroadcastRetryPlan(run.app_run_id, {
        root_cause: retryRootCause.trim(),
        retry_reason: retryReason.trim(),
      });
      const next = await retryIpBroadcastAppRun(run.app_run_id);
      setRun(next);
      setNotice("重试计划已记录，已按固定输入提交一次受控重试；不会重复创建未授权 Provider 任务。 ");
      setRetryRootCause("");
      setRetryReason("");
    } catch (retryError) {
      setError(errorMessage(retryError));
    } finally {
      setBusy(false);
    }
  }

  async function handoffToPublishing() {
    if (!run || !onOpenPublishCenter || !["needs_review", "completed"].includes(run.state)) return;
    const details = run.artifact_details || {};
    const versionIds = ["video", "final_video", "cover", "publish_copy"]
      .map((key) => details[key]?.artifact_version_id)
      .filter((value, index, values): value is string => typeof value === "string" && Boolean(value) && values.indexOf(value) === index);
    if (!versionIds.some((versionId) => versionId === details.video?.artifact_version_id || versionId === details.final_video?.artifact_version_id)) {
      setError("当前运行还没有可交付视频；请先刷新结果或确认生成完成。 ");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const packageData = await createPublishPackageV2({
        project_id: run.project_id,
        artifact_version_ids: versionIds,
      });
      onOpenPublishCenter(packageData.package_id);
      setNotice("数字人视频、封面和发布文案已固定交给发布中心；平台最终发布仍由你人工确认。 ");
    } catch (handoffError) {
      setError(errorMessage(handoffError));
    } finally {
      setBusy(false);
    }
  }

  async function handoffHistoryVideo(
    record: GenerationRecordBlock,
    item: GenerationVideoResultItem,
  ) {
    if (!onOpenPublishCenter) return;
    setBusy(true);
    setError("");
    try {
      if (!item.artifact_version_ids.length) {
        throw new Error("当前成片还没有可发布的视频文件");
      }
      const packageData = await createPublishPackageV2({
        project_id: record.project_id,
        artifact_version_ids: item.artifact_version_ids,
      });
      onOpenPublishCenter(packageData.package_id);
      setNotice("视频成品已固定交给发布中心；平台最终发布仍由你人工确认。 ");
    } catch (handoffError) {
      const message = errorMessage(handoffError);
      setError(message);
      throw handoffError;
    } finally {
      setBusy(false);
    }
  }

  function startNewRun() {
    clearStoredPointer();
    clearStoredPending();
    setRun(null);
    setRunVoiceSnapshot(null);
    setPending(null);
    setRetryRootCause("");
    setRetryReason("");
    setSpokenScript("");
    setSpokenScriptPrepared(false);
    setNotice("已保留历史结果；现在可以在当前项目上创建一条新任务。 ");
    setError("");
  }

  function changeSourceMode(next: SourceMode) {
    if (pending && pending.source_mode !== next) {
      setNotice("上次提交尚未收到确认，请先恢复或清理待提交状态，再切换来源类型。 ");
      return;
    }
    setSourceMode(next);
    setSourceRecoveryBlocked(false);
    setPinnedSourceArtifactId("");
    setPinnedSourceVersionId("");
    setArtifactId("");
    setCopyArtifactId("");
    setCopyVersionId("");
    setCopyVersions([]);
    setVersionId("");
    setCopyVersionId("");
    setVersions([]);
    setVariantIndex(0);
    setSpokenScript("");
    setSpokenScriptPrepared(false);
    setError("");
  }

  function changeDigitalHumanMode(next: DigitalHumanMode) {
    if (pending && pending.input_payload.digital_human && typeof pending.input_payload.digital_human === "object") {
      const pendingMode = (pending.input_payload.digital_human as Record<string, unknown>).mode;
      if (pendingMode !== next) {
        setNotice("上次提交尚未收到确认，请先恢复或清理待提交状态，再切换数字人模式。 ");
        return false;
      }
    }
    setDigitalHumanMode(next);
    const expectedMedia = next === "video_lipsync" ? "video" : "image";
    if (portraitMediaType && portraitMediaType !== expectedMedia) {
      setPortraitId("");
      setPortraitSceneId("");
      setPortraitAssetRevisionId("");
      setPortraitMediaType("");
      setPortraitName("");
      setPortraitDetails({});
      setNotice("已清理与当前模式不兼容的数字人素材，请重新选择对应场景。 ");
    }
    return true;
  }

  function changeProject(nextProjectId: string) {
    if (nextProjectId === projectId) return;
    if (contextDirty && !window.confirm("当前项目资料有未保存草稿（已保存在本机），确定切换吗？")) return;
    setProjectId(nextProjectId);
    setContextSnapshot(null);
    setContextDirty(false);
    setProjectDetailsOpen(false);
    setSourceRecoveryBlocked(false);
    setPinnedSourceArtifactId("");
    setPinnedSourceVersionId("");
    setArtifactId("");
    setCopyArtifactId("");
    setCopyVersionId("");
    setCopyVersions([]);
    setVersionId("");
    setVersions([]);
    setSpokenScript("");
    setSpokenScriptPrepared(false);
    if (pending && pending.project_id !== nextProjectId) {
      clearStoredPending();
      setPending(null);
    }
    if (run && run.project_id !== nextProjectId) {
      setRun(null);
      setRunVoiceSnapshot(null);
      clearStoredPointer();
      setNotice("已切换到其他项目；旧运行指针已清理，请显式创建或恢复当前项目运行。 ");
    }
  }

  function handleContextSaved(snapshot: ContextSnapshot) {
    setContextSnapshot(snapshot);
    setContextDirty(false);
    setProjects((current) => current.map((project) => (
      project.project_id === snapshot.project_id
        ? { ...project, current_context_snapshot_id: snapshot.context_snapshot_id }
        : project
    )));
  }

  function changeArtifact(nextArtifactId: string) {
    setSourceRecoveryBlocked(false);
    setPinnedSourceArtifactId("");
    setPinnedSourceVersionId("");
    setArtifactId(nextArtifactId);
    setVersionId("");
    if (sourceMode === "selected_title") {
      setCopyVersionId("");
      setCopyVersions([]);
    }
    setVersions([]);
    setSpokenScript("");
    setSpokenScriptPrepared(false);
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

  const resultState: WorkbenchViewState = !run
    ? "empty"
    : run.state === "failed" || run.state === "cancelled"
      ? "failed"
      : run.state === "needs_review"
        ? "needs_review"
        : run.state === "completed"
          ? "saved"
          : "running";
  const resultStatePresentation = {
    empty: { label: "等待开始", color: "default" as const },
    running: { label: "正在处理", color: "processing" as const },
    failed: { label: "需要处理", color: "error" as const },
    needs_review: { label: "等待确认", color: "warning" as const },
    saved: { label: "已保存", color: "success" as const },
  }[resultState];
  const digitalHumanPrimaryActions = (
    <div className="digital-human-app-actions">
      {run ? (
        <div className="digital-human-app-run-start-actions">
          <Tag color="processing">本次任务已创建</Tag>
          <Button onClick={startNewRun} disabled={busy}>重新制作</Button>
        </div>
      ) : <Button block size="large" type="primary" onClick={() => void startGeneration()} disabled={!canStart || busy} loading={busy}>{spokenScriptPrepared ? "确认口播稿并生成视频" : "开始生成"}</Button>}
    </div>
  );
  const legacyView = (
    <section className="digital-human-app-workspace" aria-label="数字人口播应用">
      <div className="digital-human-app-heading">
        <div>
          <Typography.Text type="secondary">APPLICATION · {APP_ID}</Typography.Text>
          <Typography.Title level={2}>数字人口播视频</Typography.Title>
          <Typography.Paragraph type="secondary">
            从项目、可信文案或选定标题进入统一运行链路；选择数字人形象后可调用已配置的 TTS/数字人服务生成真实视频，最终发布仍由人工确认。
          </Typography.Paragraph>
        </div>
        <SpaceButtons onBack={onBack} />
      </div>

      {error ? <Alert type="error" showIcon message="应用运行未完成" description={error} /> : null}
      {notice ? <Alert type="info" showIcon message={notice} /> : null}
      {sourceUpdateAvailable ? <Alert type="warning" showIcon message="上游来源已有新版本" description={run ? "当前运行仍锁定原来源版本，不会静默切换。点击“新建运行”后重新选择版本，确认后再生成。" : "当前输入仍锁定已带入版本，不会静默切换；请重新选择来源版本后再生成。"} /> : null}

      <Card id="digital-human-workbench-input" title="开始创作" className="digital-human-app-card">
        {workbenchV2 ? (
          <>
            <ProjectContextSelector
              projects={projects}
              value={projectId}
              disabled={loading || busy}
              onChange={changeProject}
              onCreate={() => void createProject()}
              onEdit={() => setProjectDetailsOpen(true)}
            />
            {brandProjectV1 && selectedProject ? (
              <BrandProjectContextPanel
                project={selectedProject}
                snapshot={contextSnapshot}
                open={contextSnapshot?.schema_version === 3 && projectDetailsOpen}
                onOpen={() => setProjectDetailsOpen(true)}
                onClose={() => setProjectDetailsOpen(false)}
                onSaved={handleContextSaved}
                onReload={reloadSelectedProjectContext}
                onDirtyChange={setContextDirty}
              />
            ) : selectedProject && contextSnapshot?.schema_version !== 2 ? (
              <ProjectBriefDisclosure ready={false}>
                <ProjectBriefEditor
                  projectId={selectedProject.project_id}
                  projectName={selectedProject.name}
                  snapshot={contextSnapshot}
                  onSaved={handleContextSaved}
                  onDirtyChange={setContextDirty}
                />
              </ProjectBriefDisclosure>
            ) : null}
            {selectedProject && contextSnapshot?.schema_version === 2 && projectDetailsOpen ? (
              <section className="project-details-editor" aria-label="编辑当前项目信息">
                <div className="project-details-editor__heading">
                  <Typography.Text strong>编辑项目信息</Typography.Text>
                  <Button size="small" onClick={() => setProjectDetailsOpen(false)}>完成</Button>
                </div>
                <ProjectBriefEditor
                  projectId={selectedProject.project_id}
                  projectName={selectedProject.name}
                  snapshot={contextSnapshot}
                  onSaved={handleContextSaved}
                  onDirtyChange={setContextDirty}
                />
              </section>
            ) : null}
          </>
        ) : (
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
        )}
        {brandProjectV1 ? (
          <BrandProjectCreateDialog
            open={projectCreateOpen}
            busy={busy}
            onCancel={() => setProjectCreateOpen(false)}
            onCreated={handleBrandProjectCreated}
          />
        ) : null}
        <details className="digital-human-source-switcher">
          <summary>
            <span>口播来源</span>
            <strong>{sourceMode === "blank_project" ? "直接输入" : sourceMode === "copywriting" ? "已有文案" : sourceMode === "generated_marketing_copy" ? "自动生成文案" : "标题＋文案"}</strong>
            <small>更换</small>
          </summary>
          <div className="digital-human-app-source-tabs" role="tablist" aria-label="口播来源">
            {(["blank_project", "copywriting", "generated_marketing_copy", "selected_title"] as SourceMode[]).map((mode) => (
              <button key={mode} type="button" role="tab" aria-selected={sourceMode === mode} onClick={() => changeSourceMode(mode)}>
                {mode === "blank_project" ? "直接输入" : mode === "copywriting" ? "已有文案" : mode === "generated_marketing_copy" ? "自动写文案" : "标题＋文案"}
              </button>
            ))}
          </div>
        </details>
        {sourceMode === "blank_project" ? (
          <div className="digital-human-app-field">
            <Typography.Text strong>自定义口播文案</Typography.Text>
            <Input.TextArea aria-label="制作目标" rows={3} value={goal} onChange={(event) => { setGoal(event.target.value); setSpokenScript(""); setSpokenScriptPrepared(false); }} placeholder="直接粘贴你确认过的口播内容" />
          </div>
        ) : (
          <div className="digital-human-app-source-selects">
            <select aria-label="来源产物" value={artifactId} onChange={(event) => changeArtifact(event.target.value)} disabled={!projectId || busy}>
              <option value="">选择一段{sourceMode === "selected_title" ? "标题" : "文案"}</option>
              {sourceArtifacts.map((artifact) => <option key={artifact.artifact_id} value={artifact.artifact_id}>{artifactLabel(artifact)}</option>)}
            </select>
            {sourceMode === "selected_title" ? (
              <>
                <select aria-label="完整文案产物" value={copyArtifactId} onChange={(event) => { setCopyArtifactId(event.target.value); setCopyVersionId(""); setCopyVersions([]); clearSpokenScriptPreparation(); }} disabled={!projectId || busy}>
                  <option value="">再选择一段完整文案</option>
                  {artifacts.filter((artifact) => artifact.artifact_type === "copywriting" && artifact.status !== "archived").map((artifact) => <option key={artifact.artifact_id} value={artifact.artifact_id}>{artifactLabel(artifact)}</option>)}
                </select>
                <select aria-label="文案变体" value={String(variantIndex)} onChange={(event) => { setVariantIndex(Number(event.target.value)); clearSpokenScriptPreparation(); }} disabled={!copyVersions.length || busy}>
                  {copyVariants.map((variant, index) => <option key={index} value={index}>文案方案 {index + 1} · {typeof variant === "object" && variant && "title" in variant ? String(variant.title) : "可选内容"}</option>)}
                </select>
              </>
            ) : (
              <select aria-label="文案变体" value={String(variantIndex)} onChange={(event) => { setVariantIndex(Number(event.target.value)); clearSpokenScriptPreparation(); }} disabled={!versions.length || busy}>
                {variants.map((variant, index) => <option key={index} value={index}>文案方案 {index + 1} · {typeof variant === "object" && variant && "title" in variant ? String(variant.title) : "可选内容"}</option>)}
              </select>
            )}
          </div>
        )}
        {spokenScriptPrepared ? (
          <div className="digital-human-app-field" aria-label="确认口播稿">
            <label htmlFor="digital-human-spoken-script">最终口播稿</label>
            <Input.TextArea
              id="digital-human-spoken-script"
              aria-label="最终口播稿"
              rows={6}
              value={spokenScript}
              onChange={(event) => setSpokenScript(event.target.value)}
              maxLength={2000}
            />
            <Typography.Text type="secondary">已按短句和自然停顿整理；你可以直接编辑，确认后再生成视频。</Typography.Text>
          </div>
        ) : null}
        <details className="digital-human-selling-points">
          <summary>补充本次卖点（可选）</summary>
          <div className="digital-human-app-field">
            <Input.TextArea id="digital-human-selling-points" aria-label="本次卖点" rows={2} value={sellingPoints} onChange={(event) => { setSellingPoints(event.target.value); clearSpokenScriptPreparation(); }} placeholder="例如：工作日下午茶套餐、现磨咖啡和当日烘焙面包" maxLength={160} />
            {projectSellingPointSuggestions.length ? (
              <div className="creation-quick-tags__list" aria-label="项目卖点建议">
                {projectSellingPointSuggestions.map((item) => {
                  const selectedItems = sellingPoints.split(/[\n,，]/).map((value) => value.trim()).filter(Boolean);
                  const active = selectedItems.includes(item);
                  return (
                    <button
                      key={item}
                      type="button"
                      aria-pressed={active}
                      onClick={() => {
                        const next = new Set(selectedItems);
                        if (active) next.delete(item);
                        else next.add(item);
                        setSellingPoints(Array.from(next).join("，"));
                        clearSpokenScriptPreparation();
                      }}
                    >
                      {item}
                    </button>
                  );
                })}
              </div>
            ) : null}
          </div>
        </details>
        <div className="digital-human-app-field">
          <label>数字人形象</label>
          <div className="digital-human-choice-row">
            <div>
              <strong>{portraitName || (portraitId ? "已选择数字人" : "请选择形象")}</strong>
              <span>{portraitMediaType === "video" ? "视频形象 · 保留原动作并匹配口型" : portraitMediaType === "image" ? "图片形象 · 自动生成口播动作" : "支持图片或视频，选择后自动匹配生成方式"}</span>
            </div>
            <Button aria-label="选择数字人形象" onClick={() => setPortraitPickerOpen(true)} disabled={!projectId || busy}>
              {portraitId ? "更换" : "选择"}
            </Button>
          </div>
          {portraitId && portraitSceneId ? (
            <div className="digital-human-app-asset-summary" aria-label="数字人素材详情">
              <Tag color="processing">{portraitMediaType === "video" ? "视频形象" : "图片形象"}</Tag>
              {portraitDetails.quality ? <Tag color={portraitDetails.quality === "已就绪" ? "success" : "warning"}>{portraitDetails.quality}</Tag> : null}
            </div>
          ) : null}
        </div>
        <div className="digital-human-app-field">
          <label>声音</label>
          <div className="digital-human-choice-row">
            <div>
              <strong>{displayedVoiceName}</strong>
              <span>{displayedVoiceDescription}</span>
            </div>
            <div className="digital-human-choice-actions">
              {displayedVoiceProfileId && !run ? <Button aria-label="试听当前声音" size="small" onClick={() => setVoicePickerOpen(true)} disabled={busy}>试听</Button> : null}
              <Button aria-label="更换口播声音" size="small" onClick={() => setVoicePickerOpen(true)} disabled={busy || Boolean(run)}>更换</Button>
              {voiceOverrideId && !run ? <Button aria-label="恢复人物默认声音" size="small" type="text" onClick={() => { setVoiceOverrideId(""); setVoiceOverrideName(""); }}>恢复人物默认</Button> : null}
            </div>
          </div>
        </div>
        <details className="digital-human-more-settings">
          <summary>发布文案与更多设置</summary>
          <div className="digital-human-app-quality-fields" aria-label="发布与封面文案">
            <div className="digital-human-app-field">
              <label htmlFor="digital-human-publish-title">发布标题</label>
              <Input id="digital-human-publish-title" value={publishTitle} onChange={(event) => setPublishTitle(event.target.value)} placeholder="可选；留空会自动生成" maxLength={55} />
            </div>
            <div className="digital-human-app-field">
              <label htmlFor="digital-human-publish-description">发布描述</label>
              <Input.TextArea id="digital-human-publish-description" rows={2} value={publishDescription} onChange={(event) => setPublishDescription(event.target.value)} placeholder="可选；留空会自动生成" maxLength={180} />
            </div>
            <div className="digital-human-app-field">
              <label htmlFor="digital-human-cover-title">封面标题</label>
              <Input id="digital-human-cover-title" value={coverTitle} onChange={(event) => setCoverTitle(event.target.value)} placeholder="可选；最多 24 个字" maxLength={24} status={coverTitle.length > 24 || coverTitle.split(/\r?\n/).some((line) => line.length > 12) ? "error" : undefined} />
            </div>
            <div className="digital-human-app-field">
              <label htmlFor="digital-human-hashtags">话题标签</label>
              <Input id="digital-human-hashtags" value={hashtagsText} onChange={(event) => setHashtagsText(event.target.value)} placeholder="可选；例如：门店经营 到店优惠" />
            </div>
          </div>
          <div className="digital-human-app-more-config-row">
            <Checkbox checked={subtitleEnabled} onChange={(event) => setSubtitleEnabled(event.target.checked)} disabled={busy}>
              添加可读字幕
            </Checkbox>
          </div>
        </details>
        {!workbenchV2 ? digitalHumanPrimaryActions : null}
        {contextDirty ? <Typography.Text type="warning">请先保存或放弃项目资料草稿，再开始生成。</Typography.Text> : null}
        <AssetPickerDialog
          open={portraitPickerOpen}
          kind="digital_human"
          selectedId={portraitId}
          onClose={() => setPortraitPickerOpen(false)}
          onSelect={(item: LibraryItemV2) => {
            setPortraitId(item.resource_id);
            setPortraitName(item.name);
            setPortraitSceneId("");
            setPortraitAssetRevisionId("");
            setPortraitMediaType("");
            setPortraitDetails({});
            setPortraitDefaultVoiceId(String(item.summary.default_voice_id || ""));
            setPortraitDefaultVoiceName(String(item.summary.default_voice_name || ""));
            setVoiceOverrideId("");
            setVoiceOverrideName("");
            setPortraitPickerOpen(false);
          }}
          onSelectScene={(item: LibraryItemV2, sceneId: string) => {
            const scene = item.scenes?.find((entry) => entry.scene_id === sceneId);
            const mediaType = scene?.preview_media_type || "";
            const inferredMode: DigitalHumanMode = mediaType === "video" ? "video_lipsync" : "image_talking";
            if (!changeDigitalHumanMode(inferredMode)) return;
            setPortraitId(item.resource_id);
            setPortraitName(item.name);
            setPortraitSceneId(sceneId);
            setPortraitMediaType(mediaType);
            setPortraitAssetRevisionId(scene?.source_revision_id || "");
            const width = Number(scene?.width || item.summary.width || item.summary.reference_width || 0);
            const height = Number(scene?.height || item.summary.height || item.summary.reference_height || 0);
            const durationMs = Number(scene?.duration_ms || item.summary.duration_ms || item.summary.reference_duration_ms || 0);
            setPortraitDetails({
              ...(width > 0 && height > 0 ? { width, height } : {}),
              ...(durationMs > 0 ? { durationMs } : {}),
              quality: item.status === "ready" ? "已就绪" : item.status,
            });
            setPortraitDefaultVoiceId(String(item.summary.default_voice_id || ""));
            setPortraitDefaultVoiceName(String(item.summary.default_voice_name || ""));
            setVoiceOverrideId("");
            setVoiceOverrideName("");
            setPortraitPickerOpen(false);
          }}
          context={{
            session_id: projectId || "app-center",
            step: "digital_human",
            purpose: "数字人口播形象",
            slot_id: "digital-human",
            allowed_kinds: ["digital_human"],
            required_capabilities: ["digital_human"],
            selection_mode: "single",
          }}
        />
        <AssetPickerDialog
          open={voicePickerOpen}
          kind="voice"
          selectedId={displayedVoiceProfileId}
          onClose={() => setVoicePickerOpen(false)}
          onSelect={(item: LibraryItemV2) => {
            setVoiceOverrideId(item.resource_id);
            setVoiceOverrideName(item.name);
            setVoicePickerOpen(false);
          }}
          context={{
            session_id: projectId || "app-center",
            step: "digital_human",
            purpose: "本次口播声音",
            slot_id: "digital-human-voice",
            allowed_kinds: ["voice"],
            required_capabilities: ["use"],
            selection_mode: "single",
          }}
        />
      </Card>

      <Card
        id="digital-human-workbench-result"
        title="生成结果"
        extra={workbenchV2 ? <Tag color={resultStatePresentation.color}>{resultStatePresentation.label}</Tag> : null}
        className="digital-human-app-card"
      >
        {!resultHistoryV1 ? (run ? (
          <div className="digital-human-app-run" aria-label="应用运行状态">
            <details className="digital-human-run-record">
              <summary>运行记录</summary>
              <div className="digital-human-app-run-meta">
                <span>运行：<code>{run.app_run_id}</code></span>
                <span>任务：<code>{run.session_id}</code></span>
              </div>
            </details>
            <Typography.Paragraph type="secondary">{projectionLabels[run.projection.when || ""] || "状态已读取"} · {taskStatusLabels[run.projection.task_status || "pending"] || run.projection.task_status || "待执行"}</Typography.Paragraph>
            {run.error_code ? <Alert type="warning" showIcon message={run.error_code} /> : null}
            <details className="digital-human-progress-disclosure">
              <summary>{["needs_review", "completed"].includes(run.state) ? "查看生成过程" : "查看生成进度"}</summary>
              <div className="digital-human-app-progress" aria-label="数字人生成进度">
                {[
                  [1, "准备内容"],
                  [2, "准备形象"],
                  [3, "生成配音"],
                  [4, "生成画面"],
                  [5, "添加字幕"],
                  [6, "完成成片"],
                ].map(([step, label]) => {
                  const stepStatus = run.step_status[String(step)] || "pending";
                  const statusLabel = ({ pending: "待处理", ready: "已准备", running: "处理中", done: "已完成", error: "需处理" } as Record<string, string>)[stepStatus] || stepStatus;
                  return <div key={String(step)} className={`digital-human-app-progress-step digital-human-app-progress-step--${stepStatus}`}>
                    <span className="digital-human-app-progress-index">{step}</span>
                    <span>{label}</span>
                    <Typography.Text type="secondary">{statusLabel}</Typography.Text>
                  </div>;
                })}
              </div>
            </details>
            {run.state === "failed" ? (
              <div className="digital-human-app-retry-plan" aria-label="受控重试计划">
                <Typography.Text strong>失败后受控重试</Typography.Text>
                <Typography.Text type="secondary">先记录根因和本次理由，系统才会释放一次重试；不会重复创建 Provider 任务。</Typography.Text>
                <Input.TextArea aria-label="失败原因" rows={2} value={retryRootCause} onChange={(event) => setRetryRootCause(event.target.value)} placeholder="失败原因，例如：TTS_PROVIDER_TIMEOUT" maxLength={500} disabled={busy} />
                <Input.TextArea aria-label="重试理由" rows={2} value={retryReason} onChange={(event) => setRetryReason(event.target.value)} placeholder="本次重试理由和修复动作" maxLength={500} disabled={busy} />
                <Button type="primary" onClick={() => void retryWithPlan()} disabled={busy || !retryRootCause.trim() || !retryReason.trim()}>提交计划并重试</Button>
              </div>
            ) : null}
            <div className="digital-human-app-actions">
              <Button type="primary" onClick={() => void mutateRun("accept")} disabled={busy || run.state !== "needs_review"}>确认接收结果</Button>
              {onOpenPublishCenter && ["needs_review", "completed"].includes(run.state) ? <Button onClick={() => void handoffToPublishing()} disabled={busy}>交给发布中心</Button> : null}
              <details className="digital-human-run-actions">
                <summary>更多操作</summary>
                <div>
                  <Button size="small" onClick={() => void refreshRun()} disabled={busy}>刷新状态</Button>
                  <Button size="small" onClick={() => void mutateRun("cancel")} disabled={busy || ["completed", "cancelled"].includes(run.state)}>取消</Button>
                  <Button size="small" onClick={() => void mutateRun("retry")} disabled={busy || run.state !== "cancelled" || run.app_version === APP_VERSION}>重试</Button>
                  {allowLocalExecute && ["draft", "queued", "running"].includes(run.state) ? <Button size="small" onClick={() => void mutateRun("execute")} disabled={busy}>开始生成</Button> : null}
                </div>
              </details>
            </div>
            {run.state === "cancelled" && run.app_version === APP_VERSION ? <Typography.Text type="secondary">本次生成已取消；需要重新制作时，请点击“新建运行”。</Typography.Text> : null}
            {(run.state === "needs_review" || run.state === "completed") ? <DigitalHumanResultPanel run={run} busy={busy} onDownload={(artifactKey = "final_video") => void downloadArtifact(run.session_id, artifactKey)} /> : null}
            <Typography.Text type="secondary">确认接收只完成本地人工交接，不代表抖音发布。</Typography.Text>
          </div>
        ) : (
          <Typography.Text type="secondary">选择文案和数字人形象后，生成进度和视频结果会显示在这里。</Typography.Text>
        )) : null}
        {resultHistoryV1 && run && run.state !== "completed" ? (
          <div className="digital-human-current-run">
            <div>
              <Typography.Text strong>
                {run.state === "needs_review"
                  ? "视频已经生成"
                  : run.state === "failed"
                    ? "这次没有生成成功"
                    : "正在制作视频"}
              </Typography.Text>
              <Typography.Text type="secondary">
                {run.state === "needs_review"
                  ? "请先预览成片；确认接收不会自动发布到平台。"
                  : run.state === "failed"
                    ? "左侧设置仍为你保留，可以检查后再试一次。"
                    : "完成后会自动出现在下方生成记录。"}
              </Typography.Text>
            </div>
            <div className="digital-human-current-run__actions">
              {run.state === "needs_review" ? (
                <Button
                  size="small"
                  type="primary"
                  onClick={() => void mutateRun("accept")}
                  disabled={busy}
                >
                  确认接收
                </Button>
              ) : null}
              <Button size="small" onClick={() => void refreshRun()} disabled={busy}>
                刷新
              </Button>
              {["draft", "queued", "running"].includes(run.state) ? (
                <Button size="small" onClick={() => void mutateRun("cancel")} disabled={busy}>
                  取消
                </Button>
              ) : null}
            </div>
            {run.state === "failed" ? (
              <details className="digital-human-current-run__retry">
                <summary>查看原因并重试</summary>
                <div>
                  {run.error_code ? (
                    <Typography.Text type="secondary">
                      失败原因：{run.error_code}
                    </Typography.Text>
                  ) : null}
                  <Input.TextArea
                    aria-label="失败原因"
                    rows={2}
                    value={retryRootCause}
                    onChange={(event) => setRetryRootCause(event.target.value)}
                    placeholder="记录已确认的失败原因"
                    maxLength={500}
                    disabled={busy}
                  />
                  <Input.TextArea
                    aria-label="重试理由"
                    rows={2}
                    value={retryReason}
                    onChange={(event) => setRetryReason(event.target.value)}
                    placeholder="说明本次修复动作，避免重复无效调用"
                    maxLength={500}
                    disabled={busy}
                  />
                  <Button
                    size="small"
                    type="primary"
                    onClick={() => void retryWithPlan()}
                    disabled={busy || !retryRootCause.trim() || !retryReason.trim()}
                  >
                    确认后重试
                  </Button>
                </div>
              </details>
            ) : null}
          </div>
        ) : null}
        {resultHistoryV1 && projectId ? (
          <ProjectGenerationHistory
            projectId={projectId}
            appId={APP_ID}
            refreshKey={run ? `${run.app_run_id}:${run.state}:${run.state_version}:${run.updated_at}` : ""}
            onPublish={onOpenPublishCenter
              ? (record, item) => handoffHistoryVideo(
                record,
                item as GenerationVideoResultItem,
              )
              : undefined}
          />
        ) : null}
      </Card>
    </section>
  );
  if (workbenchV2) {
    return (
      <AppWorkbenchShell
        eyebrow="视频创作"
        title="数字人口播视频"
        description="把一段文案和数字人形象，变成可以直接检查和发布的口播视频。"
        onBack={onBack}
        adoptedContent={legacyView}
        adoptedInputFooter={digitalHumanPrimaryActions}
        adoptedInputId="digital-human-workbench-input"
        adoptedResultId="digital-human-workbench-result"
        resultState={resultState}
        showAdoptedState={false}
      />
    );
  }
  return legacyView;
}

function SpaceButtons({ onBack }: { onBack: () => void }) {
  return <Button onClick={onBack}>返回应用中心</Button>;
}
