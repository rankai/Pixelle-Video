from pathlib import Path

import yaml


def test_webhook_service_runs_from_mounted_project_dir():
    compose = yaml.safe_load(Path("docker-compose.prod.yml").read_text())
    webhook = compose["services"]["webhook"]

    assert webhook["working_dir"] == "${PROJECT_DIR}"
    assert "${PROJECT_DIR:?PROJECT_DIR is required}:${PROJECT_DIR}" in webhook["volumes"]
    assert webhook["environment"]["PROJECT_ROOT"] == "${PROJECT_DIR}"


def test_webhook_server_validates_deploy_script_before_spawn():
    source = Path("scripts/webhook-server.js").read_text()

    assert "DEPLOY_SCRIPT" in source
    assert "existsSync(DEPLOY_SCRIPT)" in source
    assert "PROJECT_ROOT/PROJECT_DIR" in source
    assert "spawn('bash', [DEPLOY_SCRIPT]" in source


def test_webhook_server_does_not_log_failed_auth_token():
    source = Path("scripts/webhook-server.js").read_text()

    assert "鉴权失败 token=" not in source
    assert "鉴权失败" in source


def test_webhook_server_supports_hmac_signature_auth():
    source = Path("scripts/webhook-server.js").read_text()

    assert "DEPLOY_WEBHOOK_HMAC_SECRET" in source
    assert "DEPLOY_WEBHOOK_REQUIRE_HMAC" in source
    assert "x-pixelle-timestamp" in source
    assert "x-pixelle-signature" in source
    assert ".createHmac('sha256', HMAC_SECRET)" in source
    assert "crypto.timingSafeEqual" in source
    assert "HMAC_WINDOW_SECONDS" in source


def test_webhook_image_starts_server_from_image_path():
    dockerfile = Path("Dockerfile.webhook").read_text()

    assert 'CMD ["node", "/app/scripts/webhook-server.js"]' in dockerfile


def test_external_nginx_proxy_allows_large_video_uploads():
    runbook = Path("docs/deployment/web-auto-deploy-runbook.md").read_text()

    assert "client_max_body_size 2048m;" in runbook
