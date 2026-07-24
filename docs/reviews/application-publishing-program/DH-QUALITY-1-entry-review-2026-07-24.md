# DH-QUALITY-1 Entry 独立六维复审（2026-07-24）

## 结论

- Gate：`PG-DH-D`
- 结论：`entry_passed_with_boundary`
- P0：0
- P1：0
- 实质性 P2：0
- 下一唯一 Stage：`DH-QUALITY-1-IMPLEMENTATION`
- 审查线程：`/root/dh_dual_entry_reviewer`
- 审查方式：只读；未修改业务代码，未调用 Provider、LLM、TTS、FFmpeg、浏览器或平台。

本 Entry 已把内容来源、字段所有权、封面/字幕规则、Artifact 接收条件、失败矩阵和回滚边界冻结，可进入质量业务实现。该结论不等价于真实媒体生成、字幕视觉质量或平台发布通过。

## 六维验证

| 维度 | 结论 | 验证依据 |
| --- | --- | --- |
| 需求完整性 | 通过 | 自定义口播、已有文案 Artifact、上游生成文案和标题+完整文案四个 canonical mode 已与 DH-DUAL V2 对齐；旧草案 mode 仅允许在边界归一化；`spoken_script`、发布标题/描述、封面标题、话题、字幕 preset 的来源与 payload 路径已冻结；title-only、跨项目绑定、封面长度和完整 Artifact 要求均有契约。 |
| 逻辑正确性 | 通过 | `content_source.script` 或固定 Artifact variant 生成 `spoken_script`；来源版本在 Run 创建时固定；标题不能替代脚本；delivery 字段类型/默认值明确；新 Run 使用 `readable_v2`，旧 Run 无 preset 保留原渲染语义；accept 只接收完整结果且不发布。 |
| 边界情况 | 有界通过 | 失败矩阵覆盖隐式脚本改写、来源缺失、title-only、跨项目、封面超长/非法 fallback、字幕 preset 缺失、旧 Run 样式漂移和缺流/无字幕 Artifact。真实字幕抽帧、封面溢出、媒体编解码/时长和 Provider 失败重试留给后续实现/质量证据 Stage。 |
| 代码质量 | 通过 | 本 Entry 仅修改 contract、fixture、Entry 测试与证据文档；目标测试 Ruff check/format、JSON parse 和 `git diff --check` 均通过。 |
| 测试覆盖 | 通过 | 定向 quality Entry：8 项（质量 4 + DH-DUAL Entry 4）；六文件应用中心 Entry 回归：26 passed、12 个既有 Pydantic deprecation warnings，其中既有 V2 fixture 覆盖 `generated_marketing_copy`；AC-5 API/Adapter/Artifact 回归：47 passed；quality fixture 覆盖 11 项（5 valid/6 invalid），失败矩阵 9 项。 |
| 实际运行结果 | 通过且有边界 | Entry 证据明确 provider/LLM/TTS/browser/platform/upload/final click/default flags/business code 均为 0/false；JSON、Ruff、diff 检查复跑通过。没有在本 Entry 伪造或生成真实媒体；真实 TTS→数字人→后期、字幕/封面视觉和 Artifact 文件证据后置，最终发布继续人工确认。 |

## 复验命令与结果

```text
uv run pytest -q tests/digital_human_quality_entry_contract_test.py tests/digital_human_dual_mode_entry_contract_test.py
8 passed

uv run pytest -q tests/digital_human_quality_entry_contract_test.py tests/digital_human_dual_mode_entry_contract_test.py tests/app_center_ip_broadcast_entry_contract_test.py tests/app_center_ip_broadcast_desktop_entry_contract_test.py tests/app_center_ip_broadcast_handoff_entry_contract_test.py tests/app_center_registry_test.py
26 passed, 12 warnings

uv run pytest -q tests/app_center_ip_broadcast_api_test.py tests/app_center_ip_broadcast_adapter_test.py tests/app_center_ip_broadcast_artifact_test.py
47 passed, 12 warnings

uv run ruff check tests/digital_human_quality_entry_contract_test.py
uv run ruff format --check tests/digital_human_quality_entry_contract_test.py
passed

python3 -m json.tool <contract/fixture/QA JSON>
passed

git diff --check
passed
```

## 证据索引

- Entry：[`DH-QUALITY-1-entry-2026-07-24.md`](DH-QUALITY-1-entry-2026-07-24.md)
- QA：[`qa/DH-QUALITY-1-entry-2026-07-24.json`](qa/DH-QUALITY-1-entry-2026-07-24.json)
- Contract：[`digital-human-quality-entry.contract.json`](../../contracts/app-center/digital-human-quality-entry.contract.json)
- Fixture：[`digital-human-quality-entry-fixtures.json`](../../contracts/app-center/fixtures/digital-human-quality-entry-fixtures.json)
- 上游 canonical V2：[`digital-human-video-input-v2.contract.json`](../../contracts/app-center/digital-human-video-input-v2.contract.json)

## 后续边界

进入 `DH-QUALITY-1-IMPLEMENTATION` 后，必须把 canonical mode 与 alias 的边界归一化、上述 payload 映射和失败码落实到服务端/桌面实现，并补充真实运行测试；不得在媒体 adapter 内复制 LLM，不得把 `goal` 隐式改成脚本。随后才能进入 `DH-QUALITY-2`，按一次有目的的 TTS→RunningHub→后期调用采集视频、封面、字幕和 Artifact 证据。最终发布自动点击仍保持关闭。
