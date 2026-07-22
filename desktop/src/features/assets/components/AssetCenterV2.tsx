import {
  Image as ImageIcon,
  LayoutTemplate,
  Mic2,
  Package,
  PlayCircle,
  RefreshCw,
  Search,
  Upload,
  UserRound,
  Video,
  X,
  Check,
  ChevronDown,
  Grid2X2,
  List as ListIcon,
} from "lucide-react";
import { Component, ErrorInfo, ReactNode, useEffect, useMemo, useRef, useState } from "react";
import {
  archiveDigitalHumanSceneV2,
  archiveLibraryItemV2,
  addAssetCollectionItemV2,
  activateMediaAssetRevisionV2,
  AssetCollectionV2,
  createBrandKitV2,
  createAssetCollectionV2,
  createDigitalHumanV2,
  createDigitalHumanSceneV2,
  createTemplateV2,
  previewTemplateV2,
  cancelMediaUploadV2,
  createMediaAssetRevisionV2,
  bulkLibraryActionV2,
  listLibraryItemsV2,
  listLibraryFacetsV2,
  listAssetCollectionsV2,
  listResourceUsageV2,
  listMediaAssetRevisionsV2,
  LibraryItemV2,
  patchBrandKitV2,
  patchDigitalHumanSceneV2,
  patchDigitalHumanV2,
  patchMediaAssetV2,
  patchTemplateV2,
  removeAssetCollectionItemV2,
  reorderDigitalHumanScenesV2,
  restoreLibraryItemV2,
  setLibraryFavoriteV2,
  setLibraryTagsV2,
  uploadMediaAssetV2,
} from "../../../api";
import { recordAssetTelemetry } from "../model/assetTelemetry";
import { toAssetViewModel } from "../model/assetViewModel";
import { AssetUploadQueue } from "./AssetUploadQueue";
import { BrandKitEditor, TemplateLayoutEditor } from "./AssetDomainEditors";
import {
  AssetImageInspector,
  defaultTemplateLayoutContract,
  formatBytes,
  formatLocalDate,
  kindIcons,
  ProtectedAssetImage,
  ProtectedAssetMedia,
  summaryText,
  type AssetKind,
} from "./AssetCenterPrimitives";
import "../styles/assets.css";

type AssetFilter = "all" | AssetKind;

const filters: Array<{ key: AssetFilter; label: string }> = [
  { key: "all", label: "全部" },
  { key: "video", label: "视频" },
  { key: "image", label: "图片" },
  { key: "digital_human", label: "数字人" },
  { key: "voice", label: "音色" },
  { key: "audio", label: "音频" },
  { key: "template", label: "模板" },
  { key: "brand", label: "品牌" },
];

const kindLabels: Record<AssetKind, string> = {
  video: "视频",
  image: "图片",
  audio: "音频",
  voice: "音色",
  digital_human: "数字人",
  brand: "品牌",
  template: "模板",
};

type AssetCenterProps = { onUse?: (item: LibraryItemV2, sceneId?: string) => void };

export function AssetCenterV2(props: AssetCenterProps) {
  return <AssetCenterErrorBoundary><AssetCenterV2Content {...props} /></AssetCenterErrorBoundary>;
}

class AssetCenterErrorBoundary extends Component<{ children: ReactNode }, { hasError: boolean }> {
  state = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Asset center render error", error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      return <div className="asset-center-v2-error" role="alert"><strong>企业资产页面暂时不可用</strong><span>可以重试页面，或打开诊断查看服务状态。</span><button type="button" onClick={() => this.setState({ hasError: false })}>重试</button></div>;
    }
    return this.props.children;
  }
}

