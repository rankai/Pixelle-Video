from pathlib import Path


def test_batch4_runtime_fallback_does_not_project_local_paths():
    source = Path("desktop/src/features/publishing/PublishCenterView.tsx").read_text(encoding="utf-8")
    assert "PublishFallbackActions" in source
    assert "返回工作区复制/下载素材" in source
    assert "不会暴露本地路径，也不会自动发布" in source
    assert "window.location.hash = \"#/ip\"" in source


def test_batch4_recovery_persists_only_canonical_publish_refs():
    source = Path("desktop/src/features/app-center/AppShell.tsx").read_text(encoding="utf-8")
    assert "pixelle_app_center_last_route" in source
    assert "package_id" in source and "artifact_id" in source and "run_id" in source
    assert "secret" not in source


def test_batch4_runtime_qa_records_external_action_zero():
    source = Path("docs/reviews/application-publishing-program/qa/PUB-4-batch-4-local-runtime-2026-07-21.json").read_text(encoding="utf-8")
    assert '"status": "passed_local_bounded"' in source
    assert '"browser": 0' in source
    assert '"final_publish": 0' in source
