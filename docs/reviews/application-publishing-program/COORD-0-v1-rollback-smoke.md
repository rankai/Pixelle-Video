# COORD-0 V1 rollback smoke design/evidence

这是不触碰平台的本地状态 contract smoke：创建 V2 package/run fixture → 关闭 V2 flag → 保留 profile 与 package/run 历史 → 走 V1 素材复制 fallback → 再开启 V2 只读历史；预期无重复上传、无 production write、无 profile/cookie 删除。结果 fixture 见 `docs/contracts/publishing/fixtures/v1-rollback-smoke.json`。

验证命令：`uv run pytest -q tests/coord0_contract_test.py -k rollback`。真实平台窗口和用户登录属于 PUB-1/PUB-2 的人工门禁，不在 COORD-0 伪造通过。

