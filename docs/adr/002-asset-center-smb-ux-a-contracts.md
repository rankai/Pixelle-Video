# ADR-002：资产中心 SMB UX-A 契约与交互边界

- 状态：Accepted（UX-A 证据复审通过，可进入 UX-1）
- 日期：2026-07-18
- 范围：七种资产投影、生产选择器上下文、错误码、管理/选择 action adapter、灰度开关
- 前置：`docs/adr/001-enterprise-asset-library-v2.md`

## 背景

资产库 V2 已有统一资源内核，但现有页面把不同领域压成通用 `summary`，并让管理卡片与生产选择器共享副作用。SMB UX 需要业务语言、渐进展开和清晰确认，同时不能复制一套“老板版”数据或组件。

## 决策

### 七种类型化 view model

`image`、`video`、`audio`、`voice`、`digital_human`、`template`、`brand` 使用 discriminated union。列表只返回 `display` 和 `capabilities`，领域原始 contract 只在详情接口返回；前端不得再用 `Object.entries(summary)` 直接渲染。

对应 Python/JSON/TypeScript 证据：

- `api/schemas/asset_library_ux0.py`；
- `docs/schemas/asset-view-model.schema.json`；
- `desktop/src/features/assets/model/ux0Contracts.ts`。

### picker context 与 action adapter

选择器必须收到 `session_id/step/purpose/slot_id/allowed_kinds` 及规格约束。卡片是纯展示；管理页和选择器分别实现 action adapter：

| 语境 | 允许动作 | 禁止副作用 |
| --- | --- | --- |
| 管理 | 预览、收藏、编辑、归档、用于生产 | 卡片单击 patch session |
| 选择器 | 预览、选中、确认、取消、快捷添加 | 未确认写 session/usage |

管理/选择的确认动作由一次性 reconcile 写入 usage；取消不写入。数字人点击人物或场景只改变预览状态，明确“使用此数字人”才确认。

### 错误码与文案

服务连接、列表、预览、单文件上传、重复决策、游标失效、兼容性和归档错误分别落在对应边界。默认不显示 API 地址或内部 ID；诊断层才允许复制技术信息。重启上传的用户文案固定为“应用已重启，请重新选择原文件继续上传”。

### 灰度

`VITE_ASSET_CENTER_SMB_UX` / `PIXELLE_ASSET_CENTER_SMB_UX` 默认关闭，独立于已启用的 V2 内核开关。迁移和兼容 API 不读取该 UX 开关，因此关闭前台不会阻止数据迁移或回滚。

## 后果

UX-1 可以按稳定类型投影和 action adapter 拆组件，但必须先通过本 ADR 及四份核心契约的评审。旧 V2 页面和旧接口在观察窗口内保留。

## 证据

- 低保真状态图和测量协议：`docs/reviews/2026-07-18-asset-center-ux0-evidence.md`；
- 契约 fixture：`tests/fixtures/ux0/`；
- 自动化验证：`tests/asset_library_ux0_contract_test.py`。
