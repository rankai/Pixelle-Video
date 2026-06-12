from pathlib import Path


STYLES = Path("desktop/src/styles.css").read_text()


def test_delivery_polish_has_mobile_layout_guards():
    assert "@media (max-width: 760px)" in STYLES
    mobile = STYLES[STYLES.index("@media (max-width: 760px)") :]
    assert ".diagnostic-check-row" in mobile
    assert ".config-check-row" in mobile
    assert ".system-status-item" in mobile
    assert "grid-template-columns: 1fr" in mobile
    assert "width: 100%" in mobile
    assert ".platform-capability-head" in mobile
