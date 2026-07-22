# ADR-004：VoiceProfile 作为音频 revision 的领域资源

- 状态：Accepted（UX-A 证据复审通过，可进入 UX-1）
- 日期：2026-07-18
- 范围：音色库、普通音频/BGM、配音选择、旧 voice reference 迁移

## 背景

V2 当前可以把 audio media 投影成 voice。这样普通 BGM 会混入音色 facet，且生产引用缺少明确的领域身份。本 ADR 把音色定义为引用不可变 audio revision 的 `VoiceProfile`，而不是另一份文件。

## 决策

VoiceProfile 字段固定为：

| 字段 | 语义 |
| --- | --- |
| `voice_id` | 稳定领域资源 ID；迁移时保持旧 `reference_id` |
| `audio_asset_id` | 指向媒体资产 |
| `audio_revision_id` | 必须指向该 audio asset 的存在 revision |
| `legacy_reference_id` | 可选旧映射，便于对账和回滚 |
| `language/style/authorization_status` | 领域展示与生产约束 |

Schema：`docs/schemas/voice-profile.schema.json`；fixture：`tests/fixtures/ux0/voice-migration/`。

普通 BGM 仍是 `audio`，只出现在音频/BGM列表，不创建 VoiceProfile，不计入 voice facet。同一 audio revision 可以被 BGM 或 voice 引用，但名称、授权、归档状态和 usage 互不冒充。

## 迁移与生产解析

迁移先读取旧 `voice_references.json`，由稳定旧 ID 生成 `VoiceProfile.voice_id`，并解析对应的 `media-audio-*` asset 与 `revision-audio-*-1`。生产 session 仍使用旧 ID 读取 mapping；新选择器必须从服务端重新读取 VoiceProfile，禁止前端临时构造 `kind: voice`。

`scripts/voice_profile_migration_dry_run.py` 只读生成候选 profile、文件 SHA、普通 BGM 排除清单和 session 引用对账。dry-run 的 `writes_performed` 必须为 0，旧引用解析率必须为 100%。

## 回滚

VoiceProfile 投影为 additive migration。回滚先关闭 profile 投影/领域接口，再恢复 manifest backup；不删除 audio revision 或原文件。`docs/migrations/voice-profile-dry-run-2026-07-18.json` 记录本次 fixture dry-run 结果和 rollback plan。
