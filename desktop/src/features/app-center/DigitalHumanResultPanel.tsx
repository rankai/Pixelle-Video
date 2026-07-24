import { Button, Tag, Typography } from "antd";
import { useEffect, useState } from "react";
import { artifactBlobUrl } from "../../api";
import type { IpBroadcastAppRun } from "../../api";

export function DigitalHumanResultPanel({ run, busy, onDownload }: { run: IpBroadcastAppRun; busy: boolean; onDownload: () => void }) {
  const hasFinalVideo = run.artifact_keys?.includes("final_video") || run.artifact_keys?.includes("video");
  const [previewUrl, setPreviewUrl] = useState("");
  const [previewError, setPreviewError] = useState("");

  useEffect(() => {
    let active = true;
    let resolvedUrl = "";
    setPreviewUrl("");
    setPreviewError("");
    if (!hasFinalVideo || !["needs_review", "completed"].includes(run.state)) return () => undefined;
    void artifactBlobUrl(run.session_id, "final_video")
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
  }, [hasFinalVideo, run.session_id, run.state]);

  return (
    <div className="digital-human-app-result" aria-label="生成结果">
      <div className="digital-human-app-result-heading">
        <Typography.Text strong>结果交付</Typography.Text>
        <Tag color="processing">默认预览：final_video</Tag>
        {hasFinalVideo ? <Button size="small" onClick={onDownload} disabled={busy}>下载最终视频</Button> : null}
      </div>
      <div className="digital-human-app-result-list">
        {[
          ["final_video", "最终视频", hasFinalVideo],
          ["cover", "封面", run.artifact_keys?.includes("cover")],
          ["publish_copy", "发布文案", run.artifact_keys?.includes("publish_copy")],
        ].map(([key, label, available]) => (
          <div key={String(key)} className="digital-human-app-result-item">
            <span>{label}</span>
            <Tag color={available ? "success" : "default"}>{available ? "已生成" : "待生成"}</Tag>
          </div>
        ))}
      </div>
      {hasFinalVideo ? (
        <div className="digital-human-app-result-preview" aria-label="final_video 预览">
          {previewUrl ? <video src={previewUrl} controls muted preload="metadata" /> : <Typography.Text type="secondary">{previewError ? "final_video 预览暂不可用，仍可下载最终视频。" : "正在加载 final_video 预览…"}</Typography.Text>}
        </div>
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
