# 应用工作台轻量化重构：Design QA

日期：2026-07-29
验收范围：门店营销文案、爆款标题、抖音图文、数字人口播视频

## 设计目标

面向没有内容运营和技术经验的中小门店老板，将工作页统一为：

1. 选择项目；
2. 点选少量本次必要选项；
3. 始终可见的主生成按钮；
4. 以内容为主的结果区；
5. 下载、交付按业务优先级呈现，历史生成统一留在“任务记录”。

保留 Pixelle 现有颜色、字体、圆角、按钮与状态 token，不复制参考产品的品牌视觉。

## 对比依据

- 参考页面：
  - `/var/folders/lt/6g5zql0d37g7pvzj7gny8g4r0000gn/T/codex-clipboard-7a27c9e9-73c8-4b4b-9423-c2b49b9dd884.png`
  - `/var/folders/lt/6g5zql0d37g7pvzj7gny8g4r0000gn/T/codex-clipboard-21119188-4cf4-4dfd-8fad-7488f372b640.png`
- 重构前：`/tmp/pixelle-app-workbench-light-audit/01-current-douyin-carousel.png`
- 重构后桌面：
  - `/tmp/pixelle-app-workbench-owner-audit/marketing-copy-final-3.png`
  - `/tmp/pixelle-app-workbench-owner-audit/viral-titles-final.png`
  - `/tmp/pixelle-app-workbench-owner-audit/douyin-carousel-final-2.png`
  - `/tmp/pixelle-app-workbench-owner-audit/digital-human-video-final.png`
- 重构后窄屏：
  - `/tmp/pixelle-app-workbench-light-audit/08-responsive-marketing-copy.png`
  - `/tmp/pixelle-app-workbench-light-audit/09-responsive-marketing-result.png`

参考图和实现截图已在同一次视觉比较中检查。

## 迭代记录

### 第一轮发现

- 项目资料、项目目标、版本和交付动作全部展开，首屏认知负担过高。
- `INPUT / OUTPUT`、Artifact、Run、revision、V2 等词汇以技术模型而不是老板任务组织。
- 右侧按钮无优先级，下载、复制、版本和应用交接挤在同一行。
- 项目资料使用多层 Card 和边框，左侧比参考页面明显更重。
- 生成按钮在长表单底部，用户进入页面后看不到完成任务的主动作。

### 修复

- 选择项目成为所有应用的统一轻入口；“我的项目”下提供切换、编辑当前项目和新建项目。
- 正式应用工作台不再提供“保存项目 / 归档项目”等生命周期操作；新项目从“我的项目”弹窗创建，归档留给未来统一项目管理入口。
- 项目信息完整时不再重复展示资料卡；缺失时才就地提示补充，编辑入口收进“我的项目”。
- 去除工作台 `INPUT / OUTPUT` 和英文应用代号，统一为中文任务名称。
- 项目卖点自动带入为轻标签，营销利益点使用一键点选标签；风格样例默认只展示 4 个。
- 爆款标题只展示“已有文案 / 写个主题 / 粘贴内容”，抖音图文只展示“本次使用哪段内容”，不出现文案产物、固定内容版本和来源版本。
- 结果动作改为一个主动作和一个“更多”入口；工作台只显示本次最新结果，历史生成去“任务记录”查看。
- 缺失事实和发布风险改为中性、默认收起的完善建议。
- 左右区域独立滚动；桌面端主生成按钮固定在左栏底部。
- 数字人的发布字段、运行编号和维护操作移入“更多设置 / 运行记录”。
- 窄屏使用“创作配置 / 生成结果”双页签，不把两栏压成窄列。
- 图文结果卡去除内部横向滚动，历史图片仅显示业务名称，不暴露 `asset:` 引用。
- Workbench V2 去除“结果版本 / 版本与记录 / 查看版本”等内部追溯控件；后台仍固定真实版本，保证重启恢复和交接一致性。
- 历史无名项目不再泄露 `project_...` 内部 ID，统一显示为带日期的“未命名项目”。
- 标题与文案候选卡统一占满结果栏可用宽度，不再挤在左侧留下大面积空白。

## 最终检查

| 检查项 | 结果 | 依据 |
| --- | --- | --- |
| 信息层级 | 通过 | 首屏只保留项目、本次输入和主动作 |
| 主题一致性 | 通过 | 继续使用现有 app token、Ant Design 组件和侧边栏体系 |
| 操作优先级 | 通过 | 每页一个持续可见的主生成动作；右侧主交付动作与“更多”分离 |
| 技术信息下沉 | 通过 | 正常页面不显示 Artifact、固定内容版本、结果版本、运行编号；后台仍保留追溯关系 |
| 四应用一致性 | 通过 | 文案、标题、图文和数字人使用同一左右工作台结构 |
| 窄屏可用性 | 通过 | 输入与结果页签可切换，内容不横向溢出 |
| 真实数据与功能 | 通过 | 未替换后端调用、项目快照、Artifact、交付与发布逻辑 |
| 核心点选交互 | 通过 | “我的项目”菜单、标题内容来源页签、图文更多配置、数字人图片/视频模式均在真实浏览器中完成切换验证 |
| 自动化验证 | 通过 | Desktop 17 files / 107 tests 全部通过；应用工作台/数字人后端定向 46 tests 通过；TypeScript / Vite production build 通过；`git diff --check` 通过 |

## 剩余非阻塞项

- Ant Design `List`、`Alert.message`、`Input.addonAfter` 有上游弃用警告，但不影响本次交互与视觉结果。
- 外部商品链接自动解析不属于本轮已有能力；当前轻量入口对应 Pixelle 的“选择项目”，不在界面伪造解析成功。

Final result: **passed**
