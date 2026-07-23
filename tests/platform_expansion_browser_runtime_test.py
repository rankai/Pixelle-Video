import asyncio

from pixelle_video.services.publish.browser_runtime import (
    PlaywrightPublishContext,
    _file_input_selected,
)


class _FakeChooser:
    def __init__(self, page, kind):
        self.page = page
        self.kind = kind
        self.paths = []

    async def set_files(self, path):
        self.paths.append(path)
        if self.kind == "video":
            self.page.video_uploaded = True
        else:
            self.page.cover_uploaded = True


class _FakeFileChooserExpectation:
    def __init__(self, page, kind):
        self.page = page
        self.kind = kind
        self.chooser = _FakeChooser(page, kind)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    @property
    def value(self):
        async def get_value():
            return self.chooser

        return get_value()


class _FakeLocator:
    def __init__(self, page, kind, index=0):
        self.page = page
        self.kind = kind
        self.index = index

    def nth(self, index):
        return _FakeLocator(self.page, self.kind, index)

    @property
    def first(self):
        return self

    @property
    def last(self):
        return self

    async def count(self):
        state = self.page
        if self.kind == "resume":
            return int(state.resume_visible)
        if self.kind == "cover_labels":
            return 2
        if self.kind == "dialog":
            return int(state.modal)
        if self.kind == "upload_button":
            return int(state.modal and not state.cover_uploaded)
        if self.kind == "confirm":
            return int(state.modal and state.cover_uploaded)
        if self.kind in {"upload_tab", "upload_video_button"}:
            return int(state.modal if self.kind == "upload_tab" else not state.video_uploaded)
        if self.kind == "video":
            return int(state.video_uploaded or state.unrelated_video)
        if self.kind == "scoped_video":
            return int(state.video_uploaded)
        if self.kind == "cover_preview":
            return int(state.cover_uploaded)
        if self.kind in {"body", "file_input"}:
            return 1
        return 0

    async def is_visible(self):
        return (await self.count()) > 0

    async def click(self):
        if self.kind == "resume":
            self.page.resume_visible = False
            self.page.video_uploaded = True
        elif self.kind == "cover_labels":
            self.page.modal = True
        elif self.kind == "confirm":
            self.page.modal = False

    async def inner_text(self):
        return "上传封面"

    async def get_attribute(self, name, **_kwargs):
        if self.kind == "cover_preview" and name in {"src", "currentSrc", "data-cover-url"}:
            return "blob:volatile-preview"
        return None

    async def evaluate(self, _script):
        return {
            "src": "blob:uploaded-video",
            "poster": "",
            "width": 640,
            "height": 360,
        }

    def get_by_role(self, role, *, name=None, exact=None):
        del exact
        if role == "button" and name == "上传视频":
            return _FakeLocator(self.page, "upload_video_button")
        if role == "button" and name == "上传图片":
            return _FakeLocator(self.page, "upload_button")
        if role == "button" and name == "确认":
            return _FakeLocator(self.page, "confirm")
        return _FakeLocator(self.page, "dialog")

    def get_by_text(self, text, *, exact=None):
        del exact
        if text == "上传封面":
            return _FakeLocator(self.page, "upload_tab")
        return _FakeLocator(self.page, "none")


class _FakePage:
    def __init__(self):
        self.video_uploaded = False
        self.cover_uploaded = False
        self.modal = False
        self.resume_visible = False
        self.fail_chooser = False
        self.unrelated_video = False
        self.chooser_expectations = []

    def locator(self, selector):
        if selector == "video":
            return _FakeLocator(self, "video")
        if "video" in selector and ("main" in selector or "preview" in selector or "upload" in selector or "editor" in selector):
            return _FakeLocator(self, "scoped_video")
        if selector == "body":
            return _FakeLocator(self, "body")
        if "cover" in selector or "default-cover" in selector:
            return _FakeLocator(self, "cover_preview")
        return _FakeLocator(self, "none")

    def get_by_role(self, role, *, name=None, exact=None):
        del exact
        if role == "dialog":
            return _FakeLocator(self, "dialog")
        if role == "button" and name == "继续编辑":
            return _FakeLocator(self, "resume")
        if role == "button" and name == "上传视频":
            return _FakeLocator(self, "upload_video_button")
        return _FakeLocator(self, "none")

    def get_by_text(self, text, *, exact=None):
        del exact
        if text == "封面设置":
            return _FakeLocator(self, "cover_labels")
        return _FakeLocator(self, "none")

    def expect_file_chooser(self, **_kwargs):
        if self.fail_chooser:
            raise RuntimeError("chooser unavailable")
        kind = "cover" if self.modal else "video"
        expectation = _FakeFileChooserExpectation(self, kind)
        self.chooser_expectations.append(expectation)
        return expectation

    async def wait_for_timeout(self, _ms):
        return None


