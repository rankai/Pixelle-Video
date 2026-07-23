import { Image as ImageIcon, LayoutTemplate, Mic2, Package, Search, Upload, UserRound, Video, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { assetBlobUrl, createVoiceProfileV2, LibraryItemV2, listLibraryItemsV2, uploadMediaAssetV2 } from "../../../api";
import type { PickerContext } from "../model/ux0Contracts";
import { AssetUploadQueue } from "./AssetUploadQueue";
import { recordAssetTelemetry } from "../model/assetTelemetry";

type PickerKind = "video" | "image" | "audio" | "voice" | "digital_human" | "template" | "brand";

const labels: Record<PickerKind, string> = {
  video: "视频",
  image: "图片",
  audio: "音频",
  voice: "音色",
  digital_human: "数字人",
  template: "模板",
  brand: "品牌",
};

const icons = { video: Video, image: ImageIcon, audio: Mic2, voice: Mic2, digital_human: UserRound, template: LayoutTemplate, brand: Package };

export function AssetPickerDialog({
  open,
  kind,
  selectedId,
  selectionMode = "single",
  selectedIds = [],
  onClose,
  onSelect,
  onSelectMany,
  onSelectScene,
  context,
}: {
  open: boolean;
  kind: PickerKind;
  selectedId?: string;
  selectionMode?: "single" | "multiple";
  selectedIds?: string[];
  onClose: () => void;
  onSelect: (item: LibraryItemV2) => void;
  onSelectMany?: (items: LibraryItemV2[]) => void;
  onSelectScene?: (item: LibraryItemV2, sceneId: string) => void;
  context?: PickerContext;
}) {
  const [query, setQuery] = useState("");
  const [favoriteOnly, setFavoriteOnly] = useState(false);
  const [items, setItems] = useState<LibraryItemV2[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [activeItem, setActiveItem] = useState<LibraryItemV2 | null>(null);
  const [multiSelected, setMultiSelected] = useState<LibraryItemV2[]>([]);
  const [uploading, setUploading] = useState(false);
  const [pendingItem, setPendingItem] = useState<LibraryItemV2 | null>(null);
  const [pendingScene, setPendingScene] = useState<string>("");
  const [queueOpen, setQueueOpen] = useState(false);
  const multiSelectionInitialized = useRef(false);
  const selectedIdsKey = selectedIds.join("|");

  useEffect(() => {
    if (!open) return;
    recordAssetTelemetry("asset_picker_opened", { kind, entry: "picker" });
    setError("");
    let cancelled = false;
    setLoading(true);
    void listLibraryItemsV2(kind, query, { favorite: favoriteOnly || undefined, sort: "recent" })
      .then((result) => {
        if (!cancelled) {
          setItems(result.items);
          if (selectionMode === "multiple") {
            const selectedKeys = new Set(selectedIdsKey.split("|").filter(Boolean));
            const visibleKeys = new Set(result.items.map((item) => item.resource_id));
            setMultiSelected((current) => {
              if (!multiSelectionInitialized.current) {
                multiSelectionInitialized.current = true;
                return result.items.filter((item) => selectedKeys.has(item.resource_id));
              }
              // Keep selections that are outside the current search result;
              // changing the query must not silently drop already selected
              // assets from the final multi-select confirmation.
              return [
                ...current.filter((item) => !visibleKeys.has(item.resource_id)),
                ...result.items.filter((item) => current.some((selected) => selected.resource_id === item.resource_id)),
              ];
            });
          }
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [favoriteOnly, kind, open, query, selectedIdsKey, selectionMode]);

  useEffect(() => {
    if (!open) return;
    setActiveItem(null);
    setMultiSelected([]);
    multiSelectionInitialized.current = false;
    setPendingItem(null);
    setPendingScene("");
    setError("");
  }, [kind, open]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); onClose(); return; }
      if (event.key !== "Tab") return;
      const dialog = document.querySelector<HTMLElement>(".library-picker-dialog");
      if (!dialog) return;
      const focusable = Array.from(dialog.querySelectorAll<HTMLElement>("button, input, select, textarea, [tabindex]:not([tabindex='-1'])")).filter((element) => !element.hasAttribute("disabled"));
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose, open]);

  if (!open) return null;
  async function quickUpload(file: File) {
    if (!(kind === "video" || kind === "image" || kind === "audio" || kind === "voice")) return;
    setUploading(true);
    setError("");
    try {
      const uploaded = await uploadMediaAssetV2(kind === "voice" ? "audio" : kind, file.name, file);
      const item: LibraryItemV2 = {
        resource_id: uploaded.asset_id,
        kind,
        name: uploaded.name,
        description: uploaded.description,
        status: uploaded.status,
        cover_url: uploaded.thumbnail_url || uploaded.file_url,
        file_url: uploaded.file_url,
        tags: [],
        favorite: false,
        created_at: uploaded.created_at,
        updated_at: uploaded.updated_at,
        summary: { bytes: Number(uploaded.revision.bytes || 0), duration_ms: Number(uploaded.revision.duration_ms || 0), width: Number(uploaded.revision.width || 0), height: Number(uploaded.revision.height || 0) },
      };
      if (kind === "voice") {
        const voice = await createVoiceProfileV2({ name: file.name, audio_asset_id: uploaded.asset_id });
        setPendingItem(voice);
        return;
      }
      if (selectionMode === "multiple") {
        setMultiSelected((current) => current.some((entry) => entry.resource_id === item.resource_id) ? current : [...current, item]);
      } else {
        setPendingItem(item);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setUploading(false);
    }
  }
  return (
    <div className="modal-backdrop asset-modal-backdrop" role="presentation">
      <section className="modal library-picker-dialog" role="dialog" aria-modal="true" aria-label={`选择${labels[kind]}资产`}>
        <header className="modal-title">
          <div>
            <h2>选择{labels[kind]}资产</h2>
            <p>{context?.purpose ? `${context.purpose} · ` : ""}先预览，再确认；确认后才会把稳定资源 ID 写入生产流。</p>
          </div>
          <div className="library-picker-header-actions">
            {(kind === "video" || kind === "image" || kind === "audio" || kind === "voice") ? <button type="button" className="library-picker-upload" onClick={() => setQueueOpen(true)}><Upload size={15} /> 快捷上传</button> : null}
            <button type="button" onClick={onClose} aria-label="关闭选择器"><X size={18} /></button>
          </div>
        </header>
        <label className="library-picker-search">
          <Search size={16} />
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={`搜索${labels[kind]}名称或文件名`} autoFocus />
        </label>
        <div className="library-picker-filterbar"><button type="button" className={favoriteOnly ? "active" : ""} onClick={() => setFavoriteOnly((value) => !value)} aria-pressed={favoriteOnly}>仅看收藏</button><span>最近使用优先</span></div>
        {loading ? <div className="empty-state">正在加载资产…</div> : null}
        {error ? <div className="asset-center-v2-error">{error}</div> : null}
        <div className="library-picker-grid">
          {items.map((item) => {
            const Icon = icons[item.kind];
            const mediaSrc = item.cover_url || item.file_url || "";
            const compatibility = getPickerCompatibility(item, context);
            const choose = () => {
              if (compatibility.reason) {
                recordAssetTelemetry("asset_picker_incompatible_seen", { kind: item.kind, entry: "picker" });
                if (selectionMode === "multiple") setError(`当前素材不可用于${context?.purpose || "此步骤"}：${compatibility.reason}`);
                else setPendingItem(item);
                return;
              }
              if (item.kind === "digital_human" && item.scenes?.length && selectionMode === "single") {
                setActiveItem(item); setPendingItem(item); setPendingScene("");
              } else if (selectionMode === "multiple") {
                setMultiSelected((current) => current.some((entry) => entry.resource_id === item.resource_id) ? current.filter((entry) => entry.resource_id !== item.resource_id) : [...current, item]);
              } else setPendingItem(item);
            };
            return (
              <button type="button" key={item.resource_id} className={`library-picker-card ${(selectedId === item.resource_id || pendingItem?.resource_id === item.resource_id || selectedIds.includes(item.resource_id) || multiSelected.some((entry) => entry.resource_id === item.resource_id)) ? "selected" : ""}`} aria-disabled={Boolean(compatibility.reason)} title={compatibility.reason || undefined} onClick={choose} onDoubleClick={() => { if (selectionMode === "single" && !compatibility.reason && item.kind !== "digital_human") { recordAssetTelemetry("asset_picker_confirmed", { kind: item.kind, entry: "picker" }); onSelect(item); onClose(); } }} onKeyDown={(event) => { if (event.key === "Enter" && selectionMode === "single" && !compatibility.reason && item.kind !== "digital_human") { event.preventDefault(); recordAssetTelemetry("asset_picker_confirmed", { kind: item.kind, entry: "picker" }); onSelect(item); onClose(); } }}>
                <div className={`library-picker-card-media kind-${item.kind}`}>
                  {mediaSrc && (item.kind === "video" || item.kind === "image" || item.kind === "digital_human") ? <PickerProtectedImage src={mediaSrc} alt="" /> : <Icon size={28} />}
                </div>
                <strong>{item.name}</strong>
                <span>{compatibility.reason ? `不可用于当前步骤：${compatibility.reason}` : item.description || labels[item.kind]}</span>
              </button>
            );
          })}
          {!loading && !items.length ? <div className="empty-state">没有匹配的资产。</div> : null}
        </div>
        {pendingItem ? <div className="library-picker-preview" aria-label="当前资产预览"><div>{pendingItem.cover_url && (pendingItem.kind === "image" || pendingItem.kind === "digital_human") ? <PickerProtectedImage src={pendingItem.cover_url} alt={pendingItem.name} /> : pendingItem.kind === "voice" || pendingItem.kind === "audio" ? <PickerProtectedAudio src={pendingItem.file_url || pendingItem.cover_url || ""} title={pendingItem.name} /> : <strong>{labels[pendingItem.kind]}</strong>}</div><section><strong>{pendingItem.name}</strong><span>{pendingItem.description || "暂无说明"}</span><small>{pendingItem.kind === "video" ? "播放预览可在详情中打开" : "当前选择不会写入生产流，点击底部确认后才会回填"}</small></section></div> : null}
        {activeItem?.kind === "digital_human" ? (
          <div className="library-picker-scene-panel" aria-label="选择数字人场景">
            <div><strong>{activeItem.name} · 选择场景</strong><button type="button" onClick={() => setActiveItem(null)}>返回人物列表</button></div>
            <div className="library-picker-scene-grid">
                  {(activeItem.scenes || []).map((scene) => (
                <button type="button" key={scene.scene_id} className={pendingScene === scene.scene_id ? "selected" : ""} onClick={() => { setPendingItem(activeItem); setPendingScene(scene.scene_id); }}>
                  {scene.preview_url ? <PickerProtectedImage src={scene.preview_url} alt="" /> : null}<strong>{scene.name}</strong><span>{scene.shot_size || "默认景别"}</span>
                </button>
                  ))}
            </div>
          </div>
        ) : null}
        {selectionMode === "multiple" ? <footer className="library-picker-multi-footer"><span>已选 {multiSelected.length} 项</span><button type="button" className="primary" disabled={!multiSelected.length} onClick={() => { recordAssetTelemetry("asset_picker_confirmed", { kind, entry: "picker" }); onSelectMany?.(multiSelected); }}>确认选择</button></footer> : <footer className="library-picker-multi-footer"><span>{pendingItem ? `已预览：${pendingItem.name}${pendingScene ? " · 已选场景" : ""}` : "请选择并预览一个资产"}</span><span>{pendingItem && context?.required_capabilities?.length ? `适配能力：${context.required_capabilities.join("、")}` : ""}</span>{pendingItem && getPickerCompatibility(pendingItem, context).reason ? <small role="alert">{getPickerCompatibility(pendingItem, context).reason}</small> : null}<button type="button" className="primary" disabled={!pendingItem || Boolean(pendingItem && getPickerCompatibility(pendingItem, context).reason) || (pendingItem?.kind === "digital_human" && Boolean(pendingItem.scenes?.length) && !pendingScene)} onClick={() => { if (!pendingItem || getPickerCompatibility(pendingItem, context).reason) return; recordAssetTelemetry("asset_picker_confirmed", { kind: pendingItem.kind, entry: "picker" }); if (pendingScene && onSelectScene) onSelectScene(pendingItem, pendingScene); else onSelect(pendingItem); onClose(); }}>确认使用</button></footer>}
      </section>
      {queueOpen ? <AssetUploadQueue allowedKinds={kind === "voice" ? ["audio"] : [kind as "image" | "video" | "audio"]} domainKind={kind === "voice" ? "voice" : undefined} onClose={() => setQueueOpen(false)} onUploaded={async () => { const result = await listLibraryItemsV2(kind, "", { sort: "recent", limit: 1 }); const newest = result.items[0]; if (newest) setPendingItem(newest); setQueueOpen(false); }} /> : null}
    </div>
  );
}

function PickerProtectedImage({ src, alt }: { src: string; alt: string }) {
  const [resolved, setResolved] = useState("");
  useEffect(() => {
    let disposed = false;
    let current = "";
    setResolved("");
    void assetBlobUrl(src).then((url) => {
      if (disposed) { URL.revokeObjectURL(url); return; }
      current = url;
      setResolved(url);
    }).catch(() => { if (!disposed) setResolved(src); });
    return () => { disposed = true; if (current) URL.revokeObjectURL(current); };
  }, [src]);
  return <img src={resolved || src} alt={alt} loading="lazy" />;
}

function PickerProtectedAudio({ src, title }: { src: string; title: string }) {
  const [resolved, setResolved] = useState("");
  useEffect(() => {
    let disposed = false;
    let current = "";
    setResolved("");
    void assetBlobUrl(src).then((url) => {
      if (disposed) { URL.revokeObjectURL(url); return; }
      current = url;
      setResolved(url);
    }).catch(() => { if (!disposed) setResolved(src); });
    return () => { disposed = true; if (current) URL.revokeObjectURL(current); };
  }, [src]);
  return <audio controls src={resolved || src} aria-label={`${title}试听`} />;
}

function getPickerCompatibility(item: LibraryItemV2, context?: PickerContext): { reason?: string } {
  if (!context) return {};
  if (!context.allowed_kinds.includes(item.kind)) return { reason: `当前步骤需要${context.allowed_kinds.join("、")}资产` };
  if (item.status === "archived") return { reason: "资产已归档，请先恢复" };
  const capabilities = item.capabilities || ["preview", "use", "favorite"];
  const missing = context.required_capabilities.filter((capability) => !capabilities.includes(capability));
  if (missing.length) return { reason: `缺少${missing.join("、")}能力` };
  if (context.max_duration_ms !== undefined) {
    const duration = Number(item.summary.duration_ms || item.summary.reference_duration_ms || 0);
    if (duration > context.max_duration_ms) return { reason: `时长超过当前步骤上限 ${Math.round(context.max_duration_ms / 1000)} 秒` };
  }
  if (context.aspect_ratio) {
    const ratio = Number(item.summary.aspect_ratio || 0);
    if (ratio && Math.abs(ratio - context.aspect_ratio) > 0.15) return { reason: "画面比例与当前槽位不匹配" };
  }
  return {};
}