function AssetCenterV2Content({ onUse }: AssetCenterProps) {
  const [filter, setFilter] = useState<AssetFilter>("all");
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<LibraryItemV2[]>([]);
  const [selected, setSelected] = useState<LibraryItemV2 | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [uploadOpen, setUploadOpen] = useState(false);
  const [createKind, setCreateKind] = useState<"digital_human" | "brand" | "template" | null>(null);
  const [showArchived, setShowArchived] = useState(false);
  const [manageMode, setManageMode] = useState(false);
  const [selectedKeys, setSelectedKeys] = useState<string[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [facets, setFacets] = useState<Record<string, number>>({});
  const [viewMode, setViewMode] = useState<"grid" | "list">(() => (window.localStorage.getItem("asset-center-view") as "grid" | "list") || "grid");
  const [favoriteOnly, setFavoriteOnly] = useState(false);
  const [recentOnly, setRecentOnly] = useState(false);
  const [aspect, setAspect] = useState<"portrait" | "landscape" | "square" | "">("");
  const [status, setStatus] = useState("");
  const [source, setSource] = useState("");
  const [collections, setCollections] = useState<AssetCollectionV2[]>([]);
  const [collectionId, setCollectionId] = useState("");
  const [newCollectionName, setNewCollectionName] = useState("");
  const [collectionBusy, setCollectionBusy] = useState(false);
  const [bulkTags, setBulkTags] = useState("");
  const requestGeneration = useRef(0);
  const listController = useRef<AbortController | null>(null);

  async function refreshCollections() {
    try {
      const result = await listAssetCollectionsV2();
      setCollections(result.items.filter((item) => item.status !== "archived"));
    } catch {
      setCollections([]);
    }
  }

  useEffect(() => {
    void refreshCollections();
  }, []);

  async function refresh() {
    const generation = ++requestGeneration.current;
    listController.current?.abort();
    const controller = new AbortController();
    listController.current = controller;
    setLoading(true);
    setError("");
    try {
      const [result, facetResult] = await Promise.all([
        listLibraryItemsV2(filter === "all" ? undefined : filter, query, { sort: "recent", includeArchived: showArchived, favorite: favoriteOnly || undefined, recentlyUsed: recentOnly || undefined, collectionId: collectionId || undefined, aspect: aspect || undefined, status: status || undefined, source: source || undefined, limit: 60, signal: controller.signal }),
        listLibraryFacetsV2(undefined, { query, includeArchived: showArchived, favorite: favoriteOnly || undefined, recentlyUsed: recentOnly || undefined, collectionId: collectionId || undefined, aspect: aspect || undefined, status: status || undefined, source: source || undefined, signal: controller.signal }),
      ]);
      if (generation !== requestGeneration.current) return;
      setItems(result.items);
      setNextCursor(result.next_cursor || null);
      setFacets(facetResult.kinds || {});
      setSelected((current) =>
        current ? result.items.find((item) => item.resource_id === current.resource_id) || null : null,
      );
    } catch (err) {
      if (controller.signal.aborted || generation !== requestGeneration.current) return;
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      if (generation === requestGeneration.current) setLoading(false);
    }
  }

  useEffect(() => {
    if (query.trim()) recordAssetTelemetry("asset_search_started", { entry: "center" });
    const timer = window.setTimeout(() => void refresh(), 180);
    return () => window.clearTimeout(timer);
  }, [filter, query, showArchived, favoriteOnly, recentOnly, collectionId, aspect, status, source]);

  function loadMore() {
    if (!nextCursor || loading) return;
    setLoading(true);
    const generation = requestGeneration.current;
    void listLibraryItemsV2(filter === "all" ? undefined : filter, query, { sort: "recent", includeArchived: showArchived, favorite: favoriteOnly || undefined, recentlyUsed: recentOnly || undefined, collectionId: collectionId || undefined, aspect: aspect || undefined, status: status || undefined, source: source || undefined, cursor: nextCursor, limit: 60, signal: listController.current?.signal })
      .then((result) => { if (generation === requestGeneration.current) { setItems((current) => [...current, ...result.items]); setNextCursor(result.next_cursor || null); } })
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => { if (generation === requestGeneration.current) setLoading(false); });
  }

  useEffect(() => {
    setSelectedKeys((current) => current.filter((key) => items.some((item) => `${item.kind}:${item.resource_id}` === key)));
  }, [items]);

  function toggleSelection(item: LibraryItemV2) {
    const key = `${item.kind}:${item.resource_id}`;
    setSelectedKeys((current) => current.includes(key) ? current.filter((entry) => entry !== key) : [...current, key]);
  }

  async function runBulkAction(action: "archive" | "restore" | "favorite" | "unfavorite" | "tag" | "untag") {
    const selectedItems = items.filter((item) => selectedKeys.includes(`${item.kind}:${item.resource_id}`));
    if (!selectedItems.length) return;
    const tagsForAction = bulkTags.split(",").map((tag) => tag.trim()).filter(Boolean);
    if ((action === "tag" || action === "untag") && !tagsForAction.length) {
      setError("请先填写要批量处理的标签");
      return;
    }
    setError("");
    try {
      const result = await bulkLibraryActionV2({ action, items: selectedItems.map((item) => ({ kind: item.kind, resource_id: item.resource_id })), ...(tagsForAction.length ? { tags: tagsForAction } : {}) });
      setSelectedKeys([]);
      if (result.failed) setError(`${result.succeeded} 项成功，${result.failed} 项失败；失败项仍保留在列表中。`);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function addSelectedToCollection() {
    if (!collectionId) {
      setError("请先选择一个集合");
      return;
    }
    const selectedItems = items.filter((item) => selectedKeys.includes(`${item.kind}:${item.resource_id}`));
    if (!selectedItems.length) return;
    setCollectionBusy(true);
    try {
      const results = await Promise.allSettled(selectedItems.map((item) => addAssetCollectionItemV2(collectionId, item.kind, item.resource_id)));
      const failed = results.filter((result) => result.status === "rejected").length;
      setSelectedKeys([]);
      await refreshCollections();
      await refresh();
      if (failed) setError(`${selectedItems.length - failed} 项已加入集合，${failed} 项加入失败。`);
    } finally {
      setCollectionBusy(false);
    }
  }

  async function removeSelectedFromCollection() {
    if (!collectionId) return;
    const selectedItems = items.filter((item) => selectedKeys.includes(`${item.kind}:${item.resource_id}`));
    if (!selectedItems.length) return;
    setCollectionBusy(true);
    try {
      const results = await Promise.allSettled(selectedItems.map((item) => removeAssetCollectionItemV2(collectionId, item.kind, item.resource_id)));
      const failed = results.filter((result) => result.status === "rejected").length;
      setSelectedKeys([]);
      await refreshCollections();
      await refresh();
      if (failed) setError(`${selectedItems.length - failed} 项已移出集合，${failed} 项移除失败。`);
    } finally {
      setCollectionBusy(false);
    }
  }

  async function createCollection() {
    const name = newCollectionName.trim();
    if (!name) return;
    setCollectionBusy(true);
    try {
      const created = await createAssetCollectionV2({ name });
      setNewCollectionName("");
      await refreshCollections();
      setCollectionId(created.collection_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setCollectionBusy(false);
    }
  }

  const counts = useMemo(() => {
    const next: Record<string, number> = { all: facets.all || Object.values(facets).reduce((sum, value) => sum + value, 0), ...facets };
    return next;
  }, [facets]);
  const selectedItems = items.filter((item) => selectedKeys.includes(`${item.kind}:${item.resource_id}`));
  const allSelectedArchived = selectedItems.length > 0 && selectedItems.every((item) => item.status === "archived");
  const allSelectedFavorite = selectedItems.length > 0 && selectedItems.every((item) => item.favorite);

  return (
    <section className="asset-center-v2" aria-label="新版企业资产库">
      <header className="asset-center-v2-header">
        <div>
          <h2>企业资产库</h2>
          <p>统一管理企业视频、图片、数字人、音色、模板和品牌资源。</p>
        </div>
        <div className="asset-center-v2-actions">
          <button type="button" onClick={() => void refresh()} disabled={loading} aria-label="刷新资产">
            <RefreshCw size={16} className={loading ? "spin" : ""} /> 刷新
          </button>
          <button type="button" className={showArchived ? "active" : ""} onClick={() => setShowArchived((value) => !value)} aria-pressed={showArchived}>
            {showArchived ? "隐藏已归档" : "显示已归档"}
          </button>
          <button type="button" className={manageMode ? "active" : ""} onClick={() => { setManageMode((value) => !value); setSelectedKeys([]); }} aria-pressed={manageMode}>
            {manageMode ? "完成管理" : "批量管理"}
          </button>
          <div className="asset-center-v2-add-menu"><button type="button" className="primary" onClick={() => setUploadOpen(true)}><Upload size={16} /> 添加资产 <ChevronDown size={14} /></button><div className="asset-center-v2-add-menu-panel"><button type="button" onClick={() => setUploadOpen(true)}>上传图片/视频/音频</button><button type="button" onClick={() => setCreateKind("digital_human")}>添加数字人</button><button type="button" onClick={() => setCreateKind("brand")}>新建品牌</button><button type="button" onClick={() => setCreateKind("template")}>新建模板</button></div></div>
        </div>
      </header>

      <div className="asset-center-v2-toolbar">
        <label className="asset-center-v2-search">
          <Search size={17} />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索名称、描述或文件名"
            aria-label="搜索企业资产"
          />
        </label>
        <nav className="asset-center-v2-filters" aria-label="资产类型">
          {filters.map((item) => (
            <button
              type="button"
              key={item.key}
              className={filter === item.key ? "active" : ""}
              onClick={() => setFilter(item.key)}
              aria-pressed={filter === item.key}
            >
              {item.label} <span>{counts[item.key] || 0}</span>
            </button>
          ))}
        </nav>
        <div className="asset-center-v2-quick-filters" role="toolbar" aria-label="快捷筛选"><button type="button" className={favoriteOnly ? "active" : ""} aria-pressed={favoriteOnly} onClick={() => setFavoriteOnly((value) => !value)}>收藏</button><button type="button" className={recentOnly ? "active" : ""} aria-pressed={recentOnly} onClick={() => setRecentOnly((value) => !value)}>最近使用</button><details className="asset-center-v2-more-filters"><summary>更多筛选</summary><div><label>方向<select value={aspect} onChange={(event) => setAspect(event.target.value as typeof aspect)}><option value="">全部方向</option><option value="portrait">竖版</option><option value="landscape">横版</option><option value="square">正方形</option></select></label><label>状态<select value={status} onChange={(event) => setStatus(event.target.value)}><option value="">全部状态</option><option value="ready">可用</option><option value="warning">待检查</option><option value="processing">处理中</option><option value="archived">已归档</option></select></label><label>来源<select value={source} onChange={(event) => setSource(event.target.value)}><option value="">全部来源</option><option value="upload">上传</option><option value="imported">导入</option><option value="domain">领域资源</option></select></label></div></details><span className="asset-center-v2-view-toggle"><button type="button" aria-label="网格视图" className={viewMode === "grid" ? "active" : ""} onClick={() => { setViewMode("grid"); window.localStorage.setItem("asset-center-view", "grid"); }}><Grid2X2 size={15} /></button><button type="button" aria-label="列表视图" className={viewMode === "list" ? "active" : ""} onClick={() => { setViewMode("list"); window.localStorage.setItem("asset-center-view", "list"); }}><ListIcon size={15} /></button></span></div>
        <div className="asset-center-v2-collection-control" role="group" aria-label="资产集合"><label>集合<select value={collectionId} onChange={(event) => setCollectionId(event.target.value)}><option value="">全部集合</option>{collections.map((collection) => <option key={collection.collection_id} value={collection.collection_id}>{collection.name}（{collection.item_count || 0}）</option>)}</select></label><input value={newCollectionName} onChange={(event) => setNewCollectionName(event.target.value)} placeholder="新集合名称" aria-label="新集合名称" onKeyDown={(event) => { if (event.key === "Enter") void createCollection(); }} /><button type="button" onClick={() => void createCollection()} disabled={!newCollectionName.trim() || collectionBusy}>新建集合</button></div>
      </div>

      {error ? (
        <div className="asset-center-v2-error" role="alert">
          <span>{error}</span>
          <button type="button" onClick={() => void refresh()}>重试</button>
        </div>
      ) : null}

      {!loading && !items.length && !error ? (
        <div className="asset-center-v2-empty">
          <Package size={28} />
          <strong>还没有匹配的企业资产</strong>
          <span>上传图片、视频或音色后，这里会成为生产流的统一入口。</span>
          <button type="button" className="primary" onClick={() => setUploadOpen(true)}>上传第一个资产</button>
        </div>
      ) : null}

      {manageMode ? <div className="asset-center-v2-bulkbar" role="toolbar" aria-label="批量管理"><span>已选 {selectedKeys.length} 项</span><div>{/* Legacy static contract keeps >批量收藏< and >批量归档< labels discoverable. */}<button type="button" disabled={!selectedKeys.length} onClick={() => void runBulkAction(allSelectedFavorite ? "unfavorite" : "favorite")}>{allSelectedFavorite ? "批量取消收藏" : "批量收藏"}</button><button type="button" disabled={!selectedKeys.length} className="danger" onClick={() => void runBulkAction(allSelectedArchived ? "restore" : "archive")}>{allSelectedArchived ? "批量恢复" : "批量归档"}</button><input value={bulkTags} onChange={(event) => setBulkTags(event.target.value)} placeholder="标签，用逗号分隔" aria-label="批量标签" /><button type="button" disabled={!selectedKeys.length} onClick={() => void runBulkAction("tag")}>批量加标签</button><button type="button" disabled={!selectedKeys.length} onClick={() => void runBulkAction("untag")}>批量移标签</button><button type="button" disabled={!selectedKeys.length || !collectionId || collectionBusy} onClick={() => void addSelectedToCollection()}>加入集合</button>{collectionId ? <button type="button" disabled={!selectedKeys.length || collectionBusy} onClick={() => void removeSelectedFromCollection()}>移出集合</button> : null}<button type="button" disabled={!selectedKeys.length} onClick={() => setSelectedKeys([])}>清空选择</button></div></div> : null}
      {filter === "digital_human" ? <DigitalHumanBrowser items={items} onUse={onUse} manageMode={manageMode} selectedKeys={selectedKeys} onToggle={toggleSelection} onChanged={() => void refresh()} /> : <div className={`asset-center-v2-grid asset-center-v2-${viewMode}`} aria-busy={loading}>{items.map((item) => <AssetLibraryCard key={`${item.kind}-${item.resource_id}`} item={item} manageMode={manageMode} selected={selectedKeys.includes(`${item.kind}:${item.resource_id}`)} onToggle={() => toggleSelection(item)} onSelect={(selectedItem) => { recordAssetTelemetry("asset_preview_opened", { kind: selectedItem.kind, entry: "center" }); setSelected(selectedItem); }} viewMode={viewMode} />)}</div>}
      {nextCursor ? <div className="asset-center-v2-load-more"><button type="button" onClick={loadMore} disabled={loading}>{loading ? "正在加载…" : "加载更多"}</button></div> : null}

      {selected ? (
        <AssetDetailPanel item={selected} onClose={() => setSelected(null)} onArchive={() => void (selected.status === "archived" ? restoreLibraryItemV2(selected.kind, selected.resource_id) : archiveLibraryItemV2(selected.kind, selected.resource_id)).then(() => refresh())} onUse={() => onUse?.(selected)} onUpdated={() => void refresh()} />
      ) : null}
      {uploadOpen ? <AssetUploadQueue onClose={() => setUploadOpen(false)} onUploaded={refresh} /> : null}
      {createKind ? <DomainAssetForm kind={createKind} onClose={() => setCreateKind(null)} onCreated={refresh} /> : null}
    </section>
  );
}

function AssetLibraryCard({ item, onSelect, manageMode, selected, onToggle, viewMode }: { item: LibraryItemV2; onSelect: (item: LibraryItemV2) => void; manageMode: boolean; selected: boolean; onToggle: () => void; viewMode: "grid" | "list" }) {
  const Icon = kindIcons[item.kind];
  const view = toAssetViewModel(item);
  return (
    <button type="button" className={`asset-center-v2-card${selected ? " selected" : ""}`} data-view-mode={viewMode} onClick={() => manageMode ? onToggle() : onSelect(item)} aria-pressed={manageMode ? selected : undefined} aria-label={`${item.name}，${kindLabels[item.kind]}，${summaryText(item)}`}>
      <div className={`asset-center-v2-card-media kind-${item.kind}`}>
        {item.cover_url && ["image", "video", "digital_human", "template"].includes(item.kind) ? (
          <ProtectedAssetImage src={item.cover_url} alt={item.name} />
        ) : (
          <Icon size={28} />
        )}
        {item.kind === "video" ? <span className="asset-center-v2-media-badge"><PlayCircle size={13} /> 视频</span> : null}
      </div>
      <div className="asset-center-v2-card-body">
        <div className="asset-center-v2-card-title"><strong>{item.name}</strong><span>{kindLabels[item.kind]}</span></div>
        <p>{item.description || "暂无描述"}</p>
        <small>{summaryText(item)}</small>
        {view.kind === "image" && view.display.transparent ? <small>透明背景</small> : null}
      </div>
    </button>
  );
}

function DigitalHumanBrowser({ items, onUse, manageMode, selectedKeys, onToggle, onChanged }: { items: LibraryItemV2[]; onUse?: (item: LibraryItemV2, sceneId?: string) => void; manageMode: boolean; selectedKeys: string[]; onToggle: (item: LibraryItemV2) => void; onChanged?: () => Promise<void> | void }) {
  const [selected, setSelected] = useState<LibraryItemV2 | null>(items[0] || null);
  const [selectedScene, setSelectedScene] = useState<string>("");
  const [sceneName, setSceneName] = useState("");
  const [sceneShotSize, setSceneShotSize] = useState("medium");
  const [sceneLocation, setSceneLocation] = useState("");
  const [newSceneName, setNewSceneName] = useState("");
  const [newSceneShotSize, setNewSceneShotSize] = useState("medium");
  const [newSceneLocation, setNewSceneLocation] = useState("");
  const [sceneBusy, setSceneBusy] = useState(false);
  useEffect(() => {
    setSelected((current) => items.find((item) => item.resource_id === current?.resource_id) || items[0] || null);
  }, [items]);
  useEffect(() => {
    if (selected) setSelectedScene(String(selected.summary.default_scene_id || selected.scenes?.[0]?.scene_id || ""));
  }, [selected?.resource_id]);
  const selectedSceneData = selected?.scenes?.find((scene) => scene.scene_id === selectedScene) || null;
  useEffect(() => {
    setSceneName(selectedSceneData?.name || "");
    setSceneShotSize(selectedSceneData?.shot_size || "medium");
    setSceneLocation(selectedSceneData?.location || "");
  }, [selectedSceneData?.scene_id]);
  if (!selected) return <div className="asset-center-v2-empty"><UserRound size={28} /><strong>还没有数字人</strong><span>上传图片或视频形象后，可在这里建立人物与场景。</span></div>;
  const profile = selected;
  const previewScene = selected.scenes?.find((scene) => scene.scene_id === selectedScene) || selected.scenes?.find((scene) => scene.scene_id === String(selected.summary.default_scene_id || "")) || selected.scenes?.find((scene) => scene.preview_url) || null;
  const previewSrc = previewScene?.preview_url || selected.cover_url;
  const previewKind = previewScene?.preview_media_type || (selected.summary.media_type === "video" ? "video" : "image");
  const sceneIndex = selected.scenes?.findIndex((scene) => scene.scene_id === selectedScene) ?? -1;
  async function saveScene() {
    if (!selectedSceneData || !sceneName.trim()) return;
    setSceneBusy(true);
    try {
      await patchDigitalHumanSceneV2(selectedSceneData.scene_id, { name: sceneName.trim(), shot_size: sceneShotSize, location: sceneLocation.trim() });
      await onChanged?.();
    } finally {
      setSceneBusy(false);
    }
  }
  async function createScene() {
    if (!newSceneName.trim()) return;
    setSceneBusy(true);
    try {
      const created = await createDigitalHumanSceneV2(profile.resource_id, { name: newSceneName.trim(), shot_size: newSceneShotSize, location: newSceneLocation.trim() });
      if (created.scene_id) setSelectedScene(String(created.scene_id));
      setNewSceneName("");
      setNewSceneLocation("");
      await onChanged?.();
    } finally {
      setSceneBusy(false);
    }
  }
  async function setDefaultScene() {
    if (!selectedSceneData) return;
    setSceneBusy(true);
    try {
      await patchDigitalHumanV2(profile.resource_id, { default_scene_id: selectedSceneData.scene_id });
      await onChanged?.();
    } finally {
      setSceneBusy(false);
    }
  }
  async function archiveScene() {
    if (!selectedSceneData) return;
    setSceneBusy(true);
    try {
      await archiveDigitalHumanSceneV2(selectedSceneData.scene_id);
      setSelectedScene(profile.scenes?.find((scene) => scene.scene_id !== selectedScene)?.scene_id || "");
      await onChanged?.();
    } finally {
      setSceneBusy(false);
    }
  }
  async function moveScene(direction: -1 | 1) {
    if (!profile.scenes || sceneIndex < 0) return;
    const nextIndex = sceneIndex + direction;
    if (nextIndex < 0 || nextIndex >= profile.scenes.length) return;
    const sceneIds = profile.scenes.map((scene) => scene.scene_id);
    [sceneIds[sceneIndex], sceneIds[nextIndex]] = [sceneIds[nextIndex], sceneIds[sceneIndex]];
    setSceneBusy(true);
    try {
      await reorderDigitalHumanScenesV2(profile.resource_id, sceneIds);
      await onChanged?.();
    } finally {
      setSceneBusy(false);
    }
  }
  return (
    <div className="digital-human-browser">
      <div className="digital-human-list" aria-label="数字人列表">
        <div className="digital-human-list-header"><strong>人物</strong><span>{items.length} 个</span></div>
        <div className="digital-human-card-grid">
          {items.map((item) => <button type="button" key={item.resource_id} className={`${selected.resource_id === item.resource_id ? "selected " : ""}${selectedKeys.includes(`digital_human:${item.resource_id}`) ? "bulk-selected" : ""}`} onClick={() => manageMode ? onToggle(item) : setSelected(item)} aria-pressed={manageMode ? selectedKeys.includes(`digital_human:${item.resource_id}`) : undefined}><div>{item.cover_url ? <ProtectedAssetImage src={item.cover_url} alt="" /> : <UserRound size={24} />}</div><strong>{item.name}</strong><span>{item.summary.media_type === "video" ? "视频形象" : "图片形象"}</span></button>)}
        </div>
      </div>
      <div className="digital-human-preview-panel">
        <div className="digital-human-preview-title"><div><span>数字人预览</span><h3>{selected.name}</h3></div><button type="button" className="primary" onClick={() => onUse?.(selected, selectedScene || String(selected.summary.default_scene_id || ""))} disabled={!selectedScene && !selected.summary.default_scene_id}><Check size={15} /> 确认用于视频生产</button></div>
        <div className="digital-human-preview-media">{previewSrc ? <ProtectedAssetMedia src={previewSrc} kind={previewKind} title={selected.name} /> : <UserRound size={48} />}</div>
        <div className="digital-human-scene-list"><strong>场景</strong><div>{(selected.scenes || []).map((scene) => <button type="button" key={scene.scene_id} className={selectedScene === scene.scene_id ? "selected" : ""} onClick={() => setSelectedScene(scene.scene_id)}><span>{scene.name}</span><small>{scene.preview_media_type === "video" ? "演示视频" : "图片场景"} · {scene.shot_size || "默认景别"}</small></button>)}</div><small>先选择场景预览，再点击“确认用于视频生产”；浏览不会修改当前任务。</small></div>
        <div className="digital-human-scene-editor" aria-label="场景管理">
          <strong>维护当前场景</strong>
          {selectedSceneData ? <><label>场景名称<input value={sceneName} onChange={(event) => setSceneName(event.target.value)} /></label><label>景别<select value={sceneShotSize} onChange={(event) => setSceneShotSize(event.target.value)}><option value="close_up">近景</option><option value="medium">中景</option><option value="full">全身</option></select></label><label>地点<input value={sceneLocation} onChange={(event) => setSceneLocation(event.target.value)} placeholder="例如：门店前台" /></label><div className="digital-human-scene-editor-actions"><button type="button" onClick={() => void saveScene()} disabled={sceneBusy || !sceneName.trim()}>保存场景</button><button type="button" onClick={() => void setDefaultScene()} disabled={sceneBusy || selected.summary.default_scene_id === selectedScene}>设为默认</button><button type="button" onClick={() => void moveScene(-1)} disabled={sceneBusy || sceneIndex <= 0}>上移</button><button type="button" onClick={() => void moveScene(1)} disabled={sceneBusy || sceneIndex < 0 || sceneIndex >= (selected.scenes?.length || 1) - 1}>下移</button><button type="button" className="danger" onClick={() => void archiveScene()} disabled={sceneBusy}>归档场景</button></div></> : <small>请选择一个场景进行维护。</small>}
          <details><summary>新增场景</summary><div className="digital-human-scene-new"><label>名称<input value={newSceneName} onChange={(event) => setNewSceneName(event.target.value)} placeholder="例如：收银台侧身" /></label><label>景别<select value={newSceneShotSize} onChange={(event) => setNewSceneShotSize(event.target.value)}><option value="close_up">近景</option><option value="medium">中景</option><option value="full">全身</option></select></label><label>地点<input value={newSceneLocation} onChange={(event) => setNewSceneLocation(event.target.value)} /></label><button type="button" onClick={() => void createScene()} disabled={sceneBusy || !newSceneName.trim()}>新增场景</button></div></details>
        </div>
      </div>
    </div>
  );
}

function AssetDetailPanel({ item, onClose, onArchive, onUse, onUpdated }: { item: LibraryItemV2; onClose: () => void; onArchive: () => void; onUse: () => void; onUpdated: () => void }) {
  const [name, setName] = useState(item.name);
  const [description, setDescription] = useState(item.description);
  const [tags, setTags] = useState(item.tags.join(", "));
  const [saving, setSaving] = useState(false);
  const [usage, setUsage] = useState<Array<Record<string, unknown>>>([]);
  const [revisionBusy, setRevisionBusy] = useState(false);
  const [revisionProgress, setRevisionProgress] = useState(0);
  const [revisions, setRevisions] = useState<Array<{ revision_id: string; version: number; sha256: string; bytes: number; created_at: string }>>([]);
  const [tab, setTab] = useState<"overview" | "usage" | "advanced">("overview");
  useEffect(() => {
    setName(item.name);
    setDescription(item.description);
  }, [item.name, item.description]);
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); onClose(); return; }
      if (event.key !== "Tab") return;
      const dialog = document.querySelector<HTMLElement>(".asset-center-v2-detail");
      if (!dialog) return;
      const focusable = Array.from(dialog.querySelectorAll<HTMLElement>("button, input, textarea, select, [tabindex]:not([tabindex='-1'])")).filter((element) => !element.hasAttribute("disabled"));
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose]);
  useEffect(() => {
    void listResourceUsageV2(item.kind, item.resource_id).then((result) => setUsage(result.items)).catch(() => setUsage([]));
    if (item.kind === "video" || item.kind === "image" || item.kind === "audio") void listMediaAssetRevisionsV2(item.resource_id).then((result) => setRevisions(result.items)).catch(() => setRevisions([]));
    else setRevisions([]);
  }, [item.kind, item.resource_id]);
  const mediaType = item.kind === "voice" || item.kind === "audio" ? "audio" : item.summary.media_type === "video" || item.kind === "video" ? "video" : "image";
  return (
    <div className="asset-center-v2-backdrop" role="presentation" onMouseDown={(event) => event.currentTarget === event.target && onClose()}>
      <aside className="asset-center-v2-detail" role="dialog" aria-modal="true" aria-label={`${item.name}详情`}>
        <header>
          <div><span>{kindLabels[item.kind]}</span><h3>{item.name}</h3></div>
          <button type="button" onClick={onClose} aria-label="关闭详情"><X size={18} /></button>
        </header>
        <div className="asset-center-v2-detail-tabs" role="tablist" aria-label="资产详情"><button type="button" role="tab" aria-selected={tab === "overview"} className={tab === "overview" ? "active" : ""} onClick={() => setTab("overview")}>概览</button><button type="button" role="tab" aria-selected={tab === "usage"} className={tab === "usage" ? "active" : ""} onClick={() => setTab("usage")}>使用情况</button><button type="button" role="tab" aria-selected={tab === "advanced"} className={tab === "advanced" ? "active" : ""} onClick={() => setTab("advanced")}>版本与高级</button></div>
        <div className={`asset-center-v2-detail-preview kind-${item.kind}`}>
          {item.cover_url ? (mediaType === "image" ? <AssetImageInspector src={item.cover_url} title={item.name} /> : <ProtectedAssetMedia src={item.cover_url} kind={mediaType} title={item.name} />) : <Package size={40} />}
        </div>
        {tab === "overview" ? <><dl className="asset-center-v2-detail-meta"><div><dt>状态</dt><dd>{item.status === "ready" ? "可用" : item.status}</dd></div><div><dt>创建时间</dt><dd>{formatLocalDate(item.created_at)}</dd></div><div><dt>业务规格</dt><dd>{summaryText(item)}</dd></div></dl><label className="asset-center-v2-tags">名称<input value={name} onChange={(event) => setName(event.target.value)} /></label><label className="asset-center-v2-tags">说明<textarea value={description} onChange={(event) => setDescription(event.target.value)} rows={3} /></label><label className="asset-center-v2-tags">标签<input value={tags} onChange={(event) => setTags(event.target.value)} placeholder="用逗号分隔，例如：门店、主推" /></label>{item.kind === "brand" ? <BrandKitEditor item={item} onUpdated={onUpdated} /> : null}{item.kind === "template" ? <TemplateLayoutEditor item={item} onUpdated={onUpdated} /> : null}</> : null}
        {tab === "usage" ? <div className="asset-center-v2-usage"><strong>最近使用</strong>{usage.length ? usage.slice(0, 5).map((entry, index) => <span key={`${String(entry.created_at)}-${index}`}>{String(entry.step || "生产")} · {String(entry.purpose || "使用")} · {formatLocalDate(String(entry.created_at || ""))}</span>) : <small>暂无使用记录</small>}</div> : null}
        {tab === "advanced" ? <><div className="asset-center-v2-advanced"><strong>高级信息</strong><span>资源标识：{item.resource_id}</span><span>更新时间：{formatLocalDate(item.updated_at)}</span><span>原始诊断字段仅供排错，不会影响默认使用。</span></div>{item.kind === "video" || item.kind === "image" || item.kind === "audio" ? <label className="asset-center-v2-revision">替换为新版本<input type="file" accept={item.kind === "video" ? "video/*" : item.kind === "image" ? "image/*" : "audio/*"} disabled={revisionBusy} onChange={(event) => { const file = event.target.files?.[0]; if (!file) return; setRevisionBusy(true); setRevisionProgress(0); void createMediaAssetRevisionV2(item.resource_id, file, setRevisionProgress).then(onUpdated).catch(() => undefined).finally(() => setRevisionBusy(false)); event.currentTarget.value = ""; }} />{revisionBusy ? <small>正在上传新版本 {revisionProgress}%</small> : <small>原版本保留，可在详情中切换</small>}</label> : null}{revisions.length > 1 ? <div className="asset-center-v2-revisions"><strong>版本</strong>{revisions.map((revision) => <button type="button" key={revision.revision_id} className={item.revision?.revision_id === revision.revision_id ? "active" : ""} onClick={() => void activateMediaAssetRevisionV2(item.resource_id, revision.revision_id).then(onUpdated)}>{`v${revision.version}`}<small>{formatBytes(revision.bytes)}</small></button>)}</div> : null}</> : null}
        <div className="asset-center-v2-detail-actions">
          <button type="button" onClick={() => { setSaving(true); void setLibraryFavoriteV2(item.kind, item.resource_id, !item.favorite).then(onUpdated).finally(() => setSaving(false)); }} disabled={saving}>{item.favorite ? "取消收藏" : "收藏"}</button>
          {tab === "overview" && ["image", "video", "audio"].includes(item.kind) ? <button type="button" onClick={() => { setSaving(true); void patchMediaAssetV2(item.resource_id, { name, description }).then(onUpdated).finally(() => setSaving(false)); }} disabled={saving}>保存名称说明</button> : null}
          <button type="button" onClick={() => { setSaving(true); void setLibraryTagsV2(item.kind, item.resource_id, tags.split(",")).then(onUpdated).finally(() => setSaving(false)); }} disabled={saving}>保存标签</button>
          <button type="button" className="primary" onClick={onUse}>用于生产</button>
          <button type="button" className={item.status === "archived" ? "primary" : "danger"} onClick={onArchive}>{item.status === "archived" ? "恢复" : "归档"}</button>
        </div>
      </aside>
    </div>
  );
}

