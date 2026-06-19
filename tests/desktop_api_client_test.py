from pathlib import Path


SOURCE = Path("desktop/src/api.ts").read_text()


def test_api_fetch_formats_nginx_413_upload_error():
    assert "formatHttpError" in SOURCE
    assert "response.status === 413" in SOURCE
    assert "上传文件过大" in SOURCE
    assert "Request Entity Too Large" in SOURCE
