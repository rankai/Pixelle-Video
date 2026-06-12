from pathlib import Path


SOURCE = Path("desktop/src/App.tsx").read_text()


def test_ip_learning_ui_requires_topic_confirmation_before_script_generation():
    assert "ipLearningNeedsTopicConfirmation" in SOURCE
    assert "确认选题并生成文案" in SOURCE
    assert "请选择一个学习选题" in SOURCE
    assert 'execute("source")' in SOURCE


def test_ip_learning_ui_uses_existing_execute_flow_not_api_helper_directly():
    source_step = SOURCE[SOURCE.index("function SourceStep(") : SOURCE.index("function CopywritingStep")]

    assert "runStep(" not in source_step
    assert "confirmIpLearningTopic" in source_step


def test_ip_learning_confirmation_does_not_render_duplicate_primary_ctas():
    draft_step = SOURCE[SOURCE.index("function DraftStep(") : SOURCE.index("function SourceStep(")]
    source_step = SOURCE[SOURCE.index("function SourceStep(") : SOURCE.index("function CopywritingStep")]

    assert "{!ipLearningNeedsTopicConfirmation ? (" in draft_step
    assert 'className="panel-primary-actions"' in draft_step
    assert "showPanelActions && !ipLearningNeedsTopicConfirmation" in source_step
