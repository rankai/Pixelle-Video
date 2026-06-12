from pathlib import Path


APP_SOURCE = Path("desktop/src/App.tsx").read_text()
API_SOURCE = Path("desktop/src/api.ts").read_text()


def test_desktop_api_exposes_config_check_without_connection_wording():
    assert "export type DesktopDiagnostics" in API_SOURCE
    assert "export type ConfigCheckResult" in API_SOURCE
    assert "checkDesktopConfig" in API_SOURCE
    assert '"/api/desktop/config/check"' in API_SOURCE
    assert "testDesktopConnection" not in API_SOURCE
    assert "/connections/" not in API_SOURCE


def test_config_view_uses_config_completeness_check_copy():
    config_view = APP_SOURCE[APP_SOURCE.index("function ConfigView(") : APP_SOURCE.index("function DiagnosticsView")]

    assert "检查当前配置" in config_view
    assert "配置项已填写，尚未验证服务账号是否可用" in config_view
    assert "检查 LLM 配置" not in config_view
    assert "检查 RunningHub 配置" not in config_view
    assert "测试 LLM 连接" not in config_view
    assert "测试 RunningHub 连接" not in config_view
    assert "测试连接" not in config_view
    assert "checkDesktopConfig" in config_view
    assert "config-check-row" in config_view


def test_diagnostics_view_renders_structured_checks():
    diagnostics_view = APP_SOURCE[APP_SOURCE.index("function DiagnosticsView(") : APP_SOURCE.index("function AssetImage")]

    assert "diagnostic-check-row" in diagnostics_view
    assert "diagnostics?.checks" in diagnostics_view


def test_browser_smoke_can_pass_desktop_token_from_vite_env():
    assert "VITE_DESKTOP_TOKEN" in API_SOURCE
