# DH-QUALITY-2 工作流 A/B 与媒体质量 Entry（2026-07-24）

## 状态

entry_passed_with_boundary。只冻结一次性 Provider 计划、固定输入、质量维度、证据格式和失败矩阵；本 Entry 没有调用真实 Provider、TTS、浏览器、平台或最终发布。

## 冻结内容

- 图片 stable 只允许一次；图片候选只有记录明确 A/B 理由后才允许各一次；视频 natural 只允许一次。
- 图片/视频共用同一份 8–12 秒门店营销口播、同一 TTS 音频、同一人物语义、同一模板和 readable_v2 preset。
- 每次 Provider 调用必须记录 task id、创建次数、输入 revision、原始视频、ffprobe、字幕文件、抽帧、最终 Artifact；没有证据不得解释为质量通过。
- Provider 失败不得无分析重试；若确需重试，先记录根因、唯一重试计划和重复任务防护。
- PG-DH-E 需要 video、cover、publish_copy、spoken_script 四类 Artifact；final_video 必须 1080×1920、H.264/AAC、字幕已烧录、时长误差在 0.5 秒或 2% 内。
- 本 Entry 与后续 live smoke 均保持 platform_actions=0、final_publish_clicked=false；最终人工发布不属于本批。

## 验证

- quality2 Entry contract：4 passed。
- contract/fixture JSON parse、Ruff、format、git diff check：通过。

## 边界

- 本 Entry 不等价真实图片/视频质量通过；真实 Provider 仍需按固定计划执行并保存视觉证据。
- 任何真实扫码、授权、余额、Provider 状态或最终发布动作遇到不确定性都暂停，不连续重试。
- 独立六维复审按用户要求延后到 Program 完成。
