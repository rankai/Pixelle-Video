# APP-WORKBENCH-4 Entry：抖音图文

## Entry 结论

`PG-AW-E_entry=passed_with_boundary`，允许进入本阶段业务实现。

## 复用事实

本阶段不新建第二套图文领域模型，直接复用 AC-4 已通过的：

- `carousel_plan`、`carousel_page`、`carousel_package` Artifact；
- 固定 3:4、3/5/8 页规则；
- 已登记 asset refs 与受信路径 resolver；
- 本地 PNG renderer、ZIP、页序与 SHA；
- 单页 retry 追加 ArtifactVersion 并使旧发布包失效；
- `carousel_package` 到 PublishPackage V2 handoff；
- 页面失败、缺图、缺字体和文本溢出错误码。

## 冻结输入

- 项目与 ContextSnapshot v2；
- 内容来源及固定 `artifact_version_id`；
- 封面钩子、图文目标、发布文案偏好；
- 图片资产及精确 revision；
- 风格、页数与 template；
- 品牌色、必须使用图片、CTA 等更多配置；
- 恢复时只读取本项目最近一次图文 v2 Run，不跨项目或热更新来源。

## 冻结结果

- 计划阶段：按页展示角色、标题、正文、CTA 和绑定资产；
- 渲染阶段：缩略图导航、竖版页面预览、当前页错误；
- 编辑文本或替换图片只重渲染受影响页；
- 单页失败只重试该页；
- 保存后追加 ArtifactVersion，不覆盖旧页面或旧 package；
- 下载支持图片组/ZIP/发布文案；
- 交给发布中心固定当前 `carousel_package` 版本，重复点击幂等；
- handoff 只进入发布中心，不打开抖音创作者平台。

## 允许修改

- 抖音图文 workbench 输入和结果组件；
- 图文 input v2 的最小 validator/normalizer；
- 既有 carousel retry/edit/package API 的缺口接线；
- 必要 ArtifactVersion/PublishPackage handoff；
- 对应 tests、fixture、视觉和运行证据。

## 明确禁止

- 不重写已通过的 AC-4 renderer；
- 不引入 AI 生图、外部商品解析或第二模型配置源；
- 不提前修改数字人工作台；
- 不打开发布平台，不执行上传，不点击最终发布；
- 不覆盖旧 Run、ArtifactVersion、PNG、ZIP 或 PublishPackage。

## Gate 验收

- 来源版本与资产 revision 在刷新/重启后恢复；
- 3/5/8 页计划、PNG、ZIP、页序、发布文案和 Artifact 完整；
- 文本或图片局部变更只产生受影响页的新版本；
- 单页失败可见且可单独重试；
- 缺图、缺字体、文本溢出显示用户可理解的原因；
- handoff 到发布中心固定正确 package 且重复点击幂等；
- 桌面左右工作台和窄屏配置/结果 Tab 可用；
- 自动化、build、视觉对照和六维自审 P0/P1=0；
- 发布平台动作和最终发布点击均为 0。

## 回滚

- 抖音图文工作台 v2 flag 关闭时回到既有图文 UI；
- 运行中任务不取消；
- 既有 plan/page/package、PNG、ZIP 和 handoff 继续可读；
- 不删除本地资产或历史版本；
- PG-L 外部边界不变。
