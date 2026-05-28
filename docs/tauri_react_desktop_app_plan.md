# Tauri + React Desktop App Plan

## Summary

目标是在 1 周到 10 天内交付老板 IP 口播 Windows 桌面 App v1。技术路线选用 Tauri + React + 本地 Python FastAPI sidecar。首版只迁移老板 IP 口播 1-6 主流程，Home 和 History 暂时保留在 Streamlit，后续再逐步迁入同一个桌面 App。

整体迁移路线：

```text
v1：Tauri + React 只承载老板 IP口播
v2：迁移 Home 快速合成
v3：迁移 History / 素材库 / 任务中心
v4：Streamlit 退为内部调试入口或废弃
```

## Why This Plan

方案评分：8.5/10。

优点：

- 保留 Python 核心能力，不重写 TTS、RunningHub、FFmpeg、Playwright、视频合成。
- React 负责复杂 UI，适合分镜、素材库、任务状态、模板卡片、配置页。
- Tauri 负责桌面窗口、安装包、本地进程管理和文件权限。
- 首版只做 IP 口播，避免 Home/History 同时迁移导致周期失控。
- Streamlit 保留为回归基线，降低迁移风险。

主要风险：

- 10 天内完成安装包、配置页、React UI、API 抽取，周期偏紧。
- Windows 打包会遇到 FFmpeg、Playwright、Python sidecar、路径权限问题。
- 后续需要维护 Python、React、Tauri 三层工程。
- RunningHub 远程任务首版无法保证真正取消，只能停止本地等待。

## Target Architecture

```text
Tauri Windows App
  └─ React + TypeScript 前端
       └─ HTTP API / 任务轮询
            └─ Python FastAPI sidecar
                 └─ pixelle_video 核心服务
                      ├─ LLM
                      ├─ TTS
                      ├─ RunningHub / ComfyUI
                      ├─ FFmpeg
                      ├─ Playwright
                      ├─ yt-dlp
                      └─ 素材库 / 缓存 / 输出文件
```

首版关键原则：

- React 不直接调用 Python 内部函数，只调用 FastAPI。
- FastAPI 不依赖 Streamlit session state。
- Streamlit 页面保留，不参与桌面 App。
- 本地后端只监听 `127.0.0.1`。
- 文件下载使用 artifact id，不允许前端传任意路径。
- API Key、Bearer token、本地 session token 不写入日志。

## Phased Implementation

### Phase 0：冻结稳定基线

周期：0.5 天

目标：

- 保存当前 Streamlit IP 口播稳定版本。
- 确认 1-6 主流程能跑通。
- 建立迁移分支。

任务：

- 运行 `uv run pytest -q`。
- 运行 `uv run ruff check .`。
- 手动验证 Streamlit IP 口播：
  - 素材来源
  - AI 改写
  - 声音生成
  - 数字人生成
  - 一键成片
  - 下载发布素材
- 提交当前稳定代码。
- 创建分支：`codex/tauri-react-desktop-v1`。

进入下一阶段条件：

- 测试通过。
- lint 通过。
- Streamlit IP 口播无阻塞问题。
- 当前代码已提交。

### Phase 1：抽 IP 口播本地 API

周期：2 天

目标：

- 新增 `/api/ip-broadcast`。
- 将 IP 口播 1-6 步封装为本地 API。
- React 后续只通过 API 驱动流程。

任务：

- 新增 session store。
- 新增 API schema：
  - `IpBroadcastSession`
  - `IpBroadcastState`
  - `IpBroadcastStepStatus`
  - `IpBroadcastConfig`
  - `IpBroadcastRunStepRequest`
  - `IpBroadcastRunStepResponse`
- 新增接口：
  - `POST /api/ip-broadcast/sessions`
  - `GET /api/ip-broadcast/sessions/{session_id}`
  - `PATCH /api/ip-broadcast/sessions/{session_id}/config`
  - `POST /api/ip-broadcast/sessions/{session_id}/steps/{step_key}/run`
  - `POST /api/ip-broadcast/sessions/{session_id}/continue`
  - `GET /api/ip-broadcast/sessions/{session_id}/artifacts/{artifact_key}`
- 步骤 key：
  - `source`
  - `copywriting`
  - `voice`
  - `digital_human`
  - `postproduction`
  - `publish`
- TaskType 增加 `ip_broadcast_step`。
- 长任务使用 TaskManager + 轮询。
- 失败时写入对应 step notice，不清空已有产物。
- API 不导入 Streamlit。

进入下一阶段条件：

- curl 或 API 测试可跑通最小链路。
- 任一步失败状态正确。
- Streamlit 页面不回归。
- `uv run pytest -q` 通过。
- `uv run ruff check .` 通过。

