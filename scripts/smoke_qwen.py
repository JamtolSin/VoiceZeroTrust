"""Optional real-GPU smoke test using the Qwen project's published demo reference."""
import sys
from pathlib import Path
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
import soundfile as sf
from src.service import DemoService
from src.synthesizer import QwenSynthesizer


def main():
    folder = app.RUNTIME / "smoke-qwen"
    folder.mkdir(exist_ok=True)
    reference = folder / "official-reference.wav"
    if not reference.exists():
        with urlopen("https://qianwen-res.oss-cn-beijing.aliyuncs.com/Qwen3-TTS-Repo/clone.wav", timeout=60) as response:
            reference.write_bytes(response.read())
    service = DemoService(QwenSynthesizer(), folder / "requests")
    result = service.generate_demo(
        str(reference), True, True,
        reference_text="Okay. Yeah. I resent you. I love you. I respect you. But you know what? You blew it! And thanks to you.",
    )
    rate, samples = result.audio
    sf.write(folder / "education-output.wav", samples, rate)
    print(f"SUCCESS: {len(samples)/rate:.2f}s output, {result.elapsed_seconds:.1f}s elapsed", flush=True)


if __name__ == "__main__":
    main()
