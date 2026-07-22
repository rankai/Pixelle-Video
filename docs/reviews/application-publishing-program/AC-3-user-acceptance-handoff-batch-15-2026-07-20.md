# AC-3 真实用户/人工验收交接批次 15

状态：`superseded_by_internal_simulation`

用户已明确授权由主线程执行内部模拟用户任务，不要求真实人工接入；因此本协议的人工等待被批次 15 的浏览器模拟取代。

以下“唯一人工动作”段落是原始人工 fallback 协议，保留用于未来真实人工验收，不是当前 AC-D Gate 的阻塞条件；当前权威结果以 [`AC-3-user-completion-simulated-batch-15-2026-07-20.md`](AC-3-user-completion-simulated-batch-15-2026-07-20.md) 为准。

批次 14 已完成内部合成与受控 Playwright smoke，但 PG-D 仍不能关闭。下一步必须由真实目标用户或产品负责人完成一次不带测试人员代操作的本地应用中心任务，补齐真实完成时间、求助次数、失败原因和主观可用性记录。

## 唯一人工动作

在本地应用中心打开“门店营销文案”，使用一个不含敏感信息的真实门店场景，完成：

1. 填写项目名称、营销目标、产品或服务；
2. 点击“保存草稿”；
3. 点击“创建运行草稿”；
4. 点击“执行”，等待进入“待审核”；
5. 查看生成结果后点击“确认完成”。

只做这一笔，不点击抖音发布、不上传平台、不重复重试。若遇到失败，记录失败画面和错误码后停止，不让测试人员代替用户完成下一步。

## 需要回填的最小证据

```json
{
  "scenario": "",
  "started_at_utc": "",
  "ended_at_utc": "",
  "final_state": "completed|failed|cancelled",
  "help_count": 0,
  "operator_intervention": false,
  "failure_reason": null,
  "user_rating_1_to_5": null,
  "screenshot_sha256": null,
  "artifact_version_id": null,
  "publish_triggered": false
}
```

证据不得包含 API key、Cookie、二维码或完整个人信息。内部模拟结果由 Luna 写入台账并交严格审查线程复验；真实人工验收仍可作为后续增强证据，但不再是当前唯一阻塞条件。

## 当前边界

- 批次 14 的 10 个场景是内部 RTL mock，不是 10 名真实用户；Playwright smoke 是单场景、单 viewport、route-mock 的浏览器预检。
- 真实 provider/ArtifactVersion 是否产生由本次人工动作如实记录，不得用 mock 结果替代。
- 批次 15 已按上述要求逐项记录 10 个浏览器模拟任务的动作、解释/介入、最终状态和证据，见 [`AC-3-user-completion-simulated-batch-15-2026-07-20.md`](AC-3-user-completion-simulated-batch-15-2026-07-20.md)。
