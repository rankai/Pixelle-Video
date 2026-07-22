# COORD-0 FinalActionGuard evidence

这是静态 contract/fixture 证据，不是业务实现。`final-action-guard.matrix.json` 默认 deny，允许动作必须有 page fingerprint，发布/确认发布/未知/坐标动作均拒绝并进入 `waiting_for_human`。

验证：`uv run pytest -q tests/coord0_contract_test.py -k 'guard or projection'`。

