import base64
import mimetypes
from pathlib import Path
from typing import Any

import streamlit as st
from loguru import logger

from pixelle_video.services.video_asset_service import VideoAssetService
from web.ip_broadcast.modules.m5_templates import build_card_text_html
from web.utils.streamlit_helpers import safe_rerun


def get_video_asset_svc() -> VideoAssetService:
    return VideoAssetService()


def render_video_asset_management() -> None:
    svc = get_video_asset_svc()
    with st.expander("视频素材管理", expanded=False):
        assets = svc.list_assets()
        if assets:
            cols_per_row = 3
            rows = [assets[i : i + cols_per_row] for i in range(0, len(assets), cols_per_row)]
            for row in rows:
                cols = st.columns(cols_per_row)
                for col, asset in zip(cols, row):
                    with col:
                        with st.container(border=True):
                            render_video_asset_cover(asset)
                            st.markdown(
                                build_card_text_html(
                                    title=asset.name,
                                    subtitle=format_video_asset_meta(asset),
                                    tooltip=f"{asset.name} · {asset.created_at}",
                                ),
                                unsafe_allow_html=True,
                            )
                            if st.button(
                                "删除",
                                key=f"ipb_video_asset_delete_{asset.asset_id}",
                                use_container_width=True,
                            ):
                                delete_video_asset(svc, asset.asset_id)
        else:
            st.caption("暂无视频素材。")

        st.markdown("**上传新视频素材**")
        name = st.text_input(
            "素材名称",
            key="ipb_video_asset_new_name",
            placeholder="例如：客户案例、门店环境、产品演示",
        )
        uploaded = st.file_uploader(
            "上传视频素材",
            type=["mp4", "mov", "webm"],
            key="ipb_video_asset_uploader",
        )
        if st.button("保存视频素材", key="ipb_video_asset_save_btn", use_container_width=True):
            save_video_asset(svc, name, uploaded)


def render_group_video_asset_selector(group: dict[str, Any]) -> None:
    svc = get_video_asset_svc()
    assets = svc.list_assets()
    if not assets:
        st.warning("暂无视频素材，请先在上方「视频素材管理」里上传。")
        return

    asset_paths = {asset.asset_id: asset.asset_path() for asset in assets}
    options = [""] + [asset.asset_id for asset in assets]
    labels = {"": "请选择视频素材"}
    labels.update({asset.asset_id: asset.name for asset in assets})
    current_id = group.get("video_asset_id", "")
    if current_id not in options:
        current_id = ""
    selected_id = st.selectbox(
        "选择视频素材",
        options=options,
        index=options.index(current_id),
        format_func=lambda asset_id: labels.get(asset_id, asset_id),
        key=f"ipb_overlay_asset_{group['group_id']}",
    )
    if selected_id:
        apply_video_asset_to_group(group, selected_id, asset_paths[selected_id])
        asset = next(item for item in assets if item.asset_id == selected_id)
        render_video_asset_cover(asset, height=90)
    else:
        group["video_asset_id"] = ""
        group["uploaded_video_path"] = ""


def apply_video_asset_to_group(group: dict[str, Any], asset_id: str, asset_path: str) -> None:
    group["video_asset_id"] = asset_id
    group["uploaded_video_path"] = asset_path


def save_video_asset(svc: VideoAssetService, name: str, uploaded) -> None:
    clean_name = name.strip()
    if not clean_name:
        st.warning("请填写素材名称。")
        return
    if uploaded is None:
        st.warning("请上传视频素材。")
        return
    try:
        ext = uploaded.name.rsplit(".", 1)[-1].lower()
        svc.save_asset(clean_name, uploaded.getvalue(), ext)
        st.success(f"视频素材「{clean_name}」已保存。")
        safe_rerun()
    except Exception as e:
        st.error(str(e))
        logger.exception(e)


def delete_video_asset(svc: VideoAssetService, asset_id: str) -> None:
    if video_asset_in_use(asset_id):
        st.warning("该素材正在覆盖组中使用，请先取消对应覆盖组或更换素材。")
        return
    svc.delete_asset(asset_id)
    safe_rerun()


def video_asset_in_use(asset_id: str) -> bool:
    return any(
        group.get("video_asset_id") == asset_id
        for group in st.session_state.get("ipb_visual_groups", [])
    )


def render_video_asset_cover(asset, height: int = 120) -> None:
    if asset.thumbnail_exists():
        st.markdown(
            build_video_asset_cover_html(asset.thumbnail_path(), height=height),
            unsafe_allow_html=True,
        )
        return
    st.markdown(build_video_asset_missing_cover_html(height=height), unsafe_allow_html=True)


def build_video_asset_cover_html(cover_path: str, height: int = 120) -> str:
    path = Path(cover_path)
    mime_type = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"""
    <div style="height:{height}px; border:1px solid #e5e7eb; border-radius:6px;
                overflow:hidden; background:#111827;">
        <img src="data:{mime_type};base64,{data}" alt="视频素材封面"
             style="width:100%; height:{height}px; object-fit:cover; display:block;" />
    </div>
    """


def build_video_asset_missing_cover_html(height: int = 120) -> str:
    return f"""
    <div style="height:{height}px; border:1px dashed #cbd5e1; border-radius:6px;
                background:#f8fafc; display:flex; align-items:center; justify-content:center;
                color:#94a3b8; font-size:13px;">
        暂无封面
    </div>
    """


def format_video_asset_meta(asset) -> str:
    parts = []
    if asset.duration:
        parts.append(f"{asset.duration:.1f}s")
    if asset.size:
        parts.append(format_file_size(asset.size))
    return " · ".join(parts) or asset.created_at


def format_file_size(size: int) -> str:
    if size < 1024 * 1024:
        return f"{size / 1024:.1f}KB"
    return f"{size / (1024 * 1024):.1f}MB"
