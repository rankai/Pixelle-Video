"""Shared status UI helpers for the IP broadcast production flow."""

import html

import streamlit as st


def set_step_notice(step: int, kind: str, message: str) -> None:
    st.session_state[f"_ipb_step_{step}_notice"] = {"kind": kind, "message": message}


def render_step_notice(step: int) -> None:
    notice = st.session_state.get(f"_ipb_step_{step}_notice")
    if not notice:
        return
    render_notice(str(notice.get("kind") or "info"), str(notice.get("message") or ""))


def render_notice(kind: str, message: str) -> None:
    if not message:
        return
    if kind == "success":
        st.success(message)
    elif kind == "error":
        st.error(message)
    elif kind == "warning":
        st.warning(message)
    else:
        st.info(message)


def show_global_loading(message: str) -> None:
    safe_message = html.escape(message)
    st.markdown(
        f"""
        <div style="
            position: fixed;
            inset: 0;
            z-index: 2147483000;
            background: rgba(15, 23, 42, 0.38);
            display: flex;
            align-items: center;
            justify-content: center;
            pointer-events: none;
        ">
            <div style="
                min-width: min(420px, calc(100vw - 40px));
                padding: 22px 24px;
                border-radius: 8px;
                background: #ffffff;
                box-shadow: 0 18px 48px rgba(15, 23, 42, 0.28);
                border: 1px solid rgba(148, 163, 184, 0.35);
                text-align: center;
                color: #0f172a;
                font-size: 16px;
                line-height: 1.6;
                font-weight: 600;
            ">
                <div style="
                    width: 28px;
                    height: 28px;
                    margin: 0 auto 12px;
                    border: 3px solid #dbeafe;
                    border-top-color: #2563eb;
                    border-radius: 50%;
                    animation: ipbSpin 0.9s linear infinite;
                "></div>
                {safe_message}
            </div>
        </div>
        <style>
            @keyframes ipbSpin {{
                to {{ transform: rotate(360deg); }}
            }}
        </style>
        """,
        unsafe_allow_html=True,
    )
