import { FilePlus2, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { cancelMediaUploadV2, createVoiceProfileV2, finalizeDeferredMediaUploadV2, setLibraryTagsV2, uploadDeferredMediaAssetV2 } from "../../../api";
import { recordAssetTelemetry } from "../model/assetTelemetry";

type UploadKind = "image" | "video" | "audio";
type QueueStatus = "queued" | "uploading" | "awaiting_duplicate_decision" | "finalized" | "failed" | "cancelled" | "needs_file";
type QueueEntry = { id: string; file: File; declaredSize: number; kind: UploadKind; preview: string; status: QueueStatus; progress: number; uploadId?: string; sha256?: string; error?: string; duplicateAssetId?: string | null; preflightError?: boolean };
const MAX_UPLOAD_BYTES = 100 * 1024 * 1024;
const UPLOAD_KIND_LABELS: Record<UploadKind, string> = { image: "图片", video: "视频", audio: "音频" };

function inferKind(file: File): UploadKind | null {
  if (file.type.startsWith("image/")) return "image";
  if (file.type.startsWith("video/")) return "video";
  if (file.type.startsWith("audio/")) return "audio";
  const extension = file.name.split(".").pop()?.toLowerCase();
  if (["png", "jpg", "jpeg", "webp", "gif"].includes(extension || "")) return "image";
  if (["mp4", "mov", "webm", "m4v"].includes(extension || "")) return "video";
  if (["mp3", "wav", "flac", "m4a", "aac", "ogg"].includes(extension || "")) return "audio";
  return null;
}

export function AssetUploadQueue({ onClose, onUploaded, allowedKinds = ["image", "video", "audio"], domainKind }: { onClose: () => void; onUploaded: () => Promise<void>; allowedKinds?: UploadKind[]; domainKind?: "voice" }) {
  const [entries, setEntries] = useState<QueueEntry[]>(() => {
    try {
      const saved = JSON.parse(window.localStorage.getItem("pixelle.asset.upload-queue.v1") || "[]") as Array<{ id: string; filename: string; size: number; kind: UploadKind; status: QueueStatus; uploadId?: string; sha256?: string; error?: string }>;
      return saved.filter((item) => item.status !== "finalized").map((item) => ({ id: item.id, file: new File([], item.filename), declaredSize: item.size, kind: item.kind, preview: "", status: "needs_file", progress: 0, uploadId: item.uploadId, sha256: item.sha256, error: item.error || "应用已重启，请重新选择原文件继续上传" }));
    } catch { return []; }
  });
  const [batchName, setBatchName] = useState("");
  const [batchTags, setBatchTags] = useState("");
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const controllers = useRef(new Map<string, AbortController>());
  const cancelRequested = useRef(false);
  const entriesRef = useRef(entries);
  const allowedKindsLabel = allowedKinds.map((kind) => UPLOAD_KIND_LABELS[kind]).join("、");
  const allowedKindsAccept = allowedKinds.map((kind) => `${kind}/*`).join(",");
  const dialogLabel = domainKind === "voice" ? "添加音色参考音频" : allowedKinds.length === 1 ? `添加${allowedKindsLabel}资产` : "批量添加资产";
  const dialogTitle = domainKind === "voice" ? "添加音色参考" : allowedKinds.length === 1 ? `添加${allowedKindsLabel}资产` : "添加企业资产";
  const completeCount = entries.filter((entry) => entry.status === "finalized").length;
  const failedCount = entries.filter((entry) => entry.status === "failed").length;
  const canStart = entries.some((entry) => entry.status === "queued" || entry.status === "failed");

  useEffect(() => {
    entriesRef.current = entries;
    const metadata = entries.filter((entry) => entry.status !== "finalized").map((entry) => ({ id: entry.id, filename: entry.file.name, size: entry.declaredSize, kind: entry.kind, status: entry.status, uploadId: entry.uploadId, sha256: entry.sha256, error: entry.error }));
    window.localStorage.setItem("pixelle.asset.upload-queue.v1", JSON.stringify(metadata));
  }, [entries]);

  useEffect(() => () => {
    entriesRef.current.forEach((entry) => { if (entry.preview) URL.revokeObjectURL(entry.preview); });
    controllers.current.forEach((controller) => controller.abort());
  }, []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === "Escape" && !busy) { event.preventDefault(); onClose(); } };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [busy, onClose]);

  async function hashFile(file: File) {
    if (!window.crypto?.subtle) return undefined;
    const digest = await window.crypto.subtle.digest("SHA-256", await file.arrayBuffer());
    return Array.from(new Uint8Array(digest)).map((value) => value.toString(16).padStart(2, "0")).join("");
  }

  async function preflightFile(file: File, kind: UploadKind): Promise<string | undefined> {
    if (file.size <= 0) return "文件为空，无法上传";
    if (file.size > MAX_UPLOAD_BYTES) return "文件超过 100 MB 上传上限";
    if (kind === "image") {
      try {
        if (typeof createImageBitmap === "function") {
          const bitmap = await createImageBitmap(file);
          const valid = bitmap.width > 0 && bitmap.height > 0;
          bitmap.close();
          if (!valid) return "图片尺寸无效";
        }
      } catch {
        return "图片无法解析，请检查文件是否损坏";
      }
    }
    if (kind === "video" || kind === "audio") {
      const objectUrl = URL.createObjectURL(file);
      try {
        const media = document.createElement(kind);
        media.preload = "metadata";
        const metadataReady = new Promise<boolean>((resolve) => {
          const timer = window.setTimeout(() => resolve(false), 5000);
          media.onloadedmetadata = () => { window.clearTimeout(timer); resolve(Number.isFinite(media.duration) || kind === "video"); };
          media.onerror = () => { window.clearTimeout(timer); resolve(false); };
        });
        media.src = objectUrl;
        if (!(await metadataReady)) return `${kind === "video" ? "视频" : "音频"}无法解析，请检查文件是否损坏`;
      } finally {
        URL.revokeObjectURL(objectUrl);
      }
    }
    return undefined;
  }

  async function addFiles(fileList: FileList | File[]) {
    const files = Array.from(fileList);
    const next: QueueEntry[] = [];
    for (const file of files) {
      const inferred = inferKind(file);
      const kind = inferred || allowedKinds[0] || "image";
      let preflightError: string | undefined;
      if (!inferred) preflightError = "不支持的文件格式，请选择图片、视频或音频";
      else if (!allowedKinds.includes(inferred)) preflightError = `当前选择器不支持${inferred === "video" ? "视频" : inferred === "audio" ? "音频" : "图片"}`;
      else preflightError = await preflightFile(file, inferred);
      const digest = await hashFile(file).catch(() => undefined);
      const recovery = inferred ? entries.find((entry) => entry.status === "needs_file" && entry.file.name === file.name && entry.declaredSize === file.size && entry.kind === inferred) : undefined;
      if (recovery?.sha256 && digest && recovery.sha256 !== digest) {
        next.push({ ...recovery, file, preview: URL.createObjectURL(file), status: "failed", progress: 0, error: "原文件校验失败，SHA-256 与中断记录不一致", preflightError: true });
        continue;
      }
      next.push({ id: recovery?.id || `${file.name}-${file.size}-${file.lastModified}-${Math.random()}`, file, declaredSize: file.size, kind, preview: URL.createObjectURL(file), status: preflightError ? "failed" : "queued", progress: 0, uploadId: undefined, sha256: digest, error: preflightError, preflightError: Boolean(preflightError) });
    }
    setEntries((current) => [...current.filter((entry) => entry.status !== "needs_file" || !files.some((file) => file.name === entry.file.name && file.size === entry.declaredSize)), ...next]);
  }

  function removeEntry(id: string) {
    const entry = entries.find((item) => item.id === id);
    if (entry) URL.revokeObjectURL(entry.preview);
    controllers.current.get(id)?.abort();
    if (entry?.uploadId && (entry.status === "uploading" || entry.status === "awaiting_duplicate_decision")) void cancelMediaUploadV2(entry.uploadId).catch(() => undefined);
    setEntries((current) => current.filter((item) => item.id !== id));
  }

  async function start() {
    if (busy) return;
    cancelRequested.current = false;
    setBusy(true);
    recordAssetTelemetry("asset_upload_started", { entry: "center" });
    const candidates = entries.filter((entry) => entry.status === "queued" || (entry.status === "failed" && !entry.preflightError));
    for (const entry of candidates) {
      if (cancelRequested.current) break;
      const controller = new AbortController();
      controllers.current.set(entry.id, controller);
        setEntries((current) => current.map((item) => item.id === entry.id ? { ...item, status: "uploading", progress: 0, error: undefined } : item));
      try {
        const result = await uploadDeferredMediaAssetV2(entry.kind, batchName.trim() && candidates.length === 1 ? batchName.trim() : batchName.trim() ? `${batchName.trim()} · ${entry.file.name}` : entry.file.name, entry.file, (progress) => setEntries((current) => current.map((item) => item.id === entry.id ? { ...item, progress } : item)), (uploadId) => setEntries((current) => current.map((item) => item.id === entry.id ? { ...item, uploadId } : item)), controller.signal);
        if (result.upload.status === "uploaded") {
          const finalized = await finalizeDeferredMediaUploadV2(result.upload.upload_id);
          const assetId = finalized.asset?.asset_id || finalized.upload.duplicate_asset_id;
          const domainId = domainKind === "voice" && assetId ? (await createVoiceProfileV2({ name: entry.file.name, audio_asset_id: assetId })).resource_id : assetId;
          if (domainId && batchTags.trim()) await setLibraryTagsV2(domainKind || entry.kind, domainId, batchTags.split(/[，,]/).map((tag) => tag.trim()).filter(Boolean));
          setEntries((current) => current.map((item) => item.id === entry.id ? { ...item, status: "finalized", progress: 100, sha256: String(result.upload.sha256 || item.sha256 || "") } : item));
          await onUploaded();
        } else {
          setEntries((current) => current.map((item) => item.id === entry.id ? { ...item, status: "awaiting_duplicate_decision", progress: 100, sha256: String(result.upload.sha256 || item.sha256 || ""), duplicateAssetId: result.upload.duplicate_asset_id || null } : item));
        }
        recordAssetTelemetry("asset_upload_succeeded", { kind: entry.kind, entry: "center" });
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        setEntries((current) => current.map((item) => item.id === entry.id ? { ...item, status: controller.signal.aborted ? "cancelled" : "failed", error: message } : item));
        recordAssetTelemetry(controller.signal.aborted ? "asset_upload_cancelled" : "asset_upload_failed", { kind: entry.kind, entry: "center" });
      } finally {
        controllers.current.delete(entry.id);
      }
    }
    setBusy(false);
  }

  async function finalize(entry: QueueEntry, policy: "reuse_existing" | "attach_revision" | "create_separate") {
    if (!entry.uploadId) return;
    try {
      const result = await finalizeDeferredMediaUploadV2(entry.uploadId, policy, policy === "attach_revision" ? entry.duplicateAssetId || undefined : undefined);
      const assetId = result.asset?.asset_id || result.upload.duplicate_asset_id;
      const domainId = domainKind === "voice" && assetId ? (await createVoiceProfileV2({ name: entry.file.name, audio_asset_id: assetId })).resource_id : assetId;
      if (domainId && batchTags.trim()) await setLibraryTagsV2(domainKind || entry.kind, domainId, batchTags.split(/[，,]/).map((tag) => tag.trim()).filter(Boolean));
      setEntries((current) => current.map((item) => item.id === entry.id ? { ...item, status: "finalized", duplicateAssetId: result.upload.duplicate_asset_id || null } : item));
      recordAssetTelemetry("asset_duplicate_resolved", { kind: entry.kind, entry: "center" });
      await onUploaded();
    } catch (error) {
      setEntries((current) => current.map((item) => item.id === entry.id ? { ...item, status: "failed", error: error instanceof Error ? error.message : String(error) } : item));
    }
  }

  async function cancelAll() {
    cancelRequested.current = true;
    for (const entry of entries) {
      controllers.current.get(entry.id)?.abort();
      if (entry.uploadId && entry.status === "uploading") await cancelMediaUploadV2(entry.uploadId).catch(() => undefined);
    }
    setEntries((current) => current.map((item) => item.status === "uploading" || item.status === "queued" ? { ...item, status: "cancelled" } : item));
  }

  async function closeQueue() {
    if (busy) await cancelAll();
    onClose();
  }

  const summary = useMemo(() => `${completeCount}/${entries.length} 已入库${failedCount ? ` · ${failedCount} 个失败，可单独重试` : ""}${entries.some((entry) => entry.status === "needs_file") ? " · 重启后请重新选择原文件" : ""}`, [completeCount, entries, failedCount]);
  return <div className="asset-center-v2-backdrop asset-upload-backdrop" role="presentation"><section className="asset-center-v2-upload asset-upload-queue" role="dialog" aria-modal="true" aria-label={dialogLabel}>
    <header><div><span>共享上传队列</span><h3>{dialogTitle}</h3></div><button type="button" onClick={() => void closeQueue()} aria-label={busy ? "取消上传并关闭队列" : "关闭上传队列"}><X size={18} /></button></header>
    <label className={`asset-upload-dropzone${dragging ? " dragging" : ""}`} onDragOver={(event) => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={(event) => { event.preventDefault(); setDragging(false); addFiles(event.dataTransfer.files); }}><FilePlus2 size={22} /><strong>拖放{allowedKindsLabel}到这里</strong><span>也可以点击选择{allowedKinds.length === 1 ? "文件" : "多个文件"}；系统会自动识别类型并保留本地预览</span><input type="file" multiple accept={allowedKindsAccept} onChange={(event) => { if (event.target.files) addFiles(event.target.files); event.currentTarget.value = ""; }} /></label>
    <div className="asset-upload-batch-fields"><label>批量名称（可选）<input value={batchName} onChange={(event) => setBatchName(event.target.value)} placeholder="留空使用文件名" /></label><label>批量标签（可选）<input value={batchTags} onChange={(event) => setBatchTags(event.target.value)} placeholder="门店、主推" /></label></div>
    <div className="asset-upload-queue-list">{entries.map((entry) => <div className="asset-upload-queue-row" key={entry.id}><div className={`asset-upload-queue-thumb kind-${entry.kind}`}>{entry.preview && entry.kind === "image" ? <img src={entry.preview} alt="" /> : entry.preview && entry.kind === "video" ? <video src={entry.preview} muted /> : <span>{entry.kind === "audio" ? "音频" : "文件"}</span>}</div><div className="asset-upload-queue-main"><strong>{entry.file.name}</strong><span>{entry.kind === "image" ? "图片" : entry.kind === "video" ? "视频" : "音频"} · {(entry.declaredSize / 1024 / 1024).toFixed(1)} MB</span>{entry.status === "uploading" ? <progress max={100} value={entry.progress} /> : null}{entry.status === "failed" || entry.status === "needs_file" ? <small className="asset-upload-error">{entry.error || "上传失败"}</small> : null}{entry.status === "awaiting_duplicate_decision" ? <div className="asset-upload-duplicate"><span>上传完成，请选择重复处理策略</span><button type="button" onClick={() => void finalize(entry, "reuse_existing")}>使用已有资产</button><button type="button" onClick={() => void finalize(entry, "attach_revision")}>作为新版本</button><button type="button" onClick={() => void finalize(entry, "create_separate")}>创建独立资产</button></div> : null}</div><span className="asset-upload-queue-status">{entry.status === "finalized" ? "已入库" : entry.status === "cancelled" ? "已取消" : entry.status === "needs_file" ? "重启后需重选" : entry.status === "failed" ? "失败" : entry.status === "awaiting_duplicate_decision" ? "待确认" : entry.status === "uploading" ? `${entry.progress}%` : "待上传"}</span><button type="button" onClick={() => removeEntry(entry.id)} aria-label={`移除${entry.file.name}`}><X size={15} /></button></div>)}</div>
    <footer><span>{summary}</span><div>{busy ? <button type="button" onClick={() => void cancelAll()}>取消上传</button> : null}<button type="button" className="primary" onClick={() => void start()} disabled={!canStart || busy}>{busy ? "上传中…" : "开始上传"}</button><button type="button" onClick={() => void closeQueue()}>{busy ? "取消并关闭" : "关闭"}</button></div></footer>
  </section></div>;
}
