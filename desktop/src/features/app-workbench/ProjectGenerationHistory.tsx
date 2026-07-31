import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Alert, Button, Empty, Input, Modal, Segmented, Skeleton, Tag, Typography } from "antd";
import { Check, Copy, Download, Eye, ImageOff, Pencil, Play, RefreshCw, Send } from "lucide-react";

import {
  downloadGenerationRecordMedia,
  generationRecordMediaBlobUrl,
  getGenerationRecordPreview,
  listGenerationRecords,
  type GenerationCarouselResultItem,
  type GenerationMediaPreview,
  type GenerationRecordBlock,
  type GenerationRecordItem,
  type GenerationTextResultItem,
  type GenerationVideoResultItem,
} from "../../api";

type Props = {
  projectId: string;
  appId: GenerationRecordBlock["app_id"];
  refreshKey?: string;
  onCopy?: (
    record: GenerationRecordBlock,
    item: GenerationTextResultItem,
  ) => Promise<void>;
  onSelect?: (
    record: GenerationRecordBlock,
    item: GenerationTextResultItem,
  ) => Promise<void>;
  onEdit?: (
    record: GenerationRecordBlock,
    item: GenerationTextResultItem,
    nextText: string,
  ) => Promise<void>;
  onRunAction?: (record: GenerationRecordBlock) => Promise<void>;
  onPublish?: (
    record: GenerationRecordBlock,
    item: GenerationCarouselResultItem | GenerationVideoResultItem,
  ) => Promise<void>;
};

type Scope = "current_app" | "all_results";

const SCOPE_STORAGE_KEY = "pixelle.app-result-history.scope.v1";

const statusCopy: Record<
  GenerationRecordBlock["status"],
  { label: string; color: "default" | "processing" | "warning" | "success" | "error" }
> = {
  queued: { label: "等待生成", color: "processing" },
  running: { label: "生成中", color: "processing" },
  needs_review: { label: "待确认", color: "warning" },
  completed: { label: "已完成", color: "success" },
  failed: { label: "生成失败", color: "error" },
  cancelled: { label: "已取消", color: "default" },
};

const runActionCopy: Partial<Record<GenerationRecordBlock["status"], string>> = {
  queued: "取消",
  running: "取消",
  needs_review: "确认完成",
  failed: "重试",
};

function initialScope(): Scope {
  try {
    return window.sessionStorage.getItem(SCOPE_STORAGE_KEY) === "all_results"
      ? "all_results"
      : "current_app";
  } catch {
    return "current_app";
  }
}

function formatRecordTime(value: string | null, fallback: string) {
  const timestamp = Date.parse(value || fallback);
  if (!Number.isFinite(timestamp)) return "刚刚";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(timestamp);
}

function isTextItem(item: GenerationRecordItem): item is GenerationTextResultItem {
  return item.kind === "copy" || item.kind === "title";
}

function isMediaItem(
  item: GenerationRecordItem,
): item is GenerationCarouselResultItem | GenerationVideoResultItem {
  return item.kind === "carousel" || item.kind === "video";
}

function formatDuration(seconds: number) {
  const rounded = Math.max(0, Math.round(seconds));
  return `${String(Math.floor(rounded / 60)).padStart(2, "0")}:${String(rounded % 60).padStart(2, "0")}`;
}

function persistedSelectionKeys(records: GenerationRecordBlock[]) {
  return new Set(
    records.flatMap((record) => (
      record.items
        .filter((item): item is GenerationTextResultItem => (
          isTextItem(item) && item.selected === true
        ))
        .map((item) => `${record.record_id}:${item.item_id}`)
    )),
  );
}

