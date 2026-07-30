import { Button, Dropdown, Select, Space } from "antd";
import { MoreOutlined } from "@ant-design/icons";

import type { ArtifactVersion } from "../../api";

export type HandoffAction = {
  key: string;
  label: string;
  onClick: () => void;
  disabled?: boolean;
  primary?: boolean;
};

export function VersionSwitcher({
  versions,
  value,
  onChange,
  disabled = false,
  label = "结果版本",
}: {
  versions: ArtifactVersion[];
  value?: string;
  onChange: (versionId: string) => void;
  disabled?: boolean;
  label?: string;
}) {
  if (versions.length < 2) return null;
  return (
    <details className="app-workbench-version-disclosure">
      <summary>版本与记录</summary>
      <label className="app-workbench-version-switcher">
        <span>{label}</span>
        <Select
          aria-label={label}
          size="small"
          value={value || versions[versions.length - 1]?.artifact_version_id}
          disabled={disabled}
          options={versions.map((version) => ({
            value: version.artifact_version_id,
            label: `v${version.version_number} · ${version.source === "edited" ? "编辑" : version.source === "generated" ? "生成" : "导入"}`,
          }))}
          onChange={onChange}
        />
      </label>
    </details>
  );
}

export function HandoffActions({ actions, disabled = false }: { actions: HandoffAction[]; disabled?: boolean }) {
  if (!actions.length) return null;
  const primary = actions.find((action) => action.primary) || actions[0];
  const secondary = actions.filter((action) => action.key !== primary.key);
  return (
    <Space wrap size="small" className="app-workbench-handoff-actions">
      <Button
        key={primary.key}
        size="small"
        type={primary.primary ? "primary" : "default"}
        disabled={disabled || primary.disabled}
        onClick={primary.onClick}
      >
        {primary.label}
      </Button>
      {secondary.length ? (
        <Dropdown
          disabled={disabled}
          trigger={["click"]}
          menu={{
            items: secondary.map((action) => ({
              key: action.key,
              label: action.label,
              disabled: action.disabled,
              onClick: action.onClick,
            })),
          }}
        >
          <Button size="small" icon={<MoreOutlined />} aria-label="更多操作">更多</Button>
        </Dropdown>
      ) : null}
    </Space>
  );
}

export function ArtifactActions({
  versions,
  selectedVersionId,
  onVersionChange,
  actions,
  disabled = false,
}: {
  versions?: ArtifactVersion[];
  selectedVersionId?: string;
  onVersionChange?: (versionId: string) => void;
  actions?: HandoffAction[];
  disabled?: boolean;
}) {
  return (
    <Space wrap size="small" className="app-workbench-artifact-actions">
      {versions && onVersionChange ? <VersionSwitcher versions={versions} value={selectedVersionId} onChange={onVersionChange} disabled={disabled} /> : null}
      <HandoffActions actions={actions || []} disabled={disabled} />
    </Space>
  );
}
