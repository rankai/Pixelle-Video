# AC-5 数字人口播应用化 implementation batch 7 Entry 独立六维复审（2026-07-20）

状态：`entry_passed_with_boundary`

评审人：独立严格审查线程 `/root/pg_a_closure_reviewer_v3`（只读审查，未修改代码）。

## 评审范围

- [`AC-5-implementation-batch-7-entry-2026-07-20.md`](AC-5-implementation-batch-7-entry-2026-07-20.md)
- [`ip-broadcast-desktop-entry.contract.json`](../../contracts/app-center/ip-broadcast-desktop-entry.contract.json)
- [`ip-broadcast-desktop-entry-fixtures.json`](../../contracts/app-center/fixtures/ip-broadcast-desktop-entry-fixtures.json)
- [`tests/app_center_ip_broadcast_desktop_entry_contract_test.py`](../../../tests/app_center_ip_broadcast_desktop_entry_contract_test.py)

## 六维结论

1. **需求完整性：通过。** 双 flag 门控（backend flag → Registry manifest.enabled 映射已显式）、旧 `/ip` 保留、新 `/apps/digital-human-video` 不 alias、blank/copywriting/selected_title 三来源、安全响应投影、重启恢复和 local gray 边界均已冻结。
2. **逻辑正确性：通过。** flag/readiness 门控、来源 project 所属与 source revision pin、waiting 非终态、显式 accept 和重启不重复创建/执行规则相互一致。
3. **边界情况：通过。** flag-off、backend-off/not-ready、缺 variant、跨项目来源、final publish blocked、零 provider/platform side effect 均有 fixture；旧入口和本地持久化命名空间隔离明确。
4. **代码/文档质量：通过。** JSON 可解析，契约断言明确；Entry 阶段没有桌面业务代码、provider、浏览器、平台或事实源修改；Ruff 与 `git diff --check` clean。
5. **测试覆盖：通过（Entry 有界）。** 3 个契约测试覆盖路由/双 flag/Registry 映射、三来源、错误/等待状态、重启复用、本地灰度证据字段和最终发布阻断。
6. **实际运行结果：通过（Entry 级）。** `uv run pytest -q tests/app_center_ip_broadcast_desktop_entry_contract_test.py` = **3 passed**；未触发业务 API、真实 provider、浏览器或平台动作。

## 问题清单

- P0：0。
- P1：0。
- P2/实现阶段边界：桌面新路由真实实现、运行时 API/重启 E2E、本地 gray-cycle 录像/DOM SHA 生成和连续生产灰度仍后置；exactly-one/source revision/context snapshot 的更细运行时负例可在 implementation 增补，不阻塞 Entry。

## 放行与禁止

`APP-IPB/AC-5 implementation batch 7 Entry` 以 `entry_passed_with_boundary` 放行进入 batch7 implementation。实现仍只能使用隔离 local executor/fixture；不得打开真实 provider、Playwright/浏览器、抖音授权/上传/最终发布，不得关闭旧 `/ip` 入口或改变 PublishRun/PublishPackage/模型配置事实源。
