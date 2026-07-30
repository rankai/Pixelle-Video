import { useEffect, useMemo, useState } from "react";
import { Alert, Button, Collapse, Input, Select, Space, Tag, Typography } from "antd";

import { saveContextSnapshot, type ContextSnapshot } from "../../api";

export type ContextFactV2 = {
  fact_id: string;
  text: string;
  source: "user" | "brand_revision" | "asset_metadata" | "artifact_version";
  source_ref?: string | null;
};

export type ProjectContextV2 = {
  schema_version: 2;
  subject_type: "store" | "brand" | "product" | "service" | "campaign";
  store_or_brand: {
    name: string;
    industry: string;
    address: string | null;
    contact: string | null;
  };
  offer: {
    name: string;
    category: string;
    price_facts: ContextFactV2[];
    promotion_facts: ContextFactV2[];
  };
  audience: {
    primary: string;
    scenes: string[];
  };
  selling_points: ContextFactV2[];
  proof_points: ContextFactV2[];
  required_facts: ContextFactV2[];
  forbidden_claims: string[];
  asset_refs: Array<{ asset_id: string; asset_revision: string }>;
  brand_revision_ref: string | null;
};

type ContextForm = {
  subjectType: ProjectContextV2["subject_type"];
  storeName: string;
  industry: string;
  address: string;
  contact: string;
  offerName: string;
  offerCategory: string;
  audience: string;
  scenes: string;
  priceFacts: string;
  promotionFacts: string;
  sellingPoints: string;
  proofPoints: string;
  requiredFacts: string;
  forbiddenClaims: string;
  assetRefs: string;
  brandRevisionRef: string;
};

type StoredDraft = {
  projectId: string;
  baseSnapshotId: string | null;
  form: ContextForm;
  savedAt: string;
};

type Props = {
  projectId: string;
  projectName: string;
  snapshot: ContextSnapshot | null;
  onSaved: (snapshot: ContextSnapshot) => void;
  onDirtyChange?: (dirty: boolean) => void;
};

const SUBJECT_OPTIONS = [
  { value: "store", label: "门店" },
  { value: "brand", label: "品牌" },
  { value: "product", label: "商品" },
  { value: "service", label: "服务" },
  { value: "campaign", label: "营销活动" },
];

function stringValue(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function lines(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value
      .map((item) => (typeof item === "string" ? item : typeof item === "object" && item ? stringValue((item as Record<string, unknown>).text) : ""))
      .filter(Boolean);
  }
  return typeof value === "string" ? value.split(/\r?\n|[,，]/).map((item) => item.trim()).filter(Boolean) : [];
}

function factLines(value: unknown): string {
  return lines(value).join("\n");
}

