import type { KeyboardEvent, ReactNode } from "react";
import { useId, useState } from "react";
import { Button, Tag, Typography } from "antd";

export type WorkbenchViewState = "empty" | "running" | "failed" | "needs_review" | "saved";

const stateCopy: Record<WorkbenchViewState, { label: string; description: string; color: "default" | "processing" | "error" | "warning" | "success" }> = {
  empty: { label: "还未生成", description: "完成左侧选择后，结果会显示在这里。", color: "default" },
  running: { label: "生成中", description: "正在为你生成内容，可以先做别的事情。", color: "processing" },
  failed: { label: "需要处理", description: "本次内容没有生成成功，输入已为你保留。", color: "error" },
  needs_review: { label: "请确认", description: "内容已经生成，确认满意后即可下载或继续制作。", color: "warning" },
  saved: { label: "已完成", description: "内容已保存，可以下载、复制或继续制作。", color: "success" },
};

type Props = {
  eyebrow: string;
  title: string;
  description: string;
  onBack?: () => void;
  banner?: ReactNode;
  input?: ReactNode;
  inputFooter?: ReactNode;
  result?: ReactNode;
  adoptedContent?: ReactNode;
  adoptedInputFooter?: ReactNode;
  adoptedInputId?: string;
  adoptedResultId?: string;
  showAdoptedState?: boolean;
  resultState?: WorkbenchViewState;
  inputLabel?: string;
  resultLabel?: string;
};

export function AppWorkbenchShell({
  eyebrow,
  title,
  description,
  onBack,
  banner,
  input,
  inputFooter,
  result,
  adoptedContent,
  adoptedInputFooter,
  adoptedInputId,
  adoptedResultId,
  showAdoptedState = true,
  resultState = "empty",
  inputLabel = "创作配置",
  resultLabel = "生成结果",
}: Props) {
  const [mobilePane, setMobilePane] = useState<"input" | "result">("input");
  const inputId = useId();
  const resultId = useId();
  const state = stateCopy[resultState];
  const resolvedInputId = adoptedInputId || inputId;
  const resolvedResultId = adoptedResultId || resultId;
  function moveMobileTab(event: KeyboardEvent<HTMLButtonElement>, nextPane: "input" | "result") {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const pane = event.key === "Home" || event.key === "ArrowLeft" ? "input" : event.key === "End" || event.key === "ArrowRight" ? "result" : nextPane;
    setMobilePane(pane);
    const targetIndex = pane === "input" ? 0 : 1;
    const tabs = event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>('[role="tab"]');
    tabs?.[targetIndex]?.focus();
  }

  return (
    <section className="app-workbench-shell" aria-label={`${title}应用工作台`}>
      <header className="app-workbench-header">
        <div>
          <Typography.Text className="app-workbench-context">{eyebrow}</Typography.Text>
          <Typography.Title level={3}>{title}</Typography.Title>
          <Typography.Paragraph type="secondary">{description}</Typography.Paragraph>
        </div>
        {onBack ? <Button type="text" className="app-workbench-back" onClick={onBack}>← 应用中心</Button> : null}
      </header>

      {banner ? <div className="app-workbench-banner">{banner}</div> : null}

      <div className="app-workbench-mobile-tabs" role="tablist" aria-label="工作台区域">
        <button
          type="button"
          role="tab"
          aria-selected={mobilePane === "input"}
          aria-controls={resolvedInputId}
          onClick={() => setMobilePane("input")}
          onKeyDown={(event) => moveMobileTab(event, "result")}
        >
          {inputLabel}
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={mobilePane === "result"}
          aria-controls={resolvedResultId}
          onClick={() => setMobilePane("result")}
          onKeyDown={(event) => moveMobileTab(event, "input")}
        >
          {resultLabel}
        </button>
      </div>

      {adoptedContent ? (
        <div className="app-workbench-adopted" data-mobile-pane={mobilePane}>
          {showAdoptedState ? <div className="app-workbench-adopted-state" aria-live="polite">
            <Tag color={state.color}>{state.label}</Tag>
            <Typography.Text type="secondary">{state.description}</Typography.Text>
          </div> : null}
          {adoptedContent}
          {adoptedInputFooter ? <div className="app-workbench-adopted-footer">{adoptedInputFooter}</div> : null}
        </div>
      ) : (
        <div className="app-workbench-grid" data-mobile-pane={mobilePane}>
          <section id={inputId} className="app-workbench-pane app-workbench-pane--input" aria-label={inputLabel}>
            <div className="app-workbench-pane-heading">
              <Typography.Title level={4}>{inputLabel}</Typography.Title>
            </div>
            <div className="app-workbench-pane-body">{input}</div>
            {inputFooter ? <div className="app-workbench-pane-footer">{inputFooter}</div> : null}
          </section>

          <section id={resultId} className="app-workbench-pane app-workbench-pane--result" aria-label={resultLabel} aria-live="polite">
            <div className="app-workbench-pane-heading">
              <Typography.Title level={4}>{resultLabel}</Typography.Title>
              <Tag color={state.color}>{state.label}</Tag>
            </div>
            <Typography.Paragraph className="app-workbench-state-copy" type="secondary">
              {state.description}
            </Typography.Paragraph>
            <div className="app-workbench-pane-body">{result}</div>
          </section>
        </div>
      )}
    </section>
  );
}