### Phase 2：增加桌面安全边界

周期：0.5-1 天

目标：

- 让本地 API 满足桌面 App 安全要求。

任务：

- 桌面模式后端只监听 `127.0.0.1`。
- CORS 禁止 `*`，只允许 Tauri WebView origin。
- 增加 `X-Pixelle-Desktop-Token`。
- Tauri 启动后端时生成随机 token。
- 后端校验 token。
- 桌面模式关闭 `/docs`、`/redoc`、`/openapi.json`。
- 文件接口改为 artifact-based。
- 禁止前端传任意绝对路径。
- 日志脱敏：
  - LLM api_key
  - RunningHub api_key
  - Bearer token
  - desktop token

进入下一阶段条件：

- 无 token 请求返回 401。
- 文件越权访问被拒绝。
- 日志中无明文密钥。
- 本机以外无法访问后端。

### Phase 3：Tauri + React 工程骨架

周期：1-1.5 天

目标：

- 建立桌面 App 基础工程。
- 能启动 Python FastAPI sidecar。
- React 能访问本地 API。

任务：

- 新增 `desktop/`：
  - Tauri
  - React
  - TypeScript
  - Vite
  - API client
  - 状态管理
  - theme tokens
- Tauri 启动 Python sidecar。
- 关闭窗口时停止 sidecar。
- React 启动页检查：
  - 后端 health
  - IP 口播 API health
  - FFmpeg
  - Playwright
  - yt-dlp
  - config 状态
- 建立基础页面：
  - 启动自检页
  - 配置页
  - IP 口播页骨架
  - 日志/诊断入口

进入下一阶段条件：

- `tauri dev` 可启动桌面窗口。
- React 能访问后端。
- 后端异常退出时 UI 有提示。
- 关闭 App 后无残留 Python 进程。

### Phase 4：配置页 v1

周期：1 天

目标：

- 用户不需要手动编辑 `config.yaml`。
- 首次启动可完成必要配置。

配置页 v1 字段：

- LLM：
  - `base_url`
  - `api_key`
  - `model`
- RunningHub：
  - `api_key`
  - `instance_type`
- 输出目录：
  - `output_dir`

功能：

- API Key 脱敏展示。
- 保存配置。
- 测试 LLM 配置。
- 检测 RunningHub key 是否存在。
- 检测 FFmpeg。
- 检测 Playwright。
- 保存后提示重启本地服务或自动触发后端 reload。

暂不做：

- workflow 全量编辑。
- 高级并发配置。
- 多环境切换。
- 用户账号系统。
- 云同步配置。

进入下一阶段条件：

- 首次启动无 config 时进入配置页。
- 配置保存成功。
- 后端能重新读取配置。
- 配置保存失败有明确错误。

### Phase 5：React 重做 IP 口播 1-6 UI

周期：2.5-3 天

目标：

- 用 React 重做老板 IP 口播主界面。
- 桌面 App 内跑通完整链路。

页面结构：

- 顶部生产主控台。
- 三列布局：
  - 第 1 列：素材来源 + 文案确认
  - 第 2 列：声音生成 + 数字人视频
  - 第 3 列：一键成片 + 视频发布

Step 1：素材来源

- 视频链接/分享文本。
- 粘贴脚本。
- 行业+人设。
- IP 学习。
- 手动 5 条视频链接兜底。

Step 2：文案确认

- 最终口播文案。
- 写作风格。
- 目标字数。
- AI 改写/优化文案。

Step 3：声音生成

- local / comfyui。
- Edge / Index / Spark 参数。
- 参考音频库。
- 上传参考音频。
- 录音保存。
- 试听。

Step 4：数字人视频

- 形象库卡片。
- 图片形象 / 视频形象按 workflow 类型校验。
- 支持：
  - 旧 digital_combination
  - 图片 AI App
  - 快速版 AI App
  - 视频改口型 AI App
- 宽高参数可编辑。

Step 5：一键成片

- 画面模板。
- 视频素材管理。
- 画面规划。
- 高级成片设置。
- 发布素材与封面。

Step 6：视频发布

- 视频预览。
- 下载最终视频。
- 复制标题。
- 复制描述。
- 复制标签。
- 打开输出目录。

UX 要求：

- 每步按钮放在配置之后。
- 每步末尾只显示一个 notice。
- loading 可停止。
- 错误显示在对应步骤。
- 失败后可重试当前步骤。
- 生产主控台进度与后端状态一致。
- 大视频预览使用后端 URL，不转 base64。

进入下一阶段条件：

