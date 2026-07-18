# UX-E 目标用户、发布设备与灰度签署模板

- 日期：2026-07-18
- 状态：`pending_external_evidence`
- 对象：`2026-07-18-asset-center-v2-smb-usability-implementation-plan.md`
- 数据模板：`docs/migrations/asset-center-uxe-release-evidence-template-2026-07-18.json`

本模板只定义证据格式，不填充虚构的用户、设备、录像或 glyph 结果。只有固定 release 桌面、固定 1000 条数据、五位目标用户和真实灰度观察结果均填入后，才能把 `status` 改为 `pass`。

必须满足：

- 至少 2 位门店老板、2 位店长/运营、1 位熟练视频运营；每位记录独立完成结果、成功率、中位数、P95、任务明细和录像路径；
- 固定 release app version、commit、窗口、主题、本地服务 revision 和数据集 SHA；
- 记录真实 MP4 抽帧的 glyph mask IoU，最低值不低于 `0.98`；当前本地 contract-box gate 的 `layout_mask_iou=1.0` 不能替代此字段；
- 灰度开启、观察窗口、成功率、回退演练和旧 V2 健康状态均有证据；
- 在上述证据完成前，`default_rollout_authorized` 必须保持 `false`。
