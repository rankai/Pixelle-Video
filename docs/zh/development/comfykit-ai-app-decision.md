# ComfyKit AI App 集成决策记录

## 背景

Pixelle-Video 通过第三方依赖 `comfykit>=0.1.12` 调用 ComfyUI 和 RunningHub 普通 workflow。该依赖来自独立仓库 `puke3615/ComfyKit`，不是 `rankai/Pixelle-Video` 仓库内代码。

IP 口播新增的 RunningHub 数字人口播能力使用 AI App 接口 `/task/openapi/ai-app/run`，不是 ComfyKit 当前已封装的普通 workflow 调用链路。

## 当前决策

短期不 fork ComfyKit。先在 Pixelle-Video 内保留轻量 wrapper，保证 IP 口播数字人 AI App 生成流程可用。

原因：

- AI App 调用刚接入，需要先用真实素材跑稳上传、任务创建、状态轮询、结果解析和错误处理。
- 现在只覆盖了一个明确的业务场景，过早 fork 会增加依赖发布、版本锁定和上游同步成本。
- ComfyKit 上游是公开仓库，MIT license，后续更适合整理成通用 PR。

## 后续路线

1. 在 Pixelle-Video 内继续验证 AI App wrapper。
2. 稳定后整理通用接口，优先向 ComfyKit 上游提 PR：
   - `RunningHubClient.run_ai_app(webapp_id, node_info_list)`
   - `RunningHubExecutor.execute_ai_app(...)`
   - 可选 `ComfyKit.execute_ai_app(...)`
3. 只有在上游长期无响应，或 Pixelle-Video 后续强依赖多种 AI App 能力时，再考虑 fork 并维护私有版本。

## 当前实现位置

- `pixelle_video/services/digital_human_service.py`
- `workflows/runninghub/digital_talk_image_prompt.json`
