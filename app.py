import os
from pathlib import Path

RUNTIME = Path(__file__).resolve().parent / ".runtime"
RUNTIME.mkdir(exist_ok=True)
os.environ["GRADIO_TEMP_DIR"] = str(RUNTIME / "gradio")
os.environ["TTS_HOME"] = str(RUNTIME / "models")
os.environ["HF_HOME"] = str(RUNTIME / "huggingface")
os.environ["MPLCONFIGDIR"] = str(RUNTIME / "matplotlib")
os.environ["GRADIO_ANALYTICS_ENABLED"] = "False"

from src.ui import build_app

if __name__ == "__main__":
    build_app(RUNTIME).launch(server_name="127.0.0.1", server_port=7860,
                              share=False, inbrowser=False, max_file_size="20mb")
