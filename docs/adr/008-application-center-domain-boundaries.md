# ADR-008 应用中心领域边界

- 状态：accepted for COORD-0
- 决策：App Registry 只持有 manifest；ContentProject 持有上下文；Artifact/ArtifactVersion 持有可编辑创作事实；AppRun 持有一次应用执行事实；Generic Task 只做进度投影。
- 禁止：Task 代替 Project/Run、Asset 代替 Artifact、应用中心创建第二份 PublishPackage。
- 交接：应用中心输出 `publish_package_ref`，发布域在创建 V2 package 时生成 immutable snapshot。
- 回滚：关闭 app-center flags；保留事实表和版本，不删除旧口播/旧任务。
