import { Alert, Button, Card, Divider, Space, Tag, Typography } from "antd";
import { useEffect, useMemo, useState, type ReactNode } from "react";

import {
  artifactBlobUrl,
  createPublishPackageFromSessionV2,
  downloadArtifact,
  type IpBroadcastState,
  type PublishPlatform,
  type PublishResult,
} from "../../api";

const SUPPORTED_PLATFORMS: PublishPlatform[] = ["douyin", "xiaohongshu", "shipinhao", "kuaishou"];

export function PublishWorkspace({
  session,
  downloadFinalVideo,
  onOpenPublishCenter,
}: {
  session: IpBroadcastState;
  downloadFinalVideo: () => Promise<void>;
  onOpenPublishCenter: (packageId?: string) => void;
}) {
  const [loadingPlatform, setLoadingPlatform] = useState<PublishPlatform | null>(null);
  const [result, setResult] = useState<PublishResult | null>(null);
  const publishPackage = readRecord(session.state.publish_package);
  const platformSuggestions = readPlatformSuggestions(
    publishPackage.platform_suggestions || session.state.platform_suggestions,
  );
  const title = String(publishPackage.title || session.state.title || "");
  const coverTitle = String(publishPackage.cover_title || title);
  const description = String(publishPackage.description || session.state.description || "");
  const commentCta = String(publishPackage.comment_cta || "");
  const hashtagList = readStringArray(publishPackage.hashtags || session.state.hashtags);
  const hashtags = hashtagList.join(" ");
  const script = String(publishPackage.script || session.state.final_script || "");
  const finalVideoPath = String(session.state.final_video_path || "");
  const coverPath = String(session.state.cover_path || "");
  const publishReady = Boolean(session.artifacts.final_video || finalVideoPath);
  const coverReady = Boolean(session.artifacts.cover || coverPath);
  const preferredPlatforms = readStringArray(
    publishPackage.preferred_platforms || session.state.business_publish_platforms,
  ).filter(isPublishPlatform);
  const orderedPlatforms = useMemo(() => {
    const requested = preferredPlatforms.length ? preferredPlatforms : SUPPORTED_PLATFORMS;
    return [...new Set([...requested, ...SUPPORTED_PLATFORMS])];
  }, [preferredPlatforms.join("|")]);
  const primaryPlatform = orderedPlatforms[0] || "douyin";
  const deliveryItems = [
    { label: "视频", ready: publishReady },
    { label: "封面", ready: coverReady },
    { label: "标题", ready: Boolean(title) },
    { label: "描述", ready: Boolean(description) },
    { label: "话题", ready: Boolean(hashtags) },
  ];

  async function prepareDraft(platform: PublishPlatform) {
    if (!finalVideoPath) return;
    setLoadingPlatform(platform);
    setResult(null);
    try {
      // PUB-4 batch 3: the legacy step only hands off to the canonical publish
      // center; it never owns a second platform/package/run orchestration path.
      const packageData = await createPublishPackageFromSessionV2({
        project_id: `legacy_${session.session_id}`,
        session_id: session.session_id,
        platform_copy: { title, description, hashtags: hashtagList },
      });
      onOpenPublishCenter(packageData.package_id);
      setResult({
        status: "draft_ready",
        platform,
        message: "已切换到统一发布中心；请在那里选择账号并人工确认。",
        requires_human_confirmation: true,
      });
    } catch (error) {
      setResult({
        status: "failed",
        platform,
        message: error instanceof Error ? error.message : String(error),
        requires_human_confirmation: true,
      });
    } finally {
      setLoadingPlatform(null);
    }
  }

  return (
    <div className="publish-workbench publish-workspace-v2">
      <Alert
        className="human-confirmation-guard"
        type="warning"
        showIcon
        title="发布前安全停手"
        description="发布助手只负责打开目标平台并填充视频、封面、标题、描述和话题。请你检查平台预览后亲自点击最终发布，系统不会执行这一步。"
      />
      {result ? (
        <Alert
          className="step-notice"
          type={result.status === "failed" ? "error" : result.status === "draft_ready" ? "success" : "info"}
          showIcon
          title={result.message || publishStatusLabel(result.status)}
          description={
            result.filled_fields?.length
              ? `已处理：${result.filled_fields.map(fieldLabel).join("、")}。最终发布仍需人工确认。`
              : undefined
          }
        />
      ) : null}

      <div className="publish-layout">
        <div className="publish-main">
          <Card className={`publish-hero ${publishReady ? "" : "pending"}`} variant="borderless">
            <div className="publish-ready-head">
              <div>
                <Typography.Title level={4}>{publishReady ? "发布包已就绪" : "等待最终成片"}</Typography.Title>
                <Typography.Text type="secondary">
                  {publishReady
                    ? "系统已按平台整理发布信息，可以选择目标平台开始填充。"
                    : "先完成一键成片，系统将生成视频、封面和各平台文案。"}
                </Typography.Text>
              </div>
              <Tag color={publishReady ? "success" : "default"}>{publishReady ? "可开始" : "未就绪"}</Tag>
            </div>
            <DeliveryChecklist items={deliveryItems} />
          </Card>

          <Card title="选择发布平台" variant="borderless">
            <div className="platform-grid platform-assistant-grid">
              {orderedPlatforms.map((platform) => {
                const suggestion = platformSuggestions[platform] || {};
                const platformTitle = String(suggestion.title || title || "暂无标题建议");
                const platformDescription = String(suggestion.description || description || "暂无描述建议");
                return (
                  <section key={platform} className="platform-card">
                    <div className="platform-capability-head">
                      <strong>{platformLabel(platform)}</strong>
                      <Tag color="processing">自动填充 · 人工发布</Tag>
                    </div>
                    <p className="platform-draft-title">{platformTitle}</p>
                    <small>{platformDescription}</small>
                    <Space wrap>
                      <Button
                        type="primary"
                        disabled={!publishReady || !finalVideoPath}
                        loading={loadingPlatform === platform}
                        onClick={() => prepareDraft(platform)}
                      >
                        打开{platformLabel(platform)}
                      </Button>
                      <CopyButton
                        label="复制该平台素材"
                        disabled={!publishReady}
                        text={buildPlatformText({
                          platform,
                          title: platformTitle,
                          description: platformDescription,
                          hashtags,
                          commentCta,
                        })}
                      />
                    </Space>
                  </section>
                );
              })}
            </div>
          </Card>

          <Card title="发布文案与素材" variant="borderless">
            <PublishField label="封面大字" value={coverTitle} singleLine copyLabel="复制封面大字" />
            <PublishField label="标题" value={title} singleLine copyLabel="复制标题" />
            <PublishField label="描述" value={description} rows={4} copyLabel="复制描述" />
            <PublishField label="评论区引导" value={commentCta} singleLine copyLabel="复制引导语" />
            <PublishField label="话题标签" value={hashtags} singleLine copyLabel="复制话题" />
            <PublishField
              label="口播文案"
              value={script}
              rows={6}
              copyLabel="复制口播文案"
              extra={
                session.artifacts.script ? (
                  <Button onClick={() => downloadArtifact(session.session_id, "script")}>下载文案</Button>
                ) : null
              }
            />
          </Card>
        </div>

        <aside className="publish-aside">
          <Card className="publish-preview-card" title="发布检查" variant="borderless">
            <ArtifactPreview sessionId={session.session_id} artifactKey="final_video" kind="video" enabled={publishReady} />
            {coverReady ? (
              <>
                <Divider />
                <Typography.Text type="secondary">封面预览</Typography.Text>
                <ArtifactPreview sessionId={session.session_id} artifactKey="cover" kind="image" enabled />
              </>
            ) : null}
            <Divider />
            <Button
              type="primary"
              block
              disabled={!publishReady || !finalVideoPath}
              loading={loadingPlatform === primaryPlatform}
              onClick={() => prepareDraft(primaryPlatform)}
            >
              打开首选平台：{platformLabel(primaryPlatform)}
            </Button>
            <Space orientation="vertical" className="publish-file-actions">
              <Button block disabled={!publishReady} onClick={downloadFinalVideo}>下载最终视频</Button>
              {session.artifacts.publish_package_json ? (
                <Button block onClick={() => downloadArtifact(session.session_id, "publish_package_json")}>
                  下载发布包 JSON
                </Button>
              ) : null}
            </Space>
            <Divider />
            <Typography.Text type="secondary">安全边界</Typography.Text>
            <p className="publish-safety-copy">自动填充到此为止。浏览器中的最终发布按钮必须由你本人点击。</p>
          </Card>
        </aside>
      </div>
    </div>
  );
}

