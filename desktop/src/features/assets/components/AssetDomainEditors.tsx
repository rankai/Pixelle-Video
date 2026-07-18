import { useEffect, useState } from "react";
import {
  BrandKitV2Payload,
  LibraryItemV2,
  listLibraryItemsV2,
  patchBrandKitV2,
  patchTemplateV2,
  previewTemplateV2,
} from "../../../api";

type EditorProps = { item: LibraryItemV2; onUpdated: () => Promise<void> | void };

function valueAt(source: Record<string, unknown>, path: string[], fallback: string): string {
  let current: unknown = source;
  for (const key of path) {
    if (!current || typeof current !== "object") return fallback;
    current = (current as Record<string, unknown>)[key];
  }
  return current === undefined || current === null ? fallback : String(current);
}

function setAt(source: Record<string, unknown>, path: string[], value: number) {
  let current = source;
  for (const key of path.slice(0, -1)) {
    const next = current[key];
    if (!next || typeof next !== "object" || Array.isArray(next)) current[key] = {};
    current = current[key] as Record<string, unknown>;
  }
  current[path[path.length - 1]] = value;
}

export function BrandKitEditor({ item, onUpdated }: EditorProps) {
  const source = item.brand || {};
  const [draft, setDraft] = useState<BrandKitV2Payload>({});
  const [images, setImages] = useState<LibraryItemV2[]>([]);
  const [audio, setAudio] = useState<LibraryItemV2[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setDraft({
      brand_name: String(source.brand_name || item.name),
      logo_asset_id: source.logo_asset_id ? String(source.logo_asset_id) : null,
      default_bgm_asset_id: source.default_bgm_asset_id ? String(source.default_bgm_asset_id) : null,
      primary_color: String(source.primary_color || "#1f6feb"),
      secondary_color: String(source.secondary_color || "#0f766e"),
      font_family: String(source.font_family || "noto-sans-sc-bold"),
      default_subtitle_style: String(source.default_subtitle_style || ""),
      ending_card_text: String(source.ending_card_text || ""),
      store_address: String(source.store_address || ""),
      phone: String(source.phone || ""),
      coupon_phrase: String(source.coupon_phrase || ""),
    });
  }, [item.name, item.resource_id, source]);

  useEffect(() => {
    void Promise.all([
      listLibraryItemsV2("image", "", { limit: 100, sort: "recent" }),
      listLibraryItemsV2("audio", "", { limit: 100, sort: "recent" }),
    ]).then(([imageResult, audioResult]) => {
      setImages(imageResult.items);
      setAudio(audioResult.items);
    }).catch(() => undefined);
  }, []);

  function update(key: keyof BrandKitV2Payload, value: string) {
    setDraft((current) => ({ ...current, [key]: value }));
  }

  async function save() {
    setBusy(true);
    setError("");
    try {
      await patchBrandKitV2(item.resource_id, draft);
      await onUpdated();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return <section className="asset-domain-editor" aria-label="品牌编辑器">
    <div className="asset-domain-editor-heading"><strong>品牌配置</strong><small>保存后可在品牌选择器和成片结尾卡复用。</small></div>
    <div className="asset-domain-editor-grid">
      <label>品牌名称<input value={draft.brand_name || ""} onChange={(event) => update("brand_name", event.target.value)} /></label>
      <label>Logo<select value={draft.logo_asset_id || ""} onChange={(event) => update("logo_asset_id", event.target.value)}><option value="">不设置 Logo</option>{images.map((image) => <option key={image.resource_id} value={image.asset_id || image.resource_id}>{image.name}</option>)}</select></label>
      <label>默认 BGM<select value={draft.default_bgm_asset_id || ""} onChange={(event) => update("default_bgm_asset_id", event.target.value)}><option value="">不设置 BGM</option>{audio.map((item) => <option key={item.resource_id} value={item.asset_id || item.resource_id}>{item.name}</option>)}</select></label>
      <label>字体<select value={draft.font_family || "noto-sans-sc-bold"} onChange={(event) => update("font_family", event.target.value)}><option value="noto-sans-sc-bold">Noto Sans CJK SC（随应用分发）</option></select></label>
      <label>主色<input type="color" value={draft.primary_color || "#1f6feb"} onChange={(event) => update("primary_color", event.target.value)} /></label>
      <label>辅色<input type="color" value={draft.secondary_color || "#0f766e"} onChange={(event) => update("secondary_color", event.target.value)} /></label>
    </div>
    <details><summary>结尾卡与门店信息</summary><div className="asset-domain-editor-grid"><label>结尾卡文案<input value={draft.ending_card_text || ""} onChange={(event) => update("ending_card_text", event.target.value)} /></label><label>默认字幕样式<input value={draft.default_subtitle_style || ""} onChange={(event) => update("default_subtitle_style", event.target.value)} placeholder="可选样式说明" /></label><label>门店地址<input value={draft.store_address || ""} onChange={(event) => update("store_address", event.target.value)} /></label><label>电话<input value={draft.phone || ""} onChange={(event) => update("phone", event.target.value)} /></label><label>优惠/团购话术<input value={draft.coupon_phrase || ""} onChange={(event) => update("coupon_phrase", event.target.value)} /></label></div></details>
    <div className="brand-preview" style={{ borderColor: draft.primary_color, color: draft.secondary_color }}><strong>{draft.brand_name || "品牌预览"}</strong><span>{draft.ending_card_text || "门店优惠信息将在这里预览"}</span><small>{draft.store_address || "门店地址"} · {draft.phone || "联系电话"}</small></div>
    {error ? <div className="asset-center-v2-error" role="alert">{error}</div> : null}
    <button type="button" className="primary" onClick={() => void save()} disabled={busy || !draft.brand_name?.trim()}>{busy ? "保存中…" : "保存品牌并进入生产"}</button>
  </section>;
}

export function TemplateLayoutEditor({ item, onUpdated }: EditorProps) {
  const contract = item.layout_contract;
  const template = item.template || {};
  const [displayName, setDisplayName] = useState(item.name);
  const [shortDescription, setShortDescription] = useState(String(template.short_description || item.description || ""));
  const [fields, setFields] = useState({ titleX: "72", titleY: "160", titleWidth: "936", titleHeight: "360", titleFontSize: "72", subtitleX: "72", subtitleY: "600", subtitleWidth: "936", subtitleHeight: "240", subtitleFontSize: "48", videoFontSize: "48", videoMarginV: "180" });
  const [previewUrl, setPreviewUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setDisplayName(item.name);
    setShortDescription(String((item.template || {}).short_description || item.description || ""));
    if (!item.layout_contract) return;
    setFields({
      titleX: valueAt(item.layout_contract, ["cover", "title", "x"], "72"),
      titleY: valueAt(item.layout_contract, ["cover", "title", "y"], "160"),
      titleWidth: valueAt(item.layout_contract, ["cover", "title", "width"], "936"),
      titleHeight: valueAt(item.layout_contract, ["cover", "title", "height"], "360"),
      titleFontSize: valueAt(item.layout_contract, ["cover", "title", "font_size"], "72"),
      subtitleX: valueAt(item.layout_contract, ["cover", "subtitle", "x"], "72"),
      subtitleY: valueAt(item.layout_contract, ["cover", "subtitle", "y"], "600"),
      subtitleWidth: valueAt(item.layout_contract, ["cover", "subtitle", "width"], "936"),
      subtitleHeight: valueAt(item.layout_contract, ["cover", "subtitle", "height"], "240"),
      subtitleFontSize: valueAt(item.layout_contract, ["cover", "subtitle", "font_size"], "48"),
      videoFontSize: valueAt(item.layout_contract, ["video_subtitle", "font_size"], "48"),
      videoMarginV: valueAt(item.layout_contract, ["video_subtitle", "margin_v"], "180"),
    });
    setPreviewUrl(String(item.template?.preview_url || item.cover_url || ""));
  }, [item]);

  function updateField(key: keyof typeof fields, value: string) {
    setFields((current) => ({ ...current, [key]: value.replace(/[^0-9]/g, "") }));
  }

  async function save() {
    if (!contract) return;
    setBusy(true);
    setError("");
    try {
      const draft = JSON.parse(JSON.stringify(contract)) as Record<string, unknown>;
      for (const [key, path] of Object.entries({ titleX: ["cover", "title", "x"], titleY: ["cover", "title", "y"], titleWidth: ["cover", "title", "width"], titleHeight: ["cover", "title", "height"], titleFontSize: ["cover", "title", "font_size"], subtitleX: ["cover", "subtitle", "x"], subtitleY: ["cover", "subtitle", "y"], subtitleWidth: ["cover", "subtitle", "width"], subtitleHeight: ["cover", "subtitle", "height"], subtitleFontSize: ["cover", "subtitle", "font_size"], videoFontSize: ["video_subtitle", "font_size"], videoMarginV: ["video_subtitle", "margin_v"] } as Record<string, string[]>)) setAt(draft, path, Math.max(1, Number(fields[key as keyof typeof fields]) || 1));
      const preview = await previewTemplateV2(draft, { title: displayName.trim() || item.name, subtitle: "同一份布局契约预览" });
      await patchTemplateV2(item.resource_id, { display_name: displayName.trim() || item.name, short_description: shortDescription, schema_version: 2, renderer_version: String(template.renderer_version || "ip-broadcast-composer-v2"), cover_contract: { canvas_width: Number(valueAt(draft, ["canvas", "width"], "1080")), canvas_height: Number(valueAt(draft, ["canvas", "height"], "1920")) }, subtitle_contract: { font_size: Number(fields.videoFontSize) || 48 }, layout_contract: preview.resolved_contract, preview_url: preview.preview_url || null });
      setPreviewUrl(preview.preview_url || "");
      await onUpdated();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  if (!contract) return <section className="asset-domain-editor" aria-label="模板编辑器"><strong>模板尚未绑定可编辑布局契约</strong><small>该模板仍可在高级信息中查看 renderer 和 revision；保存新的 V2 contract 后才能进行可视化编辑。</small></section>;
  return <section className="asset-domain-editor" aria-label="模板布局编辑器"><div className="asset-domain-editor-heading"><strong>模板视觉布局</strong><small>预览和保存均经过服务端 TemplateLayoutContract resolver。</small></div><div className="asset-domain-editor-grid"><label>模板名称<input value={displayName} onChange={(event) => setDisplayName(event.target.value)} /></label><label>说明<input value={shortDescription} onChange={(event) => setShortDescription(event.target.value)} /></label><label>标题 X<input inputMode="numeric" value={fields.titleX} onChange={(event) => updateField("titleX", event.target.value)} /></label><label>标题 Y<input inputMode="numeric" value={fields.titleY} onChange={(event) => updateField("titleY", event.target.value)} /></label><label>标题宽度<input inputMode="numeric" value={fields.titleWidth} onChange={(event) => updateField("titleWidth", event.target.value)} /></label><label>标题高度<input inputMode="numeric" value={fields.titleHeight} onChange={(event) => updateField("titleHeight", event.target.value)} /></label><label>标题字号<input inputMode="numeric" value={fields.titleFontSize} onChange={(event) => updateField("titleFontSize", event.target.value)} /></label><label>副标题 X<input inputMode="numeric" value={fields.subtitleX} onChange={(event) => updateField("subtitleX", event.target.value)} /></label><label>副标题 Y<input inputMode="numeric" value={fields.subtitleY} onChange={(event) => updateField("subtitleY", event.target.value)} /></label><label>副标题宽度<input inputMode="numeric" value={fields.subtitleWidth} onChange={(event) => updateField("subtitleWidth", event.target.value)} /></label><label>副标题高度<input inputMode="numeric" value={fields.subtitleHeight} onChange={(event) => updateField("subtitleHeight", event.target.value)} /></label><label>副标题字号<input inputMode="numeric" value={fields.subtitleFontSize} onChange={(event) => updateField("subtitleFontSize", event.target.value)} /></label><label>成片字号<input inputMode="numeric" value={fields.videoFontSize} onChange={(event) => updateField("videoFontSize", event.target.value)} /></label><label>字幕底部距离<input inputMode="numeric" value={fields.videoMarginV} onChange={(event) => updateField("videoMarginV", event.target.value)} /></label></div>{previewUrl ? <img className="asset-template-preview" src={previewUrl} alt="模板权威预览" /> : null}{error ? <div className="asset-center-v2-error" role="alert">{error}</div> : null}<button type="button" className="primary" onClick={() => void save()} disabled={busy}>{busy ? "预览并保存中…" : "预览并保存模板版本"}</button></section>;
}
