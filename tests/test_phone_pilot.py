import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from backend.server import create_app
from backend.window import MAX_BYTES, Window

TOKEN = "phone-pilot-test-key-123456"


def test_user_supplied_unicode_connection_key():
    key = "테스트-사용자-연결키-1234567890"
    with TestClient(create_app(token=key)) as client:
        with client.websocket_connect("/call/test-room") as ws:
            ws.send_json({"token": key})
            assert ws.receive_json()["type"] == "waiting"


def authenticate(ws, automatic=True):
    ws.send_json({"token": TOKEN, "automatic": automatic})
    assert ws.receive_json()["type"] == "waiting"
    ws.send_json({"type": "ready"})


def send_second(ws, value=1):
    for _ in range(5):
        ws.send_bytes(bytes([value, 0]) * 3200)


def test_window_is_bounded_prospective_and_discards_after_deadline():
    window = Window("manual", now=100)
    window.add(b"\x01\x00" * 16000, now=101)
    window.add(b"\x02\x00" * MAX_BYTES, now=109)
    assert len(window.data) == MAX_BYTES
    before = bytes(window.data)
    window.add(b"\x03\x00", now=110)
    assert window.take() == before
    assert not window.data
    with pytest.raises(ValueError):
        window.add(b"x", now=102)


def test_server_requires_secret_and_rejects_wrong_auth():
    with pytest.raises(RuntimeError):
        create_app(token="short")
    with TestClient(create_app(token=TOKEN)) as client:
        assert client.get("/health").json()["model_ready"] is False
        assert client.get("/").status_code == 200
        assert client.get("/audio-worklet.js").status_code == 200
        with client.websocket_connect("/call/test-room") as ws:
            ws.send_json({"token": "wrong"})
            with pytest.raises(WebSocketDisconnect) as exc:
                ws.receive_json()
            assert exc.value.code == 1008
        with client.websocket_connect("/call/test-room") as ws:
            ws.send_json(["invalid"])
            with pytest.raises(WebSocketDisconnect) as exc:
                ws.receive_json()
            assert exc.value.code == 1008


def test_real_duplex_transport_auto_and_manual_windows_without_history():
    captured = []

    def analyzer(pcm):
        captured.append(pcm)
        return {"acoustic": {"status": "test-double", "fake_score": None}}

    with TestClient(create_app(token=TOKEN, analyzer=analyzer, duration=.25)) as client:
        with client.websocket_connect("/call/test-room") as phone:
            authenticate(phone)
            with client.websocket_connect("/call/test-room") as pc:
                authenticate(pc, automatic=False)
                assert phone.receive_json()["type"] == "connected"
                assert pc.receive_json()["type"] == "connected"
                assert phone.receive_json()["reason"] == "automatic"
                send_second(pc, 1)
                for _ in range(5):
                    assert phone.receive_bytes() == b"\x01\x00" * 3200
                assert phone.receive_json()["type"] == "analyzing"
                assert phone.receive_json()["type"] == "result"
                assert captured == [b"\x01\x00" * 16000]
                # Idle audio is still delivered for the call, never added to next analysis.
                pc.send_bytes(b"\x02\x00" * 320)
                assert phone.receive_bytes() == b"\x02\x00" * 320
                phone.send_bytes(b"\x03\x00" * 320)
                assert pc.receive_bytes() == b"\x03\x00" * 320
                phone.send_json({"type": "analyze"})
                assert phone.receive_json()["reason"] == "manual"
                send_second(pc, 4)
                for _ in range(5):
                    phone.receive_bytes()
                assert phone.receive_json()["type"] == "analyzing"
                result = phone.receive_json()
                assert result["reason"] == "manual"
                assert captured[-1] == b"\x04\x00" * 16000


def test_short_window_abstains_and_room_capacity_is_two():
    def forbidden(_):
        raise AssertionError("Short audio must not be classified")

    with TestClient(create_app(token=TOKEN, analyzer=forbidden, duration=.1)) as client:
        with client.websocket_connect("/call/test-room") as a:
            authenticate(a)
            with client.websocket_connect("/call/test-room") as b:
                authenticate(b, automatic=False)
                a.receive_json(); b.receive_json(); a.receive_json()
                with client.websocket_connect("/call/test-room") as c:
                    c.send_json({"token": TOKEN})
                    with pytest.raises(WebSocketDisconnect):
                        c.receive_json()
                assert a.receive_json()["type"] == "analyzing"
                assert a.receive_json()["report"]["acoustic"]["status"] == "판단 보류"


def test_model_error_not_safe_and_duplicate_request_does_not_restart_window():
    def broken(_):
        raise RuntimeError("private diagnostic")

    with TestClient(create_app(token=TOKEN, analyzer=broken, duration=.25)) as client:
        with client.websocket_connect("/call/test-room") as a:
            authenticate(a)
            with client.websocket_connect("/call/test-room") as b:
                authenticate(b, automatic=False)
                a.receive_json(); b.receive_json(); a.receive_json()
                a.send_json({"type": "analyze"})
                assert a.receive_json()["type"] == "error"
                send_second(b)
                for _ in range(5):
                    a.receive_bytes()
                a.receive_json()
                result = a.receive_json()
                assert result["report"]["acoustic"]["status"] == "사용 불가"
                assert result["report"]["acoustic"]["fake_score"] is None
                assert "private diagnostic" not in str(result)


def test_disconnect_cancels_capture_and_room_can_be_reused():
    seen = []
    with TestClient(create_app(token=TOKEN, analyzer=lambda pcm: seen.append(pcm), duration=10)) as client:
        with client.websocket_connect("/call/test-room") as a:
            authenticate(a)
            with client.websocket_connect("/call/test-room") as b:
                authenticate(b, automatic=False)
                a.receive_json(); b.receive_json(); a.receive_json()
            assert a.receive_json()["type"] == "ended"
        assert seen == []
        with client.websocket_connect("/call/test-room") as c:
            authenticate(c)


def test_invalid_frame_and_manual_before_peer():
    with TestClient(create_app(token=TOKEN)) as client:
        with client.websocket_connect("/call/test-room") as ws:
            authenticate(ws)
            ws.send_json({"type": "analyze"})
            assert ws.receive_json()["type"] == "error"
            ws.send_bytes(b"odd")
            with pytest.raises(WebSocketDisconnect):
                ws.receive_json()
