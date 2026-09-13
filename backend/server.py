"""Authenticated LAN-only PCM call pilot. Run one worker: rooms are in memory."""
import asyncio
import hmac
import os
import re
import tempfile
import uuid
import wave
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from backend.window import RATE, SECONDS, Window


def analyze_pcm(pcm):
    from src.detection.service import DetectionService
    from src.detection.profiles import build_profile
    # Keep the existing baseline default; candidate is an explicit server option.
    if not hasattr(analyze_pcm, "service"):
        profile = os.environ.get("VZT_PROFILE", "baseline")
        if profile not in {"baseline", "candidate"}:
            raise ValueError("Use baseline or candidate; research-only profiles are not auto-enabled")
        analyze_pcm.service = DetectionService(acoustic=build_profile(profile))
    with tempfile.TemporaryDirectory(prefix="vzt-pilot-") as folder:
        path = Path(folder) / "window.wav"
        with wave.open(str(path), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(RATE)
            output.writeframes(pcm)
        return analyze_pcm.service.analyze(path, enable_acoustic=True,
            enable_asr=os.environ.get("VZT_ASR", "1") == "1")


def create_app(token=None, analyzer=None, duration=SECONDS):
    token = token if token is not None else os.environ.get("VZT_TOKEN", "")
    if len(token) < 16:
        raise RuntimeError("Set VZT_TOKEN to a random secret of at least 16 characters")
    analyzer = analyzer or analyze_pcm
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    rooms = {}
    model_busy = asyncio.Lock()

    @app.get("/health")
    async def health():
        return {"status": "ok", "transport": "lan-pcm-pilot", "model_ready": False,
                "notice": "Transport health only; model execution is reported per analysis"}

    @app.get("/")
    async def companion():
        return FileResponse(Path(__file__).with_name("companion.html"))

    @app.get("/audio-worklet.js")
    async def audio_worklet():
        return FileResponse(Path(__file__).with_name("audio-worklet.js"), media_type="text/javascript")

    @app.get("/apk")
    async def apk():
        path = Path(__file__).resolve().parents[1] / ".runtime/phone-pilot/VoiceZeroTrust-pilot.apk"
        if not path.is_file():
            raise HTTPException(404, "APK not copied to .runtime/phone-pilot; use GitHub Actions artifact")
        return FileResponse(path, media_type="application/vnd.android.package-archive", filename="VoiceZeroTrust-pilot.apk")

    @app.websocket("/call/{room}")
    async def call(ws: WebSocket, room: str):
        await ws.accept()
        participant = {"ws": ws, "window": None, "timer": None, "busy": False, "automatic": True,
                       "ready": False, "send_lock": asyncio.Lock(), "closed": False}
        tasks = set()

        async def send(peer, payload):
            async with peer["send_lock"]:
                await asyncio.wait_for(peer["ws"].send_json(payload), 3)

        async def finish():
            window = participant["window"]
            if window is None:
                return
            participant["window"] = None
            participant["busy"] = True
            pcm = window.take()
            analysis_id = uuid.uuid4().hex
            try:
                await send(participant, {"type": "analyzing", "id": analysis_id,
                    "reason": window.reason, "samples": len(pcm) // 2,
                    "duration_seconds": len(pcm) / (RATE * 2)})
                if len(pcm) < RATE * 2:
                    result = {"acoustic": {"status": "판단 보류", "fake_score": None},
                              "recommendation": "수신 음성이 1초 미만입니다. 연결과 마이크를 확인하세요."}
                elif model_busy.locked():
                    # Do not retain a queue of voice clips while CPU inference is busy.
                    result = {"acoustic": {"status": "사용 불가", "fake_score": None},
                              "recommendation": "서버가 다른 분석을 처리 중입니다. 잠시 후 다시 판별하세요."}
                else:
                    async with model_busy:
                        try:
                            result = await asyncio.to_thread(analyzer, pcm)
                        except Exception:
                            result = {"acoustic": {"status": "사용 불가", "fake_score": None},
                                      "recommendation": "모델 실행 실패. 서버 의존성·모델 다운로드 상태를 확인하세요."}
                if not participant["closed"]:
                    await send(participant, {"type": "result", "id": analysis_id,
                        "reason": window.reason, "duration_seconds": len(pcm)/(RATE*2), "report": result})
            finally:
                pcm = b""
                participant["busy"] = False

        async def timer():
            await asyncio.sleep(duration)
            await finish()

        async def start(reason):
            if participant["window"] is not None or participant["busy"]:
                await send(participant, {"type": "error", "message": "이미 수집 또는 분석 중입니다."})
                return
            participant["window"] = Window(reason)
            await send(participant, {"type": "capturing", "reason": reason, "seconds": duration})
            task = asyncio.create_task(timer())
            participant["timer"] = task
            tasks.add(task)
            task.add_done_callback(tasks.discard)

        participant["start"] = start
        try:
            auth = await asyncio.wait_for(ws.receive_json(), 10)
            if not isinstance(auth, dict):
                await ws.close(code=1008, reason="Invalid authentication message")
                return
            supplied = auth.get("token", "")
            if not isinstance(supplied, str) or not hmac.compare_digest(supplied.encode("utf-8"), token.encode("utf-8")):
                await ws.close(code=1008, reason="Authentication failed")
                return
            if not re.fullmatch(r"[A-Za-z0-9-]{4,40}", room):
                await ws.close(code=1008, reason="Invalid room")
                return
            if len(rooms) >= 8 and room not in rooms:
                await ws.close(code=1013, reason="Server full")
                return
            peers = rooms.setdefault(room, [])
            if len(peers) >= 2:
                await ws.close(code=1008, reason="Room full")
                return
            participant["automatic"] = auth.get("automatic", True) is True
            peers.append(participant)
            await send(participant, {"type": "waiting", "message": "상대방 연결을 기다립니다."})
            while True:
                message = await asyncio.wait_for(ws.receive(), 60)
                if message["type"] == "websocket.disconnect":
                    break
                if message.get("text") is not None:
                    import json
                    command = json.loads(message["text"])
                    if not isinstance(command, dict):
                        await ws.close(code=1008, reason="Invalid command")
                        break
                    if command.get("type") == "ping":
                        await send(participant, {"type": "pong"})
                    elif command.get("type") == "ready":
                        if participant["ready"]:
                            continue
                        participant["ready"] = True
                        if len(peers) == 2 and all(p["ready"] for p in peers):
                            for peer in peers:
                                await send(peer, {"type": "connected", "message": "앱 내 실험 통화 연결됨"})
                            for peer in peers:
                                if peer["automatic"]:
                                    await peer["start"]("automatic")
                    elif command.get("type") == "analyze":
                        if len(peers) == 2 and all(p["ready"] for p in peers):
                            await start("manual")
                        else:
                            await send(participant, {"type": "error", "message": "상대방과 먼저 연결하세요."})
                    continue
                pcm = message.get("bytes")
                if pcm is None or not 0 < len(pcm) <= 6400 or len(pcm) % 2:
                    await ws.close(code=1008, reason="Invalid PCM frame")
                    break
                for peer in list(peers):
                    if peer is participant or not peer["ready"] or not participant["ready"]:
                        continue
                    async with peer["send_lock"]:
                        await asyncio.wait_for(peer["ws"].send_bytes(pcm), 3)
                    if peer["window"] is not None:
                        peer["window"].add(pcm)
        except (WebSocketDisconnect, asyncio.TimeoutError, ValueError, RuntimeError):
            pass
        finally:
            peers = rooms.get(room, [])
            remaining = []
            if participant in peers:
                remaining = [peer for peer in peers if peer is not participant]
                rooms.pop(room, None)
            # Tear down both capture windows before network awaits or task cancellation.
            for peer in [participant, *remaining]:
                peer["closed"] = True
                if peer["window"] is not None:
                    peer["window"].take()
                    peer["window"] = None
                # Running CPU inference owns its semaphore until it actually finishes.
                if not peer["busy"] and peer["timer"] is not None:
                    peer["timer"].cancel()

            async def close_connections():
                for peer in remaining:
                    try:
                        await send(peer, {"type": "ended", "message": "상대방이 통화를 종료했습니다."})
                        await peer["ws"].close(code=1000)
                    except (RuntimeError, WebSocketDisconnect, asyncio.TimeoutError):
                        pass
                try:
                    await ws.close(code=1000)
                except (RuntimeError, WebSocketDisconnect):
                    pass

            await asyncio.shield(close_connections())
    return app
