from detection_app import build_app


def test_ui_has_independent_analysis_controls():
    class Stub:
        def analyze(self, *args, **kwargs):
            raise AssertionError("Building UI must not load or invoke models")
    app = build_app(Stub())
    labels = [c.get("props", {}).get("label") for c in app.config["components"]]
    assert "음향 분석" in labels
    assert "대화 분석 및 권장 행동" in labels
    assert "대사가 없으면 한국어 자동 전사" in labels
