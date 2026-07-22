from pathlib import Path

SOURCE = Path("desktop/src/StudioApp.tsx").read_text()


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


def test_v2_asset_center_exposes_bulk_management_actions():
    source = Path("desktop/src/features/assets/components/AssetCenterV2.tsx").read_text()

    assert '"批量管理"' in source
    assert 'bulkLibraryActionV2' in source
    assert ">批量收藏<" in source
    assert ">批量归档<" in source


def test_v2_digital_human_creation_captures_cover_and_demo_video():
    source = Path("desktop/src/features/assets/components/AssetCenterV2.tsx").read_text()

    assert '数字人封面图' in source
    assert '演示视频' in source
    assert 'uploadMediaAssetV2("image"' in source
    assert 'uploadMediaAssetV2("video"' in source
    assert 'preview_media_type === "video"' in source
    assert '用于点击数字人后的演示预览和场景素材' in source


def test_v2_production_source_uses_shared_brand_picker():
    source = Path("desktop/src/StudioApp.tsx").read_text()
    source_step = source[source.index("function SourceStep(") : source.index("function VoiceStep(")]

    assert 'kind="brand"' in source_step
    assert "brandV2PickerOpen" in source_step
    assert 'brand_kit_id: item.resource_id' in source_step


def test_v2_postproduction_uses_shared_audio_picker_for_bgm():
    source = Path("desktop/src/StudioApp.tsx").read_text()
    settings = source[source.index("function PostproductionMoreSettings(") : source.index("function BgmPickerModal(")]

    assert 'kind="audio"' in settings
    assert "bgm_asset_id" in settings
    assert "brand_bgm_asset_id: \"\"" in settings
    assert 'item.kind === "audio"' in source
    assert "bgm_asset_id: item.resource_id" in source


def test_v2_reload_uses_domain_projection_for_all_asset_types():
    source = Path("desktop/src/StudioApp.tsx").read_text()
    reload_source = source[source.index("async function reloadAssets()") : source.index("async function execute(")]

    for kind in ['"voice"', '"digital_human"', '"template"', '"brand"']:
        assert f"listLibraryItemsV2({kind})" in reload_source
    assert "mapV2VoiceAsset" in reload_source
    assert "mapV2PortraitAsset" in reload_source
    assert "mapV2TemplateAsset" in reload_source
    assert "mapV2BrandKit" in reload_source