- 粘贴脚本路径完整跑通。
- 视频链接或 IP 学习路径至少跑通一种。
- TTS、数字人、一键成片可用。
- 失败/取消不会卡 loading。
- React UI 不依赖 Streamlit。

### Phase 6：Windows 安装包

周期：1.5-2 天

目标：

- 交付 Windows 安装包。
- 用户不需要安装 Python、Node、Rust。

任务：

- 打包 Python FastAPI sidecar。
- Tauri 配置 Windows installer。
- 随包携带：
  - Python runtime / sidecar exe
  - FFmpeg
  - Playwright Chromium
  - yt-dlp
  - workflows
  - templates
  - config template
  - demo/static assets
- 用户数据目录：
  - config
  - output
  - cache
  - logs
  - uploaded assets
- 首次启动：
  - 自动创建用户数据目录。
  - 无配置时进入配置页。
  - 依赖异常时进入诊断页。
- 增加端口策略：
  - 优先固定端口。
  - 被占用时自动寻找可用端口。
  - React 从 Tauri 获取实际后端地址。

进入下一阶段条件：

- 生成 Windows 安装包。
- 干净 Windows 机器安装成功。
- 非管理员用户可运行。
- 安装路径包含空格时可运行。
- FFmpeg/Playwright/yt-dlp 自检通过。
- 完整 IP 口播链路跑通一次。

### Phase 7：发布候选与回归

周期：1 天

目标：

- 输出内部可试用 RC 包。
- 补齐日志、错误提示和文档。

任务：

- 增加常见错误提示：
  - API Key 缺失。
  - 401。
  - RunningHub 失败。
  - RunningHub 超时。
  - FFmpeg 失败。
  - Playwright 缺失。
  - 文件权限不足。
  - 端口占用。
- 增加日志导出：
  - 打开日志目录。
  - 导出最近一次任务日志。
  - 日志脱敏。
- 增加用户文档：
  - 安装。
  - 首次配置。
  - 生成视频。
  - 常见问题。
  - 日志导出。
- 执行完整测试矩阵。

完成标准：

- `uv run pytest -q` 通过。
- `uv run ruff check .` 通过。
- React build 通过。
- Tauri build 通过。
- Windows 安装包安装成功。
- 干净 Windows 环境完成一条完整 IP 口播视频。
- 日志不包含 API Key 明文。

## Performance Requirements

- 保留 TTS 缓存。
- 保留数字人缓存。
- 快速版数字人输出长于音频时自动裁剪。
- BGM 长于视频时按主视频长度输出。
- RunningHub 长任务轮询 1-2 秒一次。
- idle 状态降低轮询频率。
- 大文件不转 base64。
- 重复输入不重复调用昂贵接口。

## Security Requirements

- 后端只监听 `127.0.0.1`。
- 本地 API 需要 desktop token。
- CORS 不允许 `*`。
- 文件下载 artifact-based。
- 上传文件校验：
  - basename
  - 扩展名白名单
  - 文件大小
  - 保存目录限制
- 删除素材必须限制在素材库目录内。
- 日志脱敏。
- 配置页 API Key 脱敏显示。
- 不开放任意 path 读取接口。

## Test Plan

后端 API：

- 创建 session。
- 更新配置。
- 每一步依赖检查。
- 每一步成功/失败状态。
- task 轮询。
- task cancel。
- artifact 下载。

安全：

- 无 token 401。
- CORS 限制。
- 文件越权拒绝。
- 非法上传拒绝。
- 日志无 key。

业务：

- 粘贴脚本完整链路。
- 视频链接提取链路。
- IP 学习链路。
- 手动 5 条链接兜底。
- local Edge TTS。
- RunningHub TTS。
- 旧 digital_combination。
- 图片 AI App。
- 快速版 AI App。
- 视频改口型 AI App。
- 一键成片。
- BGM 长于视频。
- 覆盖视频素材。

桌面：

- 启动 sidecar。
- 关闭 sidecar。
- 端口占用 fallback。
- 配置保存。
- 日志导出。
- 打开输出目录。

Windows：

- 干净系统。
- 中文路径。
- 空格路径。
- 非管理员运行。
- 首次启动无 config。
- 无网络/401/RunningHub 失败提示。

## Assumptions

- 首版只做 Windows。
- 首版只迁移老板 IP 口播。
- 首版交付 Windows 安装包。
- 首版提供配置页面。
- 首版按 6 步 API 封装。
- 首版不做真实发布平台 API。
- 首版不做自动更新。
- 首版不做代码签名，除非时间允许。
- 首版不做用户账号系统。
- RunningHub 远程任务取消不作为 v1 承诺。
- Home 和 History 后续迁移到同一个 Tauri + React App。
