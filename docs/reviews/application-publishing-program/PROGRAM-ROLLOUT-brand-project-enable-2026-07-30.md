# PROGRAM-ROLLOUT 品牌项目新版正式启用

- 日期：2026-07-30
- Change Request：`CR-BRAND-PROJECT-ROLLOUT-001`
- 上位入口：`PROGRAM-ROLLOUT / PG-L-BRAND-ROLLOUT`
- 前置 Gate：`PG-BP-F_passed_with_boundary`
- 状态：`implementation_pass_with_boundary`
- 分支：`codex/publish-v2-sidecar-gate`
- 启用前 HEAD：`8de798d260459bb0e62d44b0bb7ab670f4b8b92f`

## 1. 本次交付

品牌项目新版开发 Gate 已通过。本批次不增加产品功能，只把已评审通过的应用工作台和品牌项目能力正式带入桌面生产构建：

1. `desktop/.env.production` 打开应用工作台四项生产开关和 `VITE_BRAND_PROJECT_BOUNDARY_V1`；
2. Tauri 启动打包 sidecar 时默认传入 `PIXELLE_BRAND_PROJECT_BOUNDARY_V1=1`，避免 WebView 已开启而本地 FastAPI 返回 disabled；
3. 明确保留回滚：启动进程显式设置 `PIXELLE_BRAND_PROJECT_BOUNDARY_V1=0/false` 时，前端和 sidecar 均回到旧交互；
4. standalone FastAPI 的代码默认仍为 `false`，不把开发服务器或其他部署静默升级为新版；
5. 增加生产构建、Windows sidecar 同步和回滚契约测试；
6. 修复 375px 窄屏下旧项目品牌关联提示的按钮挤压正文问题。

## 2. 验证结果

| 验证项 | 结果 |
| --- | --- |
| 新增启用/回滚/Windows 契约聚合 | `137 passed / 0 failed` |
| Desktop 全量 | `18 files / 125 passed` |
| Desktop production build | `4610 modules transformed`，通过；仅既有 chunk-size warning |
| Tauri 编译与单测 | `2 passed / 0 failed` |
| Rust format | `cargo fmt --check` 通过 |
| diff whitespace | `git diff --check` 通过 |
| 敏感信息与 QA 数据库检查 | 未发现真实密钥；QA 目录无 `.sqlite/.sqlite3/.db/.bak/.lock` |

## 3. 真实可视化

使用本地真实 FastAPI 与 Vite 桌面页面验证，不使用静态 mock：

- 应用中心：四个应用均显示并可进入；
- 门店营销文案、爆款标题、抖音图文、数字人：均进入统一轻量左右工作台；
- “我的项目”可打开并查看项目列表；
- 旧项目只显示面向用户的“关联品牌包”提示，不暴露 Artifact、revision、snapshot、fingerprint；
- 品牌关联弹窗在未选择品牌时禁止确认，不发生静默写入；
- 1265px 桌面和 375px 窄屏均无横向溢出；
- 窄屏旧项目提示正文横向可读，操作按钮独立换行；
- 控制台只有既有 Ant Design deprecation warning，无运行时 error。

截图、视口指标和 SHA-256 清单见
[`qa/PROGRAM-ROLLOUT-brand-project-enable-2026-07-30/manifest.json`](qa/PROGRAM-ROLLOUT-brand-project-enable-2026-07-30/manifest.json)。

## 4. 发布和回滚边界

- 应用工作台/品牌项目：桌面生产构建默认开启；
- standalone FastAPI：默认仍关闭，必须显式开启；
- 回滚：桌面启动环境设置 `PIXELLE_BRAND_PROJECT_BOUNDARY_V1=0`，保留既有项目、快照和历史生成结果；
- Publish V2 最终发布按钮仍由人工点击，本批次没有改变自动发布边界；
- Windows CI 通过不等于 Windows 真实用户设备验收；安装、首次启动、关闭重开、sidecar health 和端口释放仍需用户在真实 Windows 设备完成；
- 产品负责人签字、真实平台 rollback/WebView SLA 仍属于 PG-L 未完成边界。

## 5. 独立六维复审

首轮独立复审发现并已修复：

1. P1：编译期前端开启、运行时只关闭 sidecar 会产生 split-brain。现由 Tauri
   `desktop_runtime` 返回同一布尔开关，React 在首屏渲染前把编译期能力与运行时能力取交集，
   sidecar 使用同一个解析结果；unset/true 为开启，`0/false` 为前后端同步回滚，非法值失败关闭。
2. P2：数字人普通 UI 的 `Artifact`、`final_video` 技术词改为“历史结果”“可交付视频”“最终视频”。
3. P1：数字人“口播来源”四个 Tab 在工作台输入区被裁切。改为自适应 2×2
   网格，1265px 与 375px 的 tablist `clientWidth === scrollWidth`，四项均完整落在容器内；
   增加 CSS 契约回归断言。
4. 证据型 P2：补齐本批次 1265px 应用中心、四应用、我的项目入口和 375px
   旧项目提示/数字人来源截图与哈希清单。

同一独立严格审查线程最终复验结论为 `PASS with boundary`，P0/P1/P2 均为 0。
审查依据见
[`PROGRAM-ROLLOUT-brand-project-enable-review-2026-07-30.md`](PROGRAM-ROLLOUT-brand-project-enable-review-2026-07-30.md)。
当前可以进入分批提交、推送、PR 合并和 Windows NSIS 安装包构建。