function MediaResultCard({
  record,
  item,
  onPublish,
}: {
  record: GenerationRecordBlock;
  item: GenerationCarouselResultItem | GenerationVideoResultItem;
  onPublish?: Props["onPublish"];
}) {
  const [thumbnailUrl, setThumbnailUrl] = useState("");
  const [thumbnailError, setThumbnailError] = useState(false);
  const [preview, setPreview] = useState<GenerationMediaPreview | null>(null);
  const [previewUrls, setPreviewUrls] = useState<string[]>([]);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState("");
  const [publishing, setPublishing] = useState(false);
  const previewUrlsRef = useRef<string[]>([]);
  const thumbnailPath = item.kind === "carousel" ? item.cover_url : item.poster_url;

  useEffect(() => {
    let active = true;
    let objectUrl = "";
    setThumbnailError(false);
    void generationRecordMediaBlobUrl(thumbnailPath)
      .then((value) => {
        if (!active) {
          URL.revokeObjectURL(value);
          return;
        }
        objectUrl = value;
        setThumbnailUrl(value);
      })
      .catch(() => {
        if (active) setThumbnailError(true);
      });
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [thumbnailPath]);

  useEffect(() => () => {
    previewUrlsRef.current.forEach((value) => URL.revokeObjectURL(value));
    previewUrlsRef.current = [];
  }, []);

  function replacePreviewUrls(nextUrls: string[]) {
    previewUrlsRef.current.forEach((value) => URL.revokeObjectURL(value));
    previewUrlsRef.current = nextUrls.filter(Boolean);
    setPreviewUrls(nextUrls);
  }

  function closePreview() {
    replacePreviewUrls([]);
    setPreview(null);
    setPreviewError("");
  }

  async function openPreview() {
    if (previewLoading) return;
    setPreviewLoading(true);
    setPreviewError("");
    try {
      const nextPreview = await getGenerationRecordPreview(item.preview_url);
      const paths = nextPreview.kind === "carousel"
        ? nextPreview.pages.map((page) => page.image_url)
        : [nextPreview.playback_url];
      setPreview(nextPreview);
      const resolved = await Promise.allSettled(
        paths.map(generationRecordMediaBlobUrl),
      );
      const urls = resolved.map((result) => (
        result.status === "fulfilled" ? result.value : ""
      ));
      replacePreviewUrls(urls);
      if (resolved.some((result) => result.status === "rejected")) {
        setPreviewError(
          nextPreview.kind === "carousel"
            ? "部分页面暂时无法显示，仍可下载成品或复制发布文案。"
            : "视频暂时无法在线播放，仍可下载成品或复制发布文案。",
        );
      }
    } catch (loadError) {
      setPreviewError(
        loadError instanceof Error ? loadError.message : "预览暂不可用，仍可稍后重试",
      );
    } finally {
      setPreviewLoading(false);
    }
  }

  async function publish() {
    if (!onPublish || publishing) return;
    setPublishing(true);
    setPreviewError("");
    try {
      await onPublish(record, item);
    } catch (publishError) {
      setPreviewError(
        publishError instanceof Error ? publishError.message : "暂时无法交给发布中心",
      );
    } finally {
      setPublishing(false);
    }
  }

  async function copyPublishCopy() {
    if (!preview?.publish_copy || !navigator.clipboard) return;
    try {
      const copy = preview.publish_copy;
      await navigator.clipboard.writeText(
        [copy.title, copy.description, copy.hashtags.map((tag) => `#${tag}`).join(" ")]
          .filter(Boolean)
          .join("\n"),
      );
    } catch (copyError) {
      setPreviewError(
        copyError instanceof Error ? copyError.message : "发布文案暂时无法复制",
      );
    }
  }

  async function downloadProduct(path = preview?.download_url || item.download_url) {
    setPreviewError("");
    try {
      await downloadGenerationRecordMedia(
        path,
        item.kind === "carousel" ? `${item.title}.zip` : `${item.title}.mp4`,
      );
    } catch (downloadError) {
      setPreviewError(
        downloadError instanceof Error ? downloadError.message : "成品暂时无法下载",
      );
    }
  }

  async function downloadPage(page: { page_index: number; image_url: string; download_url?: string }) {
    setPreviewError("");
    try {
      await downloadGenerationRecordMedia(
        page.download_url || page.image_url,
        `${item.title}-第${page.page_index}页.png`,
      );
    } catch (downloadError) {
      setPreviewError(
        downloadError instanceof Error ? downloadError.message : "单页图片暂时无法下载",
      );
    }
  }

  const metadata = item.kind === "carousel"
    ? `${item.page_count} 页${item.missing_facts?.length ? ` · 待补充 ${item.missing_facts.length} 项事实` : ""}`
    : formatDuration(item.duration_seconds);
  const previewLabel = item.kind === "carousel" ? "预览" : "播放";

  return (
    <>
      <article className="generation-media-card" aria-label={`${item.title}成品`}>
        {item.kind === "carousel" && item.missing_facts?.length ? (
          <Typography.Text type="warning" className="generation-media-card__notice">
            待补充事实：{item.missing_facts.join("、")}
          </Typography.Text>
        ) : null}
        <div
          className="generation-media-card__main"
          role="button"
          tabIndex={0}
          aria-label={`${previewLabel}${item.title}`}
          onClick={() => void openPreview()}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              void openPreview();
            }
          }}
        >
          <div className="generation-media-card__thumbnail">
            {thumbnailUrl ? (
              <img src={thumbnailUrl} alt="" />
            ) : (
              <div className="generation-media-card__thumbnail-fallback" aria-hidden>
                {thumbnailError
                  ? <ImageOff size={24} />
                  : <Skeleton.Image active />}
              </div>
            )}
            {item.kind === "video" ? (
              <span className="generation-media-card__play" aria-hidden>
                <Play size={20} fill="currentColor" />
              </span>
            ) : null}
          </div>
          <div className="generation-media-card__copy">
            <strong>{item.title}</strong>
            <span>{metadata}</span>
            {item.kind === "video" ? (
              <span>{item.digital_human_name} · {item.voice_name}</span>
            ) : null}
          </div>
        </div>
        <div className="generation-media-card__actions">
          <Button
            type="text"
            icon={item.kind === "carousel" ? <Eye size={16} /> : <Play size={16} />}
            loading={previewLoading}
            onClick={() => void openPreview()}
          >
            {previewLabel}
          </Button>
          {item.kind === "video" ? (
            <Button
              type="text"
              icon={<Download size={16} />}
              onClick={() => void downloadProduct()}
            >
              下载
            </Button>
          ) : null}
          {onPublish ? (
            <Button
              type="text"
              icon={<Send size={16} />}
              loading={publishing}
              onClick={() => void publish()}
            >
              去发布
            </Button>
          ) : null}
        </div>
      </article>
      {previewError ? (
        <div className="generation-media-card__error" role="alert">
          <span>{previewError}</span>
          <Button
            type="link"
            size="small"
            icon={<Download size={14} />}
            onClick={() => void downloadProduct()}
          >
            下载成品
          </Button>
        </div>
      ) : null}
      <Modal
        title={preview?.title || item.title}
        open={Boolean(preview)}
        width={preview?.kind === "video" ? 760 : 920}
        onCancel={closePreview}
        destroyOnHidden
        footer={preview ? [
          <Button
            key="download"
            icon={<Download size={16} />}
            onClick={() => void downloadProduct(preview.download_url)}
          >
            下载成品
          </Button>,
          preview.publish_copy ? (
            <Button key="copy" icon={<Copy size={16} />} onClick={() => void copyPublishCopy()}>
              复制发布文案
            </Button>
          ) : null,
          <Button key="close" type="primary" onClick={closePreview}>关闭</Button>,
        ] : null}
      >
        {preview && previewError ? (
          <Alert
            type="warning"
            showIcon
            title={previewError}
            className="generation-media-preview__alert"
          />
        ) : null}
        {preview?.kind === "carousel" ? (
          <div className="generation-carousel-preview" aria-label="图文完整预览">
            {preview.pages.map((page, index) => (
              <figure key={page.page_index}>
                {previewUrls[index] ? (
                  <img
                    src={previewUrls[index]}
                    alt={`图文第 ${page.page_index} 页`}
                  />
                ) : (
                  <div className="generation-carousel-preview__fallback">
                    <ImageOff size={24} />
                    <span>第 {page.page_index} 页暂时无法预览</span>
                  </div>
                )}
                <figcaption>
                  <span>{page.page_index} / {preview.page_count}</span>
                  <Button
                    type="link"
                    size="small"
                    icon={<Download size={14} />}
                    onClick={() => void downloadPage(page)}
                  >
                    下载本页
                  </Button>
                </figcaption>
              </figure>
            ))}
          </div>
        ) : preview?.kind === "video" ? (
          <div className="generation-video-preview">
            {previewUrls[0] ? (
              <video
                controls
                preload="metadata"
                src={previewUrls[0]}
                poster={thumbnailUrl || undefined}
                aria-label={preview.title}
              />
            ) : (
              <div className="generation-video-preview__fallback">
                <ImageOff size={28} />
                <span>暂时无法在线播放，请下载成片查看。</span>
              </div>
            )}
            {preview.publish_copy?.description ? (
              <Typography.Paragraph>{preview.publish_copy.description}</Typography.Paragraph>
            ) : null}
          </div>
        ) : null}
      </Modal>
    </>
  );
}

