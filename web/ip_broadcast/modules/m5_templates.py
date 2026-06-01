import base64
import html
import mimetypes
from pathlib import Path

import streamlit as st

from pixelle_video.services.ip_broadcast_templates import list_ip_broadcast_templates
from web.utils.streamlit_helpers import safe_rerun


def render_template_selector() -> None:
    templates = list_ip_broadcast_templates()
    current_id = st.session_state.get("ipb_m5_template_id", templates[0].template_id)
    template_ids = [item.template_id for item in templates]
    if current_id not in template_ids:
        current_id = templates[0].template_id

    st.markdown("**画面模板**")
    cols = st.columns(len(templates))
    for col, template in zip(cols, templates):
        with col:
            selected = template.template_id == current_id
            with st.container(border=True):
                render_template_preview(template.preview_image_path)
                st.markdown(
                    build_card_text_html(
                        title=template.display_name,
                        subtitle=template.short_description,
                        tooltip=template.full_description,
                    ),
                    unsafe_allow_html=True,
                )
                if selected:
                    st.button(
                        "已选择",
                        key=f"ipb_m5_template_selected_{template.template_id}",
                        use_container_width=True,
                        disabled=True,
                        type="primary",
                    )
                elif st.button(
                    "选择",
                    key=f"ipb_m5_template_select_{template.template_id}",
                    use_container_width=True,
                ):
                    st.session_state.ipb_m5_template_id = template.template_id
                    safe_rerun()
    st.session_state.ipb_m5_template_id = st.session_state.get("ipb_m5_template_id", current_id)


def render_template_preview(preview_path: str) -> None:
    path = Path(preview_path)
    if not path.exists():
        st.markdown(build_template_missing_preview_html(height=180), unsafe_allow_html=True)
        return
    st.markdown(build_template_preview_html(str(path), height=180), unsafe_allow_html=True)


def build_card_text_html(title: str, subtitle: str, tooltip: str = "") -> str:
    safe_title = html.escape(title)
    safe_subtitle = html.escape(subtitle)
    safe_tooltip = html.escape(tooltip or subtitle, quote=True)
    return f"""
    <div style="padding:8px 2px 2px;">
        <div style="min-height:20px; display:flex; align-items:flex-start;
                    font-size:14px; line-height:20px; font-weight:700; color:#111827;">
            {safe_title}
        </div>
        <div title="{safe_tooltip}"
             style="min-height:34px; font-size:12px; line-height:17px; color:#6b7280;
                    display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical;
                    overflow:hidden;">
            {safe_subtitle}
        </div>
    </div>
    """


def build_template_preview_html(preview_path: str, height: int = 180) -> str:
    path = Path(preview_path)
    mime_type = mimetypes.guess_type(path.name)[0] or "image/png"
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"""
    <div style="height:{height}px; border:1px solid #e5e7eb; border-radius:6px;
                overflow:hidden; background:#f8fafc; display:flex; align-items:center;
                justify-content:center;">
        <img src="data:{mime_type};base64,{data}" alt="画面模板效果图"
             style="width:100%; height:{height}px; object-fit:contain; display:block;" />
    </div>
    """


def build_template_missing_preview_html(height: int = 180) -> str:
    return f"""
    <div style="height:{height}px; border:1px dashed #cbd5e1; border-radius:6px;
                background:#f8fafc; display:flex; align-items:center; justify-content:center;
                color:#94a3b8; font-size:13px;">
        暂无效果图
    </div>
    """