class _FakeWujieRoot:
    pass


class _FakeShipinhaoPage(_FakePage):
    def __init__(self):
        super().__init__()
        self.wujie_root = _FakeWujieRoot()

    def locator(self, selector):
        if selector == "wujie-app":
            return _FakeWujieHost(self.wujie_root)
        return super().locator(selector)


class _FakeWujieHost:
    def __init__(self, root):
        self.root = root

    @property
    def first(self):
        return self

    async def count(self):
        return 1


def test_shipinhao_editor_selectors_use_wujie_app_root():
    async def run():
        page = _FakeShipinhaoPage()
        context = PlaywrightPublishContext(object(), "shipinhao")
        context.page = page
        root = await context._content_root()
        assert isinstance(root, _FakeWujieHost)
        assert root.root is page.wujie_root

    asyncio.run(run())


class _SelectedFileLocator:
    @property
    def first(self):
        return self

    @property
    def last(self):
        return self

    def nth(self, _index):
        return self

    async def count(self):
        return 1

    async def evaluate(self, _script):
        return True


class _SelectedFileRoot:
    def locator(self, _selector):
        return _SelectedFileLocator()


def test_shipinhao_cover_file_readback_uses_scoped_root_after_input_replacement():
    async def run():
        root = _SelectedFileRoot()
        assert await _file_input_selected(root, "image") is True

    asyncio.run(run())


class _ClosedNavigationPage:
    def __init__(self, context):
        self.context = context

    async def goto(self, _url, **_kwargs):
        self.context.pages.append(_LiveNavigationPage())

    def is_closed(self):
        return True


class _LiveNavigationPage:
    def is_closed(self):
        return False


class _NavigationContext:
    def __init__(self):
        self.pages = []


def test_open_creator_page_rebinds_to_platform_shell_replacement_tab():
    async def run():
        context = _NavigationContext()
        context.pages = [_ClosedNavigationPage(context)]
        runtime_context = PlaywrightPublishContext(context, "xiaohongshu")
        await runtime_context.open_creator_page()
        assert isinstance(runtime_context.page, _LiveNavigationPage)

    asyncio.run(run())


def test_hidden_challenge_copy_does_not_override_authenticated_editor_state():
    class Body:
        first = None

        async def get_attribute(self, name):
            return {"data-state": "editor_ready", "data-auth-state": "signed_in"}.get(name)

    Body.first = Body()

    class HiddenLocator:
        async def count(self):
            return 0

        def nth(self, _index):
            return self

        async def is_visible(self):
            return False

    class HiddenChallengePage:
        url = "https://creator.xiaohongshu.com/publish/publish?source=official"

        def is_closed(self):
            return False

        def locator(self, selector):
            return Body.first if selector == "body" else HiddenLocator()

        def get_by_text(self, _text, *, exact=False):
            del exact
            return HiddenLocator()

        async def content(self):
            return "<main>风险验证 captcha</main>"

    async def run():
        context = PlaywrightPublishContext(object(), "xiaohongshu")
        context.page = HiddenChallengePage()
        assert await context.detect_state() == "editor_ready"

    asyncio.run(run())


def test_kuaishou_upload_video_uses_project_playwright_filechooser_and_is_idempotent():
    async def run():
        page = _FakePage()
        context = PlaywrightPublishContext(object(), "kuaishou")
        context.page = page
        assert await context.upload_video("/tmp/video.mp4") is True
        assert page.chooser_expectations[0].chooser.paths == ["/tmp/video.mp4"]
        assert await context.upload_video("/tmp/video.mp4") is True
        assert len(page.chooser_expectations) == 1

    asyncio.run(run())


def test_kuaishou_preview_probe_ignores_unrelated_visible_video():
    async def run():
        page = _FakePage()
        page.unrelated_video = True
        context = PlaywrightPublishContext(object(), "kuaishou")
        context.page = page
        assert await context._has_uploaded_media_preview() is False

    asyncio.run(run())


