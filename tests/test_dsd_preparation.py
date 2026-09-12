from types import SimpleNamespace
import hashlib
import pytest

from scripts.prepare_dsd import PARTS, audit_metadata, check_download_space, download_ranges, verify_part, write_once


def test_dsd_wrong_metadata_fails_closed():
    with pytest.raises(ValueError, match="checksum"):
        audit_metadata(b"untrusted metadata")


def test_dsd_storage_guard(tmp_path, monkeypatch):
    total = sum(size for size, _ in PARTS)
    monkeypatch.setattr("scripts.prepare_dsd.shutil.disk_usage", lambda _: SimpleNamespace(free=total))
    with pytest.raises(RuntimeError, match="Insufficient space"):
        check_download_space(tmp_path)
    monkeypatch.setattr("scripts.prepare_dsd.shutil.disk_usage", lambda _: SimpleNamespace(free=total + 40 * 1024**3))
    check_download_space(tmp_path)


def test_dsd_no_overwrite_and_hash_checks(tmp_path):
    path = tmp_path / "example"
    write_once(path, b"123")
    write_once(path, b"123")
    with pytest.raises(ValueError, match="differs"):
        write_once(path, b"changed")
    assert verify_part(path, 3, hashlib.md5(b"123").hexdigest()) == hashlib.sha256(b"123").hexdigest()
    with pytest.raises(ValueError, match="size"):
        verify_part(path, 4, "wrong")
    with pytest.raises(ValueError, match="MD5"):
        verify_part(path, 3, "wrong")


class Response:
    status_code = 206

    def __init__(self, start, end, payload):
        self.headers = {"Content-Range": f"bytes {start}-{end}/{len(payload)}"}
        self.payload = payload[start:end + 1]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def raise_for_status(self):
        pass

    def iter_content(self, size):
        yield self.payload


def test_range_download_resumes_and_checks_headers(tmp_path, monkeypatch):
    path = tmp_path / "part"
    path.write_bytes(b"ab")
    calls = []
    def get(url, headers, **kwargs):
        start, end = map(int, headers["Range"].removeprefix("bytes=").split("-"))
        calls.append((start, end))
        return Response(start, end, b"abcdefg")
    download_ranges(SimpleNamespace(get=get), "url", path, 7, chunk_size=3)
    assert path.read_bytes() == b"abcdefg"
    assert calls == [(2, 4), (5, 6)]
    monkeypatch.setattr("scripts.prepare_dsd.time.sleep", lambda _: None)
    bad = tmp_path / "bad"
    response = Response(0, 2, b"abc")
    response.status_code = 200
    with pytest.raises(ValueError, match="exact download range"):
        download_ranges(SimpleNamespace(get=lambda *a, **k: response), "url", bad, 3)
    assert not bad.exists()
