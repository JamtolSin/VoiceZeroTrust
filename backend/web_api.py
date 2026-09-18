"""Temporary authenticated web-demo API; bind to loopback behind HTTPS tunnel."""
import asyncio
import base64
import hmac
import io
import logging
import os
import secrets
import tempfile
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

MAX_BYTES = 20 * 1024 * 1024
TTL = 900


def create_app(token=None, runner=None, origins=None):
    token = token or os.environ.get("VZT_WEB_TOKEN", "")
    if len(token) < 32:
        raise RuntimeError("VZT_WEB_TOKEN must contain at least 32 characters")
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(CORSMiddleware,
        allow_origins=origins or os.environ.get("VZT_WEB_ORIGINS", "http://127.0.0.1:8080").split(","),
        allow_methods=["GET", "POST"], allow_headers=["Authorization", "Content-Type"])
    jobs, tasks = {}, set()
    busy = asyncio.Lock()

    def authenticate(request):
        supplied = request.headers.get("authorization", "").encode()
        if not hmac.compare_digest(supplied, ("Bearer " + token).encode()):
            raise HTTPException(401, "연결 키를 확인해 주세요.")

    def prune():
        for key, value in list(jobs.items()):
            if value["status"] != "running" and time.monotonic() - value["created"] > TTL:
                del jobs[key]

    @app.get("/health")
    async def health(request: Request):
        authenticate(request)
        prune()
        return {"status": "ok", "busy": busy.locked(), "notice": "연결 확인; 모델 실행 결과는 요청별로 표시됩니다."}

    async def execute(job_id, operation, data, suffix, fields):
        try:
            with tempfile.TemporaryDirectory(prefix="vzt-web-") as folder:
                source = Path(folder) / ("input" + suffix)
                source.write_bytes(data)
                result = await asyncio.to_thread(runner or run_model, operation, source, fields)
            jobs[job_id].update(status="complete", result=result)
        except ValueError as exc:
            jobs[job_id].update(status="failed", error=str(exc))
        except Exception:
            logging.exception("Web model execution failed")
            jobs[job_id].update(status="failed", error="모델 실행에 실패했습니다. 서버 로그를 확인해 주세요.")
        finally:
            jobs[job_id]["created"] = time.monotonic()
            busy.release()

    @app.post("/jobs/{operation}")
    async def submit(operation: str, request: Request):
        authenticate(request)
        if operation not in {"generate", "detect"}:
            raise HTTPException(404, "지원하지 않는 작업입니다.")
        prune()
        if busy.locked():
            raise HTTPException(409, "모델이 처리 중입니다. 완료 후 다시 시도해 주세요.")
        await busy.acquire()
        launched = False
        try:
            # Bound the raw request before multipart parsing, including chunked bodies.
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > MAX_BYTES + 65536:
                    raise HTTPException(413, "파일은 20MB 이하여야 합니다.")
            request._body = bytes(body)
            async with request.form(max_files=1, max_fields=6) as form:
                upload = form.get("audio")
                if not hasattr(upload, "read"):
                    raise HTTPException(400, "음성 파일을 선택해 주세요.")
                suffix = Path(upload.filename or "").suffix.lower()
                if suffix not in {".wav", ".mp3", ".m4a", ".aac", ".ogg", ".webm", ".flac"}:
                    raise HTTPException(400, "지원하지 않는 음성 형식입니다.")
                data = await upload.read(MAX_BYTES + 1)
                if not data or len(data) > MAX_BYTES:
                    raise HTTPException(413, "비어 있지 않은 20MB 이하 파일을 사용해 주세요.")
                fields = {k: str(form.get(k, "")) for k in ("consent", "license", "transcript", "profile", "research")}
                if len(fields["transcript"]) > 20000:
                    raise HTTPException(400, "대사는 20,000자 이하여야 합니다.")
                if fields["consent"] != "true":
                    raise HTTPException(400, "음성 사용 동의를 확인해 주세요.")
            job_id = secrets.token_urlsafe(24)
            jobs[job_id] = {"status": "running", "created": time.monotonic()}
            task = asyncio.create_task(execute(job_id, operation, data, suffix, fields))
            tasks.add(task)
            task.add_done_callback(tasks.discard)
            launched = True
            return {"id": job_id, "status": "running"}
        finally:
            if not launched:
                busy.release()

    @app.get("/jobs/{job_id}")
    async def result(job_id: str, request: Request):
        authenticate(request)
        prune()
        if job_id not in jobs:
            raise HTTPException(404, "결과가 만료되었거나 존재하지 않습니다.")
        return {k: v for k, v in jobs[job_id].items() if k != "created"}

    return app


_services = {}


def run_model(operation, source, fields):
    if operation == "generate":
        import soundfile as sf
        from src.service import DemoService
        from src.synthesizer import QwenSynthesizer
        if "generate" not in _services:
            _services["generate"] = DemoService(QwenSynthesizer(), Path(".runtime/web/requests"))
        result = _services["generate"].generate_demo(str(source), fields["consent"] == "true",
            fields["license"] == "true", reference_text=fields["transcript"])
        buffer = io.BytesIO()
        sf.write(buffer, result.audio[1], result.audio[0], format="WAV")
        return {"model": result.model, "elapsed_seconds": result.elapsed_seconds,
                "input_seconds": result.input_seconds,
                "audio_base64": base64.b64encode(buffer.getvalue()).decode()}
    from src.detection.service import DetectionService
    from src.detection.profiles import build_profile
    profile = fields["profile"] or "baseline"
    research = fields["research"] == "true"
    if profile == "korean-research" and not research:
        raise ValueError("한국어 후보의 비상업 연구·평가 이용 범위를 확인해 주세요.")
    if profile not in _services:
        _services[profile] = DetectionService(acoustic=build_profile(profile, allow_noncommercial=research))
    return _services[profile].analyze(str(source), transcript=fields["transcript"], enable_acoustic=True)
