import asyncio
import hashlib

import pytest

from pixelle_video.app_center.llm_port import AppLLMPortError, FakeLLMPort
from pixelle_video.app_center.repository import (
    AppCenterRepository,
    AppCenterRepositoryError,
)
from pixelle_video.app_center.structured_apps import StructuredLLMExecutor
from pixelle_video.app_center.style_presets import (
    list_style_presets,
    resolve_style_preset,
)


def _context_payload():
    return {
        "schema_version": 2,
        "subject_type": "store",
        "store_or_brand": {
            "name": "街角咖啡",
            "industry": "咖啡餐饮",
            "address": None,
            "contact": None,
        },
        "offer": {
            "name": "午后咖啡套餐",
            "category": "饮品套餐",
            "price_facts": [],
            "promotion_facts": [],
        },
        "audience": {"primary": "附近上班族", "scenes": ["午后休息"]},
        "selling_points": [
            {
                "fact_id": "selling-1",
                "text": "现磨咖啡",
                "source": "user",
                "source_ref": None,
            }
        ],
        "proof_points": [],
        "required_facts": [],
        "forbidden_claims": ["全城第一"],
        "asset_refs": [],
        "brand_revision_ref": None,
    }


def _copy_output():
    variants = []
    for index, angle in enumerate(("利益", "好奇", "场景"), start=1):
        hook = f"午后轻松一下{index}"
        body = "现磨咖啡，适合附近上班族午后休息。"
        cta = "到店了解"
        full_text = hook + body + cta
        variants.append(
            {
                "version_name": f"版本{index}",
                "angle": angle,
                "hook": hook,
                "body": body,
                "cta": cta,
                "full_text": full_text,
                "word_count": len(full_text),
                "estimated_seconds": (len(full_text) + 3) // 4,
            }
        )
    return {"variants": variants, "missing_facts": [], "risk_flags": []}


def _title_output():
    return {
        "candidates": [
            {
                "title": f"午后咖啡选择第{index}招",
                "angle": "场景",
                "objective": "click",
                "length": len(f"午后咖啡选择第{index}招"),
                "banned_matches": [],
                "risk_labels": ["无"],
            }
            for index in range(1, 6)
        ],
        "missing_facts": [],
        "risk_flags": [],
    }


def _project_and_snapshot(repository):
    project = repository.create_project("工作台文本 v2", "验证风格和交接")
    snapshot = repository.save_context_snapshot(
        project.project_id,
        _context_payload(),
        schema_version=2,
    )
    return repository.get_project(project.project_id), snapshot


def _marketing_payload(project_id, snapshot_id):
    return {
        "schema_version": 2,
        "app_id": "builtin.marketing-copy",
        "input_schema_ref": "marketing-copy-input.v2",
        "project_id": project_id,
        "context_snapshot_id": snapshot_id,
        "task_brief": {
            "goal": "吸引附近上班族到店",
            "offer_name": "午后咖啡套餐",
            "selling_point_fact_ids": ["selling-1"],
            "benefit_tags": ["到店"],
            "audience": "附近上班族",
            "content_format": "oral",
            "length_bucket": "short_15s",
            "must_include": ["现磨咖啡"],
            "cta": "到店了解",
        },
        "style_ref": {"style_id": "copy.owner_voice", "version": 1},
        "custom_style_reference": None,
        "source_artifact_version_ids": [],
    }


def test_trusted_style_registry_exposes_public_projection_only():
    items = list_style_presets(app_id="builtin.marketing-copy")
    assert len(items) == 8
    assert {"style_id", "version", "family", "name", "description", "example"} == set(items[0])
    assert "prompt_rules" not in items[0]
    assert resolve_style_preset("copy.owner_voice", 1, app_id="builtin.marketing-copy").prompt_rules


def test_marketing_v2_uses_pinned_context_and_trusted_style_rules(tmp_path):
    repository = AppCenterRepository(tmp_path / "text-v2.sqlite")
    project, snapshot = _project_and_snapshot(repository)
    payload = _marketing_payload(project.project_id, snapshot.context_snapshot_id)
    run = repository.create_app_run(
        project.project_id,
        "builtin.marketing-copy",
        "1.1.0",
        payload,
        idempotency_key="marketing-v2-style-001",
        context_snapshot_id=snapshot.context_snapshot_id,
    )
    port = FakeLLMPort(_copy_output())
    result = asyncio.run(
        StructuredLLMExecutor(repository, port, app_id="builtin.marketing-copy").execute(run)
    )
    assert port.requests[0].input_schema_ref == "marketing-copy-input.v2"
    assert "使用自然第一人称" in port.requests[0].trusted_style_rules
    assert (
        result.content["validation_facts"]["input"]["style_ref"]["style_id"] == "copy.owner_voice"
    )
    assert result.content["validation_facts"]["context"]["offer"]["name"] == "午后咖啡套餐"


