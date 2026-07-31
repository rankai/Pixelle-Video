# APP-BIZ-4 数字人视频/口播改造复验记录

日期：2026-07-31

## 结论

第二轮独立严格只读复验：**PASS**。

首轮审查发现的 P1 问题已完成修复并由同一审查线程复验：

- 空或全空白最终口播稿会阻断 AppRun 创建，并保留用户编辑内容；
- 来源版本、复制版本异步变化会清除旧的口播稿准备态；
- `context_snapshot_id` 从准备请求传递到服务端并完成快照绑定校验；
- 数字人名称、声音名称由服务端规范化输入固定保存，结果面板和历史卡展示；
- 历史视频卡提供卡片级下载入口。

## 六维验证依据

1. 需求完整性：项目/来源内容 → 可见可编辑最终口播稿 → 选择数字人 → 默认或覆盖声音 → 生成 → 播放、下载、发布交接闭环；失败保留输入，诊断信息不进入普通结果展示。
2. 逻辑正确性：用户确认口播稿后才创建 AppRun；用户编辑稿进入最终不可变输入；原始来源 artifact/version 绑定保留；幂等 pending、恢复和 context snapshot 约束保持有效。
3. 边界情况：空稿、超长稿、来源版本缺失或归档、未知模板、不完整来源、非 v2、图片/视频模式切换、默认/覆盖声音、重复提交、provider envelope、失败恢复均通过测试。
4. 代码质量：继续复用既有媒体、字幕、后期和发布权威；`prepare-script` 只做准备，不创建 AppRun；`execute_local` 与受信媒体导入路径明确隔离；Ruff、compileall、JSON 契约和 `git diff --check` 通过。
5. 测试覆盖：数字人/历史定向前端 34 passed；后端独立定向复验 125 passed；前端全量 153 passed；构建通过。
6. 实际运行：UI/API HTTP 200，数字人应用 enabled/ready；`image_talking` 与 `video_lipsync` 均完成 `needs_review → completed`，产物包含 `cover / publish_copy / video`。

## 真实媒体证据

命令：

```text
uv run python /tmp/pixelle_app4_media_evidence.py
```

受信路径导入仓库中已存在的真实 MP4/PNG，独立 `ffprobe` 结果：H.264 + AAC、1080×1920、音视频流完整、时长 5.291667 秒。

- video SHA-256：`d5ff6533de96e392a009907f3d03023566c8fa635824e1b27de7260e63973aa4`
- cover SHA-256：`e11373ca5bdeced21a6c5582a67f93122d387489baa3fb20bd5609c064685a02`

未调用付费 provider，未执行外部平台发布；该证据验证真实文件的可读性、受信导入、Artifact 注册、人工确认与完成态闭环，不等同于再次调用付费 provider。

## 非阻塞限制

- 开发服务器未加载 `.env.production` 时会按项目约定回退旧工作台；生产配置和 production build 已开启并验证应用中心路由。
- `data/app_center.sqlite` 的历史 registry seed drift 属于既有环境/数据迁移问题，不是本次数字人业务逻辑阻断项；清洁数据库和当前一致 registry rows 可正常验证。
