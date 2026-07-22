# COORD-0 Tauri/sidecar 重启基线

日期：2026-07-19；执行者：主线程；结果：`passed`

## Tauri CLI 首次 PATH-negative 探针（历史）

第一次探针曾因执行环境没有把 `~/.cargo/bin` 放进 PATH，在 `cargo metadata` 阶段失败；该失败已保留为历史边界。随后使用显式 `PATH="/Users/nickfury/.cargo/bin:$PATH"` 重跑，`cargo 1.97.1`、`rustc 1.97.1` 可用，Tauri 本体完成编译并启动桌面进程。

```text
failed to run 'cargo metadata' command to get workspace directory:
failed to run command cargo metadata --no-deps --format-version 1:
No such file or directory (os error 2)
```

## Tauri 本体 + sidecar 两轮重启

命令：`PATH="/Users/nickfury/.cargo/bin:$PATH" npm run tauri:dev`（工作目录 `desktop/`）。每轮均观察 `pixelle-video-desktop` 进程、其子进程 `src-tauri/target/debug/pixelle-api --host 127.0.0.1 --port 8100`，并请求 `/health`；随后发送 Ctrl-C，确认桌面进程、sidecar 和 8100 端口全部退出。

| 轮次 | 观察时间（UTC） | 进程/health | 停止观察（UTC） | 结果 |
| --- | --- | --- | --- | --- |
| cycle 1 | `2026-07-19T08:49:35.339299Z` | Tauri PID `73903`；sidecar PID `74917`；`/health` 返回 `{"status":"healthy","version":"0.1.0","service":"Pixelle-Video API"}` | `2026-07-19T08:50:08.298163Z` | 进程消失，8100 连接失败（端口关闭） |
| cycle 2 | `2026-07-19T08:51:25.022494Z` | Tauri PID `76485`；sidecar PID `76580`；`/health` 返回同上 | `2026-07-19T08:51:57.741731Z` | 进程消失，8100 连接失败（端口关闭） |

Tauri 重启后追加一次既有抖音 profile 只读探针（不上传、不发布）：`2026-07-19T08:52:53.364956Z`，`logged_in=true`，上传页 URL 保持 `https://creator.douyin.com/creator-micro/content/upload`。

## 已构建 sidecar 重启闭环

为隔离 Tauri CLI 工具缺失与 sidecar 本身能力，使用已存在的 `desktop/src-tauri/bin/pixelle-api-aarch64-apple-darwin`，在仓库根目录、Tauri debug 等价环境变量和隔离临时数据目录 `/tmp/pixelle-sidecar-runtime-clean-20260719` 下运行两次：启动 → `/health` → 停止 → 确认端口关闭 → 再启动 → `/health` → 停止。

| 事件 | UTC 时间 | 结果 |
| --- | --- | --- |
| cycle 1 process started | `2026-07-19T01:30:15.901900+00:00` | pid `10841` |
| cycle 1 health | `2026-07-19T01:30:24.566313+00:00` | `{"status":"healthy","version":"0.1.0","service":"Pixelle-Video API"}` |
| cycle 1 stopped | `2026-07-19T01:30:25.411761+00:00` | exit `-15`，port closed `true`，warning `[]` |
| cycle 2 process started | `2026-07-19T01:30:25.411876+00:00` | pid `11007` |
| cycle 2 health | `2026-07-19T01:30:33.529485+00:00` | `{"status":"healthy","version":"0.1.0","service":"Pixelle-Video API"}` |
| cycle 2 stopped | `2026-07-19T01:30:34.315448+00:00` | exit `-15`，port closed `true`，warning `[]` |

## 判定边界

- sidecar 启动、health、停止、端口释放和重启均通过；
- Tauri 应用本体两轮编译、启动、停止均通过；重启后既有抖音 profile 只读登录探针为 `true`；任务 3 的桌面/sidecar/免扫码基线通过；
- 首次扫码任务 1 仍未声称完成，因为本次只复用既有授权 profile；
- 该测试没有打开抖音、上传媒体、填写字段或发布；临时运行目录不属于项目数据根目录。
