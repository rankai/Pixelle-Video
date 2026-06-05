import re
from pathlib import Path

CSS = Path("desktop/src/styles.css").read_text()


def _rule(selector: str) -> str:
    pattern = rf"(^|\n){re.escape(selector)}\s*\{{(?P<body>.*?)\n\}}"
    match = re.search(pattern, CSS, flags=re.S)
    assert match, f"Missing CSS rule for {selector}"
    return match.group("body")


def test_asset_cards_constrain_media_text_and_actions_inside_card():
    asset_card_rule = _rule(".asset-card")
    assert "grid-template-rows: auto auto minmax(38px, 1fr) auto;" in asset_card_rule
    assert "contain: layout paint;" in asset_card_rule

    text_rule = _rule(".asset-card strong")
    assert "word-break: break-word;" in text_rule
    assert "hyphens: auto;" in text_rule

    media_rule = _rule(".asset-card img,\n.asset-card video,\n.video-thumb,\n.template-demo")
    assert "min-width: 0;" in media_rule
    assert "justify-self: stretch;" in media_rule

    actions_rule = _rule(".asset-card-actions")
    assert "grid-template-columns: repeat(2, minmax(0, 1fr));" in actions_rule
    assert "width: 100%;" in actions_rule


def test_portrait_asset_grid_uses_flexible_tracks():
    portrait_grid_rule = _rule(".asset-grid.portraits")
    assert "repeat(auto-fill, minmax(220px, 1fr))" in portrait_grid_rule
    assert "min-width: 0;" in portrait_grid_rule


def test_template_cards_render_portrait_previews_without_side_letterboxing():
    template_image_rule = _rule(".asset-card.template img,\n.asset-card.template .template-demo")

    assert "aspect-ratio: 9 / 16;" in template_image_rule
    assert "width: min(100%, 210px);" in template_image_rule
    assert "height: auto;" in template_image_rule
    assert "object-fit: cover;" in template_image_rule
    assert "justify-self: center;" in template_image_rule
