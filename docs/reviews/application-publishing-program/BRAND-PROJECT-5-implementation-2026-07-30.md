# BRAND-PROJECT-5 受控启用、回滚与收口实施证据

日期：2026-07-30
Stage：`BRAND-PROJECT-5`
Gate：`PG-BP-F_implementation_review_pending`

## 1. 实施结论

Stage5 已完成隔离环境内的默认关闭核验、on→off→on 双向回滚、真实旧数据库副本
迁移、显式同步后继续运行、10 次 sidecar 轻重启、读路径性能采样和完整回归，当前
停在最终独立六维复审入口：

- `brandProjectBoundaryV1` 的后端默认、契约默认和前端 fallback 仍为 `false`，
  `desktop/.env.production` 没有生产 override；
- flag on 时显示轻量“项目与品牌资料”，flag off 完整重启后回到旧创作配置，但
  v3 项目名称和历史结果仍可读且非空；再次 on 完整重启后恢复轻量品牌项目 UI；
- on→off→on-again 三个 checkpoint 的 6 张业务表行数、逐表哈希和聚合业务哈希
  完全相同，回滚读取没有静默写入；
- 真实历史 AppCenter SQLite 只读源的迁移在临时副本上通过，旧列投影逐表哈希不变，
  `integrity_check=ok`、FK 空；故障注入后可见数据库哈希不变，原始历史备份从未修改；
- 品牌包更新没有静默修改项目；显式同步后只追加一个 ContextSnapshot、一个 AppRun、
  一个 Artifact 和一个 ArtifactVersion，项目主行只更新 current snapshot 指针和
  `updated_at`；所有既有 append-only 行逐行哈希不变；
- 10 次 sidecar 周期为 5 次 flag off + 5 次 flag on，每次 health/apps/projects
  读取成功、停止后端口释放，启动和读取前后业务哈希相同；
- Python full split `800 + 131 = 931 passed`，Desktop `18 files / 123 passed`，
  production build、Ruff、format、JSON、diff 和证据哈希检查通过；
- 未增加业务功能或字段，未修改默认 flag，未调用 LLM/TTS/RunningHub/第三方平台，
  未扫码、授权、上传、点击最终发布或提交 Git；
- `PROGRAM-ROLLOUT/PG-L_paused_external` 保持不变，不在本阶段恢复上位 Program。

## 2. 默认关闭与隔离边界

静态检查结果：

| 检查 | 结果 |
| --- | --- |
| `APIConfig.brand_project_boundary_v1_enabled` 无环境变量默认 | `false` |
| feature-flag matrix 默认 | `false` |
| `desktop/.env.production` 是否覆盖 | 否 |
| 前端 canonical/alias resolver fallback | `false` |

全部运行证据使用隔离根
`/tmp/pixelle-brand-project-stage5-closeout-v3`。生产工作数据库未打开写模式；迁移
源仅为历史备份，SHA-256 前后均为
`9c10b292f945de41cb857e31c1b6f45ba09654a0a376caaa1d72c593d935c329`。

Browser 验证只在隔离 API/Vite 进程临时打开既有 content-app flags 和品牌项目 flag。
第一次 on-again 启动遗漏既有 content-app flags，路由安全回到工作台；诊断后立即
停服。经协调层明确允许，只用完整静态 flag 清单做一次修正启动并采证，未继续循环
尝试，也未修改 `localStorage`。

## 3. on→off→on 双向回滚

固定项目：`project_4fef6d655939482b9cf6a42ec962e7d3`。

三个回滚 checkpoint 的聚合业务哈希均为：

```text
335f48e12897488a46c4d3da72b45cffde1e1da622727c85e0a3c6b3060a3aa2
```

逐表状态：

| 表 | rows | SHA-256 |
| --- | ---: | --- |
| `content_projects` | 1 | `39578bf872c18e616c82c1409822ba566be3df022701034018589a1945816158` |
| `context_snapshots` | 2 | `b4cc0f3c0f8384d749ddd5702b1a8e488ecd4478bda3532ec542cb8d482ac115` |
| `app_runs` | 5 | `a4beb46f8fa4c28f4f866a015af286a090ce0fe25fbc6dde463af8d26e01fd51` |
| `artifacts` | 11 | `ab40eda855e215a592c7504e16407bbe9f717b36e6828d2fadc39d66e663c15a` |
| `artifact_versions` | 11 | `e03161705ac906e23414818accbad2045550960d759ad6c93970014e13c13008` |
| `artifact_handoffs` | 1 | `189c8392797d45619ec2d6e852631c626337783f8d0244bf22e7470ab17fd8af` |

回滚步骤与观察：

1. on：轻量“项目与品牌资料”、项目“夏日冰咖啡推广”、固定品牌
   “北岸咖啡 · 焕新”和完成结果可见；展开项目品牌设置后，覆盖项明确标记
   “仅本项目使用”。