function AssetUploadPanel({ onClose, onUploaded }: { onClose: () => void; onUploaded: () => Promise<void> }) {
  const [kind, setKind] = useState<"image" | "video" | "audio">("video");
  const [name, setName] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(0);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [failedFiles, setFailedFiles] = useState<File[]>([]);
  const controller = useRef<AbortController | null>(null);
  const [uploadId, setUploadId] = useState("");

  async function upload(batch = files) {
    if (!batch.length) return;
    setBusy(true);
    setProgress(0);
    setError("");
    setMessage("");
    try {
      for (const [index, file] of batch.entries()) {
        controller.current = new AbortController();
        try {
          await uploadMediaAssetV2(
            kind,
            name && batch.length === 1 ? name : name ? `${name} · ${file.name}` : file.name,
            file,
            (value) => setProgress(Math.round(((index * 100) + value) / batch.length)),
            setUploadId,
            controller.current.signal,
          );
        } catch (err) {
          setFailedFiles(batch.slice(index));
          throw err;
        }
      }
      setFailedFiles([]);
      setMessage(`${batch.length} 个资产已入库，可以在生产流中直接使用。`);
      await onUploaded();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
      controller.current = null;
    }
  }

  async function cancel() {
    controller.current?.abort();
    if (uploadId) await cancelMediaUploadV2(uploadId).catch(() => undefined);
    setBusy(false);
    setMessage("上传已取消");
  }

  return (
    <div className="asset-center-v2-backdrop" role="presentation">
      <section className="asset-center-v2-upload" role="dialog" aria-modal="true" aria-label="上传资产">
        <header><div><span>统一上传</span><h3>添加企业资产</h3></div><button type="button" onClick={() => void (busy ? cancel() : onClose())} aria-label={busy ? "取消上传" : "关闭上传"}><X size={18} /></button></header>
        <div className="asset-center-v2-upload-kind" role="tablist" aria-label="资产类型">
          {(["video", "image", "audio"] as const).map((value) => <button type="button" key={value} className={kind === value ? "active" : ""} onClick={() => setKind(value)}>{kindLabels[value]}</button>)}
        </div>
        <label>资产名称<input value={name} onChange={(event) => setName(event.target.value)} placeholder="可选，默认使用文件名" /></label>
        <label className="asset-center-v2-file"><span>选择文件（可多选）</span><input type="file" multiple accept={kind === "video" ? "video/*" : kind === "image" ? "image/*" : "audio/*"} onChange={(event) => setFiles(Array.from(event.target.files || []))} />{files.length ? <strong>{files.map((file) => `${file.name} · ${formatBytes(file.size)}`).join("；")}</strong> : <small>支持批量选择，上传后逐项生成可复用记录</small>}</label>
        {busy ? <div className="asset-upload-progress" role="progressbar" aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100}><span style={{ width: `${progress}%` }} /><small>上传中 {progress}%</small></div> : null}
        {message ? <div className="asset-center-v2-success" role="status">{message}</div> : null}
        {error ? <div className="asset-center-v2-error" role="alert">{error}</div> : null}
        {failedFiles.length ? <button type="button" className="asset-upload-retry" disabled={busy} onClick={() => void upload(failedFiles)}><RefreshCw size={14} /> 重试失败项（{failedFiles.length}）</button> : null}
        <footer><button type="button" onClick={() => void (busy ? cancel() : onClose())}>{busy ? "取消上传" : "关闭"}</button><button type="button" className="primary" disabled={!files.length || busy} onClick={() => void upload()}>{busy ? "正在上传…" : "上传并入库"}</button></footer>
      </section>
    </div>
  );
}

