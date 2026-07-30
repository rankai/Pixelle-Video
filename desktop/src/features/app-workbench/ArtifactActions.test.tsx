import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { ArtifactVersion } from "../../api";
import { ArtifactActions, VersionSwitcher } from "./ArtifactActions";

const versions: ArtifactVersion[] = [
  { artifact_version_id: "v1", artifact_id: "a1", project_id: "p1", version_number: 1, schema_version: 1, content: {}, file_refs: [], source: "generated", content_fingerprint: "fp1", created_at: "now" },
  { artifact_version_id: "v2", artifact_id: "a1", project_id: "p1", version_number: 2, schema_version: 1, content: {}, file_refs: [], source: "edited", content_fingerprint: "fp2", created_at: "later" },
];

describe("ArtifactActions", () => {
  it("switches a pinned result version without creating a run", () => {
    const onChange = vi.fn();
    render(<VersionSwitcher versions={versions} value="v1" onChange={onChange} />);
    fireEvent.mouseDown(screen.getByLabelText("结果版本"));
    fireEvent.click(screen.getByText("v2 · 编辑"));
    expect(onChange).toHaveBeenCalledWith("v2", expect.objectContaining({ value: "v2" }));
  });

  it("keeps handoff actions explicit and independently callable", () => {
    const onClick = vi.fn();
    render(<ArtifactActions actions={[{ key: "digital-human", label: "制作数字人", onClick, primary: true }]} />);
    fireEvent.click(screen.getByRole("button", { name: "制作数字人" }));
    expect(onClick).toHaveBeenCalledTimes(1);
    expect(screen.queryByText("自动发布")).not.toBeInTheDocument();
  });
});
