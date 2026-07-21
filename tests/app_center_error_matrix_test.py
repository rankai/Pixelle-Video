"""Deterministic error-boundary matrix for the application-center LLM port.

These tests intentionally replace the provider service with a local fake.  They
verify stable product error codes without making network calls or retrying a
real provider.
"""

import asyncio

import pytest

from pixelle_video.app_center.llm_port import (
    AppLLMPortError,
    ConfigAppLLMPort,
    StructuredGenerationRequest,
    StructuredGenerationResponse,
)
from pixelle_video.config import config_manager
from pixelle_video.config.schema import PixelleVideoConfig


def _request(**overrides) -> StructuredGenerationRequest:
    values = {
        "app_id": "builtin.marketing-copy",
        "prompt_version": "v1",
        "input_schema_ref": "copy-input.v1",
        "output_schema_ref": "copy-output.v1",
        "prompt_variables": {"store": "测试店"},
        "context": {},
        "request_id": "error-matrix-request",
        "idempotency_key": "error-matrix-idempotency",
    }
    values.update(overrides)
    return StructuredGenerationRequest(**values)


class RaisingService:
    def __init__(self, error: BaseException):
        self.error = error
        self.calls = 0

    async def __call__(self, **_kwargs):
        self.calls += 1
        raise self.error


class RecordingService:
    def __init__(self):
        self.prompts = []

    async def __call__(self, **kwargs):
        self.prompts.append(kwargs["prompt"])
        return {"ok": True}


@pytest.mark.parametrize(
    ("message", "expected_code"),
    [
        ("401 unauthorized: provider rejected credentials", "LLM_AUTH_FAILED"),
        ("429 rate limit exceeded", "LLM_RATE_LIMITED"),
        ("invalid JSON schema in provider response", "STRUCTURED_OUTPUT_INVALID"),
        ("provider offline", "LLM_PROVIDER_FAILED"),
    ],
)
def test_config_llm_port_maps_provider_failures_to_stable_codes(monkeypatch, message, expected_code):
    monkeypatch.setattr(
        config_manager,
        "config",
        PixelleVideoConfig(llm={"api_key": "test-key", "base_url": "http://provider.test", "model": "test-model"}),
    )
    service = RaisingService(RuntimeError(message))

    with pytest.raises(AppLLMPortError) as raised:
        asyncio.run(ConfigAppLLMPort(service).generate_structured(_request()))

    assert raised.value.code == expected_code
    assert str(raised.value) == "大模型调用失败"
    assert raised.value.diagnostic == "RuntimeError"
    assert service.calls == 1


def test_config_llm_port_maps_timeout_without_retry(monkeypatch):
    monkeypatch.setattr(
        config_manager,
        "config",
        PixelleVideoConfig(llm={"api_key": "test-key", "base_url": "http://provider.test", "model": "test-model"}),
    )
    service = RaisingService(asyncio.TimeoutError())

    with pytest.raises(AppLLMPortError) as raised:
        asyncio.run(ConfigAppLLMPort(service).generate_structured(_request(timeout_ms=1000)))

    assert raised.value.code == "LLM_TIMEOUT"
    assert service.calls == 1


def test_config_llm_port_fails_closed_when_llm_is_not_configured(monkeypatch):
    monkeypatch.setattr(config_manager, "config", PixelleVideoConfig())
    service = RaisingService(RuntimeError("must not be called"))

    with pytest.raises(AppLLMPortError) as raised:
        asyncio.run(ConfigAppLLMPort(service).generate_structured(_request()))

    assert raised.value.code == "LLM_CONFIGURATION_MISSING"
    assert service.calls == 0


def test_config_llm_port_reads_model_config_change_without_reconstruction(monkeypatch):
    service = RecordingService()
    port = ConfigAppLLMPort(service)
    monkeypatch.setattr(
        config_manager,
        "config",
        PixelleVideoConfig(llm={"api_key": "first-key", "base_url": "http://provider.test", "model": "first-model"}),
    )
    first = asyncio.run(port.generate_structured(_request(request_id="config-first")))

    monkeypatch.setattr(
        config_manager,
        "config",
        PixelleVideoConfig(llm={"api_key": "second-key", "base_url": "http://provider.test", "model": "second-model"}),
    )
    second = asyncio.run(port.generate_structured(_request(request_id="config-second")))

    assert isinstance(first, StructuredGenerationResponse)
    assert isinstance(second, StructuredGenerationResponse)
    assert first.model_ref == "local-default:first-model"
    assert second.model_ref == "local-default:second-model"
    assert len(service.prompts) == 2
    assert "first-key" not in service.prompts[0] + service.prompts[1]
    assert "second-key" not in service.prompts[0] + service.prompts[1]
