# ADR-PublishAccountProfile

- 状态：accepted for COORD-0
- 决策：账号以 `account_id + platform + profile_ref` 建模，profile_ref 只指向本机受保护目录；凭证、cookie、token 不进入 API 响应、manifest、task、run 或日志。
- 初始发布状态：仅抖音 pilot 可进入后续验证，其余平台 `unverified`，COORD-0 不修改旧 UI 的 available 文案。
- 回滚：停用 account/run，不清 profile 内容；凭证恢复由用户重新登录完成。
