# PROGRAM-ROLLOUT Windows CI 实际构建运行证据（2026-07-22）

## 结论

Windows Runner 实际构建已通过：workflow run `#3`（`29881594901`）在 `windows-latest` 上完成 Windows sidecar、桌面测试和 Tauri NSIS installer，并上传 artifact。该证据将 PG-L-04 从 `deferred` 提升为 `passed_with_boundary`；Windows 实机安装、启动、关闭重开和 sidecar 重启仍需人工完成，PG-L 总状态继续 `open`。

## 运行信息

- commit：`b652960edb2f03f4c29a58f9093e011a6b689fc6`
- workflow：[`Windows NSIS installer and sidecar`](https://github.com/rankai/Pixelle-Video/actions/runs/29881594901)
- job：[`Windows NSIS installer and sidecar`](https://github.com/rankai/Pixelle-Video/actions/runs/29881594901/job/88803468708)
- runner：`windows-latest`
- target：`x86_64-pc-windows-msvc`
- started：`2026-07-22T00:54:29Z`
- completed：`2026-07-22T01:04:28Z`
- conclusion：`success`

## 实际步骤

| 步骤 | 结果 |
| --- | --- |
| Python/uv/Node/Rust setup | passed |
| locked Python dependencies | passed |
| Windows Python sidecar build | passed |
| sidecar target verification | passed |
| Windows `npm ci` | passed |
| desktop tests | passed |
| Tauri NSIS build | passed |
| artifact manifest/checksum generation | passed |
| artifact upload | passed |

## Artifact 与 SHA-256

- artifact：`pixelle-video-windows-b652960edb2f03f4c29a58f9093e011a6b689fc6`
- artifact id：`8515139706`
- artifact size：`264883933` bytes
- installer：`Pixelle Video_0.1.0_x64-setup.exe`，`134129674` bytes，SHA-256 `525b28b10face2ee83143648e62794ad9d0d13e266730ba7d255acbe42406d24`
- sidecar：`pixelle-api-x86_64-pc-windows-msvc.exe`，`131787323` bytes，SHA-256 `d25ba449cea6342ca8911419ebf1652b834a3931335c2c07787e9fa98a2eb49d`
- manifest：`windows-artifact-manifest.json`；Mac 下载解压后对 installer/sidecar 重新计算 SHA-256，均与 manifest 匹配。

## 边界与下一步

- `PG-L-04=passed_with_boundary`：真实 Windows Runner build、sidecar、NSIS installer 和 manifest 已有证据。
- `windows_install_test=pending_windows_manual_install`：尚未在 Windows 实机安装、启动、关闭重开或验证 sidecar health。
- 不自动点击最终发布，不改变 Publish V2 默认关闭、抖音灰度 0% 或其他平台 release state。
- 下一动作：在 Windows 实机按安装清单执行一次人工安装/启动/重启测试，并回传版本、SHA、截图/日志；遇到扫码、第三方授权或最终发布按钮立即暂停。
