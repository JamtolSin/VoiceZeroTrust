"""Standalone stage 3 research UI; no synthesis or detector service dependency."""
import os
from pathlib import Path

RUNTIME = Path(__file__).resolve().parent / ".runtime"
RUNTIME.mkdir(exist_ok=True)
os.environ["GRADIO_TEMP_DIR"] = str(RUNTIME / "protection-gradio")
os.environ["GRADIO_ANALYTICS_ENABLED"] = "False"
os.environ.setdefault("AUDIOSEAL_CACHE_DIR", str(RUNTIME / "audioseal"))

from src.protection.ui import build_app

if __name__ == "__main__":
    build_app().launch(server_name="127.0.0.1", server_port=7863, share=False,
                       inbrowser=False, max_file_size="20mb")
