# ADR-PlatformAdapterEvidence

- 状态：accepted for COORD-0
- 决策：每个平台 adapter 必须登记平台、版本、页面指纹、动作边界、证据类型和降级状态；没有 DOM/截图回读证据不得标记成功。
- COORD-0 只交付 contract/fixture；不改 selector、不新增真实自动化、不把任何旧平台标成 available。
- adapter 异常进入 `needs_attention` 或 `waiting_for_human`，FinalActionGuard 在最终发布按钮前停止。
- 回滚：平台级 flag 关闭，V1 素材复制/下载路径继续可用。
