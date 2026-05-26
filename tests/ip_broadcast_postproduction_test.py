from web.ip_broadcast.modules.m5_postproduction import _build_bgm_mix_command


def test_bgm_mix_command_uses_voice_audio_as_duration_source():
    cmd = _build_bgm_mix_command(
        merged_video="/tmp/merged.mp4",
        bgm_path="/tmp/long-bgm.mp3",
        output_path="/tmp/out.mp4",
        bgm_volume=0.3,
        voice_volume=1.0,
    )

    filter_index = cmd.index("-filter_complex") + 1

    assert "[voice][bgm]amix=inputs=2:duration=first[aout]" in cmd[filter_index]
    assert "-shortest" in cmd
