# PG-H 图文产物可交接 Gate 关闭复审（2026-07-20）

状态：`passed_with_boundary`

评审人：独立严格审查线程 `/root/pg_a_closure_reviewer_v3`（只读审查，未修改代码）。

## 六维结论

1. 需求完整性：3/5/8 页 PNG/ZIP 导出、图文→PublishPackage V2→`publish_package_ref`→发布中心 queued Run、本地人工停手、retry 失效/补偿和 Publish V2 关闭时下载/复制均有实现与证据。
2. 逻辑正确性：来源 ArtifactVersion 固定；视频/图文媒体形态互斥；单页 retry 产生新版本并使旧 PublishPackage 与旧 ref 失效；失败路径回滚新 ArtifactVersion 并补偿新包。
3. 边界情况：页数、页码、尺寸、文案、资产、字体、路径越权、混合媒体、LLM 结构化输出、flag-off 和下载根目录均 fail-closed；桌面端只复制可信产物内容。
4. 代码质量：继续复用 FastAPI、SQLite、既有 AppRunner/PublishPackage/LLM 事实源；未引入第二模型源、第二浏览器运行时或任何真实平台动作。
5. 测试覆盖：定向 carousel **32 passed**；后端 app-center/publish/coordination 聚合 **176 passed**；前端 **5 files/24 tests**；build、Ruff、`git diff --check` 均通过。覆盖 trusted-source 发布文案映射、旧 package/ref 失效 reason、失败补偿和 flag-off 下载。
6. 实际运行结果：本地平台中立 E2E 从标题来源经 AppRunner/假 LLM/renderer 生成 `carousel_package`，构建 PublishPackage V2 并创建 queued PublishRun，`human_confirmation_required=true` 且未确认；桌面端可下载 ZIP、复制非空来源派生发布文案。

## 独立审查问题闭环

- P0：0。
- P1：0。审查发现桌面端正常 payload 未携带 title/description/hashtags 导致发布文案为空；已修复为从同项目 `selected_title`/`title_set`/`copywriting` 可信 ArtifactVersion 派生，显式 payload 优先，并补真实生成形状/clipboard 断言。
- P2：并发 retry 输出路径冲突、失败渲染文件 orphan 清理、JSON Schema 同类 media ref cardinality、真实旧文件集成断言；source provenance 仍通过 package 内容可追溯，未扩展 PublishPackage 来源模型。

## Gate 边界与暂停点

- 本 Gate 只关闭 AC-4/PG-H，不代表真实抖音扫码、第三方授权、真实上传、字段回读、封面/描述/话题 live smoke 或最终人工发布已完成。
- 不把本地 FakeLLM/renderer、PublishRun queued/human-stop 解释为平台发布成功。
- 以上真实外部动作仍需在对应 PUB Stage 及人工暂停点单独取得证据。

## 放行结论

`APP-CAROUSEL/PG-H` 正式以 `passed_with_boundary` 关闭，允许协调队列进入下一 Stage 的 Entry；不允许跳过 AC-5 Entry 或直接进入数字人口播业务实现。
