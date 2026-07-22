# IP Broadcast UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the confirmed Graphite Blue professional workspace UI, optional skin selection in Config, and the publish package delivery page for the React desktop IP broadcast app.

**Architecture:** Keep the current API and workflow logic unchanged. Add a small theme module, wrap the app with Ant Design `ConfigProvider`, convert the shell/console/steps to Ant Design primitives, and use CSS classes for layout and skin tokens instead of inline styles.

**Tech Stack:** React 18, TypeScript, Vite, Ant Design, lucide-react, existing FastAPI backend.

---

### Task 1: Theme System

**Files:**
- Create: `desktop/src/theme.ts`
- Modify: `desktop/src/main.tsx`
- Modify: `desktop/src/App.tsx`
- Modify: `desktop/src/styles.css`

- [ ] **Step 1: Create theme tokens**

Create `desktop/src/theme.ts` exporting three skins:

```ts
export type ThemeSkin = "graphite" | "warm" | "brand";

export const themeSkins = {
  graphite: {
    label: "石墨蓝专业版",
    primary: "#2F6FED",
    bg: "#F3F6FA",
    sidebar: "#172033",
  },
  warm: {
    label: "运营温度版",
    primary: "#D97706",
    bg: "#F7F8F5",
    sidebar: "#1F2933",
  },
  brand: {
    label: "品牌表现版",
    primary: "#C2410C",
    bg: "#F5F6F8",
    sidebar: "#111827",
  },
} as const;
```

- [ ] **Step 2: Import Ant Design reset CSS**

Modify `desktop/src/main.tsx`:

```ts
import "antd/dist/reset.css";
import "./styles.css";
```

- [ ] **Step 3: Wrap app in ConfigProvider**

Modify `desktop/src/App.tsx` so the root render uses `ConfigProvider` with selected theme skin from localStorage.

- [ ] **Step 4: Add CSS variable skins**

Modify `desktop/src/styles.css` with `[data-theme="graphite"]`, `[data-theme="warm"]`, and `[data-theme="brand"]` variables. Use classes, not inline style.

- [ ] **Step 5: Verify**

Run:

```bash
npm run build
```

Expected: TypeScript and Vite build pass.

### Task 2: Professional App Shell

**Files:**
- Modify: `desktop/src/App.tsx`
- Modify: `desktop/src/styles.css`

- [ ] **Step 1: Replace topbar with Ant Design Layout**

Use `Layout`, `Sider`, `Header`, `Content`, and `Menu`. Navigation items remain:

- IP口播
- 素材资产
- 任务中心
- 配置
- 诊断

- [ ] **Step 2: Convert production console**

Use `Card`, `Progress`, `Tag`, `Button`, and `Space` for the production console. Keep the existing execution callbacks unchanged.

- [ ] **Step 3: Convert stepbar**

Use Ant Design `Steps` with `type="navigation"` and map internal step statuses to readable text.

- [ ] **Step 4: Verify**

Run:

```bash
npm run build
```

Expected: build passes and the shell has no white-only topbar/nav layout.

### Task 3: Publish Package Delivery Page

**Files:**
- Modify: `desktop/src/App.tsx`
- Modify: `desktop/src/styles.css`

- [ ] **Step 1: Restructure PublishStep**

Change step 6 into:

- top summary card
- left publish fields
- right video/cover/file info panel
- platform cards

- [ ] **Step 2: Keep copy/download behavior**

Keep existing `downloadArtifact`, `downloadFinalVideo`, and `CopyButton` behavior unchanged.

- [ ] **Step 3: Verify**

Run:

```bash
npm run build
```

Expected: build passes and publish page no longer uses the old two-column field dump.

### Task 4: Config Appearance Setting

**Files:**
- Modify: `desktop/src/App.tsx`
- Modify: `desktop/src/styles.css`

- [ ] **Step 1: Add appearance section**

Add “外观设置” to Config page with three selectable skin cards.

- [ ] **Step 2: Persist skin**

Write the selected skin to `localStorage` key `pixelle_desktop_theme_skin`.

- [ ] **Step 3: Verify**

Run:

```bash
npm run build
```

Expected: selecting a skin updates the app and refresh keeps the selection.

### Task 5: Final Verification

**Files:**
- No new files.

- [ ] **Step 1: Run frontend build**

Run:

```bash
npm run build
```

Expected: build passes.

- [ ] **Step 2: Run Python checks**

Run:

```bash
uv run ruff check .
uv run pytest -q
```

Expected: lint passes and all tests pass.

- [ ] **Step 3: Commit**

Commit with:

```bash
git add desktop/package.json desktop/package-lock.json desktop/src/main.tsx desktop/src/App.tsx desktop/src/styles.css desktop/src/theme.ts docs/superpowers/plans/2026-05-29-ip-broadcast-ui-redesign-implementation.md
git commit -m "feat: redesign ip broadcast desktop UI"
```
