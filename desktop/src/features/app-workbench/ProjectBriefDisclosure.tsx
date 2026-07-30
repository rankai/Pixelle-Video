import { useState } from "react";
import type { ReactNode } from "react";
import { Tag, Typography } from "antd";

type Props = {
  ready: boolean;
  children: ReactNode;
};

export function ProjectBriefDisclosure({ ready, children }: Props) {
  const [open, setOpen] = useState(!ready);

  return (
    <details
      className={`project-brief-disclosure${ready ? " project-brief-disclosure--ready" : ""}`}
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary>
        <span>
          <Typography.Text strong>{ready ? "项目信息已带入" : "补充项目信息"}</Typography.Text>
          <Typography.Text type="secondary">
            {ready ? "门店、商品和受众信息会自动使用" : "补充一次，之后不必重复填写"}
          </Typography.Text>
        </span>
        <span className="project-brief-disclosure__action">
          {!ready ? <Tag color="warning">待补充</Tag> : null}
          <Typography.Text type="secondary">编辑</Typography.Text>
        </span>
      </summary>
      <div className="project-brief-disclosure__body">{children}</div>
    </details>
  );
}