2. off：完整停止 API/Vite 并以 flag false 重启；新品牌区消失，旧“创作配置”
   恢复；旧 UI 的“本次主推”回填“夏日冰咖啡推广”，历史结果继续显示“已完成”。
3. on-again：再次完整停止并以 flag true 重启；轻量品牌区、固定版本说明、
   “品牌资料有更新”、项目业务字段和历史完成结果恢复。

off 和 on-again 的真实 Browser 截图分别为：

- [`browser-off-after-restart.png`](qa/BRAND-PROJECT-5-2026-07-30/browser-off-after-restart.png)，
  SHA-256
  `30ad8a705f6d7179b3ebf374083430ee0da9ea47e8d0bbb5ba8f1ac02c38894f`；
- [`browser-on-again-after-restart.png`](qa/BRAND-PROJECT-5-2026-07-30/browser-on-again-after-restart.png)，
  SHA-256
  `4e5fef43f463ade5947b669ac6c549a170e8702cc5d281a6cef3054d42825ca2`。

两次截图对应页面均为 `scrollWidth=clientWidth=1905`，没有横向溢出；普通页面不显示
`context_id`、`brand_version_id`、`domain_revision` 或 `snapshot_payload`。控制台
没有业务或网络错误，只有既有 Ant Design `List` 弃用提示。

初始 on 阶段完成了真实 DOM 和交互采证，但当时未识别正确的顶层
`tab.screenshot` 入口，因此没有该 phase 的截图；没有使用外部 Playwright、raw CDP
或替代浏览器绕行。完整 DOM、截图能力边界、URL、可见/不可见文案、console、
overflow 和对应 DB checkpoint 见
[`browser-rollback-manifest.json`](qa/BRAND-PROJECT-5-2026-07-30/browser-rollback-manifest.json)。

## 4. 真实旧 SQLite 副本迁移

历史只读备份迁移前业务表规模：

| 表 | rows |
| --- | ---: |
| `content_projects` | 6 |
| `context_snapshots` | 3 |
| `app_runs` | 10 |
| `artifacts` | 24 |
| `artifact_versions` | 31 |
| `artifact_handoffs` | 2 |

在副本上执行迁移后：

- 6 张表的旧列投影 rows/SHA-256 前后逐表相同；
- ArtifactVersion 新 provenance 列、ArtifactHandoff 源/目标快照列和
  ContextSnapshot schema v3 约束均存在；
- `PRAGMA integrity_check = ok`；
- `PRAGMA foreign_key_check = []`；
- 注入 builtin registry drift 后返回
  `registry seed drift for builtin.marketing-copy@1.0.0`，失败副本可见 SHA 前后相同；
- 历史只读源 SHA 前后相同。

早期收证脚本曾把两个迁移副本及自动备份/锁文件写到 QA 目录。7 个明确路径已逐一
`unlink`，QA 中不保留任何 `.sqlite*`；这些文件只是可重建临时副本，删除不可从 QA
恢复，但历史源备份未删除且哈希不变。脚本已改为系统临时目录并在验证结束后自动
清理，最终 JSON 只保留行数、哈希、旧列投影、FK/integrity 和失败注入结果，不引用
SQLite 二进制。

## 5. 显式同步与继续运行

品牌包先单独更新到 domain revision 3：

- 品牌名称：`北岸咖啡 · Stage5 显式同步`
- 主色：`#155E75`
- 地址：`江湾路 108 号`

品牌更新前后项目业务聚合哈希仍为
`335f48e12897488a46c4d3da72b45cffde1e1da622727c85e0a3c6b3060a3aa2`，
证明企业资产库更新不会静默改写项目或历史结果。

显式同步和新运行完成后使用：

- 新快照：`context_2c92dd29a47f4ade88d2d9b9adb58c08`
- 新运行：`run_df3bc1f7191a4f7e92e5c90ac70c7583`
- 新结果：`artifact_1f97f640db17426db0dd81a887b49bdd`
- 新版本：`artifact_version_d90370d2884b44bfb89365b132376327`

新运行和新 ArtifactVersion 均固定同一个新快照。预期和实际行数增量一致：

| 表 | delta |
| --- | ---: |
| `content_projects` | 0 |
| `context_snapshots` | +1 |
| `app_runs` | +1 |
| `artifacts` | +1 |
| `artifact_versions` | +1 |
| `artifact_handoffs` | 0 |

项目主行排除 `current_context_snapshot_id`、`updated_at` 后的稳定投影哈希前后均为
`a684c42c7e1b622e8a5db9df846eafa34d74d80df9e25b685ea49e6536ff462f`。
同步前的 2 个 ContextSnapshot、5 个 AppRun、11 个 Artifact、11 个
ArtifactVersion 和 1 个 ArtifactHandoff 均逐行登记 before/after SHA-256，全部不变。

