"""Run from repository root with VZT_WEB_TOKEN and VZT_WEB_ORIGINS configured."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uvicorn
from backend.web_api import create_app

if __name__ == "__main__":
    uvicorn.run(create_app(), host="127.0.0.1", port=8766)
