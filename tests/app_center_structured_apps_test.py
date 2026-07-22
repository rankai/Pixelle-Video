import asyncio

import pytest

from pixelle_video.app_center.llm_port import (
    AppLLMPortError,
    FakeLLMPort,
    StructuredGenerationResponse,
)
from pixelle_video.app_center.repository import AppCenterRepository
from pixelle_video.app_center.structured_apps import (
    StructuredLLMExecutor,
    build_builtin_structured_executors,
    normalize_text,
)


def _copy_output():
    variants = []
    for index, angle in enumerate(("利益", "好奇", "场景"), start=1):
        hook = f"门店亮点{index}"
        body = f"这是第{index}版真实内容"
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


def _title_output(objective="click", count=5):
    return {
        "candidates": [
            {
                "title": f"门店体验第{index}招",
                "angle": "场景",
                "objective": objective,
                "length": len(f"门店体验第{index}招"),
                "banned_matches": [],
                "risk_labels": ["无"],
            }
            for index in range(1, count + 1)
        ],
        "missing_facts": [],
        "risk_flags": [],
    }


def _run(repository, app_id, payload, port):
    project = repository.create_project("AC-3 测试", "验证结构化应用")
    run = repository.create_app_run(project.project_id, app_id, "1.0.0", payload, idempotency_key=f"{app_id}-test-run-001")
    return project, run, asyncio.run(StructuredLLMExecutor(repository, port, app_id=app_id).execute(run))


def test_marketing_executor_validates_and_writes_contract_content(tmp_path):
    repository = AppCenterRepository(tmp_path / "structured.sqlite")
    _, _, output = _run(
        repository,
        "builtin.marketing-copy",
        {"goal": "到店", "product_or_service": "咖啡", "content_format": "oral", "length_bucket": "short_15s"},
        FakeLLMPort(_copy_output()),
    )
    assert output.artifact_type == "copywriting"
    assert output.content["schema_version"] == 1
    assert len(output.content["variants"]) == 3
    assert output.provider_class == "fake"
    assert output.content["validation_facts"]["input"]["product_or_service"] == "咖啡"


def test_marketing_executor_recalculates_provider_derived_fields_locally(tmp_path):
    output = _copy_output()
    output["variants"][0]["word_count"] = 999
    output["variants"][0]["estimated_seconds"] = 1
    repository = AppCenterRepository(tmp_path / "derived-fields.sqlite")
    _, _, result = _run(
        repository,
        "builtin.marketing-copy",
        {"goal": "到店", "product_or_service": "咖啡", "content_format": "oral", "length_bucket": "short_15s"},
        FakeLLMPort(output),
    )
    variant = result.content["variants"][0]
    assert variant["word_count"] == len(variant["full_text"])
    assert variant["estimated_seconds"] == (variant["word_count"] + 3) // 4


def test_structured_executor_repairs_invalid_output_once_and_preserves_request(tmp_path):
    class SequencePort:
        def __init__(self):
            self.calls = []

        async def generate_structured(self, request, *, response_type=None):
            self.calls.append(request)
            payload = {"variants": [], "missing_facts": [], "risk_flags": []} if len(self.calls) == 1 else _copy_output()
            return StructuredGenerationResponse(payload, "local-default:test", "fake", request_id=request.request_id)

    port = SequencePort()
    repository = AppCenterRepository(tmp_path / "repair.sqlite")
    _, _, output = _run(
        repository,
        "builtin.marketing-copy",
        {"goal": "到店", "product_or_service": "咖啡", "content_format": "oral", "length_bucket": "short_15s"},
        port,
    )
    assert len(port.calls) == 2
    assert port.calls[0].idempotency_key == port.calls[1].idempotency_key
    assert port.calls[1].prompt_variables["repair_attempt"] == 1
    assert "exactly 3 variants" in port.calls[0].prompt_variables["output_contract"]
    assert "marketing output must contain exactly 3 variants" in port.calls[1].prompt_variables["repair_reason"]
    assert len(output.content["variants"]) == 3


