import json

from scripts.acr_webhook_lib import (
    ACRWebhookConfig,
    extract_acr_event,
    mark_image_ready,
    should_accept_secret,
)


def test_extracts_repository_and_tag_from_acr_push_payload():
    payload = {
        "repository": {"repo_full_name": "xiaojuntech/pixelle-video-api"},
        "push_data": {"tag": "main-a1b2c3d"},
    }

    event = extract_acr_event(payload)

    assert event.repository == "pixelle-video-api"
    assert event.service == "api"
    assert event.tag == "main-a1b2c3d"


def test_extracts_repository_and_tag_from_nested_data_payload():
    payload = {
        "data": {
            "repository": {"name": "pixelle-video-web"},
            "tag": "main-a1b2c3d",
        }
    }

    event = extract_acr_event(payload)

    assert event.repository == "pixelle-video-web"
    assert event.service == "web"
    assert event.tag == "main-a1b2c3d"


def test_marks_tag_ready_only_after_both_images_are_seen(tmp_path):
    state_path = tmp_path / "deploy_webhook_state.json"

    first = mark_image_ready(state_path, "main-a1b2c3d", "api", {"api", "web"})
    second = mark_image_ready(state_path, "main-a1b2c3d", "web", {"api", "web"})

    assert not first.ready_to_deploy
    assert second.ready_to_deploy
    assert second.services == {"api", "web"}

    state = json.loads(state_path.read_text())
    assert state["tags"]["main-a1b2c3d"]["services"] == ["api", "web"]


def test_does_not_redeploy_tag_after_it_has_been_marked_triggered(tmp_path):
    state_path = tmp_path / "deploy_webhook_state.json"

    mark_image_ready(state_path, "main-a1b2c3d", "api", {"api", "web"})
    first_web = mark_image_ready(state_path, "main-a1b2c3d", "web", {"api", "web"})
    duplicate_web = mark_image_ready(state_path, "main-a1b2c3d", "web", {"api", "web"})

    assert first_web.ready_to_deploy
    assert not duplicate_web.ready_to_deploy


def test_rejects_missing_or_wrong_secret_when_secret_is_configured():
    config = ACRWebhookConfig(secret="expected")

    assert should_accept_secret(config, "expected")
    assert not should_accept_secret(config, None)
    assert not should_accept_secret(config, "wrong")


def test_accepts_any_secret_when_secret_is_not_configured():
    config = ACRWebhookConfig(secret="")

    assert should_accept_secret(config, None)
    assert should_accept_secret(config, "anything")
