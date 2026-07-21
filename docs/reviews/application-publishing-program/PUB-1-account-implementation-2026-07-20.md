# PUB-1 account/profile implementation — 2026-07-20

状态：`pass_with_boundary`

阶段：`PUB-ACCOUNT / PUB-1`

上位入口：`docs/reviews/2026-07-18-application-center-publishing-program-progress.md`；当前 Stage 仍为 `PUB-ACCOUNT`，未进入 PUB-CORE/PUB-DOUYIN。

## 1. Scope 与边界

本批次只实现发布账号领域、canonical browser profile 管理、登录探测状态机、锁与上下文恢复、账号 API 与账号页真实数据接线。PublishPackage/PublishRun 编排、平台 selector/上传/字段填充、抖音最终发布、AC-4、数字人和管理后台均未启动。

## 2. 交付物

- `pixelle_video/services/publish/account_models.py`：平台、验证态、登录态、受控状态转移和脱敏投影。
- `pixelle_video/services/publish/account_repository.py`：publishing SQLite 迁移、账号 CRUD、默认/归档、probe 记录、锁镜像和 context registry。
- `pixelle_video/services/publish/profile_manager.py`：canonical `data/publish_browser/accounts/<platform>/<profile_ref>` 路径、legacy 只登记迁移、原子锁、stale lock 恢复和清理边界。
- `pixelle_video/services/publish/account_service.py`：账号生命周期、probe、过期/身份变化、活动可见上下文复用、应用/sidecar 崩溃后的 stale context 回收。
- `pixelle_video/services/publish/browser_runtime.py`：显式 profile path/account_id 传递；仍保留既有 Playwright 作为当前规范运行时。
- `api/schemas/publish_accounts.py`、`api/routers/publish.py`、`desktop/src/api.ts`：平台/账号列表、创建、默认、归档、清理、probe API。
- `desktop/src/features/publishing/PublishAccountsView.tsx`、`StudioApp.tsx`：账号页真实 API、连接态和平台 release state；未验证平台不显示绿色“可用”。
- `docs/contracts/publishing/publish-account.schema.json`、`publish-account-state-machine.json`、`publishing-v2.sql`：共享契约与增量 SQL。

## 3. 安全与正确性证据

- API/前端只接收 `PublishAccount` safe projection；不返回 `profile_path`、Cookie、二维码、凭证或浏览器上下文对象。
- 账号服务只使用 profile 目录作为运行时输入，不读取或复制 Cookie/二维码文件；legacy profile 仅登记 `profile_<platform>_legacy`，不复制旧目录内容。
- 登录状态只允许契约中的相邻转移；非法直接跳转会返回 `PublishAccountConflict`。
- 账号 A/B 使用独立 profile 路径和锁；锁冲突、stale lock、clear profile 防越界和保留账号行均有回归测试。
- 登录要求/过期时，probe 保留显式可见上下文供用户扫码或重新登录；认证、身份变化、错误或关闭时释放 context、runtime 和 DB/file lock。
- 有活动可见上下文时，归档会 fail-closed 返回冲突；必须先显式关闭上下文，避免账号从列表消失而 Cookie-bearing profile 仍被占用。
- 同一账号 probe 重复复用活动上下文，不重复打开 profile；身份指纹只存内部摘要，不进入 API 投影。

## 4. 验证结果

### 后端

```text
uv run pytest -q tests/publish_account_repository_test.py tests/publish_profile_manager_test.py tests/publish_account_service_test.py tests/publish_account_api_test.py
17 passed, 12 existing Pydantic warnings
```

`uv run ruff check`（PUB-1 代码与测试范围）通过。

### 前端

```text
npm run test -- --run --reporter=dot
5 files / 21 tests passed
npm run build
passed
```

仅有既有 Ant Design deprecation、jsdom `getComputedStyle` 提示和 Vite chunk warning，无失败。

### 浏览器只读 smoke

- 运行时：本地 Vite `127.0.0.1:1420` + FastAPI `127.0.0.1:8000`，Codex In-app Browser。
- 页面：`http://127.0.0.1:1420/#/publish`，标题 `Pixelle 老板 IP 口播`。
- 交互：从工作台点击一次“发布中心”，再点击一次“刷新状态”；未点击检测登录、清理、归档、添加账号或平台发布。
- DOM 结果：存在“发布账号”、抖音“试点”、视频号/快手/小红书“未验证”；不存在静态“可用”、账号加载错误或登录提示。
- 控制台：error/warn 为空；页面截图已在本次 Browser smoke 采集，未保存 Cookie/二维码/凭证。

### 全量回归边界

本次全量 Python 运行已收集 `472` 项；一次有界运行在 `68.49s` 达到 `434 passed` 后因全局线程等待停滞而中断，未将其误报为全量通过。其后包含发布账号测试的尾段独立运行已补测为 `17 passed`。因此 `full_python_regression` 仍为 `needs_attention`，不作为 PG-E 通过依据。

## 5. PG-E 验收矩阵

| 检查项 | 当前结论 | 依据/边界 |
| --- | --- | --- |
| A/B profile isolation | `passed` | profile manager/repository/service tests |
| lock conflict、stale lock、clear safety | `passed` | profile manager tests；DB/file lock 镜像 |
| 账号/上下文 stale recovery | `passed` | repository/service tests |
| 过期/重新登录状态机 | `passed_with_boundary` | fake runtime/service tests；真实平台 relogin 未在 PUB-1 触发 |
| 日志/数据库无 Cookie、二维码、凭证 | `passed` | API projection/raw DB assertions |
| 应用/sidecar 重启 | `reused_baseline` | COORD-0 Tauri/sidecar evidence；PUB-1 未重复启动平台动作 |
| 首次扫码 | `reused_baseline` | COORD-0 isolated profile evidence；PUB-1 未重新扫码 |
| packaged Tauri app-data 与真实平台 probe | `not_run_boundary` | 属于后续受控 live/packaged verification，不在本批次伪造 |
| full Python regression | `needs_attention` | 434 passed 后全局线程停滞；targeted PUB-1 与前端已通过 |

## 6. 结论与下一步

PUB-1 的代码、契约、API、账号页和确定性安全回归已完成；独立审查提出的活动上下文归档 P1 已修复，并增加归档/清理 fail-closed 回归（总计 17 项定向通过）。

硬边界：当前 `PlaywrightPublishContext.is_logged_in()` 的固定等待与宽泛 URL/文本判断属于既有发布运行时遗留能力，不能作为 PUB-1 的真实登录验证依据。平台级 `probe_login_state()` 必须在 PUB-CORE/PUB-DOUYIN 以平台身份元素、创作者能力元素、条件等待、challenge/unknown 分支重新实现；PUB-1 只负责安全持久化状态、上下文生命周期和 fake/runtime contract。当前不声称真实平台过期重登或 packaged Tauri probe 通过。

当前仍不是 PG-E 完成：严格审查线程需复验修复与该边界并从六方面给出最终结论；审查通过前，台账仍保持 `current_stage=PUB-ACCOUNT`，不得启动 PUB-CORE/PUB-DOUYIN。