function DeliveryChecklist({ items }: { items: Array<{ label: string; ready: boolean }> }) {
  return (
    <section className="publish-delivery-checklist" aria-label="发布素材交付清单">
      {items.map((item) => (
        <div key={item.label} className={item.ready ? "ready" : "missing"}>
          <span>{item.label}</span>
          <Tag color={item.ready ? "success" : "default"}>{item.ready ? "已准备" : "缺失"}</Tag>
        </div>
      ))}
    </section>
  );
}

function PublishField({
  label,
  value,
  rows = 2,
  singleLine = false,
  copyLabel,
  extra,
}: {
  label: string;
  value: string;
  rows?: number;
  singleLine?: boolean;
  copyLabel: string;
  extra?: ReactNode;
}) {
  return (
    <section className="publish-field">
      <div className="publish-field-title">
        <strong>{label}</strong>
        <Space>{extra}<CopyButton text={value} label={copyLabel} /></Space>
      </div>
      {singleLine ? <input readOnly value={value} /> : <textarea readOnly value={value} rows={rows} />}
    </section>
  );
}

function CopyButton({ text, label, disabled = false }: { text: string; label: string; disabled?: boolean }) {
  const [status, setStatus] = useState<"idle" | "success" | "error">("idle");
  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setStatus("success");
    } catch {
      setStatus("error");
    }
    window.setTimeout(() => setStatus("idle"), 1600);
  }
  return <Button danger={status === "error"} disabled={disabled || !text} onClick={copy}>{status === "success" ? "已复制" : status === "error" ? "复制失败" : label}</Button>;
}

