from pathlib import Path

SOURCE = Path("desktop/src/api.ts").read_text()


def test_api_fetch_formats_nginx_413_upload_error():
    assert "formatHttpError" in SOURCE
    assert "status === 413" in SOURCE
    assert "上传文件过大" in SOURCE
    assert "Request Entity Too Large" in SOURCE


def test_browser_runtime_probes_local_api_before_first_request():
    assert "resolveBrowserApiBaseUrl" in SOURCE
    assert 'fetch(`${candidate.replace(/\\/$/, "")}/health`' in SOURCE
    assert '"http://127.0.0.1:8000"' in SOURCE


def test_network_error_does_not_expose_api_address_in_default_ui():
    assert '"后端服务未连接，请确认 API 服务已启动。"' in SOURCE
    assert "const target = apiBaseUrl" not in SOURCE


def test_server_errors_use_business_copy_and_parse_json_detail():
    assert "status >= 500" in SOURCE
    assert '"服务器暂时不可用，请稍后重试。"' in SOURCE
    assert "JSON.parse(detail)" in SOURCE
    assert "formatHttpErrorDetail(xhr.status, xhr.responseText" in SOURCE
