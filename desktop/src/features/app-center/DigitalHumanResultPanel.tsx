import { Button, Tag, Typography } from "antd";
import { useEffect, useState } from "react";
import { artifactBlobUrl } from "../../api";
import type { IpBroadcastAppRun } from "../../api";

export function DigitalHumanResultPanel({ run, busy, onDownload }: { run: IpBroadcastAppRun; busy: boolean; onDownload: (artifactKey?: string) => void }) {
  const hasFinalVideo = run.artifact_keys?.includes("final_video") || run.artifact_keys?.includes("video");
  const finalVideoKey = run.artifact_keys?.includes("final_video") ? "final_video" : "video";
  const hasCover = run.artifact_keys?.includes("cover");
  const publishCopy = run.artifact_details?.publish_copy?.content || {};
  const spokenScript = run.artifact_details?.spoken_script?.content || {};
  const [previewUrl, setPreviewUrl] = useState("");
  const [previewError, setPreviewError] = useState("");
  const [coverUrl, setCoverUrl] = useState("");
  const [coverError, setCoverError] = useState("");

  useEffect(() => {
    let active = true;
    let resolvedUrl = "";
    setPreviewUrl("");
    setPreviewError("");
    if (!hasFinalVideo || !["needs_review", "completed"].includes(run.state)) return () => undefined;
    void artifactBlobUrl(run.session_id, finalVideoKey)
      .then((url) => {
        if (!active) { URL.revokeObjectURL(url); return; }
        resolvedUrl = url;
        setPreviewUrl(url);
      })
      .catch((error: unknown) => {
        if (active) setPreviewError(error instanceof Error ? error.message : String(error));
      });
    return () => {
      active = false;
      if (resolvedUrl) URL.revokeObjectURL(resolvedUrl);
    };
  }, [finalVideoKey, hasFinalVideo, run.session_id, run.state]);

  useEffect(() => {
    let active = true;
    let resolvedUrl = "";
    setCoverUrl("");
    setCoverError("");
    if (!hasCover || !["needs_review", "completed"].includes(run.state)) return () => undefined;
    void artifactBlobUrl(run.session_id, "cover")
      .then((url) => {
        if (!active) { URL.revokeObjectURL(url); return; }
        resolvedUrl = url;
        setCoverUrl(url);
      })
      .catch((error: unknown) => {
        if (active) setCoverError(error instanceof Error ? error.message : String(error));
      });
    return () => {
      active = false;
      if (resolvedUrl) URL.revokeObjectURL(resolvedUrl);
    };
  }, [hasCover, run.session_id, run.state]);

  async function copyText(value: string) {
    if (!value) return;
    try {
      await navigator.clipboard?.writeText(value);
    } catch {
      // Clipboard permission is optional in a desktop WebView; the artifact
      // remains available through the download action.
    }
  }

  const publishText = [
    typeof publishCopy.title === "string" ? `标题：${publishCopy.title}` : "",
    typeof publishCopy.description === "string" ? `描述：${publishCopy.description}` : "",
    Array.isArray(publishCopy.hashtags) ? `话题：${publishCopy.hashtags.join(" ")}` : "",
  ].filter(Boolean).join("\n");
  const scriptText = typeof spokenScript.spoken_script === "string" ? spokenScript.spoken_script : "";

  return (
    <div className="digital-human-app-result" aria-label="生成结果">
      <div className="digital-human-app-result-heading">
        <div>
          <Typography.Text strong>口播视频</Typography.Text>
          <Typography.Text type="secondary">检查成片，满意后即可下载或交给发布中心。</Typography.Text>
          <div className="digital-human-app-result-meta" aria-label="成片元数据">
            <Tag>{run.presentation?.digital_human_name || "已选择数字人"}</Tag>
            <Tag>{run.presentation?.voice_name || "生成时固定声音"}</Tag>
          </div>
        </div>
        {hasFinalVideo ? <Button size="small" onClick={() => onDownload(finalVideoKey)} disabled={busy}>下载最终视频</Button> : null}
      </div>
      {hasFinalVideo ? (
        <div className="digital-human-app-result-preview" aria-label="最终视频预览">
          {previewUrl ? <video src={previewUrl} controls muted preload="metadata" /> : <Typography.Text type="secondary">{previewError ? "最终视频预览暂不可用，仍可下载最终视频。" : "正在加载最终视频预览…"}</Typography.Text>}
        </div>
      ) : null}
      {(hasCover || publishText || scriptText) ? (
        <details className="digital-human-app-result-extras">
          <summary>封面、发布文案和口播稿</summary>
          <div className="digital-human-app-result-list">
            {[
              ["cover", "封面", run.artifact_keys?.includes("cover")],
              ["publish_copy", "发布文案", run.artifact_keys?.includes("publish_copy")],
              ["spoken_script", "口播稿", run.artifact_keys?.includes("spoken_script")],
            ].map(([key, label, available]) => (
              <div key={String(key)} className="digital-human-app-result-item">
                <span>{label}</span>
                <div className="digital-human-app-result-item-actions">
                  <Tag color={available ? "success" : "default"}>{available ? "已生成" : "待生成"}</Tag>
                  {available ? <Button size="small" onClick={() => onDownload(String(key))} disabled={busy}>下载</Button> : null}
                </div>
              </div>
            ))}
          </div>
          {hasCover ? (
            <div className="digital-human-app-result-content" aria-label="封面预览">
              <div className="digital-human-app-result-content-heading"><Typography.Text strong>封面预览</Typography.Text><Button size="small" onClick={() => onDownload("cover")} disabled={busy}>下载封面</Button></div>
              {coverUrl ? <img src={coverUrl} alt="生成封面" /> : <Typography.Text type="secondary">{coverError ? "封面预览暂不可用，仍可下载封面。" : "正在加载封面预览…"}</Typography.Text>}
            </div>
          ) : null}
          {publishText ? (
            <div className="digital-human-app-result-content" aria-label="发布文案内容">
              <div className="digital-human-app-result-content-heading"><Typography.Text strong>发布文案</Typography.Text><Button size="small" onClick={() => void copyText(publishText)} disabled={busy}>复制文案</Button></div>
              <pre>{publishText}</pre>
            </div>
          ) : null}
          {scriptText ? (
            <div className="digital-human-app-result-content" aria-label="口播稿内容">
              <div className="digital-human-app-result-content-heading"><Typography.Text strong>口播稿</Typography.Text><Button size="small" onClick={() => void copyText(scriptText)} disabled={busy}>复制口播稿</Button></div>
              <pre>{scriptText}</pre>
            </div>
          ) : null}
        </details>
      ) : null}
      {run.artifact_keys?.includes("digital_human_video") ? (
        <details className="digital-human-app-result-diagnostics">
          <summary>查看原始数字人视频（诊断素材）</summary>
          <Typography.Text type="secondary">原始素材仅用于诊断，不作为默认下载或发布对象。</Typography.Text>
        </details>
      ) : null}
    </div>
  );
}
