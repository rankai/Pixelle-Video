import { useState } from "react";
import { Button, Select, Typography } from "antd";

import type { ContentProject } from "../../api";

export function projectDisplayName(project: ContentProject) {
  const name = project.name?.trim();
  const looksLikeInternalId = !name
    || name === project.project_id
    || /^project_[a-z0-9_-]+$/i.test(name);
  if (!looksLikeInternalId) return name;

  const date = new Date(project.updated_at || project.created_at);
  if (Number.isNaN(date.getTime())) return "未命名项目";
  return `未命名项目 · ${date.getMonth() + 1}/${date.getDate()}`;
}

type Props = {
  projects: ContentProject[];
  value?: string;
  disabled?: boolean;
  onChange: (projectId: string) => void;
  onCreate: () => void;
  onEdit?: () => void;
};

export function ProjectContextSelector({
  projects,
  value,
  disabled = false,
  onChange,
  onCreate,
  onEdit,
}: Props) {
  const [libraryOpen, setLibraryOpen] = useState(false);
  const createValue = "__create_project__";
  const editValue = "__edit_project__";

  return (
    <div className="project-context-selector" aria-label="应用中心全局项目">
      <label className="project-context-selector__field">
        <Typography.Text strong>选择项目 <span aria-hidden="true">*</span></Typography.Text>
        <Select
          aria-label="当前创作项目"
          placeholder={projects.length ? "选择已有项目" : "从这里创建第一个项目"}
          value={value || undefined}
          open={libraryOpen}
          onOpenChange={setLibraryOpen}
          options={[
            ...projects.map((project) => ({
              value: project.project_id,
              label: projectDisplayName(project),
            })),
            ...(value && onEdit ? [{
              value: editValue,
              label: "编辑当前项目信息",
            }] : []),
            {
              value: createValue,
              label: "＋ 新建项目",
            },
          ]}
          disabled={disabled}
          onChange={(projectId) => {
            setLibraryOpen(false);
            if (projectId === createValue) onCreate();
            else if (projectId === editValue) onEdit?.();
            else onChange(projectId);
          }}
        />
      </label>
      <Button className="project-context-selector__library" aria-label="我的项目" disabled={disabled} onClick={() => setLibraryOpen(true)}>
        我的项目
      </Button>
    </div>
  );
}
