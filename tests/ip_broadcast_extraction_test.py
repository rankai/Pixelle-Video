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


def test_extract_douyin_id_accepts_search_modal_id():
    from pixelle_video.services.script_extractor import _extract_douyin_id

    url = (
        "https://www.douyin.com/jingxuan/search/%E5%8F%A3%E6%92%AD"
        "?aid=8cbdb26a-85a1-4fb3-8112-dc4ec1f1c79d"
        "&modal_id=7585777774662700346&type=general"
    )

    assert _extract_douyin_id(url) == "7585777774662700346"


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


@pytest.mark.asyncio
async def test_douyin_search_modal_url_uses_modal_id_before_ytdlp(monkeypatch):
    extractor = VideoScriptExtractor(api_key="fake", base_url="https://example.com")
    calls = []

    async def fake_extract_douyin(video_id):
        calls.append(("douyin", video_id))
        return "搜索页视频口播文案"

    async def fake_direct_url(url):
        calls.append(("direct", url))
        return ""

    monkeypatch.setattr(extractor, "_extract_douyin", fake_extract_douyin)
    monkeypatch.setattr(extractor, "_get_ytdlp_direct_video_url", fake_direct_url)

    result = await extractor.extract(
        "https://www.douyin.com/jingxuan/search/%E5%8F%A3%E6%92%AD"
        "?aid=8cbdb26a-85a1-4fb3-8112-dc4ec1f1c79d"
        "&modal_id=7585777774662700346&type=general"
    )

    assert result == "搜索页视频口播文案"
    assert calls == [("douyin", "7585777774662700346")]
