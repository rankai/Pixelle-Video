import asyncio
import json
from pathlib import Path

import pytest

from pixelle_video.app_center.llm_port import AppLLMPortError, FakeLLMPort
from pixelle_video.app_center.repository import AppCenterRepository
from pixelle_video.app_center.structured_apps import StructuredLLMExecutor

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / "docs/contracts/app-center/fixtures/app-text-entry.json").read_text(encoding="utf-8"))


def _safe_copy_output():
    variants = []
    for index, angle in enumerate(("利益", "好奇", "场景"), start=1):
        full_text = f"门店亮点{index}真实内容到店了解"
        variants.append({
            "version_name": f"版本{index}",
            "angle": angle,
            "hook": f"门店亮点{index}",
            "body": "真实内容",
            "cta": "到店了解",
            "full_text": full_text,
            "word_count": len(full_text),
            "estimated_seconds": (len(full_text) + 3) // 4,
        })
    return {"variants": variants, "missing_facts": [], "risk_flags": []}


@pytest.mark.parametrize("category", FIXTURE["categories"], ids=lambda item: item["id"])
def test_six_store_categories_pass_shared_marketing_contract(tmp_path, category):
    repository = AppCenterRepository(tmp_path / f"{category['id']}.sqlite")
    project = repository.create_project(category["store_type"], category["goal"])
    run = repository.create_app_run(
        project.project_id,
        "builtin.marketing-copy",
        "1.0.0",
        {
            "goal": category["goal"],
            "product_or_service": category["store_type"],
            "content_format": "oral",
            "length_bucket": "short_15s",
            "store_type": category["store_type"],
            "facts": category["facts"],
        },
        idempotency_key=f"fixture-{category['id']}",
    )
    output = asyncio.run(StructuredLLMExecutor(repository, FakeLLMPort(_safe_copy_output()), app_id="builtin.marketing-copy").execute(run))
    assert len(output.content["variants"]) == 3
    assert output.content["validation_facts"]["input"]["store_type"] == category["store_type"]


def test_title_duplicate_normalization_fixture_is_rejected(tmp_path):
    duplicate = {
        "candidates": [
            {"title": "同一个标题", "angle": "场景", "objective": "click", "length": 5, "banned_matches": [], "risk_labels": ["无"]}
            for _ in range(5)
        ],
        "missing_facts": [],
        "risk_flags": [],
    }
    repository = AppCenterRepository(tmp_path / "duplicate.sqlite")
    project = repository.create_project("标题", "重复")
    run = repository.create_app_run(project.project_id, "builtin.viral-titles", "1.0.0", {"platform": "douyin", "objective": "click", "count": 5, "topic": "咖啡"}, idempotency_key="duplicate-title")
    with pytest.raises(AppLLMPortError, match="unique after normalization") as raised:
        asyncio.run(StructuredLLMExecutor(repository, FakeLLMPort(duplicate), app_id="builtin.viral-titles").execute(run))
    assert raised.value.diagnostic == "TITLE_DUPLICATE"


def test_title_banned_term_fixture_is_rejected(tmp_path):
    banned = {
        "candidates": [
            {"title": ("全网第一" if index == 0 else f"咖啡体验{index}"), "angle": "场景", "objective": "click", "length": len("全网第一" if index == 0 else f"咖啡体验{index}"), "banned_matches": [], "risk_labels": ["无"]}
            for index in range(5)
        ],
        "missing_facts": [],
        "risk_flags": [],
    }
    repository = AppCenterRepository(tmp_path / "banned.sqlite")
    project = repository.create_project("标题", "禁用词")
    run = repository.create_app_run(project.project_id, "builtin.viral-titles", "1.0.0", {"platform": "douyin", "objective": "click", "count": 5, "topic": "咖啡"}, idempotency_key="banned-title")
    with pytest.raises(AppLLMPortError, match="banned term"):
        asyncio.run(StructuredLLMExecutor(repository, FakeLLMPort(banned), app_id="builtin.viral-titles").execute(run))
