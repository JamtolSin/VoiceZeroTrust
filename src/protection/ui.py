import json
from pathlib import Path
from tempfile import TemporaryDirectory

import gradio as gr

from .experiment import AudioSealBackend, RATE, run_experiment


def build_app():
    backend = AudioSealBackend()

    def execute(source, consent, external):
        try:
            report, marked = run_experiment(source, consent, external, backend)
            # Gradio copies yielded files into its expiring cache before resuming.
            with TemporaryDirectory(prefix="vzt-report-") as temporary:
                report_path = Path(temporary) / "watermark-experiment.json"
                report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                yield report, (RATE, marked), str(report_path)
        except Exception as exc:
            if isinstance(exc, ValueError):
                raise gr.Error(str(exc)) from exc
            raise gr.Error("실험 실행에 실패했습니다. AudioSeal 설치와 모델 다운로드 연결을 확인해 주세요.") from exc

    with gr.Blocks(title="VoiceZeroTrust 원본 보호 실험", delete_cache=(60, 600)) as app:
        gr.Markdown("# 원본 음성 워터마크 실험\n압축·리샘플링·2/3/5초 자르기에서 표식 검출과 무표식 대조군을 비교합니다. "
                    "학습 방지나 복제 후 표식 전달을 보장하지 않습니다. 첫 실행은 AudioSeal 모델을 다운로드합니다.")
        source = gr.Audio(sources=["upload", "microphone"], type="filepath", label="원본 음성 (2~30초, 20MB 이하)")
        consent = gr.Checkbox(label="본인 또는 사용에 동의받은 음성입니다.")
        external = gr.Audio(sources=["upload"], type="filepath", label="선택: 외부 재녹음·복제 결과 (출처 관계 미검증)")
        button = gr.Button("워터마크 실험 실행", variant="primary")
        report = gr.JSON(label="실험 결과: 점수는 사기 확률이 아닙니다")
        playback = gr.Audio(label="워터마크를 넣은 원본 — AI 합성이라는 뜻은 아닙니다", interactive=False)
        download = gr.File(label="음성 경로·전사 내용 없는 JSON 보고서")
        button.click(execute, [source, consent, external], [report, playback, download], concurrency_limit=1)
        gr.ClearButton([source, consent, external, report, playback, download])
        gr.Markdown("생성 오디오와 보고서는 로컬 Gradio 캐시에 최대 약 11분 보관됩니다. "
                    "초기화는 화면을 비우며 캐시 즉시 삭제를 의미하지 않습니다. 외부 파일 검출만으로 복제 표식 전이를 입증할 수 없습니다.")
    return app.queue(max_size=4)
