import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Avatar,
  Button,
  Card,
  Collapse,
  ColorPicker,
  Form,
  Input,
  Modal,
  Select,
  Skeleton,
  Space,
  Tag,
  Typography,
} from "antd";

import {
  createContentProject,
  getBrandProjectSummary,
  getProjectMediaRevisionPreview,
  getProjectBrandSyncPreview,
  listProjectBrands,
  replaceProjectBrand,
  syncProjectBrand,
  updateProjectMaterial,
  type BrandProjectListItem,
  type BrandSyncPreview,
  type ContentProject,
  type ContextSnapshot,
} from "../../api";

type Fact = { fact_id: string; text: string; source: string; source_ref?: string | null };
type BrandValues = {
  display_name: string;
  logo_ref: { asset_id: string; asset_revision: string } | null;
  store_address: string;
  phone: string;
  primary_color: string;
  secondary_color: string;
  font_family: string;
  default_subtitle_style: string;
  default_bgm_ref: { asset_id: string; asset_revision: string } | null;
  ending_card_text: string;
  coupon_phrase: string;
};
type BrandContext = {
  brand_id: string;
  domain_revision: number;
  values: BrandValues;
  overridden_fields: string[];
};
type ProjectBrief = {
  subject_type: string;
  offer: {
    name: string;
    category: string;
    price_facts: Fact[];
    promotion_facts: Fact[];
  };
  marketing_goal: string;
  audience: { primary: string; scenes: string[] };
  selling_points: Fact[];
  proof_points: Fact[];
  required_facts: Fact[];
  forbidden_claims: string[];
  asset_refs: Array<{ asset_id: string; asset_revision: string }>;
};
type V3Payload = {
  schema_version: 3;
  brand_context: BrandContext | null;
  project_brief: ProjectBrief;
};

const overrideFields: Array<{
  key: keyof BrandValues;
  label: string;
  placeholder: string;
  kind?: "color";
}> = [
  { key: "display_name", label: "品牌显示名称", placeholder: "本项目使用的名称" },
  { key: "store_address", label: "地址", placeholder: "本项目使用的地址" },
  { key: "phone", label: "电话", placeholder: "本项目使用的电话" },
  { key: "primary_color", label: "品牌主色", placeholder: "#2563EB", kind: "color" },
  { key: "secondary_color", label: "品牌辅色", placeholder: "#E0E7FF", kind: "color" },
  { key: "font_family", label: "默认字体", placeholder: "本项目使用的字体" },
  { key: "default_subtitle_style", label: "字幕样式", placeholder: "本项目使用的字幕样式" },
  { key: "ending_card_text", label: "结尾卡文案", placeholder: "本项目使用的结尾卡文案" },
  { key: "coupon_phrase", label: "优惠话术", placeholder: "本项目使用的优惠话术" },
];

function asV3(snapshot: ContextSnapshot | null): V3Payload | null {
  if (snapshot?.schema_version !== 3 || snapshot.payload?.schema_version !== 3) return null;
  return snapshot.payload as unknown as V3Payload;
}

function lines(value: string) {
  return value.split(/\r?\n|[,，]/).map((item) => item.trim()).filter(Boolean);
}

function factLines(value: unknown) {
  return Array.isArray(value)
    ? value.map((item) => String((item as Fact)?.text || "").trim()).filter(Boolean).join("\n")
    : "";
}

function toFacts(value: string, prefix: string): Fact[] {
  return lines(value).map((text, index) => ({
    fact_id: `${prefix}-${index + 1}`,
    text,
    source: "user",
  }));
}

function errorText(error: unknown) {
  return error instanceof Error ? error.message : "请求未完成，请稍后重试";
}

function createIdempotencyKey(projectId: string) {
  const suffix = typeof crypto.randomUUID === "function"
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return `brand-sync:${projectId}:${suffix}`;
}

export type ProjectCreateValues = {
  name: string;
  primary_goal: string;
  brand_id?: string;
  expected_brand_domain_revision?: number;
};

