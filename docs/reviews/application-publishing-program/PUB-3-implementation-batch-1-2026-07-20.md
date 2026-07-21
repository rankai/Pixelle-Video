# PUB-DOUYIN / PUB-3 Adapter Implementation Batch 1

状态：`implementation_pass_with_boundary`

## 本批交付

- `DouyinPublisher` 绑定 `douyin-entry@1`，先做 package platform 校验，拒绝跨平台 package 在浏览器启动前进入执行。
- 状态机：上传入口 → `upload_video` → `wait_for_state(editor_ready)` → 视频 readback → 标题/简介/话题/封面逐项写入与语义回读；已在 `editor_ready` 时不重复上传。
- 状态安全停手：`signed_out`、captcha、unknown、network、window_closed、cover_error；uploading/processing 保留运行态；waiting-human/cover-modal 保留人工停点。
- `PlaywrightPublishContext` 增加语义状态探针、页面 fingerprint、动作 Guard、状态轮询、字段 readback；抖音 Guard 只在 `platform == douyin` 生效，其他平台保留旧 runtime 路径。
- FinalActionGuard：允许动作仅为上传、标题、简介、话题、封面；没有 publish/submit/confirm API；`request_final_action` 永远拒绝自动最终动作。
- legacy `PublishResult` 保留旧 `status`，新增 `adapter_state` 传递 `waiting_for_login`、`waiting_for_human`、`needs_attention`、`running` 等 Run 语义，后续 PUB-4/PUB-5 负责接入 PublishRun 状态。

## 验证命令与结果

```text
uv run pytest -q tests/publish_*_test.py tests/publish_douyin_entry_contract_test.py \
  tests/publish_douyin_adapter_test.py tests/coord0_contract_test.py tests/app_center_core_test.py
109 passed, 12 existing Pydantic deprecation warnings

uv run ruff check pixelle_video/services/publish api/desktop_security.py \
  api/routers/publish_v2.py api/schemas/publish_v2.py api/tasks/models.py \
  tests/publish_*_test.py tests/coord0_contract_test.py
All checks passed

git diff --check
passed
```

## 独立审查

独立线程 `/root/pg_a_closure_reviewer_v3` 六维复验：`P0=0`、`P1=0`，结论 `implementation_pass_with_boundary`。复验覆盖跨平台早拒、上传后 editor_ready 转换、editor_ready 不重复上传、中途窗口/挑战/未知状态、字段回读、fingerprint/Guard、非抖音兼容和无真实浏览器边界。

## 不得误报的边界

- 本批只验证本地 fixture 和模拟 runtime，不代表 PG-G 或真实抖音可用。
- 真实 selector、页面语义回读、登录/挑战、codec/duration/platform capability、live 上传、最终人工发布尚未验证；真实扫码、第三方授权、真实上传和最终发布仍需暂停通知用户。
- `adapter_state` 尚未接入 PublishRun 的真实平台执行状态；该集成后置 PUB-4/PUB-5。
