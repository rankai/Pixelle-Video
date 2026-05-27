from web.ip_broadcast import status_ui


class AttrDict(dict):
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError as e:
            raise AttributeError(key) from e

    def __setattr__(self, key, value):
        self[key] = value


def test_set_step_notice_stores_kind_and_message(monkeypatch):
    session = AttrDict()
    monkeypatch.setattr(status_ui.st, "session_state", session)

    status_ui.set_step_notice(3, "success", "语音生成成功")

    assert session["_ipb_step_3_notice"] == {
        "kind": "success",
        "message": "语音生成成功",
    }


def test_render_notice_uses_matching_streamlit_background(monkeypatch):
    calls = []
    monkeypatch.setattr(status_ui.st, "success", lambda message: calls.append(("success", message)))
    monkeypatch.setattr(status_ui.st, "error", lambda message: calls.append(("error", message)))
    monkeypatch.setattr(status_ui.st, "warning", lambda message: calls.append(("warning", message)))
    monkeypatch.setattr(status_ui.st, "info", lambda message: calls.append(("info", message)))

    status_ui.render_notice("success", "完成")
    status_ui.render_notice("error", "失败")
    status_ui.render_notice("warning", "注意")
    status_ui.render_notice("info", "进行中")

    assert calls == [
        ("success", "完成"),
        ("error", "失败"),
        ("warning", "注意"),
        ("info", "进行中"),
    ]


def test_global_loading_can_be_closed(monkeypatch):
    calls = []

    class FakePlaceholder:
        def markdown(self, message, unsafe_allow_html=False):
            calls.append(("markdown", message, unsafe_allow_html))

        def empty(self):
            calls.append(("empty",))

    placeholder = FakePlaceholder()
    monkeypatch.setattr(status_ui.st, "empty", lambda: placeholder)

    returned = status_ui.show_global_loading("处理中")
    status_ui.hide_global_loading(returned)

    assert returned is placeholder
    assert calls[0][0] == "markdown"
    assert "处理中" in calls[0][1]
    assert calls[-1] == ("empty",)