def test_structured_executor_maps_second_invalid_output_to_stable_error(tmp_path):
    repository = AppCenterRepository(tmp_path / "invalid.sqlite")
    port = FakeLLMPort({"variants": [], "missing_facts": [], "risk_flags": []})
    project = repository.create_project("AC-3 测试", "验证错误")
    run = repository.create_app_run(
        project.project_id,
        "builtin.marketing-copy",
        "1.0.0",
        {"goal": "到店", "product_or_service": "咖啡", "content_format": "oral", "length_bucket": "short_15s"},
        idempotency_key="stable-output-invalid-001",
    )
    with pytest.raises(AppLLMPortError) as raised:
        asyncio.run(StructuredLLMExecutor(repository, port, app_id="builtin.marketing-copy").execute(run))
    assert raised.value.code == "STRUCTURED_OUTPUT_INVALID"
    assert raised.value.diagnostic == "MARKETING_VARIANT_COUNT"
    assert len(port.requests) == 2


@pytest.mark.parametrize(
    ("field", "claim", "expected_diagnostic"),
    [
        ("price", "到店优惠99元", "UNSUPPORTED_PRICE_FACT"),
        ("address", "欢迎到人民路8号", "UNSUPPORTED_ADDRESS_FACT"),
    ],
)
def test_marketing_executor_rejects_concrete_facts_absent_from_input(tmp_path, field, claim, expected_diagnostic):
    output = _copy_output()
    output["variants"][0]["body"] = claim
    output["variants"][0]["full_text"] = output["variants"][0]["hook"] + claim + output["variants"][0]["cta"]
    output["variants"][0]["word_count"] = len(output["variants"][0]["full_text"])
    output["variants"][0]["estimated_seconds"] = (output["variants"][0]["word_count"] + 3) // 4
    repository = AppCenterRepository(tmp_path / f"invented-{field}.sqlite")
    project = repository.create_project("AC-3 事实", "拒绝编造")
    run = repository.create_app_run(
        project.project_id,
        "builtin.marketing-copy",
        "1.0.0",
        {"goal": "到店", "product_or_service": "咖啡", "content_format": "oral", "length_bucket": "short_15s", "facts": {}},
        idempotency_key=f"invented-{field}-001",
    )
    with pytest.raises(AppLLMPortError) as raised:
        asyncio.run(StructuredLLMExecutor(repository, FakeLLMPort(output), app_id="builtin.marketing-copy").execute(run))
    assert raised.value.code == "STRUCTURED_OUTPUT_INVALID"
    assert raised.value.diagnostic == expected_diagnostic


def test_generated_fact_is_preserved_for_safe_edit_version_validation(tmp_path):
    output = _copy_output()
    output["variants"][0]["body"] = "到店优惠99元"
    output["variants"][0]["full_text"] = output["variants"][0]["hook"] + output["variants"][0]["body"] + output["variants"][0]["cta"]
    output["variants"][0]["word_count"] = len(output["variants"][0]["full_text"])
    output["variants"][0]["estimated_seconds"] = (output["variants"][0]["word_count"] + 3) // 4
    repository = AppCenterRepository(tmp_path / "edit-facts.sqlite")
    project = repository.create_project("AC-3 编辑", "保留事实")
    run = repository.create_app_run(project.project_id, "builtin.marketing-copy", "1.0.0", {"goal": "到店", "product_or_service": "咖啡", "content_format": "oral", "length_bucket": "short_15s", "facts": {"price": "99元"}}, idempotency_key="edit-facts-001")
    generated = asyncio.run(StructuredLLMExecutor(repository, FakeLLMPort(output), app_id="builtin.marketing-copy").execute(run))
    artifact = repository.create_artifact(project.project_id, "copywriting", "文案")
    version = repository.append_artifact_version(artifact.artifact_id, content=generated.content or {})
    assert version.content and version.content["variants"][0]["word_count"] == len(version.content["variants"][0]["full_text"])


