"""IP Broadcast Page - 老板IP口播智能体"""

import sys
from pathlib import Path

_script_dir = Path(__file__).resolve().parent
_project_root = _script_dir.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import streamlit as st

from web.state.session import init_session_state, init_i18n, get_pixelle_video
from web.components.header import render_header
from web.components.settings import render_advanced_settings
from web.components.faq import render_faq_sidebar

st.set_page_config(
    page_title="IP口播 - AI-Video-Factory",
    page_icon="🎙️",
    layout="wide",
    initial_sidebar_state="collapsed",
)


def main():
    init_session_state()
    init_i18n()
    render_header()
    render_faq_sidebar()
    pixelle_video = get_pixelle_video()
    render_advanced_settings()

    from web.ip_broadcast.page import render_ip_broadcast_page
    render_ip_broadcast_page(pixelle_video)


if __name__ == "__main__":
    main()