def test_kuaishou_continue_editing_reuses_existing_preview_without_chooser():
    async def run():
        page = _FakePage()
        page.resume_visible = True
        context = PlaywrightPublishContext(object(), "kuaishou")
        context.page = page
        assert await context.upload_video("/tmp/video.mp4") is True
        assert page.chooser_expectations == []

    asyncio.run(run())


def test_kuaishou_video_chooser_failure_is_fail_closed():
    async def run():
        page = _FakePage()
        page.fail_chooser = True
        context = PlaywrightPublishContext(object(), "kuaishou")
        context.page = page
        assert await context.upload_video("/tmp/video.mp4") is False

    asyncio.run(run())


def test_xiaohongshu_upload_waits_for_scoped_preview_readback():
    class Locator:
        def __init__(self, page, selector):
            self.page = page
            self.selector = selector

        @property
        def first(self):
            return self

        def nth(self, _index):
            return self

        async def count(self):
            if self.selector == "input[type='file'][accept*='video']":
                return 1
            if self.selector == "main video":
                return int(self.page.video_uploaded)
            if self.selector == "body":
                return 1
            return 0

        async def set_input_files(self, _path):
            self.page.video_uploaded = True

        async def is_visible(self):
            return self.selector == "main video" and self.page.video_uploaded

    class Page:
        url = "https://creator.xiaohongshu.com/publish/publish?source=official"

        def __init__(self):
            self.video_uploaded = False

        def locator(self, selector):
            return Locator(self, selector)

        async def wait_for_timeout(self, _ms):
            return None

    async def run():
        page = Page()
        context = PlaywrightPublishContext(object(), "xiaohongshu")
        context.page = page
        assert await context.upload_video("/tmp/video.mp4") is True

    asyncio.run(run())


def test_xiaohongshu_cover_opens_modal_sets_image_and_confirms():
    class Locator:
        def __init__(self, page, kind):
            self.page = page
            self.kind = kind

        @property
        def first(self):
            return self

        def nth(self, _index):
            return self

        async def count(self):
            if self.kind == "trigger":
                return 1
            if self.kind == "image_input":
                return int(self.page.modal)
            if self.kind == "confirm":
                return int(self.page.modal and self.page.cover_uploaded)
            if self.kind == "modal":
                return int(self.page.modal)
            if self.kind == "body":
                return 1
            return 0

        async def is_visible(self):
            return self.kind in {"trigger", "confirm"} and await self.count() > 0

        async def click(self, **_kwargs):
            if self.kind == "trigger":
                self.page.modal = True
            elif self.kind == "confirm":
                self.page.modal = False

        async def set_input_files(self, _path):
            self.page.cover_uploaded = True

    class Page:
        url = "https://creator.xiaohongshu.com/publish/publish?source=official"

        def __init__(self):
            self.modal = False
            self.cover_uploaded = False

        def locator(self, selector):
            if selector == ".upload-cover":
                return Locator(self, "trigger")
            if selector == "input[type='file'][accept*='image']":
                return Locator(self, "image_input")
            if selector == ".cover-modal":
                return Locator(self, "modal")
            if selector == "body":
                return Locator(self, "body")
            return Locator(self, "none")

        def get_by_role(self, role, *, name=None, exact=None):
            del exact
            if role == "button" and name == "确定":
                return Locator(self, "confirm")
            return Locator(self, "none")

        async def wait_for_timeout(self, _ms):
            return None

    async def run():
        page = Page()
        context = PlaywrightPublishContext(object(), "xiaohongshu")
        context.page = page
        assert await context.upload_cover("/tmp/cover.png") is True
        assert await context.read_cover_receipt("/tmp/cover.png") is not None

    asyncio.run(run())


def test_kuaishou_cover_dialog_uses_visible_upload_and_confirm_flow():
    async def run():
        page = _FakePage()
        context = PlaywrightPublishContext(object(), "kuaishou")
        context.page = page
        assert await context.upload_cover("/tmp/cover.png") is True
        assert page.chooser_expectations[0].chooser.paths == ["/tmp/cover.png"]
        assert page.modal is False
        assert await context._read_cover_urls() == ["blob:accepted-preview"]

    asyncio.run(run())