export function BrandProjectCreateDialog({
  open,
  busy,
  onCancel,
  onCreated,
}: {
  open: boolean;
  busy: boolean;
  onCancel: () => void;
  onCreated: (project: ContentProject) => void;
}) {
  const [name, setName] = useState("");
  const [goal, setGoal] = useState("");
  const [brands, setBrands] = useState<BrandProjectListItem[]>([]);
  const [selectedBrandId, setSelectedBrandId] = useState("");
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) return;
    let active = true;
    setLoading(true);
    setError("");
    listProjectBrands()
      .then(({ items }) => {
        if (!active) return;
        setBrands(items);
        setSelectedBrandId(items.length === 1 ? items[0].brand_id : "");
      })
      .catch((loadError) => {
        if (active) setError(errorText(loadError));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [open]);

  async function submit() {
    if (!name.trim() || !goal.trim() || submitting || busy) return;
    setSubmitting(true);
    setError("");
    try {
      let revision: number | undefined;
      if (selectedBrandId) {
        revision = (await getBrandProjectSummary(selectedBrandId)).domain_revision;
      }
      const created = await createContentProject({
        name: name.trim(),
        primary_goal: goal.trim(),
        brand_id: selectedBrandId || undefined,
        expected_brand_domain_revision: revision,
      });
      onCreated(created);
      setName("");
      setGoal("");
      setSelectedBrandId("");
    } catch (createError) {
      setError(errorText(createError));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open={open}
      title="新建项目"
      okText="创建项目"
      cancelText="取消"
      confirmLoading={submitting || busy}
      okButtonProps={{ disabled: loading || !name.trim() || !goal.trim() }}
      onOk={() => void submit()}
      onCancel={() => {
        if (!submitting && !busy) onCancel();
      }}
      afterOpenChange={(nextOpen) => {
        if (!nextOpen) setError("");
      }}
    >
      <Space orientation="vertical" size="middle" style={{ width: "100%" }}>
        <Typography.Paragraph type="secondary">
          项目用于组织这次营销工作。品牌资料来自企业资产库，创建后自动继承，不需要重复填写。
        </Typography.Paragraph>
        {error ? <Alert type="error" showIcon title={error} /> : null}
        <label className="creation-select-field">
          <span>项目名称</span>
          <Input
            autoFocus
            aria-label="新项目名称"
            value={name}
            placeholder="例如：夏日新品推广"
            onChange={(event) => setName(event.target.value)}
          />
        </label>
        <label className="creation-select-field">
          <span>营销目标</span>
          <Input.TextArea
            aria-label="新项目营销目标"
            value={goal}
            placeholder="例如：吸引附近上班族到店体验新品"
            rows={3}
            onChange={(event) => setGoal(event.target.value)}
          />
        </label>
        <label className="creation-select-field">
          <span>使用品牌包</span>
          {loading ? <Skeleton.Input active block /> : (
            <Select
              aria-label="新项目品牌包"
              value={selectedBrandId || undefined}
              allowClear={brands.length !== 1}
              showSearch
              optionFilterProp="label"
              placeholder={brands.length ? "选择企业资产库中的品牌包" : "企业资产库中暂无可用品牌包"}
              options={brands.map((brand) => ({ value: brand.brand_id, label: brand.name }))}
              onChange={(value) => setSelectedBrandId(value || "")}
              disabled={!brands.length}
            />
          )}
          {brands.length === 0 ? (
            <Space wrap size="small">
              <Typography.Text type="secondary">可以先创建无品牌项目，之后再明确关联。</Typography.Text>
              <Button type="link" size="small" href="#/assets">前往企业资产库</Button>
            </Space>
          ) : (
            <Typography.Text type="secondary">
              {brands.length === 1
                ? "仅有一个品牌包，已为你选中；点击“创建项目”前不会写入任何项目数据。"
                : "品牌包仍保留在企业资产库，项目只记录本次使用关系。"}
            </Typography.Text>
          )}
        </label>
      </Space>
    </Modal>
  );
}

export function BrandProjectContextPanel({
  project,
  snapshot,
  open,
  onOpen,
  onClose,
  onSaved,
  onReload,
  onDirtyChange,
}: {
  project: ContentProject;
  snapshot: ContextSnapshot | null;
  open: boolean;
  onOpen?: () => void;
  onClose: () => void;
  onSaved: (snapshot: ContextSnapshot) => void;
  onReload: () => Promise<void>;
  onDirtyChange?: (dirty: boolean) => void;
}) {
  const payload = asV3(snapshot);
  const brand = payload?.brand_context || null;
  const brief = payload?.project_brief;
  const [brands, setBrands] = useState<BrandProjectListItem[]>([]);
  const [brandsLoading, setBrandsLoading] = useState(true);
  const [brandListError, setBrandListError] = useState("");
  const [brandPickerOpen, setBrandPickerOpen] = useState(false);
  const [nextBrandId, setNextBrandId] = useState("");
  const [brandBusy, setBrandBusy] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [preview, setPreview] = useState<BrandSyncPreview | null>(null);
  const [previewError, setPreviewError] = useState("");
  const [previewOpen, setPreviewOpen] = useState(false);
  const [logoUrl, setLogoUrl] = useState("");
  const [logoUnavailable, setLogoUnavailable] = useState(false);
  const [offerName, setOfferName] = useState(brief?.offer.name || "");
  const [goal, setGoal] = useState(brief?.marketing_goal || project.primary_goal);
  const [audience, setAudience] = useState(brief?.audience.primary || "");
  const [sellingPoints, setSellingPoints] = useState(factLines(brief?.selling_points));
  const [promotion, setPromotion] = useState(factLines(brief?.offer.promotion_facts));
  const [materials, setMaterials] = useState(factLines(brief?.required_facts));
  const [overrides, setOverrides] = useState<Record<string, unknown>>({});

  useEffect(() => {
    setOfferName(brief?.offer.name || "");
    setGoal(brief?.marketing_goal || project.primary_goal);
    setAudience(brief?.audience.primary || "");
    setSellingPoints(factLines(brief?.selling_points));
    setPromotion(factLines(brief?.offer.promotion_facts));
    setMaterials(factLines(brief?.required_facts));
    setOverrides(Object.fromEntries(
      (brand?.overridden_fields || [])
        .filter((field) => overrideFields.some((item) => item.key === field))
        .map((field) => [field, brand?.values[field as keyof BrandValues]]),
    ));
    onDirtyChange?.(false);
  }, [snapshot?.context_snapshot_id, project.project_id]);

  useEffect(() => {
    let active = true;
    setBrandsLoading(true);
    setBrandListError("");
    listProjectBrands()
      .then(({ items }) => {
        if (!active) return;
        setBrands(items);
        setBrandListError("");
      })
      .catch((loadError) => {
        if (active) {
          setBrands([]);
          setBrandListError(`品牌列表加载失败：${errorText(loadError)}`);
        }
      })
      .finally(() => {
        if (active) setBrandsLoading(false);
      });
    return () => {
      active = false;
    };
  }, [project.project_id]);

  const logoAssetId = brand?.values.logo_ref?.asset_id || "";
  const logoAssetRevision = brand?.values.logo_ref?.asset_revision || "";

  useEffect(() => {
    let active = true;
    setLogoUrl("");
    setLogoUnavailable(false);
    if (logoAssetId && logoAssetRevision) {
      getProjectMediaRevisionPreview(logoAssetId, logoAssetRevision)
        .then((item) => {
          if (!active) return;
          if (item.asset_id !== logoAssetId || item.asset_revision !== logoAssetRevision) {
            throw new Error("exact media revision mismatch");
          }
          const exactUrl = item.thumbnail_url || item.file_url;
          setLogoUrl(exactUrl);
          setLogoUnavailable(!exactUrl);
        })
        .catch(() => {
          if (active) {
            setLogoUrl("");
            setLogoUnavailable(true);
          }
        });
    }
    return () => {
      active = false;
    };
  }, [logoAssetId, logoAssetRevision]);

  useEffect(() => {
    if (!brand || !snapshot) {
      setPreview(null);
      setPreviewError("");
      return;
    }
    let active = true;
    setPreviewError("");
    getProjectBrandSyncPreview(project.project_id, snapshot.context_snapshot_id)
      .then((next) => {
        if (!active) return;
        setPreview(next);
        setPreviewError("");
      })
      .catch((previewLoadError) => {
        if (active) {
          setPreview(null);
          setPreviewError(`无法检查品牌更新：${errorText(previewLoadError)}`);
        }
      });
    return () => {
      active = false;
    };
  }, [brand?.brand_id, project.project_id, snapshot?.context_snapshot_id]);

  const dirty = useMemo(() => {
    if (!brief) return false;
    const currentOverrides = Object.fromEntries(
      (brand?.overridden_fields || [])
        .filter((field) => overrideFields.some((item) => item.key === field))
        .map((field) => [field, brand?.values[field as keyof BrandValues]]),
    );
    return offerName !== brief.offer.name
      || goal !== brief.marketing_goal
      || audience !== brief.audience.primary
      || sellingPoints !== factLines(brief.selling_points)
      || promotion !== factLines(brief.offer.promotion_facts)
      || materials !== factLines(brief.required_facts)
      || JSON.stringify(overrides) !== JSON.stringify(currentOverrides);
  }, [audience, brand, brief, goal, materials, offerName, overrides, promotion, sellingPoints]);

  useEffect(() => onDirtyChange?.(dirty), [dirty, onDirtyChange]);

  async function save() {
    if (!snapshot || !brief || !offerName.trim() || !goal.trim() || !audience.trim()) return;
    setBusy(true);
    setError("");
    try {
      const nextBrief: ProjectBrief = {
        ...brief,
        offer: {
          ...brief.offer,
          name: offerName.trim(),
          promotion_facts: toFacts(promotion, "promotion"),
        },
        marketing_goal: goal.trim(),
        audience: { ...brief.audience, primary: audience.trim() },
        selling_points: toFacts(sellingPoints, "selling"),
        required_facts: toFacts(materials, "material"),
      };
      const next = await updateProjectMaterial(project.project_id, {
        expected_context_snapshot_id: snapshot.context_snapshot_id,
        project_brief: nextBrief as unknown as Record<string, unknown>,
        project_overrides: overrides,
      });
      onSaved(next);
      setError("");
    } catch (saveError) {
      setError(errorText(saveError));
    } finally {
      setBusy(false);
    }
  }

  async function changeBrand() {
    if (!nextBrandId || brandBusy) return;
    setBrandBusy(true);
    setError("");
    try {
      const summary = await getBrandProjectSummary(nextBrandId);
      await replaceProjectBrand(project.project_id, {
        brand_id: nextBrandId,
        expected_context_snapshot_id: snapshot?.context_snapshot_id || null,
        expected_domain_revision: summary.domain_revision,
      });
      setBrandPickerOpen(false);
      setNextBrandId("");
      await onReload();
    } catch (changeError) {
      setError(errorText(changeError));
    } finally {
      setBrandBusy(false);
    }
  }

  async function sync() {
    if (!snapshot) return;
    setBrandBusy(true);
    setError("");
    try {
      await syncProjectBrand(project.project_id, {
        expected_context_snapshot_id: snapshot.context_snapshot_id,
        idempotency_key: createIdempotencyKey(project.project_id),
      });
      setPreviewOpen(false);
      await onReload();
    } catch (syncError) {
      setError(errorText(syncError));
    } finally {
      setBrandBusy(false);
    }
  }

  const brandPicker = (
    <Modal
      open={brandPickerOpen}
      title={brand ? "更换项目品牌" : "关联项目品牌"}
      okText={brand ? "确认更换" : "确认关联"}
      confirmLoading={brandBusy}
      okButtonProps={{ disabled: !nextBrandId || nextBrandId === brand?.brand_id }}
      onOk={() => void changeBrand()}
      onCancel={() => !brandBusy && setBrandPickerOpen(false)}
    >
      <Typography.Paragraph type="secondary">
        关联或更换后会创建新的项目资料记录；已有生成结果继续使用原品牌版本。
      </Typography.Paragraph>
      <Select
        aria-label="选择项目品牌包"
        value={nextBrandId || undefined}
        showSearch
        optionFilterProp="label"
        placeholder="选择企业资产库中的品牌包"
        options={brands.map((item) => ({ value: item.brand_id, label: item.name }))}
        onChange={setNextBrandId}
        loading={brandsLoading}
        disabled={brandsLoading || Boolean(brandListError)}
        style={{ width: "100%" }}
      />
      {brandListError ? (
        <Alert
          type="error"
          showIcon
          title={brandListError}
          action={<Button type="link" href="#/assets">前往企业资产库</Button>}
        />
      ) : null}
    </Modal>
  );

  if (!payload || !brief) {
    return (
      <section className="brand-project-context" aria-label="旧项目品牌关联">
      <Alert
        className="brand-project-status-alert"
        type="info"
        showIcon
        title="这是旧项目"
          description="旧项目会保持原样，不会自动关联品牌。需要时可以明确关联品牌包，已有内容和结果不会改变。"
          action={<Button onClick={() => setBrandPickerOpen(true)}>关联品牌包</Button>}
        />
        {brandListError ? <Alert type="error" showIcon title={brandListError} /> : null}
        {error ? <Alert type="error" showIcon title={error} /> : null}
        {brandPicker}
      </section>
    );
  }

  return (
    <section className="brand-project-context" aria-label="项目与品牌资料">
      <Card size="small" className="brand-project-summary">
        {brand ? (
          <div className="brand-project-summary__content">
            <Avatar
              src={logoUrl || undefined}
              size={48}
              onError={() => {
                setLogoUrl("");
                setLogoUnavailable(true);
                return false;
              }}
            >
              {brand.values.display_name.slice(0, 1)}
            </Avatar>
            <div className="brand-project-summary__main">
              <Space wrap>
                <Typography.Text strong>{brand.values.display_name}</Typography.Text>
                {preview?.has_changes ? <Tag color="gold">品牌资料有更新</Tag> : <Tag>已继承品牌资料</Tag>}
                {logoUnavailable ? <Tag>Logo 暂不可用</Tag> : null}
              </Space>
              <Typography.Text type="secondary" className="brand-project-summary__desktop-copy">
                Logo、地址、电话、品牌色和默认 BGM 已从企业资产库继承。本项目保存的是固定版本，之后不会悄悄变化。
              </Typography.Text>
              <Typography.Text type="secondary" className="brand-project-summary__mobile-copy">
                已继承 Logo、联系方式、品牌色和 BGM；历史结果不会自动变化。
              </Typography.Text>
              <Space wrap size="small">
                {!open && onOpen ? <Button type="link" size="small" onClick={onOpen}>编辑本次信息</Button> : null}
                <Button type="link" size="small" onClick={() => setBrandPickerOpen(true)}>
                  {previewError ? "重新关联品牌" : "更换品牌"}
                </Button>
                {preview?.has_changes ? <Button type="link" size="small" onClick={() => setPreviewOpen(true)}>查看变化</Button> : null}
              </Space>
            </div>
            <div className="brand-project-colors" aria-label="品牌色">
              <span style={{ background: brand.values.primary_color }} />
              <span style={{ background: brand.values.secondary_color }} />
            </div>
          </div>
        ) : (
          <div className="brand-project-summary__content">
            <Avatar size={48}>项</Avatar>
            <div className="brand-project-summary__main">
              <Typography.Text strong>暂未关联品牌</Typography.Text>
              <Typography.Text type="secondary">旧项目和无品牌项目不会被自动绑定。</Typography.Text>
              <Button type="link" size="small" onClick={() => setBrandPickerOpen(true)}>关联品牌包</Button>
            </div>
          </div>
        )}
      </Card>

      {brandListError ? (
        <Alert
          type="error"
          showIcon
          title={brandListError}
          action={<Button type="link" href="#/assets">前往企业资产库</Button>}
        />
      ) : null}
      {previewError ? (
        <Alert
          className="brand-project-status-alert"
          type="warning"
          showIcon
          title={previewError}
          description="当前项目仍显示并使用已固定的历史品牌资料；同步已停用。你可以重新关联一个可用品牌包。"
          action={(
            <Space wrap className="brand-project-status-alert__actions">
              <Button size="small" disabled>同步最新品牌资料</Button>
              <Button size="small" type="primary" onClick={() => setBrandPickerOpen(true)}>重新关联品牌</Button>
            </Space>
          )}
        />
      ) : null}
      {error ? <Alert type="error" showIcon title={error} /> : null}
      {open ? (
        <Card
          size="small"
          title="本次项目信息"
          extra={<Button size="small" onClick={onClose}>完成</Button>}
          className="brand-project-editor"
        >
          <Form layout="vertical">
            <div className="brand-project-editor__grid">
              <Form.Item label="推广对象" required>
                <Input aria-label="推广对象" value={offerName} onChange={(event) => setOfferName(event.target.value)} placeholder="本次推广的产品、服务或活动" />
              </Form.Item>
              <Form.Item label="营销目标" required>
                <Input aria-label="营销目标" value={goal} onChange={(event) => setGoal(event.target.value)} placeholder="希望本次营销达成什么" />
              </Form.Item>
              <Form.Item label="目标受众" required>
                <Input aria-label="目标受众" value={audience} onChange={(event) => setAudience(event.target.value)} placeholder="这次主要面向谁" />
              </Form.Item>
              <Form.Item label="核心卖点">
                <Input.TextArea aria-label="核心卖点" value={sellingPoints} onChange={(event) => setSellingPoints(event.target.value)} rows={3} placeholder="每行一项" />
              </Form.Item>
              <Form.Item label="活动信息">
                <Input.TextArea aria-label="活动信息" value={promotion} onChange={(event) => setPromotion(event.target.value)} rows={3} placeholder="优惠、时间、规则等，每行一项" />
              </Form.Item>
              <Form.Item label="本次素材说明">
                <Input.TextArea aria-label="本次素材说明" value={materials} onChange={(event) => setMaterials(event.target.value)} rows={3} placeholder="本次必须使用或体现的素材，每行一项" />
              </Form.Item>
            </div>
            {brand ? (
              <Collapse
                ghost
                items={[{
                  key: "project-brand-settings",
                  label: "本项目品牌设置",
                  children: (
                    <div className="brand-project-overrides">
                      <Alert
                        type="info"
                        showIcon
                        title="这里的修改仅用于当前项目，不会修改企业资产库中的品牌包。"
                      />
                      <div className="brand-project-editor__grid">
                        {overrideFields.map((field) => {
                          const inherited = brand.values[field.key];
                          const overridden = Object.prototype.hasOwnProperty.call(overrides, field.key);
                          return (
                            <Form.Item
                              key={field.key}
                              label={<Space>{field.label}{overridden ? <Tag color="blue">仅本项目使用</Tag> : null}</Space>}
                              extra={overridden ? (
                                <Button
                                  type="link"
                                  size="small"
                                  onClick={() => setOverrides((current) => {
                                    const next = { ...current };
                                    delete next[field.key];
                                    return next;
                                  })}
                                >
                                  恢复品牌默认
                                </Button>
                              ) : null}
                            >
                              {field.kind === "color" ? (
                                <ColorPicker
                                  aria-label={field.label}
                                  value={String(overrides[field.key] ?? inherited)}
                                  showText
                                  onChange={(_, css) => setOverrides((current) => ({ ...current, [field.key]: css }))}
                                />
                              ) : (
                                <Input
                                  aria-label={field.label}
                                  value={String(overrides[field.key] ?? inherited)}
                                  placeholder={field.placeholder}
                                  onChange={(event) => setOverrides((current) => ({ ...current, [field.key]: event.target.value }))}
                                />
                              )}
                            </Form.Item>
                          );
                        })}
                      </div>
                      {Object.keys(overrides).length ? (
                        <Button onClick={() => setOverrides({})}>全部恢复品牌默认</Button>
                      ) : null}
                    </div>
                  ),
                }]}
              />
            ) : null}
            <Button
              type="primary"
              onClick={() => void save()}
              loading={busy}
              disabled={!dirty || !offerName.trim() || !goal.trim() || !audience.trim()}
            >
              保存本次项目信息
            </Button>
          </Form>
        </Card>
      ) : null}

      {brandPicker}

      <Modal
        open={previewOpen}
        title="品牌资料变化"
        okText="同步最新品牌资料"
        cancelText="暂不同步"
        confirmLoading={brandBusy}
        onOk={() => void sync()}
        onCancel={() => !brandBusy && setPreviewOpen(false)}
      >
        <Alert
          type="warning"
          showIcon
          title="确认后，新资料只影响之后的生成；已有结果不会改变。"
        />
        <div className="brand-sync-change-list">
          {(preview?.changes || []).map((change) => (
            <div key={change.field}>
              <Typography.Text>{change.label}</Typography.Text>
              <Tag color={change.status === "preserved_project_override" ? "blue" : "gold"}>
                {change.status === "preserved_project_override" ? "保留本项目设置" : "将同步更新"}
              </Tag>
            </div>
          ))}
        </div>
      </Modal>
    </section>
  );
}
