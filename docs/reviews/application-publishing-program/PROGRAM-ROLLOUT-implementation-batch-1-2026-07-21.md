# PROGRAM-ROLLOUT implementation batch 1：flag 事实源与安全别名（2026-07-21）

状态：`implementation_pass_with_boundary`；本批只落地 flag 解析/别名归一化和回归测试，不开启正式灰度，不修改平台 release state。

## 实现

- 新增 `desktop/src/flagResolver.ts`，统一前端 canonical flags：应用中心、内容应用、图文、数字人口播、发布 V2、资产 V2；
- `VITE_DIGITAL_HUMAN_IN_APP_CENTER` 和规划遗留名 `VITE_PUBLISH_V2_ENABLED` 只能在 canonical 缺失时归一化；canonical/alias 冲突或未知值 fail-closed；
- `desktop/src/featureFlags.ts` 只消费 resolver，不再散落解析环境变量；
- 更新既有 desktop build contract test，使其验证 resolver 行为而非脆弱源码字符串；
- 所有后端 `PIXELLE_*` canonical env 与前端 `VITE_*` 映射仍以 Entry contract 为事实源；未新增第二模型配置源或管理后台。
- P1 修复：缺失值才使用 fallback；存在但非字符串、未知字符串或 canonical/alias 冲突均返回 false，防止 true-default flag 被错误开启。
- P1 边界补强：通过 presence-aware 读取区分缺失 key 与 `undefined`；显式 `undefined` 也 fail-closed。

## 定向验证

- `npm test -- --run`：9 files / 51 tests passed（P1 修复后）；
- `npm run build`：通过；保留既有 bundle size warning，不阻塞本批；
- `uv run pytest -q tests/desktop_build_config_test.py tests/app_center_registry_test.py`：20 passed，12 个既有 Pydantic warnings；
- `uv run pytest -q tests/program_rollout_entry_contract_test.py`：2 passed；
- Ruff、JSON parse、`git diff --check`：通过。

## 边界与未完成项

- 本批没有开启 `publishCenterV2`、数字人口播、抖音灰度或任何其他平台；正式默认 rollout 仍由 PG-L 条件控制；
- macOS/Windows 打包、10×重启/10×run soak、真实性能采样、诊断导出脱敏、双向回滚和稳定观察窗口留在后续 implementation batches；
- 不执行扫码、第三方授权、最终发布或破坏性 profile/session 清理。

## 下一入口

独立六维 implementation 复审已通过（P0/P1=0）；进入 rollout batch 2（诊断/telemetry/privacy 与 rollback smoke），不得把本批误记为 PG-L 或正式放开。
