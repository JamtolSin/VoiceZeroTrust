"""Real APK/Android/transport smoke; model fixture is explicitly NOT real inference."""
import asyncio
import json
import math
from pathlib import Path
import re
import struct
import subprocess
import sys
import threading
import time
import xml.etree.ElementTree as ET

import uvicorn
from websockets.sync.client import connect

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.server import create_app

PACKAGE = "kr.voicezerotrust.pilot"
KEY = "emulator-fixture-connection-key"
evidence = Path("artifacts")
captures = []


def fixture(pcm):
    captures.append(len(pcm))
    return {"acoustic": {"status": "분석 완료", "fake_score": None,
                        "message": "EMULATOR MODEL FIXTURE — NOT REAL INFERENCE"},
            "recommendation": "Android 통화 경로 테스트만 통과"}


def adb(*args):
    return subprocess.check_output(["adb", *args], timeout=30)


def snapshot():
    for _ in range(5):
        try:
            adb("shell", "uiautomator", "dump", "/sdcard/window.xml")
            tree = ET.fromstring(adb("shell", "cat", "/sdcard/window.xml"))
            if list(tree):
                return tree
        except (subprocess.CalledProcessError, ET.ParseError):
            pass
        time.sleep(1)
    raise AssertionError("Android accessibility tree did not become ready")


def tap_id(name):
    for _ in range(6):
        tree = snapshot()
        for node in tree.iter("node"):
            if node.get("resource-id") == PACKAGE + ":id/" + name:
                x1, y1, x2, y2 = map(int, re.findall(r"\d+", node.get("bounds")))
                if y2 > y1 and node.get("enabled") == "true":
                    adb("shell", "input", "tap", str((x1+x2)//2), str((y1+y2)//2))
                    return
        adb("shell", "input", "swipe", "500", "1800", "500", "650", "300")
    raise AssertionError("Visible enabled widget missing: " + name)


def fill(name, value):
    tap_id(name)
    adb("shell", "input", "keyevent", "KEYCODE_MOVE_END")
    adb("shell", "input", "keyevent", "--longpress", "KEYCODE_DEL")
    # Initial fields are empty except room, which is left at its default.
    adb("shell", "input", "text", value)
    adb("shell", "input", "keyevent", "KEYCODE_BACK")


def main():
    evidence.mkdir(exist_ok=True)
    server = uvicorn.Server(uvicorn.Config(create_app(token=KEY, analyzer=fixture),
        host="127.0.0.1", port=8765, log_level="warning", ws_max_size=8192))
    threading.Thread(target=server.run, daemon=True).start()
    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        time.sleep(.1)
    assert server.started
    adb("install", "-r", "artifacts/VoiceZeroTrust-pilot.apk")
    adb("shell", "pm", "grant", PACKAGE, "android.permission.RECORD_AUDIO")
    adb("shell", "pm", "grant", PACKAGE, "android.permission.POST_NOTIFICATIONS")
    adb("reverse", "tcp:8765", "tcp:8765")
    adb("shell", "input", "keyevent", "KEYCODE_WAKEUP")
    adb("shell", "wm", "dismiss-keyguard")
    print(adb("shell", "am", "start", "-W", "-n", PACKAGE + "/.MainActivity").decode(), flush=True)
    fill("server", "http://127.0.0.1:8765")
    fill("token", KEY)
    tap_id("connect")
    with connect("ws://127.0.0.1:8765/call/phone-test") as peer:
        peer.send(json.dumps({"token": KEY, "automatic": False}))
        assert json.loads(peer.recv(timeout=15))["type"] == "waiting"
        peer.send('{"type":"ready"}')
        assert json.loads(peer.recv(timeout=15))["type"] == "connected"
        received = []
        stop = threading.Event()

        def read():
            while not stop.is_set():
                try:
                    frame = peer.recv(timeout=1)
                    if isinstance(frame, bytes): received.append(len(frame))
                except TimeoutError:
                    continue
                except Exception:
                    break

        def speak():
            frame = b"".join(struct.pack("<h", int(math.sin(i*2*math.pi*220/16000)*3000)) for i in range(320))
            while not stop.wait(.02):
                try: peer.send(frame)
                except Exception: break

        threading.Thread(target=read, daemon=True).start()
        threading.Thread(target=speak, daemon=True).start()
        try:
            deadline = time.monotonic() + 20
            while not captures and time.monotonic() < deadline: time.sleep(.2)
            assert captures and 16000*2 <= captures[0] <= 320000, captures
            assert sum(received) > 16000*2, "Android microphone must send audio back"
            tap_id("analyze")
            deadline = time.monotonic() + 20
            while len(captures) < 2 and time.monotonic() < deadline: time.sleep(.2)
            assert len(captures) == 2, captures
            adb("shell", "screencap", "-p", "/sdcard/result.png")
            adb("pull", "/sdcard/result.png", str(evidence / "emulator-result.png"))
            xml = ET.tostring(snapshot(), encoding="unicode")
            (evidence / "emulator-ui.xml").write_text(xml, encoding="utf-8")
            assert "분석 응답 수신" in xml, xml
            # Exercise persistent microphone foreground service while activity is backgrounded.
            adb("shell", "input", "keyevent", "KEYCODE_HOME")
            before = sum(received)
            time.sleep(2)
            assert sum(received) > before
            print("APK INSTALL + DUPLEX PCM + AUTOMATIC 10s + MANUAL 10s + BACKGROUND: PASS")
            print("Model fixture only; real phone audio quality is pending human verification.")
        finally:
            stop.set()
    time.sleep(1)
    services = adb("shell", "dumpsys", "activity", "services", PACKAGE).decode()
    assert "ServiceRecord" not in services, services
    server.should_exit = True


if __name__ == "__main__":
    try:
        main()
    finally:
        evidence.mkdir(exist_ok=True)
        (evidence / "emulator-logcat.txt").write_bytes(adb("logcat", "-d", "-t", "2000"))
        adb("shell", "screencap", "-p", "/sdcard/final.png")
        adb("pull", "/sdcard/final.png", str(evidence / "emulator-final.png"))