export function ProjectGenerationHistory({
  projectId,
  appId,
  refreshKey = "",
  onCopy,
  onSelect,
  onEdit,
  onRunAction,
  onPublish,
}: Props) {
  const [scope, setScope] = useState<Scope>(initialScope);
  const [records, setRecords] = useState<GenerationRecordBlock[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState("");
  const [actionBusy, setActionBusy] = useState("");
  const [selectedItems, setSelectedItems] = useState<Set<string>>(new Set());
  const [expandedItems, setExpandedItems] = useState<Set<string>>(new Set());
  const [editTarget, setEditTarget] = useState<{
    record: GenerationRecordBlock;
    item: GenerationTextResultItem;
  } | null>(null);
  const [editText, setEditText] = useState("");
  const [refreshSequence, setRefreshSequence] = useState(0);
  const requestSequence = useRef(0);
  const pendingSelectionKeys = useRef<Set<string>>(new Set());
  const queryKey = `${projectId}\u0000${scope}\u0000${appId}`;
  const activeQueryKey = useRef(queryKey);
  activeQueryKey.current = queryKey;

  const loadFirstPage = useCallback(async () => {
    const sequence = ++requestSequence.current;
    setLoading(true);
    setError("");
    try {
      const page = await listGenerationRecords(projectId, {
        scope,
        ...(scope === "current_app" ? { app_id: appId } : {}),
        limit: 10,
      });
      if (sequence !== requestSequence.current) return;
      setRecords(page.records);
      setNextCursor(page.next_cursor);
      const persisted = persistedSelectionKeys(page.records);
      persisted.forEach((key) => pendingSelectionKeys.current.delete(key));
      pendingSelectionKeys.current.forEach((key) => persisted.add(key));
      setSelectedItems(persisted);
    } catch (loadError) {
      if (sequence !== requestSequence.current) return;
      setError(loadError instanceof Error ? loadError.message : "生成记录暂时无法读取");
    } finally {
      if (sequence === requestSequence.current) setLoading(false);
    }
  }, [appId, projectId, scope]);

  useEffect(() => {
    void loadFirstPage();
  }, [loadFirstPage, refreshKey, refreshSequence]);

  useEffect(() => {
    try {
      window.sessionStorage.setItem(SCOPE_STORAGE_KEY, scope);
    } catch {
      // Session memory is a convenience only; the selected scope still works.
    }
  }, [scope]);

  const textRecordCount = useMemo(
    () => records.filter((record) => (
      record.result_shape === "multi_copy" || record.result_shape === "multi_title"
    )).length,
    [records],
  );

  async function loadMore() {
    if (!nextCursor || loadingMore) return;
    const sequence = ++requestSequence.current;
    const requestQueryKey = queryKey;
    const requestCursor = nextCursor;
    setLoadingMore(true);
    setError("");
    try {
      const page = await listGenerationRecords(projectId, {
        scope,
        ...(scope === "current_app" ? { app_id: appId } : {}),
        cursor: requestCursor,
        limit: 10,
      });
      if (
        sequence !== requestSequence.current
        || requestQueryKey !== activeQueryKey.current
      ) return;
      setRecords((current) => [
        ...current,
        ...page.records.filter((record) => (
          !current.some((existing) => existing.record_id === record.record_id)
        )),
      ]);
      setSelectedItems((current) => {
        const next = new Set(current);
        persistedSelectionKeys(page.records).forEach((key) => next.add(key));
        return next;
      });
      setNextCursor(page.next_cursor);
    } catch (loadError) {
      if (
        sequence !== requestSequence.current
        || requestQueryKey !== activeQueryKey.current
      ) return;
      const message = loadError instanceof Error ? loadError.message : "";
      if (message.includes("已更新") || message.includes("失效")) {
        await loadFirstPage();
      } else {
        setError(message || "更多记录暂时无法读取");
      }
    } finally {
      if (
        sequence === requestSequence.current
        && requestQueryKey === activeQueryKey.current
      ) setLoadingMore(false);
    }
  }

  async function runItemAction(
    key: string,
    action: () => Promise<void>,
    options: { markSelectedKey?: string; refresh?: boolean } = {},
  ): Promise<boolean> {
    if (actionBusy) return false;
    const selectedKey = options.markSelectedKey;
    setActionBusy(key);
    setError("");
    if (selectedKey) {
      pendingSelectionKeys.current.add(selectedKey);
      setSelectedItems((current) => new Set(current).add(selectedKey));
    }
    try {
      await action();
      if (options.refresh) setRefreshSequence((current) => current + 1);
      return true;
    } catch (actionError) {
      if (selectedKey) {
        pendingSelectionKeys.current.delete(selectedKey);
        setSelectedItems((current) => {
          const next = new Set(current);
          next.delete(selectedKey);
          return next;
        });
      }
      setError(actionError instanceof Error ? actionError.message : "操作没有完成，请重试");
      return false;
    } finally {
      setActionBusy("");
    }
  }

  function toggleExpanded(itemId: string) {
    setExpandedItems((current) => {
      const next = new Set(current);
      if (next.has(itemId)) next.delete(itemId);
      else next.add(itemId);
      return next;
    });
  }

  async function submitEdit() {
    if (!editTarget || !editText.trim() || !onEdit) return;
    const key = `edit:${editTarget.item.item_id}`;
    const saved = await runItemAction(
      key,
      () => onEdit(editTarget.record, editTarget.item, editText.trim()),
      { refresh: true },
    );
    if (!saved) return;
    setEditTarget(null);
    setEditText("");
  }

  function renderTextItem(
    record: GenerationRecordBlock,
    item: GenerationTextResultItem,
    index: number,
  ) {
    const actionKey = `${record.record_id}:${item.item_id}`;
    const selected = selectedItems.has(actionKey);
    const expanded = expandedItems.has(actionKey);
    const longCopy = item.kind === "copy" && item.text.length > 150;
    return (
      <article
        className={`generation-result-item generation-result-item--${item.kind}`}
        key={item.item_id}
        aria-label={`${item.kind === "title" ? "标题" : "文案"} ${index + 1}`}
      >
        <div className="generation-result-item__content">
          {item.label ? <span className="generation-result-item__label">{item.label}</span> : null}
          <Typography.Paragraph
            className={longCopy && !expanded ? "generation-result-item__text is-collapsed" : "generation-result-item__text"}
          >
            {item.text}
          </Typography.Paragraph>
          {longCopy ? (
            <button
              type="button"
              className="generation-result-expand"
              aria-expanded={expanded}
              onClick={() => toggleExpanded(actionKey)}
            >
              {expanded ? "收起" : "展开全文"}
            </button>
          ) : null}
        </div>
        <div className="generation-result-item__actions">
          {onCopy && item.actions.includes("copy") ? (
            <Button
              type="text"
              size="small"
              icon={<Copy size={14} aria-hidden />}
              loading={actionBusy === `copy:${actionKey}`}
              onClick={() => void runItemAction(
                `copy:${actionKey}`,
                () => onCopy(record, item),
              )}
            >
              复制
            </Button>
          ) : null}
          {onEdit && item.actions.includes("edit") ? (
            <Button
              type="text"
              size="small"
              icon={<Pencil size={14} aria-hidden />}
              onClick={() => {
                setEditTarget({ record, item });
                setEditText(item.text);
              }}
            >
              编辑
            </Button>
          ) : null}
          {onSelect && item.actions.includes("select") ? (
            <Button
              type={selected ? "default" : "text"}
              size="small"
              icon={<Check size={14} aria-hidden />}
              disabled={selected}
              loading={actionBusy === `select:${actionKey}`}
              aria-pressed={selected}
              onClick={() => void runItemAction(
                `select:${actionKey}`,
                () => onSelect(record, item),
                { markSelectedKey: actionKey },
              )}
            >
              {selected ? "已采用" : "采用"}
            </Button>
          ) : null}
        </div>
      </article>
    );
  }

  function renderRecord(record: GenerationRecordBlock) {
    const state = statusCopy[record.status];
    const textItems = record.items.filter(isTextItem);
    const mediaItem = record.items.find(isMediaItem);
    const runAction = runActionCopy[record.status];
    return (
      <section className="generation-record-block" key={record.record_id}>
        <header className="generation-record-header">
          <div className="generation-record-heading">
            <time dateTime={record.result_available_at || record.created_at}>
              {formatRecordTime(record.result_available_at, record.created_at)}
            </time>
            {scope === "all_results" ? (
              <span className="generation-record-source">{record.app_name}</span>
            ) : null}
            <Tag color={state.color}>{state.label}</Tag>
          </div>
          <div className="generation-record-meta">
            <Typography.Text>
              {record.result_shape === "single_carousel"
                ? "图文成品"
                : record.result_shape === "single_video"
                  ? "视频成片"
                  : record.summary}
            </Typography.Text>
            {runAction && onRunAction ? (
              <Button
                size="small"
                type="text"
                loading={actionBusy === `run:${record.record_id}`}
                onClick={() => void runItemAction(
                  `run:${record.record_id}`,
                  () => onRunAction(record),
                  { refresh: true },
                )}
              >
                {runAction}
              </Button>
            ) : null}
          </div>
        </header>

        {record.compatibility.state === "legacy_unavailable" ? (
          <div className="generation-record-unavailable">
            {record.compatibility.unavailable_reason || "这条历史结果暂时无法预览"}
          </div>
        ) : textItems.length ? (
          <div className={`generation-record-items generation-record-items--${record.result_shape}`}>
            {textItems.map((item, index) => renderTextItem(record, item, index))}
          </div>
        ) : mediaItem ? (
          <MediaResultCard
            record={record}
            item={mediaItem}
            onPublish={onPublish}
          />
        ) : (
          <div className="generation-record-pending">
            {record.status === "failed"
              ? "本次没有生成成功，左侧设置仍为你保留。"
              : "正在生成内容，完成后会在这里显示完整结果。"}
          </div>
        )}
      </section>
    );
  }

  return (
    <section className="project-generation-history" aria-label="生成记录">
      <div className="generation-history-toolbar">
        <div>
          <Typography.Title level={4}>生成记录</Typography.Title>
          <Typography.Text type="secondary">
            {loading ? "正在读取…" : `${records.length} 次生成${scope === "all_results" && textRecordCount !== records.length ? "，含其他应用成果" : ""}`}
          </Typography.Text>
        </div>
        <Segmented
          aria-label="生成记录范围"
          value={scope}
          options={[
            { label: "当前应用", value: "current_app" },
            { label: "全部成果", value: "all_results" },
          ]}
          onChange={(value) => setScope(value as Scope)}
        />
      </div>

      {error ? (
        <Alert
          type="error"
          showIcon
          message="生成记录暂时无法读取"
          description={error}
          action={(
            <Button
              size="small"
              icon={<RefreshCw size={14} aria-hidden />}
              onClick={() => void loadFirstPage()}
            >
              重试
            </Button>
          )}
        />
      ) : null}

      {loading ? (
        <div className="generation-history-loading" aria-label="正在加载生成记录">
          <Skeleton active paragraph={{ rows: 4 }} />
          <Skeleton active paragraph={{ rows: 3 }} />
        </div>
      ) : records.length ? (
        <div className="generation-record-stream">{records.map(renderRecord)}</div>
      ) : (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={(
            <div className="generation-history-empty-copy">
              <strong>还没有生成记录</strong>
              <span>完成左侧设置并点击生成，结果会保存在这里。</span>
            </div>
          )}
        />
      )}

      {nextCursor ? (
        <Button
          block
          className="generation-history-more"
          loading={loadingMore}
          onClick={() => void loadMore()}
        >
          加载更早记录
        </Button>
      ) : null}

      <Modal
        title={editTarget?.item.kind === "title" ? "编辑标题" : "编辑文案"}
        open={Boolean(editTarget)}
        okText="保存修改"
        cancelText="取消"
        okButtonProps={{ disabled: !editText.trim(), loading: actionBusy.startsWith("edit:") }}
        onOk={() => void submitEdit()}
        onCancel={() => {
          if (actionBusy.startsWith("edit:")) return;
          setEditTarget(null);
          setEditText("");
        }}
        destroyOnHidden
      >
        <Input.TextArea
          autoFocus
          aria-label={editTarget?.item.kind === "title" ? "标题内容" : "文案内容"}
          rows={editTarget?.item.kind === "title" ? 3 : 9}
          maxLength={editTarget?.item.kind === "title" ? 200 : 5000}
          showCount
          value={editText}
          onChange={(event) => setEditText(event.target.value)}
        />
      </Modal>
    </section>
  );
}