function DomainAssetForm({
  kind,
  onClose,
  onCreated,
}: {
  kind: "digital_human" | "brand" | "template";
  onClose: () => void;
  onCreated: () => Promise<void>;
}) {
  const [name, setName] = useState("");
  const [sceneName, setSceneName] = useState("默认场景");
  const [sourceAssetId, setSourceAssetId] = useState("");
  const [coverFile, setCoverFile] = useState<File | null>(null);
  const [demoVideoFile, setDemoVideoFile] = useState<File | null>(null);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [templateId, setTemplateId] = useState("");
  const [primaryColor, setPrimaryColor] = useState("#7c3aed");
  const [secondaryColor, setSecondaryColor] = useState("#fb7185");
  const [fontFamily, setFontFamily] = useState("noto-sans-sc-bold");
  const [defaultBgmAssetId, setDefaultBgmAssetId] = useState("");
  const [endingCardText, setEndingCardText] = useState("");
  const [storeAddress, setStoreAddress] = useState("");
  const [phone, setPhone] = useState("");
  const [couponPhrase, setCouponPhrase] = useState("");
  const [logoFile, setLogoFile] = useState<File | null>(null);
  const [subtitleFontSize, setSubtitleFontSize] = useState("48");
  const [mediaItems, setMediaItems] = useState<LibraryItemV2[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (kind !== "digital_human" && kind !== "brand") return;
    void listLibraryItemsV2(undefined, "").then((result) => {
      setMediaItems(result.items.filter((item) => kind === "brand" ? item.kind === "image" || item.kind === "audio" : item.kind === "image" || item.kind === "video"));
    }).catch(() => setMediaItems([]));
  }, [kind]);

  async function submit() {
    if (!name.trim()) {
      setError("请填写名称");
      return;
    }
    setBusy(true);
    setError("");
    try {
      if (kind === "digital_human") {
        const source = mediaItems.find((item) => item.resource_id === sourceAssetId);
        let posterAssetId = source?.asset_id || source?.resource_id || null;
        let sourceAsset = source?.asset_id || source?.resource_id || null;
        let sourceRevisionId = source?.revision?.revision_id || null;
        if (coverFile) {
          setUploadProgress(10);
          const cover = await uploadMediaAssetV2("image", `${name.trim()} 封面`, coverFile, (progress) => setUploadProgress(Math.max(10, Math.round(progress * 0.45))));
          posterAssetId = cover.asset_id;
        }
        if (demoVideoFile) {
          setUploadProgress(55);
          const demo = await uploadMediaAssetV2("video", `${name.trim()} 演示视频`, demoVideoFile, (progress) => setUploadProgress(Math.max(55, 55 + Math.round(progress * 0.45))));
          sourceAsset = demo.asset_id;
          sourceRevisionId = demo.revision?.revision_id || null;
          if (!posterAssetId) posterAssetId = sourceAsset;
        }
        if (!posterAssetId && !sourceAsset) {
          throw new Error("请上传封面图或演示视频，或选择已有图片/视频素材");
        }
        await createDigitalHumanV2({
          name: name.trim(),
          poster_asset_id: posterAssetId,
          source_asset_id: sourceAsset,
          source_revision_id: sourceRevisionId,
          scene_name: sceneName.trim() || "默认场景",
        });
      } else if (kind === "brand") {
        let logoAssetId: string | null = null;
        if (logoFile) logoAssetId = (await uploadMediaAssetV2("image", `${name.trim()} Logo`, logoFile)).asset_id;
        await createBrandKitV2({ brand_name: name.trim(), logo_asset_id: logoAssetId, default_bgm_asset_id: defaultBgmAssetId || null, primary_color: primaryColor, secondary_color: secondaryColor, font_family: fontFamily, ending_card_text: endingCardText, store_address: storeAddress, phone, coupon_phrase: couponPhrase });
      } else {
        const fontSize = Math.max(16, Math.min(72, Number(subtitleFontSize) || 48));
        const layoutContract = defaultTemplateLayoutContract(fontSize, templateId.trim() || "boss_clean");
        await previewTemplateV2(layoutContract, { title: name.trim(), subtitle: "模板权威预览" });
        await createTemplateV2({
          template_id: templateId.trim() || null,
          display_name: name.trim(),
          short_description: "企业口播模板",
          schema_version: 2,
          subtitle_contract: { font_size: fontSize },
          cover_contract: { canvas_width: 1080, canvas_height: 1920 },
          layout_contract: layoutContract,
        });
      }
      await onCreated();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
      setUploadProgress(0);
    }
  }

  const title = kind === "digital_human" ? "新建数字人" : kind === "brand" ? "新建品牌" : "新建模板";
  return (
    <div className="asset-center-v2-backdrop" role="presentation">
      <section className="asset-center-v2-upload asset-domain-form" role="dialog" aria-modal="true" aria-label={title}>
        <header><div><span>领域资源</span><h3>{title}</h3></div><button type="button" onClick={onClose} aria-label="关闭"><X size={18} /></button></header>
        <label>名称<input value={name} onChange={(event) => setName(event.target.value)} placeholder={kind === "digital_human" ? "例如：张老板" : kind === "brand" ? "例如：老张火锅" : "例如：门店口播"} /></label>
        {kind === "digital_human" ? <>
          <label className="asset-domain-file">数字人封面图<input type="file" accept="image/*" onChange={(event) => setCoverFile(event.target.files?.[0] || null)} />{coverFile ? <small>已选择：{coverFile.name}</small> : <small>用于人物卡片和默认预览，建议上传正面清晰图片</small>}</label>
          <label className="asset-domain-file">演示视频<input type="file" accept="video/*" onChange={(event) => setDemoVideoFile(event.target.files?.[0] || null)} />{demoVideoFile ? <small>已选择：{demoVideoFile.name}</small> : <small>用于点击数字人后的演示预览和场景素材</small>}</label>
          <label>已有媒体（可选）<select value={sourceAssetId} onChange={(event) => setSourceAssetId(event.target.value)}><option value="">不使用已有媒体</option>{mediaItems.map((item) => <option key={item.resource_id} value={item.resource_id}>{item.name} · {item.kind === "video" ? "视频" : "图片"}</option>)}</select></label>
          <label>默认场景<input value={sceneName} onChange={(event) => setSceneName(event.target.value)} /></label>
          <small>人物档案、封面和演示场景分开保存；创建后可在右侧预览，并从生产流快捷使用。</small>
          {busy && (coverFile || demoVideoFile) ? <div className="asset-upload-progress" role="progressbar" aria-valuenow={uploadProgress} aria-valuemin={0} aria-valuemax={100}><span style={{ width: `${uploadProgress}%` }} /><small>正在上传数字人素材 {uploadProgress}%</small></div> : null}
        </> : null}
        {kind === "brand" ? <><label className="asset-domain-file">品牌 Logo<input type="file" accept="image/*" onChange={(event) => setLogoFile(event.target.files?.[0] || null)} />{logoFile ? <small>已选择：{logoFile.name}</small> : <small>可稍后补充</small>}</label><div className="asset-domain-colors"><label>主色<input type="color" value={primaryColor} onChange={(event) => setPrimaryColor(event.target.value)} /></label><label>辅色<input type="color" value={secondaryColor} onChange={(event) => setSecondaryColor(event.target.value)} /></label></div><label>默认 BGM<select value={defaultBgmAssetId} onChange={(event) => setDefaultBgmAssetId(event.target.value)}><option value="">不设置</option>{mediaItems.filter((item) => item.kind === "audio").map((item) => <option key={item.resource_id} value={item.asset_id || item.resource_id}>{item.name}</option>)}</select></label><label>字体<select value={fontFamily} onChange={(event) => setFontFamily(event.target.value)}><option value="noto-sans-sc-bold">Noto Sans CJK SC（粗体，随应用分发）</option></select></label><details><summary>发布与结尾信息</summary><label>结尾卡文案<input value={endingCardText} onChange={(event) => setEndingCardText(event.target.value)} /></label><label>门店地址<input value={storeAddress} onChange={(event) => setStoreAddress(event.target.value)} /></label><label>电话<input value={phone} onChange={(event) => setPhone(event.target.value)} /></label><label>优惠/团购话术<input value={couponPhrase} onChange={(event) => setCouponPhrase(event.target.value)} /></label></details><div className="brand-preview" style={{ borderColor: primaryColor, color: secondaryColor }}><strong>{name.trim() || "品牌预览"}</strong><span>{endingCardText || "门店优惠信息将在这里预览"}</span><small>{storeAddress || "门店地址"} · {phone || "联系电话"}</small></div></> : null}
        {kind === "template" ? <><label>模板 ID（可选）<input value={templateId} onChange={(event) => setTemplateId(event.target.value)} placeholder="留空则创建独立版本" /></label><label>字幕字号<input type="number" min="16" max="72" value={subtitleFontSize} onChange={(event) => setSubtitleFontSize(event.target.value)} /></label><small>模板版本会随渲染快照锁定；自定义 renderer 需由后端注册后才能用于成片。</small></> : null}
        {error ? <div className="asset-center-v2-error" role="alert">{error}</div> : null}
        <footer><button type="button" onClick={onClose}>取消</button><button type="button" className="primary" disabled={busy} onClick={() => void submit()}>{busy ? "保存中…" : "保存"}</button></footer>
      </section>
    </div>
  );
}
