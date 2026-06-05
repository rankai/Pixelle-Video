from pathlib import Path

APP_SOURCE = Path("desktop/src/App.tsx").read_text()
CSS_SOURCE = Path("desktop/src/styles.css").read_text()


def _function_source(name: str) -> str:
    marker = f"function {name}("
    start = APP_SOURCE.index(marker)
    next_function = APP_SOURCE.find("\nfunction ", start + len(marker))
    return APP_SOURCE[start:] if next_function == -1 else APP_SOURCE[start:next_function]


def test_copywriting_editor_displays_dynamic_non_whitespace_character_count():
    source = _function_source("CopywritingStep")

    assert "scriptDraft" in source
    assert "setScriptDraft(event.target.value)" in source
    assert "scriptCharCount(scriptDraft)" in source
    assert "字" in source
    assert "value={scriptDraft}" in source


def test_script_character_count_ignores_whitespace():
    assert 'value.replace(/\\s/g, "").length' in APP_SOURCE


def test_script_counter_has_dedicated_style():
    assert ".script-editor-head" in CSS_SOURCE
    assert ".script-word-count" in CSS_SOURCE
