import pytest

from pixelle_video.services.script_extractor import VideoScriptExtractor


@pytest.mark.asyncio
async def test_extract_rejects_share_text_without_resolvable_video_url():
    extractor = VideoScriptExtractor(api_key="fake", base_url="https://example.com")

    with pytest.raises(ValueError, match="抖音分享口令.*TIKHUB_API_KEY"):
        await extractor.extract(
            "0.58 复制打开抖音，看看【宫野剪辑日记的作品】口播剪辑练习 "
            "素材来自@剪辑师晨晨 #剪辑 #口播剪辑 - 抖音 I@V.yg VyG:/ :9pm 09/09"
        )


def test_douyin_short_url_candidates_include_command_variants():
    from pixelle_video.services.script_extractor import _douyin_short_url_candidates

    candidates = _douyin_short_url_candidates("复制打开抖音 I@V.yg VyG:/ :9pm 09/09")

    assert "https://v.douyin.com/I@V.ygVyG/" in candidates
    assert "https://v.douyin.com/IVygVyG/" in candidates


def test_ytdlp_base_command_uses_current_python_module():
    import sys

    from pixelle_video.services.script_extractor import _ytdlp_base_cmd

    assert _ytdlp_base_cmd() == [sys.executable, "-m", "yt_dlp"]


@pytest.mark.asyncio
async def test_douyin_url_uses_ytdlp_direct_url_before_generic_fallback(monkeypatch):
    extractor = VideoScriptExtractor(api_key="fake", base_url="https://example.com")
    calls = []

    async def fake_direct_url(url):
        calls.append(("direct", url))
        return "https://cdn.example.com/video.mp4"

    async def fake_transcribe(url):
        calls.append(("transcribe", url))
        return "真实口播文案"

    monkeypatch.setattr(extractor, "_get_ytdlp_direct_video_url", fake_direct_url)
    monkeypatch.setattr(extractor, "_transcribe_video_url", fake_transcribe)

    result = await extractor.extract("https://www.douyin.com/user/video")

    assert result == "真实口播文案"
    assert calls == [
        ("direct", "https://www.douyin.com/user/video"),
        ("transcribe", "https://cdn.example.com/video.mp4"),
    ]