第一次显式同步收证调用已经正确提交上述 4 个预期新增行，但证据序列化把
`result_code` 误写成 `result`，在 JSON 落盘前抛出 `KeyError`。没有重放业务写入；
使用 AppCenter migration 自动生成、业务聚合哈希与 on-again checkpoint 相同的
pre-write backup 恢复 before 逐行哈希，再以幂等 run key 和唯一结果链只读定位本次
新增行完成证据。收证脚本已修正为 `result_code`，并支持这种只读恢复路径。

## 6. 性能与 sidecar

Repository 读路径每项 10 次：

| 操作 | p50 ms | p95 ms | max ms |
| --- | ---: | ---: | ---: |
| `get_project` | 0.223 | 0.254 | 0.254 |
| `get_context_snapshot` | 0.217 | 2.048 | 2.048 |
| `resolve_for_run` | 3.179 | 4.826 | 4.826 |

接口读路径每项 10 次：

| 操作 | p50 ms | p95 ms | max ms |
| --- | ---: | ---: | ---: |
| list projects | 0.942 | 1.217 | 1.217 |
| get project | 0.771 | 0.975 | 0.975 |
| list context snapshots | 0.983 | 1.316 | 1.316 |

Repository 使用 250 ms、接口使用 500 ms 的宽松本地 regression guard；这些数字只
用于发现数量级退化，不是生产 SLA、真实 WebView SLA 或产品性能承诺。所有基准读取
前后项目业务哈希相同。

Sidecar 完成 10 次轻重启：

- cycle 1–5：flag off；
- cycle 6–10：flag on；
- 每轮 `/health`、`/api/apps`、`/api/content-projects` 均为 200；
- 每轮进程停止后端口释放；
- 10 轮前后项目业务哈希均为
  `a67524d4aab47679b189a6e58116cfb48c55bbc27cee15dbbd166527216035fe`。

## 7. 自动化验证

Python full split：

- 非浏览器组：`800 passed / 0 failed / 12 existing warnings`；
- 浏览器/慢测试组 12 文件：`131 passed / 0 failed / 12 existing warnings`；
- 合计：`931 passed / 0 failed`。

非浏览器组首次运行是 `799 passed / 1 failed`，唯一失败为进度台账已切换
`PG-BP-F_implementation_in_progress`，但 `coord0_contract_test` 的允许枚举尚未纳入
PG-BP-F。补齐 `implementation_in_progress` 和 `implementation_review_pending`
契约枚举后，以完全相同的 800 项命令复跑通过；没有修改产品逻辑或放宽业务断言。

Desktop：

- `npm test -- --run --maxWorkers=1 --no-file-parallelism`：
  `18 files / 123 passed / 0 failed`；
- `npm run build`：通过，`4610 modules transformed`，仅既有 chunk-size warning。

最初尝试使用旧 Vitest `--poolOptions.threads.singleThread=true` 参数，被当前 Vitest
明确拒绝为 unknown option，未运行测试；随后根据当前 CLI 使用上面的单 worker 参数
完成全量。

最终还执行：

- `ruff check`；
- `ruff format --check`；
- Python compile；
- 所有 Stage5 JSON 解析；
- `git diff --check`；
- QA 证据 SHA-256 重算；
- 8117/8118/1439 端口均已释放；
- QA 目录不存在 `.sqlite*`。

## 8. 证据索引

总清单：
[`qa/BRAND-PROJECT-5-implementation-2026-07-30.json`](qa/BRAND-PROJECT-5-implementation-2026-07-30.json)。

细分证据位于
[`qa/BRAND-PROJECT-5-2026-07-30/`](qa/BRAND-PROJECT-5-2026-07-30/)：

- `prepare.json`：默认 flag、repository 基准、旧库迁移/失败注入；
- `browser-on-before.json`、`browser-off-after-restart.json`、
  `browser-on-again-after-restart.json`：回滚 DB checkpoints；
- `browser-rollback-manifest.json` 与两张 PNG：真实可视化证据；
- `brand-update.json`：品牌包更新后项目零写；
- `continue-after-rollback.json`：显式同步、新 run/result、逐行哈希与 delta；
- `sidecar.json`：10 周期和接口基准；
- `fixture.json`：隔离 fixture 身份。

## 9. Gate 边界

- 当前状态：`PG-BP-F_implementation_review_pending`；
- 等待最终独立六维终审，只有 P0/P1/实质性 P2=0 后才可由协调层决定 Gate；
- 默认 flags 保持关闭；
- 未声称 Windows 实机、产品签字、真实平台 rollback 或真实 WebView SLA 已完成；
- LLM、TTS、RunningHub、第三方 provider、平台授权、上传和最终发布点击均为 0；
- 无 Git commit；
- `PROGRAM-ROLLOUT/PG-L_paused_external` 不变，本阶段不恢复 Program。
