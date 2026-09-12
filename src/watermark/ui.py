from pathlib import Path
import gradio as gr

from .service import CAVEAT, WatermarkService


def build_app(runtime: Path):
    service = WatermarkService(runtime / "watermark")

    def embed(source, confirmed):
        try:
            output, result = service.embed_file(source, confirmed)
            return output, result.to_dict()
        except Exception as exc:
            raise gr.Error(str(exc)) from exc

    def detect(source):
        try:
            return service.detect_file(source).to_dict()
        except Exception as exc:
            raise gr.Error(str(exc)) from exc

    with gr.Blocks(title="VoiceZeroTrust · 음성 워터마크", delete_cache=(3600, 3600)) as app:
        gr.Markdown("# 교육용 합성 음성 워터마크\nAudioSeal 표식을 넣고 검출합니다. " + CAVEAT)
        gr.Markdown("2~30초 · 최대 20MB · MP3/WAV/M4A/AAC/OGG/WebM/FLAC. 첫 실행은 모델 다운로드가 필요합니다. 출력은 로컬 .runtime/watermark에 보관됩니다.")
        with gr.Tab("표식 삽입"):
            source = gr.Audio(sources=["upload"], type="filepath", label="교육용 합성 결과물")
            confirmed = gr.Checkbox(label="이 파일은 교육용 합성 결과물입니다.")
            action = gr.Button("워터마크 삽입 및 저장 결과 검증")
            output = gr.Audio(label="워터마크를 넣은 결과", type="filepath")
            report = gr.JSON(label="저장된 결과의 검출 정보")
            action.click(embed, [source, confirmed], [output, report])
        with gr.Tab("표식 검출"):
            candidate = gr.Audio(sources=["upload"], type="filepath", label="검사할 음성")
            check = gr.Button("워터마크 검사")
            result = gr.JSON(label="검출 정보 (score는 사기 확률이 아닙니다)")
            check.click(detect, [candidate], [result])
        gr.Markdown("고정 공개 태그는 위조할 수 있으며 암호학적 서명이 아닙니다. 임계값 0.5는 실험용이며 현장 검증 전입니다.")
    return app.queue(default_concurrency_limit=1, max_size=8)
