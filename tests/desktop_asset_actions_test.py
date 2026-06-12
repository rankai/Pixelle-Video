from pathlib import Path


SOURCE = Path("desktop/src/App.tsx").read_text()


def test_asset_deletes_use_confirmation_modal_with_failure_feedback():
    assert "type PendingDelete" in SOURCE
    assert "ConfirmDeleteModal" in SOURCE
    assert "deleteError" in SOURCE
    assert "删除后无法在当前素材库恢复；已生成的视频不受影响，但后续任务不能再选择这个素材。" in SOURCE


def test_asset_delete_buttons_no_longer_call_delete_directly():
    direct_calls = [
        "deleteVoiceAsset(item.reference_id).then(reload)",
        "deletePortraitAsset(item.portrait_id).then(reload)",
        "deleteVideoAsset(item.asset_id).then(reload)",
        "deleteBrandKit(item.brand_id).then(reload)",
    ]

    for call in direct_calls:
        assert call not in SOURCE


def test_all_asset_libraries_open_pending_delete():
    for title in ["确认删除音色", "确认删除形象", "确认删除视频素材", "确认删除品牌资料"]:
        assert title in SOURCE


def test_video_library_supports_video_preview_in_its_own_scope():
    video_library = SOURCE[SOURCE.index("function VideoLibrary(") : SOURCE.index("function BrandKitLibrary")]

    assert "const [preview, setPreview] = useState<AssetPreview | null>(null)" in video_library
    assert 'setPreview({ kind: "video", title: item.name, src: item.file_url })' in video_library
    assert "<AssetPreviewModal preview={preview} onClose={() => setPreview(null)} />" in video_library
