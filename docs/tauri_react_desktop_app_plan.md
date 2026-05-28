# Tauri + React Desktop App Plan

## Summary

目标是在 1 周到 10 天内交付老板 IP 口播 Windows 桌面 App v1。技术路线选用 Tauri + React + 本地 Python FastAPI sidecar。首版只迁移老板 IP 口播 1-6 主流程，Home 和 History 暂时保留在 Streamlit，后续再逐步迁入同一个桌面 App。

整体迁移路线：

```text
v1：Tauri + React 承载老板 IP口播、资源管理中心、配置与诊断
v2：迁移 Home 快速合成
v3：迁移 History / 任务中心 / 团队资产协作
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
- 素材资产独立维护，IP 口播工作台只负责选择资产和生产视频。
- 1-6 步使用步骤条和单步工作区，不使用三列长期承载复杂配置。

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
- 横向步骤条：
  - 1 素材来源
  - 2 文案确认
  - 3 声音生成
  - 4 数字人视频
  - 5 一键成片
  - 6 视频发布
- 下方单步工作区。
- 底部动作栏：
  - 上一步
  - 下一步
  - 运行当前步骤
  - 一键继续
- 窄屏时步骤条可切换为左侧竖向步骤导航。

步骤条规则：

- 已完成步骤可点击回看。
- 当前可执行步骤高亮。
- 未满足依赖的后续步骤可点击查看，但主按钮禁用并提示缺什么。
- 步骤之间切换不丢数据。
- 生产主控台固定在顶部。
- 长任务运行时步骤条显示 running。
- 错误步骤显示红色状态，可点击回到错误步骤。

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

- 从音色库选择参考音频或默认声音。
- local / comfyui。
- Edge / Index / Spark 参数。
- 上传和录音入口跳转或打开音色库维护弹窗。
- 试听。

Step 4：数字人视频

- 从形象库选择图片或视频形象。
- 图片形象 / 视频形象按 workflow 类型校验。
- 支持：
  - 旧 digital_combination
  - 图片 AI App
  - 快速版 AI App
  - 视频改口型 AI App
- 宽高参数可编辑。

Step 5：一键成片

- 从画面模板库选择模板。
- 从视频素材库选择覆盖素材。
- 画面规划摘要。
- 按钮：打开画面规划。
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
- 第 5 步不直接展开长列表；画面规划通过大弹窗或抽屉完成。

进入下一阶段条件：

- 粘贴脚本路径完整跑通。
- 视频链接或 IP 学习路径至少跑通一种。
- TTS、数字人、一键成片可用。
- 失败/取消不会卡 loading。
- React UI 不依赖 Streamlit。

### Phase 5.5：资源管理中心与画面规划编辑器

周期：1.5-2 天

目标：

- 素材资产可独立维护。
- IP 口播工作台只选择资产，不承担资产管理。
- 画面规划从第 5 步内联长表单升级为独立编辑器。

顶层菜单：

```text
Pixelle Desktop
├─ IP口播工作台
├─ 素材资产
│  ├─ 音色库
│  ├─ 形象库
│  ├─ 画面模板库
│  └─ 视频素材库
├─ 配置中心
└─ 诊断/日志
```

资源管理 API：

- `/api/assets/voices`
  - 列表
  - 上传
  - 删除
  - 获取试听/下载 artifact
- `/api/assets/portraits`
  - 列表
  - 上传图片或视频形象
  - 删除
  - 预览
  - 返回 `media_type`
- `/api/assets/videos`
  - 列表
  - 上传覆盖视频
  - 自动生成封面
  - 删除
  - 预览
- `/api/assets/templates/ip-broadcast`
  - 模板列表
  - 预览图
  - 标题位置说明
  - 字幕位置说明
  - 模板风格说明

资源页面要求：

- 卡片高度统一。
- 图片/视频封面统一比例。
- 标题、描述、操作按钮位置统一。
- 支持空状态、错误状态、上传中状态。
- 删除前二次确认。
- 正在被当前工作流使用的素材不允许删除，或提示先取消引用。

画面规划编辑器：

- 从第 5 步点击“打开画面规划”进入大弹窗或右侧抽屉。
- 首版推荐大弹窗：
  - 宽度 80%-90%。
  - 高度 80%-90%。
  - 内部三栏布局。
  - 关闭前如有未保存修改，弹出确认。
- 左侧：文案段落列表。
  - checkbox 多选段落。
  - 只允许连续段落成组。
  - 显示段落序号和摘要。
- 中间：覆盖组列表。
  - 显示覆盖段落范围。
  - 显示覆盖类型。
  - 显示素材缩略图。
  - 支持启用、禁用、删除。
- 右侧：当前组设置。
  - 覆盖类型：用户视频 / AI 视频 / 不覆盖。
  - 从视频素材库选择素材。
  - 上传新视频素材并保存到视频素材库。
  - AI 视频 prompt。
  - 覆盖方式：全屏替换 / 画中画。
- 底部操作：
  - 保存规划。
  - 清空规划。
  - 关闭。

第 5 步工作台只显示摘要：

- 是否启用画面规划。
- 覆盖组数量。
- 覆盖段落数量。
- 已选择模板。
- 已选择视频素材数量。
- 打开画面规划按钮。

进入下一阶段条件：

- 音色库、形象库、画面模板库、视频素材库可独立访问。
- IP 口播 Step 3/4/5 可从资源库选择资产。
- 画面规划弹窗能创建、编辑、保存、清空覆盖组。
- 第 5 步摘要正确反映画面规划状态。
- 资源删除和当前工作流引用关系处理正确。

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

## ToB Product Experience Recommendations

这个桌面 App 面向中小企业做口播、探店、门店推广和老板 IP 内容，产品体验要优先服务“稳定批量生产”和“资产复用”，而不是单次炫技。

### 1. 工作台与资产分离

- 工作台只做生产：
  - 选素材。
  - 选模板。
  - 运行步骤。
  - 下载结果。
- 素材资产独立维护：
  - 音色。
  - 形象。
  - 视频素材。
  - 画面模板。
- 配置中心独立维护：
  - API Key。
  - 模型。
  - RunningHub。
  - 输出目录。

这样适合企业多次复用同一批老板形象、门店素材、探店 B-roll、品牌模板。

### 2. 默认路径必须短

中小企业用户通常不是专业剪辑师。默认链路应该是：

```text
选择素材来源 → 确认文案 → 选择音色 → 选择形象 → 一键成片 → 下载
```

高级能力应该收起来：

- 声音克隆高级参数。
- 数字人 workflow 参数。
- BGM 音量。
- 去静音。
- 画面规划。
- AI 视频覆盖。

用户只在需要时进入高级配置。

### 3. 适合企业的“预设”比参数更重要

建议后续增加业务预设：

- 老板人设口播。
- 门店探店。
- 新品推荐。
- 团购转化。
- 客户案例。
- 节日活动。
- 招商加盟。
- 知识干货。

每个预设应该包含：

- 推荐文案结构。
- 推荐字数。
- 推荐模板。
- 推荐字幕风格。
- 推荐画面规划策略。

这比暴露大量参数更适合 ToB 用户。

### 4. 任务中心

任务中心是生成任务管理页，用来解决长任务不可见、失败后难定位、结果难查找的问题。IP 口播工作台管理“当前视频生产流程”，任务中心管理“所有后台任务状态和结果”。

会进入任务中心的操作：

- 提取视频口播文案。
- IP 学习抓取 5 条视频。
- AI 改写文案。
- 生成语音。
- 生成数字人视频。
- AI 视频覆盖。
- 一键成片。
- 生成标题/封面。

任务中心显示：

- 任务名称。
- 所属流程。
- 当前步骤。
- 状态：等待中 / 运行中 / 已完成 / 失败 / 已取消。
- 开始时间。
- 耗时。
- 进度。
- 结果入口。
- 重试按钮。
- 查看日志按钮。
- 打开输出目录。

v1 范围：

- 不做完整任务中心页面。
- 工作台顶部显示当前 active task。
- 当前任务失败时展示业务化错误和技术详情入口。
- 当前任务完成后显示结果入口。
- 当前任务可停止本地等待。

v1.1 范围：

- 新增简单任务中心页面。
- 显示最近任务列表。
- 支持按状态筛选：
  - 正在运行。
  - 已完成。
  - 失败。
- 失败任务可重试。
- 已完成任务可打开结果或输出目录。
- 每条任务可查看日志摘要。

v2 范围：

- 完整任务历史。
- 批量任务。
- 搜索和筛选。
- 重试策略。
- 日志导出。
- 任务结果复用。
- 多项目/多品牌任务归档。

长期应该支持批量任务：

- 同一文案生成多个标题版本。
- 同一素材生成多个平台比例。
- 同一门店生成多条探店脚本。

验收标准：

- v1：长任务运行时用户能看到当前任务状态、进度、停止入口和失败原因。
- v1.1：最近任务能按状态查看，失败任务能重试，完成任务能打开结果。
- v2：批量任务和历史结果可检索、可复用、可导出日志。

### 5. 增加品牌资产能力

中小企业通常会重复使用固定品牌元素。

建议后续新增：

- 企业 logo。
- 品牌色。
- 默认字体。
- 默认字幕样式。
- 默认片尾。
- 默认 BGM。
- 门店地址/电话/团购口令。

这些可以形成“品牌包”，一键应用到视频。

### 6. 发布素材要产品化

第 6 步不只是下载视频，应该是“发布素材包”。

建议输出：

- 视频。
- 标题。
- 描述。
- 标签。
- 封面。
- 口播文案。
- 平台发布建议。

后续可按平台生成：

- 抖音标题/标签。
- 小红书标题/正文/标签。
- 视频号标题/描述。
- 快手标题/标签。

首版不接真实发布 API，但发布素材要组织清楚。

### 7. 错误提示要面向业务用户

不要只显示技术错误。建议分两层：

- 用户提示：
  - “RunningHub Key 无效，请到配置中心检查。”
  - “当前数字人工作流只支持图片形象。”
  - “视频素材太大，请压缩后重新上传。”
- 技术详情：
  - 可展开。
  - 可复制。
  - 可导出日志。

### 8. 模板要按场景命名

模板名称不要只叫“模板 1/2/3”。建议：

- 老板知识分享。
- 门店探店推荐。
- 强转化团购。
- 高客单咨询。
- 新品上新。

模板卡片显示：

- 封面标题位置。
- 字幕位置。
- 适合场景。
- 预览图。

### 9. 为后续团队协作留入口

首版可以不做账号系统，但产品结构要预留：

- 项目。
- 素材库。
- 品牌包。
- 任务记录。
- 导出日志。

这样未来从单机工具升级为团队版不会推倒重来。

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
