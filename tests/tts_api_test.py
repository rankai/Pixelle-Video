from api.routers import tts as tts_router
from api.schemas.tts import TTSSynthesizeRequest


class FakePixelleVideo:
    def __init__(self):
        self.tts_kwargs = None

    async def tts(self, **kwargs):
        self.tts_kwargs = kwargs
        return "output/preview.mp3"


async def test_tts_synthesize_passes_desktop_voice_preview_params(monkeypatch):
    fake = FakePixelleVideo()
    monkeypatch.setattr(tts_router, "get_audio_duration", lambda _path: 1.25)

    result = await tts_router.tts_synthesize(
        TTSSynthesizeRequest(
            text="试听这条解说音色",
            inference_mode="local",
            voice="zh-CN-XiaoxiaoNeural",
            speed=1.2,
            pitch=0,
            volume=0,
        ),
        fake,
    )

    assert fake.tts_kwargs == {
        "text": "试听这条解说音色",
        "inference_mode": "local",
        "voice": "zh-CN-XiaoxiaoNeural",
        "speed": 1.2,
        "pitch": 0,
        "volume": 0,
    }
    assert result.audio_path == "output/preview.mp3"
    assert result.duration == 1.25
