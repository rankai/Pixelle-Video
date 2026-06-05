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