def test_custom_style_reference_is_fingerprinted_and_never_becomes_context(tmp_path):
    repository = AppCenterRepository(tmp_path / "custom-style.sqlite")
    project, snapshot = _project_and_snapshot(repository)
    payload = _marketing_payload(project.project_id, snapshot.context_snapshot_id)
    text = "只参考短句节奏。示例中的品牌、价格、效果都不是事实。"
    payload["style_ref"] = None
    payload["custom_style_reference"] = {
        "text": text,
        "content_fingerprint": "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "facts_imported": False,
    }
    run = repository.create_app_run(
        project.project_id,
        "builtin.marketing-copy",
        "1.1.0",
        payload,
        idempotency_key="marketing-v2-custom-001",
        context_snapshot_id=snapshot.context_snapshot_id,
    )
    port = FakeLLMPort(_copy_output())
    asyncio.run(
        StructuredLLMExecutor(repository, port, app_id="builtin.marketing-copy").execute(run)
    )
    assert port.requests[0].trusted_style_rules == ()
    assert "custom_style_reference" in port.requests[0].prompt_variables["input"]
    assert "custom_style_reference" not in port.requests[0].context

    payload["custom_style_reference"]["content_fingerprint"] = "sha256:" + "0" * 64
    broken = repository.create_app_run(
        project.project_id,
        "builtin.marketing-copy",
        "1.1.0",
        payload,
        idempotency_key="marketing-v2-custom-invalid-001",
        context_snapshot_id=snapshot.context_snapshot_id,
    )
    with pytest.raises(AppLLMPortError) as raised:
        asyncio.run(
            StructuredLLMExecutor(
                repository, FakeLLMPort(_copy_output()), app_id="builtin.marketing-copy"
            ).execute(broken)
        )
    assert raised.value.diagnostic == "CUSTOM_STYLE_FINGERPRINT"


def test_titles_v2_resolves_one_pinned_copywriting_version(tmp_path):
    repository = AppCenterRepository(tmp_path / "title-v2.sqlite")
    project, snapshot = _project_and_snapshot(repository)
    source_run = repository.create_app_run(
        project.project_id,
        "builtin.marketing-copy",
        "1.1.0",
        _marketing_payload(project.project_id, snapshot.context_snapshot_id),
        idempotency_key="title-v2-source-run-001",
        context_snapshot_id=snapshot.context_snapshot_id,
    )
    source_artifact = repository.create_artifact(
        project.project_id,
        "copywriting",
        "文案",
        source_app_run_id=source_run.app_run_id,
    )
    source_content = {
        "schema_version": 1,
        "artifact_type": "copywriting",
        "validation_facts": {
            "input": source_run.input_payload,
            "context": snapshot.payload,
        },
        **_copy_output(),
    }
    source_version = repository.append_artifact_version(
        source_artifact.artifact_id, content=source_content
    )
    payload = {
        "schema_version": 2,
        "app_id": "builtin.viral-titles",
        "input_schema_ref": "viral-titles-input.v2",
        "project_id": project.project_id,
        "context_snapshot_id": snapshot.context_snapshot_id,
        "task_brief": {
            "platform": "douyin",
            "objective": "click",
            "count": 5,
            "topic": None,
            "source_text": None,
            "keywords": ["咖啡"],
        },
        "style_ref": {"style_id": "title.feed", "version": 1},
        "custom_style_reference": None,
        "source_artifact_version_ids": [source_version.artifact_version_id],
    }
    run = repository.create_app_run(
        project.project_id,
        "builtin.viral-titles",
        "1.1.0",
        payload,
        idempotency_key="title-v2-run-001",
        context_snapshot_id=snapshot.context_snapshot_id,
    )
    port = FakeLLMPort(_title_output())
    asyncio.run(StructuredLLMExecutor(repository, port, app_id="builtin.viral-titles").execute(run))
    assert (
        port.requests[0].prompt_variables["input"]["resolved_source_content"]["artifact_type"]
        == "copywriting"
    )
    assert "用真实场景开头" in port.requests[0].trusted_style_rules


def test_result_events_store_only_ids_index_and_short_summary(tmp_path):
    repository = AppCenterRepository(tmp_path / "events.sqlite")
    project = repository.create_project("事件", "记录结果操作")
    run = repository.create_app_run(
        project.project_id,
        "builtin.marketing-copy",
        "1.0.0",
        {},
        idempotency_key="event-run-001",
    )
    artifact = repository.create_artifact(
        project.project_id,
        "copywriting",
        "文案",
        source_app_run_id=run.app_run_id,
    )
    event = repository.record_app_event(
        run.app_run_id,
        "result.liked",
        {
            "artifact_id": artifact.artifact_id,
            "item_index": 1,
            "summary": "文案版本 2",
        },
    )
    assert event.payload["item_index"] == 1
    assert repository.list_app_events(run.app_run_id)[0] == event
    with pytest.raises(AppCenterRepositoryError, match="APP_EVENT_PAYLOAD_INVALID"):
        repository.record_app_event(
            run.app_run_id,
            "result.copied",
            {"full_text": "不应把完整文案复制进事件"},
        )
