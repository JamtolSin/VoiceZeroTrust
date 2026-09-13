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


def test_korean_research_confirmation_checked_even_after_cache():
    class Stub:
        calls = 0

        def analyze(self, *args, **kwargs):
            self.calls += 1
            return {"acoustic": {"fake_score": .7, "status": "분석 완료"},
                    "content": {"status": "판단 보류"}, "recommendation": "별도 채널로 확인"}

    stub = Stub()
    app = build_app(stub)
    callback = next(fn.fn for fn in app.fns.values() if fn.fn and fn.fn.__name__ == "analyze")
    assert callback("example.wav", "", False, True, "korean-research", False)[0] is None
    assert stub.calls == 0
    assert callback("example.wav", "", False, True, "korean-research", True)[0] is not None
    assert stub.calls == 1
    for value in (False, "True", 1):
        assert callback("example.wav", "", False, True, "korean-research", value)[0] is None
    assert stub.calls == 1
