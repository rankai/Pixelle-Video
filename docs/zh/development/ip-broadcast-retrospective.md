# IP 口播智能体开发复盘

## 背景

本轮改造围绕老板 IP 口播智能体的高效跑通体验展开：把原本多个模块、多个中转按钮、多个重复输入框的页面，收敛成“素材来源 -> 文案确认 -> 声音生成 -> 数字人生成 -> 成片 -> 发布素材”的主流程。

同时补充了 IP 学习、声音参考库、数字人形象库、RunningHub AI App 数字人口播工作流、全局任务状态提示等能力。

## 做对的事情

- 先重构流程状态，再精简 UI 控件。通过 `ipb_source_text`、`ipb_final_script`、`ipb_source_mode` 等状态字段，把“当前有什么产物、下一步能做什么”变成明确逻辑，而不是靠用户在模块间搬运文本。
- 对长任务统一状态反馈。每个步骤都应有“运行中、成功、失败”的明确反馈，避免用户不知道按钮是否生效。
- 高级能力默认收起。声音克隆、BGM、去静音、手动链接兜底等能力保留，但不挤占默认路径。
- 外部平台能力先做业务内 wrapper。RunningHub AI App 接口还在验证期，先放在 Pixelle-Video 内部封装，等上传、任务创建、轮询、结果解析跑稳后，再考虑上游 ComfyKit 抽象。
- 对易失败链路提供兜底。抖音主页抓取可能遇到登录、验证码、Cookie 权限、浏览器差异，必须有清晰失败提示和手动粘贴最近 5 条视频链接的备选路径。

## 暴露的问题

- Streamlit 的同步执行模型容易让 loading 状态残留。长任务完成后如果只修改状态、不触发一致的 rerun，页面可能继续显示旧的运行中提示。
- 同一产物不要在多个位置重复预览。音频、数字人视频、最终视频应分别只有一个主预览入口，避免用户以为生成了多份结果。
- 第三方平台接口不能只根据路径名猜测。RunningHub 普通 workflow、OpenAPI、AI App、站内任务取消接口是不同链路，必须核对真实文档和前端请求形态。
- 浏览器 Cookie 读取在 macOS 上差异很大。Chrome、Safari、Firefox、国内 Chromium 系浏览器的 Cookie 位置和系统权限都不同，失败信息应告诉用户当前尝试了什么，而不是只暴露底层异常。
- 录音能力受浏览器环境影响。Codex 内置浏览器和真实浏览器的麦克风权限表现可能不同，UI 文案要避免把环境限制误描述成用户操作错误。

## 后续准则

1. 主流程按钮必须使用统一任务状态 helper，完成或失败后都要清理运行态。
2. 每个步骤只保留一个主产物预览；调试信息、历史结果、详细学习结果默认折叠。
3. 任何外部 API 集成先记录接口来源、认证方式、请求路径、请求体、响应解析和失败表现。
4. 对需要浏览器登录态的抓取能力，优先支持多浏览器 Cookie 发现，并保留手动输入兜底。
5. 新增 UI 能力时优先扩展共享 helper，而不是在单个模块里写一次性样式。
6. 提交前至少运行 IP 口播相关测试和本次改动文件的 Ruff 检查；全仓 Ruff 如有历史问题，需要明确区分。

## 当前实现重点文件

- `web/ip_broadcast/status_ui.py`
- `web/ip_broadcast/modules/m1_benchmark.py`
- `web/ip_broadcast/modules/m2_copywriting.py`
- `web/ip_broadcast/modules/m3_voice.py`
- `web/ip_broadcast/modules/m4_digital_human.py`
- `pixelle_video/services/digital_human_service.py`
- `pixelle_video/services/ip_learning.py`
- `pixelle_video/services/voice_reference_service.py`
- `docs/zh/development/comfykit-ai-app-decision.md`
