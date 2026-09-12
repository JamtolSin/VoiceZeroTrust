import os
from pathlib import Path

RUNTIME = Path(__file__).resolve().parent / ".runtime"
RUNTIME.mkdir(exist_ok=True)
os.environ["GRADIO_TEMP_DIR"] = str(RUNTIME / "gradio-watermark")
os.environ.setdefault("HF_HOME", str(RUNTIME / "huggingface"))
os.environ.setdefault("TORCH_HOME", str(RUNTIME / "torch"))
os.environ.setdefault("AUDIOSEAL_CACHE_DIR", str(RUNTIME / "audioseal"))
os.environ["GRADIO_ANALYTICS_ENABLED"] = "False"

from src.watermark.ui import build_app

if __name__ == "__main__":
    build_app(RUNTIME).launch(server_name="127.0.0.1", server_port=7862,
                             share=False, inbrowser=False, max_file_size="20mb")
