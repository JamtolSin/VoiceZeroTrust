import logging
from pathlib import Path

import gradio as gr

from src.service import DemoService, PHRASE
from src.synthesizer import QwenSynthesizer

logger = logging.getLogger(__name__)


def build_app(runtime: Path):
    service = DemoService(QwenSynthesizer(), runtime / "requests")

    def generate(audio, consent, license_ok, reference_text, progress=gr.Progress()):
        progress(0.1, desc="입력 확인 · 첫 실행은 모델 다운로드와 로딩이 필요합니다")
        try:
            result = service.generate_demo(audio, consent, license_ok, reference_text=reference_text)
        except ValueError as exc:
            return None, str(exc)
        except Exception:
            logger.exception("Synthesis failed")
            return None, "합성에 실패했습니다. 터미널 로그에서 다운로드·메모리·모델 오류를 확인해 주세요."
        warning = " · 6초 미만 입력: 유사도 저하 가능" if result.input_seconds < 6 else ""
        return result.audio, (f"완료 · 입력 {result.input_seconds:.1f}초 · "
                              f"처리 {result.elapsed_seconds:.1f}초 · {result.model} "
                              f"({service.engine.device}){warning}")

    with gr.Blocks(title="VoiceZeroTrust", delete_cache=(60, 900)) as demo:
        gr.Markdown("# VoiceZeroTrust\n목소리만으로 신원을 판단하지 마세요. 동의한 음성으로 합성 음성을 체험합니다.")
        gr.Markdown("합성 엔진: **Qwen3-TTS 1.7B Base** · 한국어 · 참조 음성 + 정확한 대사")
        with gr.Row():
            with gr.Column():
                audio = gr.Audio(sources=["upload", "microphone"], type="filepath",
                                 format=None, label="1. 음성 파일 업로드 또는 마이크 녹음")
                gr.Markdown("지원 형식: MP3 · WAV · M4A · AAC · OGG · WebM · FLAC")
                gr.Markdown("2–30초 · 첫 시도는 잡음 없는 6–10초 권장 · 한 사람의 목소리")
                reference_text = gr.Textbox(label="녹음에서 실제로 말한 내용", lines=3,
                    placeholder="음성에 들어 있는 말을 그대로 적어 주세요. 합성할 문장을 적는 칸이 아닙니다.")
                gr.Markdown("녹음 예시: 오늘은 제 목소리로 보안 교육 실험을 하고 있습니다. 창밖으로 바람이 불고 있네요.\n\n"
                            "위 문장을 읽었다면 대사 칸에도 같은 내용을 넣어 주세요. 녹음과 대사가 다르면 품질이 떨어질 수 있습니다.")
                consent = gr.Checkbox(label="본인 음성이거나, 이 합성 실험에 대한 화자의 동의를 받았습니다.")
                gr.Markdown("[Qwen3-TTS 모델 이용 조건(Apache 2.0)](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-Base/blob/main/LICENSE)")
                license_ok = gr.Checkbox(label="모델 이용 조건을 읽었으며 해당 조건에 동의합니다.")
            with gr.Column():
                gr.Textbox(value=PHRASE, label="2. 합성할 교육 문장", interactive=False)
                run = gr.Button("합성하기", variant="primary")
                status = gr.Textbox(value="입력 대기 중", label="진행 상태", interactive=False)
                output = gr.Audio(label="3. AI 합성 결과", interactive=False, format="wav")
        clear = gr.Button("화면 초기화")
        gr.Markdown("합성용 작업 파일은 처리 후 삭제됩니다. 재생용 캐시는 최대 약 16분 후 정리됩니다. "
                    "화면 초기화는 캐시의 즉시 삭제를 뜻하지 않습니다. 모델 파일은 다음 실행을 위해 보관합니다.")
        run.click(generate, [audio, consent, license_ok, reference_text], [output, status],
                  concurrency_limit=1, api_visibility="private")
        clear.click(lambda: (None, None, False, False, "입력 대기 중", ""),
                    outputs=[audio, output, consent, license_ok, status, reference_text], api_visibility="private")
    return demo.queue(default_concurrency_limit=1, max_size=4)