function ArtifactPreview({
  sessionId,
  artifactKey,
  kind,
  enabled,
}: {
  sessionId: string;
  artifactKey: string;
  kind: "video" | "image";
  enabled: boolean;
}) {
  const [url, setUrl] = useState("");
  useEffect(() => {
    if (!enabled) return;
    let disposed = false;
    let current = "";
    artifactBlobUrl(sessionId, artifactKey).then((next) => {
      if (disposed) { URL.revokeObjectURL(next); return; }
      current = next;
      setUrl(next);
    }).catch(() => { if (!disposed) setUrl(""); });
    return () => {
      disposed = true;
      if (current) URL.revokeObjectURL(current);
    };
  }, [artifactKey, enabled, sessionId]);
  if (!enabled) return <div className="video-preview-shell placeholder">等待成片</div>;
  if (!url) return <div className="video-preview-shell placeholder">正在加载预览…</div>;
  return kind === "video" ? <video className="publish-native-preview" controls src={url} /> : <img className="artifact-image-preview" src={url} alt="发布封面预览" />;
}

function platformLabel(platform: string) {
  return { douyin: "抖音", xiaohongshu: "小红书", shipinhao: "视频号", kuaishou: "快手" }[platform] || platform;
}

function fieldLabel(field: string) {
  return { video: "视频", cover: "封面", title: "标题", description: "描述", hashtags: "话题" }[field] || field;
}

function publishStatusLabel(status: PublishResult["status"]) {
  return { login_required: "请先登录平台账号", uploading: "正在上传", draft_ready: "已填充，等待人工发布", failed: "发布助手执行失败", cancelled: "发布助手已停止" }[status] || status;
}

function isPublishPlatform(platform: string): platform is PublishPlatform {
  return SUPPORTED_PLATFORMS.includes(platform as PublishPlatform);
}

function readRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function readPlatformSuggestions(value: unknown): Record<string, Record<string, unknown>> {
  const record = readRecord(value);
  return Object.fromEntries(Object.entries(record).map(([key, item]) => [key, readRecord(item)]));
}

function readStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String).filter(Boolean) : [];
}

function buildPlatformText({
  platform,
  title,
  description,
  hashtags,
  commentCta,
}: {
  platform: PublishPlatform;
  title: string;
  description: string;
  hashtags: string;
  commentCta: string;
}) {
  return [
    `平台：${platformLabel(platform)}`,
    `标题：${title}`,
    `描述：${description}`,
    hashtags ? `话题：${hashtags}` : "",
    commentCta ? `评论区引导：${commentCta}` : "",
    "视频：已准备（请从发布检查下载或预览）",
    "封面：按发布检查中的预览与下载状态确认",
    "发布方式：自动填充后人工确认",
  ].filter(Boolean).join("\n");
}

export default PublishWorkspace;