function parseLines(value: string): string[] {
  return value
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function facts(value: string, prefix: string): ContextFactV2[] {
  return parseLines(value).map((text, index) => ({
    fact_id: `${prefix}-${index + 1}`,
    text,
    source: "user",
  }));
}

function formFromV2(payload: Record<string, unknown>): ContextForm {
  const store = payload.store_or_brand && typeof payload.store_or_brand === "object"
    ? payload.store_or_brand as Record<string, unknown>
    : {};
  const offer = payload.offer && typeof payload.offer === "object"
    ? payload.offer as Record<string, unknown>
    : {};
  const audience = payload.audience && typeof payload.audience === "object"
    ? payload.audience as Record<string, unknown>
    : {};
  const assetRefs = Array.isArray(payload.asset_refs) ? payload.asset_refs : [];
  return {
    subjectType: ["store", "brand", "product", "service", "campaign"].includes(String(payload.subject_type))
      ? payload.subject_type as ContextForm["subjectType"]
      : "store",
    storeName: stringValue(store.name),
    industry: stringValue(store.industry),
    address: stringValue(store.address),
    contact: stringValue(store.contact),
    offerName: stringValue(offer.name),
    offerCategory: stringValue(offer.category),
    audience: stringValue(audience.primary),
    scenes: lines(audience.scenes).join("\n"),
    priceFacts: factLines(offer.price_facts),
    promotionFacts: factLines(offer.promotion_facts),
    sellingPoints: factLines(payload.selling_points),
    proofPoints: factLines(payload.proof_points),
    requiredFacts: factLines(payload.required_facts),
    forbiddenClaims: lines(payload.forbidden_claims).join("\n"),
    assetRefs: assetRefs.map((item) => {
      if (!item || typeof item !== "object") return "";
      const ref = item as Record<string, unknown>;
      return ref.asset_id && ref.asset_revision ? `${String(ref.asset_id)}@${String(ref.asset_revision)}` : "";
    }).filter(Boolean).join("\n"),
    brandRevisionRef: stringValue(payload.brand_revision_ref),
  };
}

export function mapLegacyContextToV2(
  payload: Record<string, unknown>,
  projectName = "",
): ProjectContextV2 {
  const storeName = stringValue(payload.store_name)
    || stringValue(payload.brand_name)
    || stringValue(payload.name)
    || projectName;
  const productOrService = stringValue(payload.product_or_service)
    || stringValue(payload.product)
    || stringValue(payload.service)
    || stringValue(payload.offer_name);
  return {
    schema_version: 2,
    subject_type: "store",
    store_or_brand: {
      name: storeName,
      industry: stringValue(payload.industry) || stringValue(payload.category),
      address: stringValue(payload.address) || null,
      contact: stringValue(payload.contact) || null,
    },
    offer: {
      name: productOrService,
      category: stringValue(payload.offer_category) || stringValue(payload.category),
      price_facts: facts(factLines(payload.price_facts), "price"),
      promotion_facts: facts(factLines(payload.promotion_facts), "promotion"),
    },
    audience: {
      primary: stringValue(payload.target_audience) || stringValue(payload.audience),
      scenes: lines(payload.scenes),
    },
    selling_points: facts(factLines(payload.selling_points), "selling"),
    proof_points: facts(factLines(payload.proof_points), "proof"),
    required_facts: facts(factLines(payload.required_facts), "required"),
    forbidden_claims: lines(payload.forbidden_claims),
    asset_refs: [],
    brand_revision_ref: null,
  };
}

function formFromSnapshot(snapshot: ContextSnapshot | null, projectName: string): ContextForm {
  const payload = snapshot?.schema_version === 2
    ? snapshot.payload
    : mapLegacyContextToV2(snapshot?.payload || {}, projectName) as unknown as Record<string, unknown>;
  return formFromV2(payload);
}

function payloadFromForm(form: ContextForm): ProjectContextV2 {
  return {
    schema_version: 2,
    subject_type: form.subjectType,
    store_or_brand: {
      name: form.storeName.trim(),
      industry: form.industry.trim(),
      address: form.address.trim() || null,
      contact: form.contact.trim() || null,
    },
    offer: {
      name: form.offerName.trim(),
      category: form.offerCategory.trim(),
      price_facts: facts(form.priceFacts, "price"),
      promotion_facts: facts(form.promotionFacts, "promotion"),
    },
    audience: {
      primary: form.audience.trim(),
      scenes: parseLines(form.scenes),
    },
    selling_points: facts(form.sellingPoints, "selling"),
    proof_points: facts(form.proofPoints, "proof"),
    required_facts: facts(form.requiredFacts, "required"),
    forbidden_claims: parseLines(form.forbiddenClaims),
    asset_refs: parseLines(form.assetRefs).map((value) => {
      const separator = value.lastIndexOf("@");
      return {
        asset_id: separator > 0 ? value.slice(0, separator).trim() : value.trim(),
        asset_revision: separator > 0 ? value.slice(separator + 1).trim() : "",
      };
    }),
    brand_revision_ref: form.brandRevisionRef.trim() || null,
  };
}

function storageKey(projectId: string) {
  return `pixelle.app-workbench.context-draft.v2:${projectId}`;
}

function readStoredDraft(projectId: string): StoredDraft | null {
  try {
    const value = JSON.parse(window.localStorage.getItem(storageKey(projectId)) || "null") as StoredDraft | null;
    return value?.projectId === projectId && value.form ? value : null;
  } catch {
    return null;
  }
}

function isComplete(form: ContextForm) {
  return Boolean(
    form.storeName.trim()
      && form.industry.trim()
      && form.offerName.trim()
      && form.offerCategory.trim()
      && form.audience.trim(),
  );
}

export function ProjectBriefEditor({
  projectId,
  projectName,
  snapshot,
  onSaved,
  onDirtyChange,
}: Props) {
  const [form, setForm] = useState<ContextForm>(() => formFromSnapshot(snapshot, projectName));
  const [dirty, setDirty] = useState(false);
  const [restored, setRestored] = useState(false);
  const [staleDraft, setStaleDraft] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const legacyPreview = Boolean(snapshot && snapshot.schema_version === 1);
  const snapshotId = snapshot?.context_snapshot_id || null;

  useEffect(() => {
    const stored = readStoredDraft(projectId);
    setForm(stored?.form || formFromSnapshot(snapshot, projectName));
    setDirty(Boolean(stored));
    setRestored(Boolean(stored));
    setStaleDraft(Boolean(stored && stored.baseSnapshotId !== snapshotId));
    setError("");
    onDirtyChange?.(Boolean(stored));
  }, [projectId, projectName, snapshotId]);

  const completion = useMemo(() => {
    const required = [form.storeName, form.industry, form.offerName, form.offerCategory, form.audience];
    return `${required.filter((value) => value.trim()).length}/${required.length}`;
  }, [form]);

  function update<Key extends keyof ContextForm>(key: Key, value: ContextForm[Key]) {
    const next = { ...form, [key]: value };
    setForm(next);
    setDirty(true);
    setRestored(false);
    setStaleDraft(false);
    onDirtyChange?.(true);
    window.localStorage.setItem(
      storageKey(projectId),
      JSON.stringify({
        projectId,
        baseSnapshotId: snapshotId,
        form: next,
        savedAt: new Date().toISOString(),
      } satisfies StoredDraft),
    );
  }

  function discardDraft() {
    window.localStorage.removeItem(storageKey(projectId));
    setForm(formFromSnapshot(snapshot, projectName));
    setDirty(false);
    setRestored(false);
    setStaleDraft(false);
    setError("");
    onDirtyChange?.(false);
  }

  async function save() {
    setBusy(true);
    setError("");
    try {
      const saved = await saveContextSnapshot(projectId, {
        schema_version: 2,
        payload: payloadFromForm(form) as unknown as Record<string, unknown>,
        source_brand_id: snapshot?.source_brand_id || null,
        source_brand_revision_id: snapshot?.source_brand_revision_id || null,
      });
      window.localStorage.removeItem(storageKey(projectId));
      setDirty(false);
      setRestored(false);
      setStaleDraft(false);
      onDirtyChange?.(false);
      onSaved(saved);
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "项目上下文保存失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="project-brief-editor" aria-label="项目上下文">
      <div className="project-brief-editor__heading">
        <div>
          <Typography.Text strong>项目信息</Typography.Text>
          <Typography.Text type="secondary">补充一次，之后做文案、标题、图文和口播都能直接使用。</Typography.Text>
        </div>
        <Space size="small">
          <Tag color={isComplete(form) ? "success" : "default"}>已填 {completion}</Tag>
        </Space>
      </div>

      {legacyPreview ? (
        <Alert
          type="info"
          showIcon
          message="请确认已带入的项目信息"
          description="我们已经尽量带入原有资料。确认并保存前，不会影响以前生成的内容。"
        />
      ) : null}
      {restored ? (
        <Alert
          type="warning"
          showIcon
          message={staleDraft ? "项目信息后来有过更新" : "已恢复上次未保存的修改"}
          description={staleDraft ? "请核对当前内容后保存，或放弃修改以恢复最新信息。" : undefined}
        />
      ) : null}
      {error ? <Alert type="error" showIcon message={error} /> : null}

      <div className="project-brief-editor__grid">
        <label className="creation-select-field">
          <span>经营主体</span>
          <Select
            aria-label="经营主体"
            value={form.subjectType}
            options={SUBJECT_OPTIONS}
            onChange={(value) => update("subjectType", value)}
          />
        </label>
        <label className="creation-select-field">
          <span>门店 / 品牌名称 *</span>
          <Input aria-label="门店或品牌名称" value={form.storeName} onChange={(event) => update("storeName", event.target.value)} />
        </label>
        <label className="creation-select-field">
          <span>行业 *</span>
          <Input aria-label="行业" value={form.industry} placeholder="如：咖啡餐饮" onChange={(event) => update("industry", event.target.value)} />
        </label>
        <label className="creation-select-field">
          <span>商品 / 服务 *</span>
          <Input aria-label="商品或服务" value={form.offerName} onChange={(event) => update("offerName", event.target.value)} />
        </label>
        <label className="creation-select-field">
          <span>品类 *</span>
          <Input aria-label="商品品类" value={form.offerCategory} onChange={(event) => update("offerCategory", event.target.value)} />
        </label>
        <label className="creation-select-field project-brief-editor__wide">
          <span>目标人群 *</span>
          <Input aria-label="目标人群" value={form.audience} placeholder="如：门店周边 3 公里的上班族" onChange={(event) => update("audience", event.target.value)} />
        </label>
        <label className="creation-select-field project-brief-editor__wide">
          <span>商品卖点</span>
          <Input.TextArea aria-label="商品卖点" value={form.sellingPoints} rows={3} placeholder="每行一个卖点" onChange={(event) => update("sellingPoints", event.target.value)} />
        </label>
        <label className="creation-select-field project-brief-editor__wide">
          <span>证明与必带事实</span>
          <Input.TextArea aria-label="证明与必带事实" value={form.proofPoints} rows={2} placeholder="每行一个可核实事实" onChange={(event) => update("proofPoints", event.target.value)} />
        </label>
      </div>

      <Collapse
        ghost
        items={[{
          key: "more",
          label: "更多项目资料",
          children: (
            <div className="project-brief-editor__grid">
              <label className="creation-select-field project-brief-editor__wide">
                <span>使用场景</span>
                <Input.TextArea aria-label="使用场景" value={form.scenes} rows={2} placeholder="每行一个场景" onChange={(event) => update("scenes", event.target.value)} />
              </label>
              <label className="creation-select-field">
                <span>价格事实</span>
                <Input.TextArea aria-label="价格事实" value={form.priceFacts} rows={2} onChange={(event) => update("priceFacts", event.target.value)} />
              </label>
              <label className="creation-select-field">
                <span>促销事实</span>
                <Input.TextArea aria-label="促销事实" value={form.promotionFacts} rows={2} onChange={(event) => update("promotionFacts", event.target.value)} />
              </label>
              <label className="creation-select-field project-brief-editor__wide">
                <span>必须出现的事实</span>
                <Input.TextArea aria-label="必须出现的事实" value={form.requiredFacts} rows={2} onChange={(event) => update("requiredFacts", event.target.value)} />
              </label>
              <label className="creation-select-field project-brief-editor__wide">
                <span>禁用表达</span>
                <Input.TextArea aria-label="禁用表达" value={form.forbiddenClaims} rows={2} placeholder="每行一个不可使用的说法" onChange={(event) => update("forbiddenClaims", event.target.value)} />
              </label>
              <label className="creation-select-field project-brief-editor__wide">
                <span>地址</span>
                <Input aria-label="门店地址" value={form.address} onChange={(event) => update("address", event.target.value)} />
              </label>
              <label className="creation-select-field">
                <span>联系方式</span>
                <Input aria-label="联系方式" value={form.contact} onChange={(event) => update("contact", event.target.value)} />
              </label>
            </div>
          ),
        }]}
      />

      <Space wrap className="project-brief-editor__actions">
        <Button type="primary" loading={busy} disabled={(!dirty && !legacyPreview) || !isComplete(form)} onClick={() => void save()}>
          保存项目信息
        </Button>
        <Button disabled={!dirty || busy} onClick={discardDraft}>放弃修改</Button>
        {snapshot ? <Typography.Text type="secondary">保存后，其他应用也会自动使用这组信息。</Typography.Text> : null}
      </Space>
    </section>
  );
}
