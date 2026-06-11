# Pixelle Video 产品交付复盘

日期：2026-06-11

## 复盘团队

- 产品架构师：审查系统边界、部署链路、可维护性和故障恢复。
- 资深短视频操作手：审查选题、文案、配音、数字人、画面、发布的高频生产流。
- 本地生活商家代表：审查第一次使用、信任感、业务默认值和交付表达。
- UE/UX 优化师：审查信息架构、交互反馈、错误态、空态和响应式。
- 全栈/安全性能工程师：审查 API 安全、上传下载、任务、容器、性能和测试。

## 本轮已完成修复

1. 文件下载接口路径穿越修复
   - 风险：`/api/files/output/%2E%2E/config.yaml` 可绕过允许目录读取配置文件。
   - 修复：拒绝绝对路径、反斜杠和 `..`，并对候选路径 `resolve()` 后按允许根目录校验。
   - 覆盖：`tests/files_api_test.py`。

2. 配置脱敏值回写保护
   - 风险：配置页读取到 `***redacted***` 后再次保存，会覆盖真实 LLM/RunningHub API Key。
   - 修复：后端 PATCH 过滤脱敏占位符，只更新真实输入的密钥；非桌面模式禁止写入本机配置。
   - 覆盖：`tests/desktop_api_test.py`。

3. webhook 鉴权失败日志脱敏
   - 风险：失败日志打印 `token`，增加部署密钥泄露风险。
   - 修复：日志只记录来源地址，不输出 token 值；支持 `x-pixelle-timestamp` + `x-pixelle-signature` HMAC 校验，并可用 `DEPLOY_WEBHOOK_REQUIRE_HMAC=true` 禁用旧 query token 入口。
   - 覆盖：`tests/deploy_webhook_config_test.py`。

4. 任务重试语义修正
   - 风险：任务中心“重试”只创建任务记录，不会原地执行原任务。
   - 修复：UI 改为“创建重试记录”，并把任务步骤映射对齐后端 6 步流程。
   - 覆盖：`tests/desktop_task_ui_test.py`。

5. 产物依赖失效
   - 风险：改文案、音色、形象、模板、BGM、画面规划后，下游旧音频、旧数字人、旧成片仍可被误用。
   - 修复：会话配置更新时按依赖清理下游产物；改文案会撤销文案确认态。
   - 覆盖：`tests/ip_broadcast_productization_test.py`。

6. BGM 与最终成片一致
   - 风险：桌面端展示 BGM 选择和音量，但后端成片未混入 BGM。
   - 修复：后期合成后按选择的 BGM 和音量调用 ffmpeg 混音，封面以最终成片为准。
   - 覆盖：`tests/ip_broadcast_productization_test.py`。

7. 画面规划素材校验
   - 风险：画面规划引用缺失视频素材时可能静默跳过，导致成片和规划不一致。
   - 修复：合成前阻断缺素材的覆盖组，并明确列出缺失片段。
   - 覆盖：`tests/ip_broadcast_postproduction_test.py`。

8. 生产 sourcemap 关闭
   - 风险：生产前端包暴露源码结构和实现细节。
   - 修复：Vite 生产构建关闭 sourcemap。
   - 覆盖：`tests/desktop_build_config_test.py`。

## 交付阻断项

### 剩余交付前必须定方案项

1. 全站生产鉴权
   - 本轮已完成：非桌面模式禁写 `/api/desktop/config`；发布自动化接口已限定桌面端本地运行。
   - 仍需决策：当前 Web 产品没有登录/JWT 体系，不能简单给浏览器内置 API Key。正式对商家开放前，必须在“账号登录 + 后端会话/JWT”或“仅内网/VPN + 网关鉴权”之间定一种上线口径。

2. webhook 最小权限部署代理
   - 本轮已完成：token 日志脱敏，支持 HMAC+时间戳防重放，正式环境可强制 HMAC。
   - 仍需决策：当前 webhook 仍依赖宿主机项目目录和部署脚本。正式生产建议限制来源 IP，并把 Docker socket 操作拆到最小权限部署代理。

### P1 内部视频团队试用前应完成

1. IP 学习流程增加人工选题确认，不默认取第一个选题直接生成文案。
2. IP broadcast session 持久化，API 重启后可恢复最近项目和任务上下文。
3. 配置页增加连接测试、依赖自检和更明确的错误提示。
4. 首页 readiness 可直达缺失素材类型，并展示完整待处理项。
5. 删除素材增加二次确认、loading 和失败反馈。
6. 视频素材库增加预览能力。
7. 发布页明确真实能力：抖音为草稿助手，其他平台为复制素材手动发布。
8. 前端主文件拆分，降低 `App.tsx` 单文件维护风险。

### P2 可后续迭代

1. 统一 Streamlit legacy 与 React desktop 的产品边界。
2. 统一依赖来源，减少 `pyproject`、requirements、Dockerfile 的漂移。
3. 完善多端响应式策略。
4. 统一 Ant Design 与自定义组件的视觉系统。

## 交付验收清单

### 安全

- 非桌面模式写入 `/api/desktop/config` 返回 403；发布自动化接口在服务器端返回 403。
- 正式商家开放前，全站生产鉴权方案已定稿并完成部署验证。
- `/api/files/output/%2E%2E/config.yaml`、绝对路径、非白名单目录均返回 403/404。
- webhook 错误日志不包含 token、API Key、ACR 密码。
- webhook 正式环境开启 `DEPLOY_WEBHOOK_REQUIRE_HMAC=true`，并配置来源 IP/VPN 限制。
- 生产 CORS 只允许实际 Web 域名。

### 业务

- 全新项目能完成一条“门店信息 -> 文案 -> 配音 -> 数字人 -> 成片 -> 发布素材包”的闭环。
- 修改文案后旧音频/旧数字人/旧成片不能直接发布。
- 选择 BGM 后最终视频能听到 BGM，或 UI 不展示 BGM。
- 缺素材的画面规划不能进入静默合成。

### 运维

- `/health/ready` 能检查配置读写、输出目录、ffmpeg、Playwright/Chromium 和核心依赖。
- API 重启后任务状态和项目恢复行为符合产品文案。
- 部署失败能阻断并回滚到上一稳定镜像。
- 桌面包在干净机器能启动 sidecar，缺 sidecar 时给出硬错误。

### 验证命令

```bash
uv run pytest tests/files_api_test.py tests/desktop_api_test.py tests/deploy_webhook_config_test.py tests/desktop_task_ui_test.py tests/desktop_build_config_test.py
uv run pytest tests/desktop_security_test.py tests/ip_broadcast_upload_security_test.py tests/assets_api_test.py tests/ip_broadcast_api_test.py tests/publish_assistant_test.py
uv run pytest tests/ip_broadcast_productization_test.py tests/ip_broadcast_postproduction_test.py
uv run pytest
cd desktop && npm run build
docker compose -f docker-compose.prod.yml config
```
