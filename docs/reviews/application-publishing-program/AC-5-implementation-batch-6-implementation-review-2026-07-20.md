# AC-5 数字人口播 implementation batch 6 独立六维复审（2026-07-20）

## 复审范围

- `PublishPackageService` canonical fingerprint、legacy/artifact source convergence、publish_copy 解析、
  package/ref 自动失效与 stale replay；`PublishCoreRepository` identity replay；Publish V2 API omission；
  AC-5 adapter/Artifact handoff 回归。
- 排除真实 provider、浏览器、抖音授权/上传/最终发布、桌面灰度和管理员控制面。
- 审查线程：`/root/pg_a_closure_reviewer_v3`，不修改业务代码。

## 六维验证

| 维度 | 结论 | 证据 |
| --- | --- | --- |
| 需求完整性 | 通过 | canonical identity、legacy-first、三来源/文案、package/ref 幂等与失效、stale replay、API omission 均覆盖 |
| 逻辑正确性 | 通过 | 70 项定向通过；版本 map、source map 相等且 fingerprint 变化、stale guard 有回归；API omission E2E 通过 |
| 边界情况 | 通过 | 同版本不同封面不互相失效；legacy package/ref 可被后续 artifact 版本正确失效；空/重复/mismatch copy fail-closed |
| 代码质量 | 通过 | Ruff clean；`git diff --check` clean；复用现有 PublishPackage/CoreRepository 事实源 |
| 测试覆盖 | 通过（有界） | 定向 70 passed/12 warnings；独立线程旧快照 67 passed/12 warnings；覆盖新增 API E2E |
| 实际运行结果 | 通过（本地/隔离） | Repository、TestClient、legacy-first、stale replay、ref 状态实跑通过；无 provider/browser/platform side effect |

## 已修复 P1

1. 未解析 publish_copy artifact；现按唯一版本解析并校验空/重复/类型/mismatch。
2. 不传 supersedes 时新版本未自动失效旧 package/ref；现按 artifact/version map 自动失效。
3. stale replay 会误伤新 package；命中已失效 package 立即 `PUBLISH_PACKAGE_STALE`。
4. source artifact ID 交集误伤同版本不同封面；现要求版本变化或完整 source map 相同且 canonical fingerprint 变化。
5. legacy-first package source kind 导致旧 ref 不失效；现从 ref source version IDs 解析 legacy package map。
6. Publish V2 optional `platform_copy` omitted 时 router 传空对象；现按 `model_fields_set` 传 `None`，从 artifact copy handoff。

## 结论

最新代码证据满足 `implementation_pass_with_boundary`，P0/P1=0；审查线程最终确认最新 optional-copy 快照，
正式关闭 batch 6。保留 P2/边界：跨进程 CAS/sidecar 多 worker、真实 provider/browser/platform、桌面入口
灰度和真实发布周期，不把本批误报为 PG-I/PG-J/PG-K 完成。
