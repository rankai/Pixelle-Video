from dataclasses import dataclass

from web.ip_broadcast import runner, state


class AttrDict(dict):
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError as e:
            raise AttributeError(key) from e

    def __setattr__(self, key, value):
        self[key] = value


@dataclass
class FakeRunnerSpec:
    step: int
    label: str
    runner: object


def _session():
    session = AttrDict()
    state.init_ip_broadcast_state(session)
    return session


def test_run_ipb_step_success_sets_done_status_and_notice(monkeypatch):
    session = _session()
    state.set_final_script("final copy", session=session)
    notices = []

    def fake_runner(_pixelle_video):
        return "runner-token"

    monkeypatch.setattr(runner.st, "session_state", session)
    monkeypatch.setattr(
        runner,
        "_get_step_runner",
        lambda _key: FakeRunnerSpec(3, "声音生成", fake_runner),
    )
    monkeypatch.setattr(runner, "run_async", lambda coro: True)
    monkeypatch.setattr(runner, "set_step_notice", lambda *args: notices.append(args))

    ok = runner.run_ipb_step("voice", object())

    assert ok is True
    assert session["ipb_step_status"][3] == "done"
    assert notices[-1] == (3, "success", "声音生成完成")


def test_run_ipb_step_false_result_sets_error_notice_and_preserves_outputs(monkeypatch, tmp_path):
    session = _session()
    state.set_final_script("final copy", session=session)
    audio_path = tmp_path / "voice.mp3"
    audio_path.write_bytes(b"audio")
    session["ipb_m3_audio_path"] = str(audio_path)
    notices = []

    def fake_runner(_pixelle_video):
        return "runner-token"

    monkeypatch.setattr(runner.st, "session_state", session)
    monkeypatch.setattr(
        runner,
        "_get_step_runner",
        lambda _key: FakeRunnerSpec(3, "声音生成", fake_runner),
    )
    monkeypatch.setattr(
        runner,
        "get_next_action",
        lambda: state.NextAction("voice", 3, "生成语音", "使用最终口播文案合成配音"),
    )
    monkeypatch.setattr(runner, "run_async", lambda coro: False)
    monkeypatch.setattr(runner, "set_step_notice", lambda *args: notices.append(args))

    ok = runner.run_ipb_step("voice", object())

    assert ok is False
    assert session["ipb_step_status"][3] == "error"
    assert session["ipb_m3_audio_path"] == str(audio_path)
    assert notices[-1] == (3, "error", "声音生成执行失败")


def test_run_ipb_step_exception_sets_error_notice(monkeypatch):
    session = _session()
    state.set_final_script("final copy", session=session)
    notices = []

    def fake_runner(_pixelle_video):
        return "runner-token"

    def raise_from_run_async(_coro):
        raise RuntimeError("boom")

    monkeypatch.setattr(runner.st, "session_state", session)
    monkeypatch.setattr(
        runner,
        "_get_step_runner",
        lambda _key: FakeRunnerSpec(3, "声音生成", fake_runner),
    )
    monkeypatch.setattr(runner, "run_async", raise_from_run_async)
    monkeypatch.setattr(runner, "set_step_notice", lambda *args: notices.append(args))

    ok = runner.run_ipb_step("voice", object())

    assert ok is False
    assert session["ipb_step_status"][3] == "error"
    assert notices[-1] == (3, "error", "boom")


def test_run_ipb_step_stops_on_missing_dependency_without_running(monkeypatch):
    session = _session()
    calls = []
    notices = []

    def fake_runner(_pixelle_video):
        calls.append("ran")
        return "runner-token"

    monkeypatch.setattr(runner.st, "session_state", session)
    monkeypatch.setattr(
        runner,
        "_get_step_runner",
        lambda _key: FakeRunnerSpec(3, "声音生成", fake_runner),
    )
    monkeypatch.setattr(runner, "set_step_notice", lambda *args: notices.append(args))

    ok = runner.run_ipb_step("voice", object())

    assert ok is False
    assert calls == []
    assert session["ipb_step_status"][3] == "pending"
    assert notices[-1] == (3, "warning", "先选择素材来源并生成可用文案")
