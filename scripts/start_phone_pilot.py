"""Start one local pilot server and print connection settings. No firewall changes."""
import os
import secrets
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)


def main():
    import uvicorn
    from backend.server import create_app
    key = os.environ.get("VZT_TOKEN") or secrets.token_urlsafe(18)
    host = os.environ.get("VZT_HOST", "0.0.0.0")
    port = int(os.environ.get("VZT_PORT", "8765"))
    addresses = sorted({item[4][0] for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)})
    print("VoiceZeroTrust Android phone pilot", flush=True)
    print(f"PC companion: http://localhost:{port}", flush=True)
    print("Phone server URL candidates: " + ", ".join(f"http://{ip}:{port}" for ip in addresses), flush=True)
    print(f"Connection key: {key}", flush=True)
    print("Room: phone-test (both endpoints must match)", flush=True)
    print("LAN laboratory transport; no cellular/PSTN integration. Keep this console open.", flush=True)
    print("Model: " + os.environ.get("VZT_PROFILE", "baseline") + "; ASR: " + os.environ.get("VZT_ASR", "1"), flush=True)
    uvicorn.run(create_app(token=key), host=host, port=port, workers=1,
                ws_max_size=8192, ws_max_queue=16, access_log=False)


if __name__ == "__main__":
    main()
