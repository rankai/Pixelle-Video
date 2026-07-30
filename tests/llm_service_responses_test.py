from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from pixelle_video.services.llm_service import LLMService


class TitlePayload(BaseModel):
    title: str


class FakeResponses:
    def __init__(self, output_text: str):
        self.output_text = output_text
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(output_text=self.output_text, output=[])


class FakeClient:
    def __init__(self, output_text: str):
        self.base_url = "https://ark.cn-beijing.volces.com/api/v3/"
        self.responses = FakeResponses(output_text)
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(
                create=self._unexpected_chat_call,
            )
        )

    async def _unexpected_chat_call(self, **_kwargs):
        raise AssertionError("Ark /api/v3 must not call chat/completions")


def test_ark_v3_is_the_only_automatic_responses_api_route():
    assert LLMService._uses_responses_api("https://ark.cn-beijing.volces.com/api/v3")
    assert LLMService._uses_responses_api("https://ark.cn-beijing.volces.com/api/v3/")
    assert not LLMService._uses_responses_api("https://api.openai.com/v1")
    assert not LLMService._uses_responses_api("https://example.com/api/v3")


@pytest.mark.asyncio
async def test_ark_structured_output_uses_responses_input_text_contract(monkeypatch):
    service = LLMService({})
    client = FakeClient('{"title":"门店新品到店"}')
    monkeypatch.setattr(service, "_create_client", lambda **_kwargs: client)
    monkeypatch.setattr(service, "_get_config_value", lambda key, default=None: {
        "model": "doubao-seed-2-1-pro-260628",
    }.get(key, default))

    result = await service("生成标题", response_type=TitlePayload)

    assert result == TitlePayload(title="门店新品到店")
    assert client.responses.calls == [
        {
            "model": "doubao-seed-2-1-pro-260628",
            "input": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": client.responses.calls[0]["input"][0]["content"][0]["text"],
                        }
                    ],
                }
            ],
        }
    ]
    prompt = client.responses.calls[0]["input"][0]["content"][0]["text"]
    assert "生成标题" in prompt
    assert "JSON Output Format Required" in prompt


@pytest.mark.asyncio
async def test_ark_plain_output_uses_responses_output_text(monkeypatch):
    service = LLMService({})
    client = FakeClient("可用结果")
    monkeypatch.setattr(service, "_create_client", lambda **_kwargs: client)
    monkeypatch.setattr(service, "_get_config_value", lambda key, default=None: {
        "model": "doubao-seed-2-1-pro-260628",
    }.get(key, default))

    assert await service("生成文案") == "可用结果"
