from web.ip_broadcast import state
from web.ip_broadcast.modules import m2_copywriting


def test_final_script_editor_uses_separate_widget_key(monkeypatch):
    session = {}
    state.init_ip_broadcast_state(session)
    state.set_final_script("生成后的文案", session=session)
    monkeypatch.setattr(m2_copywriting.st, "session_state", session)

    m2_copywriting._ensure_editor_matches_final_script()

    assert session["ipb_final_script"] == "生成后的文案"
    assert session["ipb_final_script_editor"] == "生成后的文案"
    assert "ipb_final_script_editor" != "ipb_final_script"


def test_rewrite_source_is_current_final_script(monkeypatch):
    session = {}
    state.init_ip_broadcast_state(session)
    session["ipb_source_text"] = "旧参考原文"
    state.set_final_script("当前最终文案", session=session)
    monkeypatch.setattr(m2_copywriting.st, "session_state", session)

    assert m2_copywriting._get_source_text() == "当前最终文案"


def test_request_generate_defers_long_running_rewrite(monkeypatch):
    session = {}
    state.init_ip_broadcast_state(session)
    rerun_called = []
    monkeypatch.setattr(m2_copywriting.st, "session_state", session)
    monkeypatch.setattr(m2_copywriting.st, "rerun", lambda: rerun_called.append(True))

    m2_copywriting._request_generate()

    assert session["_ipb_deferred_action"] == m2_copywriting.DEFERRED_ACTION_M2_GENERATE
    assert session["_ipb_m2_generation_pending"] is True
    assert session["_ipb_m2_last_success"] == ""
    assert session["_ipb_m2_last_error"] == ""
    assert rerun_called == [True]


def test_generation_status_message_prefers_pending_state(monkeypatch):
    session = {}
    state.init_ip_broadcast_state(session)
    session["_ipb_m2_generation_pending"] = True
    monkeypatch.setattr(m2_copywriting.st, "session_state", session)

    assert m2_copywriting._generation_status_message() == ("info", "AI 正在改写/优化文案，请稍候...")


def test_generation_status_message_shows_last_success(monkeypatch):
    session = {}
    state.init_ip_broadcast_state(session)
    session["_ipb_m2_last_success"] = "文案生成完成"
    monkeypatch.setattr(m2_copywriting.st, "session_state", session)

    assert m2_copywriting._generation_status_message() == ("success", "文案生成完成")
