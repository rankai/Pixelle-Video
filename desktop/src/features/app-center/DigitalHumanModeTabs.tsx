import { Typography } from "antd";

export type DigitalHumanMode = "image_talking" | "video_lipsync";

export function DigitalHumanModeTabs({ mode, onChange }: { mode: DigitalHumanMode; onChange: (mode: DigitalHumanMode) => void }) {
  return (
    <>
      <div className="digital-human-app-source-tabs" role="tablist" aria-label="数字人模式">
        <button type="button" role="tab" aria-selected={mode === "image_talking"} onClick={() => onChange("image_talking")}>图片数字人</button>
        <button type="button" role="tab" aria-selected={mode === "video_lipsync"} onClick={() => onChange("video_lipsync")}>视频数字人</button>
      </div>
      <Typography.Text type="secondary">
        {mode === "image_talking" ? "稳定口播模式：使用图片场景，动作克制、画面稳定。" : "稳定视频模式：保留源视频动作与背景；默认仍使用图片模式。"}
      </Typography.Text>
    </>
  );
}