def test_title_executor_enforces_exact_source_and_deterministic_length(tmp_path):
    repository = AppCenterRepository(tmp_path / "titles.sqlite")
    port = FakeLLMPort(_title_output())
    _, _, output = _run(
        repository,
        "builtin.viral-titles",
        {"platform": "douyin", "objective": "click", "count": 5, "topic": "咖啡店体验"},
        port,
    )
    assert output.artifact_type == "title_set"
    assert len(output.content["candidates"]) == 5
    assert "exactly input.count" in port.requests[0].prompt_variables["output_contract"]

    project = repository.create_project("AC-3 输入", "校验来源")
    run = repository.create_app_run(
        project.project_id,
        "builtin.viral-titles",
        "1.0.0",
        {"platform": "douyin", "objective": "click", "count": 5, "topic": "咖啡", "source_text": "同时提供"},
        idempotency_key="invalid-title-source-001",
    )
    with pytest.raises(AppLLMPortError) as raised:
        asyncio.run(StructuredLLMExecutor(repository, FakeLLMPort(_title_output()), app_id="builtin.viral-titles").execute(run))
    assert raised.value.code == "APP_INPUT_INVALID"


def test_title_executor_resolves_same_project_artifact_source(tmp_path):
    repository = AppCenterRepository(tmp_path / "title-source.sqlite")
    project = repository.create_project("AC-3 来源", "从文案生成标题")
    source_artifact = repository.create_artifact(project.project_id, "copywriting", "文案")
    source_content = _copy_output()
    source_content.update({"schema_version": 1, "artifact_type": "copywriting"})
    source_version = repository.append_artifact_version(source_artifact.artifact_id, content=source_content)
    port = FakeLLMPort(_title_output())
    run = repository.create_app_run(
        project.project_id,
        "builtin.viral-titles",
        "1.0.0",
        {"platform": "douyin", "objective": "click", "count": 5, "source_artifact_version_id": source_version.artifact_version_id},
        idempotency_key="title-source-run-001",
    )
    asyncio.run(StructuredLLMExecutor(repository, port, app_id="builtin.viral-titles").execute(run))
    assert port.requests[0].prompt_variables["input"]["resolved_source_content"]["artifact_type"] == "copywriting"


def test_title_executor_rejects_non_copywriting_source_artifact(tmp_path):
    repository = AppCenterRepository(tmp_path / "title-source-type.sqlite")
    project = repository.create_project("AC-3 来源", "拒绝错误类型")
    source_artifact = repository.create_artifact(project.project_id, "video", "视频")
    source_version = repository.append_artifact_version(source_artifact.artifact_id, content={"url": "local"})
    run = repository.create_app_run(
        project.project_id,
        "builtin.viral-titles",
        "1.0.0",
        {"platform": "douyin", "objective": "click", "count": 5, "source_artifact_version_id": source_version.artifact_version_id},
        idempotency_key="title-source-type-001",
    )
    with pytest.raises(AppLLMPortError) as raised:
        asyncio.run(StructuredLLMExecutor(repository, FakeLLMPort(_title_output()), app_id="builtin.viral-titles").execute(run))
    assert raised.value.code == "APP_INPUT_INVALID"


def test_builtin_executor_factory_registers_only_the_two_ac3_structured_apps(tmp_path):
    repository = AppCenterRepository(tmp_path / "factory.sqlite")
    executors = build_builtin_structured_executors(repository, FakeLLMPort(_copy_output()))
    assert set(executors) == {"builtin.marketing-copy", "builtin.viral-titles"}
    assert all(isinstance(executor, StructuredLLMExecutor) for executor in executors.values())


def test_title_normalization_removes_unicode_whitespace_and_punctuation():
    assert normalize_text(" A，\nB\t。 ") == "ab"
