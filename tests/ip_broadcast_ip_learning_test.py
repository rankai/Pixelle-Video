import pytest

from pixelle_video.services.ip_learning import (
    ProfileFetchBlocked,
    _extract_douyin_profile_video_urls_from_text,
    _extract_first_url,
    _extract_profile_entries,
    _headless_profile_blocked_message,
    _is_login_blocked_message,
    _is_unsupported_url_error,
    extract_many_video_scripts,
    parse_manual_video_inputs,
)
from web.ip_broadcast.modules.m1_benchmark import SOURCE_MODES


def test_source_modes_use_new_ip_learning_labels():
    assert SOURCE_MODES == ["视频链接", "粘贴脚本", "行业+人设", "IP学习"]
    assert "IP大脑" not in SOURCE_MODES
    assert "热点选题" not in SOURCE_MODES


def test_extract_profile_entries_limits_to_latest_five_absolute_urls():
    payload = {
        "entries": [
            {"url": "https://www.douyin.com/video/1"},
            {"webpage_url": "https://www.douyin.com/video/2"},
            {"id": "7123456789012345678"},
            {"url": "/video/4"},
            {"url": "https://www.douyin.com/video/5"},
            {"url": "https://www.douyin.com/video/6"},
        ]
    }

    urls = _extract_profile_entries(payload, limit=5)

    assert urls == [
        "https://www.douyin.com/video/1",
        "https://www.douyin.com/video/2",
        "https://www.douyin.com/video/7123456789012345678",
        "https://www.douyin.com/video/4",
        "https://www.douyin.com/video/5",
    ]


def test_parse_manual_video_inputs_accepts_share_text_blocks():
    text = """
    https://v.douyin.com/abc123/

    0.58 复制打开抖音，看看【某某的作品】口播 - 抖音 https://v.douyin.com/def456/
    """

    assert parse_manual_video_inputs(text) == [
        "https://v.douyin.com/abc123/",
        "0.58 复制打开抖音，看看【某某的作品】口播 - 抖音 https://v.douyin.com/def456/",
    ]


def test_extract_first_url_from_profile_share_text():
    share = "复制打开抖音，看看这个主页 https://www.douyin.com/user/MS4wLjABAAAAabc ，更多精彩"

    assert _extract_first_url(share) == "https://www.douyin.com/user/MS4wLjABAAAAabc"


def test_extract_douyin_profile_video_urls_from_vid_and_links():
    text = """
    https://www.douyin.com/user/MS4wLjAB?vid=7583741167041367359
    <a href="/video/7583741167041367360">视频</a>
    https://www.douyin.com/video/7583741167041367361
    """

    assert _extract_douyin_profile_video_urls_from_text(text, limit=5) == [
        "https://www.douyin.com/video/7583741167041367359",
        "https://www.douyin.com/video/7583741167041367360",
        "https://www.douyin.com/video/7583741167041367361",
    ]


def test_unsupported_url_error_detection():
    assert _is_unsupported_url_error(
        "WARNING: [generic] Falling back on generic information extractor "
        "ERROR: Unsupported URL: https://www.douyin.com/user/MS4w"
    )


@pytest.mark.parametrize(
    "message",
    [
        "please login to view this page",
        "扫码登录后继续",
        "captcha verification required",
        "请先登录",
        "安全验证",
    ],
)
def test_login_blocked_message_detection(message):
    assert _is_login_blocked_message(message)


@pytest.mark.asyncio
async def test_extract_many_continues_when_one_video_fails():
    class FakeExtractor:
        async def extract(self, item):
            if item == "bad":
                raise RuntimeError("需要登录")
            return f"{item} 文案"

    results = await extract_many_video_scripts(FakeExtractor(), ["good", "bad"])

    assert [r.ok for r in results] == [True, False]
    assert results[0].script == "good 文案"
    assert results[1].error == "需要登录"


def test_profile_fetch_blocked_message_is_user_facing():
    err = ProfileFetchBlocked("当前 IP 主页需要登录或验证")

    assert "登录" in str(err)


def test_headless_profile_blocked_message_does_not_suggest_browser_login_retry():
    message = _headless_profile_blocked_message()

    assert "手动粘贴" in message
    assert "本机浏览器登录" not in message
