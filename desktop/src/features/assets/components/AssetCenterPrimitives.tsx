import { Image as ImageIcon, LayoutTemplate, Mic2, Package, UserRound, Video } from "lucide-react";
import { useEffect, useState } from "react";
import { assetBlobUrl, LibraryItemV2 } from "../../../api";
import { toAssetViewModel } from "../model/assetViewModel";

export type AssetKind = LibraryItemV2["kind"];

export const kindIcons: Record<AssetKind, typeof Video> = {
  video: Video,
  image: ImageIcon,
  audio: Mic2,
  voice: Mic2,
  digital_human: UserRound,
  brand: Package,
  template: LayoutTemplate,
};

export function ProtectedAssetImage({ src, alt }: { src: string; alt: string }) {
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

export function ProtectedAssetMedia({ src, kind, title }: { src: string; kind: "audio" | "video" | "image"; title: string }) {
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
  if (kind === "audio") return <audio controls src={resolved || src} aria-label={`${title}试听`} />;
  if (kind === "video") return <video controls src={resolved || src} aria-label={`${title}预览`} />;
  return <img src={resolved || src} alt={title} />;
}

export function AssetImageInspector({ src, title }: { src: string; title: string }) {
  const [resolved, setResolved] = useState("");
  const [fit, setFit] = useState<"contain" | "cover">("contain");
  const [zoom, setZoom] = useState(1);
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
  return <div className="asset-image-inspector" aria-label={`${title}图片检查器`}>
    <div className="asset-image-inspector-toolbar" role="toolbar" aria-label="图片查看选项">
      <button type="button" onClick={() => setFit("contain")} aria-pressed={fit === "contain"}>完整</button>
      <button type="button" onClick={() => setFit("cover")} aria-pressed={fit === "cover"}>填充</button>
      <button type="button" onClick={() => setZoom((value) => Math.max(0.5, Number((value - 0.25).toFixed(2))))} aria-label="缩小图片">−</button>
      <span>{Math.round(zoom * 100)}%</span>
      <button type="button" onClick={() => setZoom((value) => Math.min(3, Number((value + 0.25).toFixed(2))))} aria-label="放大图片">＋</button>
      <button type="button" onClick={() => setZoom(1)}>重置</button>
    </div>
    <div className="asset-image-inspector-stage checkerboard">
      <img src={resolved || src} alt={title} style={{ objectFit: fit, transform: `scale(${zoom})` }} />
    </div>
  </div>;
}

export function summaryText(item: LibraryItemV2) {
  const view = toAssetViewModel(item);
  if (view.kind === "video") return view.display.duration_ms ? `${formatDuration(view.display.duration_ms)} · ${view.display.width && view.display.height ? `${view.display.width}×${view.display.height}` : "规格待分析"}` : "视频规格待分析";
  if (view.kind === "image") return view.display.width && view.display.height ? `${view.display.width}×${view.display.height}` : "图片规格待分析";
  if (view.kind === "audio") return view.display.duration_ms ? formatDuration(view.display.duration_ms) : "音频时长待分析";
  if (view.kind === "voice") return `${view.display.language} · ${view.display.style}`;
  if (view.kind === "digital_human") return `${view.display.media_types.includes("video") ? "视频形象" : "图片形象"} · ${item.tags.join("、") || "待完善资料"}`;
  if (view.kind === "template") return `${view.display.canvas_width || 1080}×${view.display.canvas_height || 1920} · v${view.display.revision}`;
  return view.display.has_logo ? "品牌套件 · 已配置 Logo" : "品牌套件待完善";
}

export function formatDuration(value: number) {
  const seconds = Math.round(value / 1000);
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

export function formatBytes(value: number) {
  if (value < 1024 * 1024) return `${Math.max(1, Math.round(value / 1024))} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatLocalDate(value: string) {
  if (!value) return "未记录";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(date);
}

export function defaultTemplateLayoutContract(fontSize: number, baseTemplateId: string) {
  return {
    schema_version: 2,
    canvas: { width: 1080, height: 1920 },
    base_template_id: baseTemplateId,
    fonts: [{ token: "brand_primary", font_id: "noto-sans-sc-bold", family: "Noto Sans CJK SC", weight: 700, style: "normal", font_sha256: "b5f0d1a190a7f9b43c310a8850630af12553df32c4c050543f9059732d9b4c0a" }],
    cover: {
      title: { x: 72, y: 160, width: 936, height: 360, font_token: "brand_primary", font_size: 72, line_height: 1.18, max_lines: 3, align: "left", vertical_align: "top", overflow: "shrink" },
      subtitle: { x: 72, y: 560, width: 936, height: 240, font_token: "brand_primary", font_size: fontSize, line_height: 1.25, max_lines: 2, align: "left", vertical_align: "top", overflow: "shrink" },
      safe_area: { top: 120, right: 60, bottom: 160, left: 60 },
    },
    video_subtitle: { font_token: "brand_primary", font_size: fontSize, alignment: 2, margin_l: 72, margin_r: 72, margin_v: 180, outline: 2, shadow: 0, max_lines: 2, safe_area: { top: 100, right: 60, bottom: 120, left: 60 }, },
  };
}
