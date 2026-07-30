import { useState } from "react";
import { Alert, Button, Input, Space, Typography } from "antd";

import type { StylePreset } from "../../api";

export type StyleSource = "preset" | "custom";

type Props = {
  presets: StylePreset[];
  source: StyleSource;
  selectedStyleId: string;
  customText: string;
  disabled?: boolean;
  onSourceChange: (source: StyleSource) => void;
  onStyleChange: (styleId: string) => void;
  onCustomTextChange: (value: string) => void;
};

export function StylePresetPicker({
  presets,
  source,
  selectedStyleId,
  customText,
  disabled = false,
  onSourceChange,
  onStyleChange,
  onCustomTextChange,
}: Props) {
  const [showAllPresets, setShowAllPresets] = useState(false);
  const compactPresets = presets.slice(0, 4);
  const selectedPreset = presets.find((preset) => preset.style_id === selectedStyleId);
  const visiblePresets = showAllPresets
    ? presets
    : selectedPreset && !compactPresets.some((preset) => preset.style_id === selectedPreset.style_id)
      ? [...compactPresets.slice(0, 3), selectedPreset]
      : compactPresets;

  return (
    <section className="style-preset-picker" aria-label="创作风格">
      <div className="style-preset-picker__heading">
        <Typography.Text strong>想用哪种表达风格？</Typography.Text>
        <Space.Compact>
          <Button
            type={source === "preset" ? "primary" : "default"}
            disabled={disabled}
            onClick={() => onSourceChange("preset")}
          >
            风格样例库
          </Button>
          <Button
            type={source === "custom" ? "primary" : "default"}
            disabled={disabled}
            onClick={() => onSourceChange("custom")}
          >
            自定义参考
          </Button>
        </Space.Compact>
      </div>

      {source === "preset" ? (
        <>
          <div className="style-preset-picker__grid">
            {visiblePresets.map((preset) => {
              const selected = preset.style_id === selectedStyleId;
              return (
                <button
                  key={`${preset.style_id}@${preset.version}`}
                  type="button"
                  className={`style-preset-card${selected ? " is-selected" : ""}`}
                  aria-pressed={selected}
                  disabled={disabled}
                  onClick={() => onStyleChange(preset.style_id)}
                >
                  <strong>{preset.name}</strong>
                  {selected ? <small>{preset.example}</small> : null}
                </button>
              );
            })}
          </div>
          {presets.length > 4 ? (
            <Button
              type="text"
              size="small"
              className="style-preset-picker__more"
              onClick={() => setShowAllPresets((current) => !current)}
            >
              {showAllPresets ? "收起风格" : `更多风格（${presets.length - 4}）`}
            </Button>
          ) : null}
        </>
      ) : (
        <Space orientation="vertical" size="small" style={{ width: "100%" }}>
          <Alert
            type="info"
            showIcon
            message="只模仿写法，不复制事实"
            description="示例中的品牌、价格、身份、效果和活动不会写入项目资料，也不会自动成为生成事实。"
          />
          <Input.TextArea
            aria-label="自定义风格参考"
            value={customText}
            rows={4}
            maxLength={2000}
            showCount
            disabled={disabled}
            placeholder="粘贴一段希望参考的表达方式"
            onChange={(event) => onCustomTextChange(event.target.value)}
          />
        </Space>
      )}
    </section>
  );
}
