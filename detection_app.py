"""Local analysis UI. No audio is sent to a remote inference API."""
import os
from pathlib import Path

RUNTIME = Path(__file__).resolve().parent / ".runtime" / "detection"
RUNTIME.mkdir(parents=True, exist_ok=True)
os.environ["GRADIO_TEMP_DIR"] = str(RUNTIME / "gradio")
os.environ["HF_HOME"] = str(RUNTIME / "models")
os.environ["MPLCONFIGDIR"] = str(RUNTIME / "matplotlib")
os.environ["GRADIO_ANALYTICS_ENABLED"] = "False"

import gradio as gr
from src.detection.service import DetectionService
from src.detection.profiles import build_profile


def build_app(service=None):
    injected_service = service
    services = {"baseline": service or DetectionService(acoustic=build_profile("baseline"), workdir=RUNTIME / "requests")}

    def analyze(path, transcript, asr, acoustic, profile, research):
        try:
            if profile not in {"baseline", "candidate", "korean-research"}:
                raise ValueError("지원하지 않는 탐지 프로필입니다.")
            if profile == "korean-research" and research is not True:
                raise ValueError("한국어 후보는 비상업 연구·평가 용도 확인이 필요합니다.")
            if profile not in services:
                services[profile] = injected_service or DetectionService(acoustic=build_profile(profile, allow_noncommercial=research), workdir=RUNTIME / "requests")
            report = services[profile].analyze(path, transcript=transcript or None,
                                     enable_asr=asr, enable_acoustic=acoustic)
            acoustic_result = report["acoustic"]
            score = acoustic_result.get("fake_score")
            acoustic_text = acoustic_result["status"]
            if score is not None:
                acoustic_text += f" · 합성 클래스 점수 {score:.3f} (사기 확률 아님)"
            if acoustic_result.get("decision"):
                acoustic_text += " · " + acoustic_result["decision"]
            acoustic_text += "\n" + acoustic_result.get("message", "이 채널은 실행하지 않았습니다.")
            content = report["content"]
            content_text = content.get("level", content["status"]) + "\n" + report["recommendation"]
            evidence = [[e["pattern"], e["snippet"], e["context"]] for e in content.get("evidence", [])]
            return report, "분석 완료. 각 채널의 상태와 근거를 확인해 주세요.", acoustic_text, content_text, evidence
        except ValueError as exc:
            return None, str(exc), "판단 보류", "판단 보류", []
        except Exception:
            return None, "분석하지 못했습니다. 파일 상태와 로컬 모델 설치·다운로드 환경을 확인해 주세요.", "사용 불가", "판단 보류", []

    with gr.Blocks(title="VoiceZeroTrust · 탐지", delete_cache=(60, 900)) as demo:
        gr.Markdown("# 음성 위험 신호 분석\n합성 흔적과 대화 속 요구 행동을 각각 확인합니다. 신원이나 사기 여부를 확정하지 않습니다.")
        with gr.Row():
            with gr.Column():
                audio = gr.Audio(sources=["upload", "microphone"], type="filepath", format=None,
                                 label="분석할 음성")
                gr.Markdown("최대 3분 · MP3/WAV/M4A/AAC/OGG/WebM/FLAC · 로컬 처리")
                transcript = gr.Textbox(label="대화 내용 직접 입력 (선택)", lines=5,
                    placeholder="입력하면 자동 전사 대신 이 텍스트를 분석합니다. 음성과 일치하는지 확인해 주세요.")
                asr = gr.Checkbox(value=True, label="대사가 없으면 한국어 자동 전사")
                acoustic = gr.Checkbox(value=True, label="합성 음향 흔적 분석")
                profile = gr.Dropdown(choices=[("기준 모델 · XLS-R", "baseline"), ("영어 연구 후보 · v2", "candidate"), ("한국어 연구 후보 · v4 · 비상업용", "korean-research")],
                                      value="baseline", label="탐지 프로필 (후보는 실험용)")
                research = gr.Checkbox(value=False, label="한국어 후보를 비상업 연구·평가에만 사용합니다")
                gr.Markdown("기본 모델은 유지합니다. 한국어 v4는 DSD 자료로 분류기만 학습한 연구 후보이며 실제 통화 안전성을 보장하지 않습니다.")
                gr.Markdown("v4 연구 결과: 전체 합성 탐지율 91.24% / 오탐률 3.29%. 단, MMSTTS 탐지율 13%, 잡음 부분집합 오탐률 75%로 품질 기준 미달입니다.")
                gr.Markdown("처음에는 공개 모델을 다운로드하므로 시간이 걸립니다. 음성은 외부 분석 API로 보내지 않습니다.")
                run = gr.Button("분석하기", variant="primary")
                status = gr.Textbox(label="진행 상태", interactive=False)
            with gr.Column():
                acoustic_result = gr.Textbox(label="음향 분석", interactive=False, lines=3)
                content_result = gr.Textbox(label="대화 분석 및 권장 행동", interactive=False, lines=3)
                evidence = gr.Dataframe(headers=["행동 신호", "해당 발언", "맥락"],
                                        datatype=["str", "str", "str"], interactive=False,
                                        label="판단에 사용한 근거")
                with gr.Accordion("전사 및 상세 결과", open=False):
                    report = gr.JSON(label="채널별 상세 정보")
        gr.Markdown("**해석 방법**\n\n"
                    "- 음향 점수는 모델의 합성 클래스 출력이며 보이스피싱 확률이 아닙니다. 한국어·새 생성기에서는 성능이 달라질 수 있습니다.\n"
                    "- 대화 분석은 학습 모델이 아닌 설명 가능한 규칙 기반 MVP입니다. 자동 전사 오류와 인용·교육 맥락 때문에 오탐/미탐이 가능합니다.\n"
                    "- 미검출·분석 실패는 안전 판정이 아닙니다. 송금·앱 설치·인증정보 요구는 알고 있는 별도 채널로 확인하세요.\n"
                    "- 입력 캐시는 최대 약 16분 후 정리됩니다. 강제 종료 시 남을 수 있습니다.")
        run.click(analyze, [audio, transcript, asr, acoustic, profile, research], [report, status, acoustic_result, content_result, evidence],
                  concurrency_limit=1, api_visibility="private")
    return demo.queue(default_concurrency_limit=1, max_size=4)


if __name__ == "__main__":
    build_app().launch(server_name="127.0.0.1", server_port=7861,
                       share=False, inbrowser=False, max_file_size="20mb")
