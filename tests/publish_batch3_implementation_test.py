from pathlib import Path


def test_legacy_publish_workspace_hands_off_without_secondary_orchestration():
    source = Path("desktop/src/features/publishing/PublishWorkspace.tsx").read_text(encoding="utf-8")
    assert "preparePlatformPublish" not in source
    assert "createPublishPackageFromSessionV2" in source
    assert "onOpenPublishCenter(packageData.package_id)" in source
    assert "已切换到统一发布中心" in source


def test_resolver_route_is_registered_before_dynamic_package_route():
    source = Path("api/routers/publish_v2.py").read_text(encoding="utf-8")
    assert source.index('@router.get("/packages/resolve"') < source.index('@router.get("/packages/{package_id}"')
    assert "PUBLISH_PACKAGE_AMBIGUOUS" in source
    assert "PUBLISH_PACKAGE_STALE" in source
