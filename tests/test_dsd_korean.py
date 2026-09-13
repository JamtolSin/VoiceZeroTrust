import io
import zipfile

from scripts.prepare_dsd_korean import SplitFile, archive_filename, assign_groups, stored_inner


def test_nested_split_zip_without_full_extraction(tmp_path):
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as archive:
        archive.writestr("audio/one.wav", b"example audio bytes")
    outer = io.BytesIO()
    with zipfile.ZipFile(outer, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("wavs.zip", inner.getvalue())
    data = outer.getvalue()
    paths = []
    for i in range(0, len(data), 37):
        path = tmp_path / str(i)
        path.write_bytes(data[i:i + 37])
        paths.append(path)
    stream = SplitFile(paths)
    assert stream.read(40) == data[:40]
    stream.seek(-10, 2)
    assert stream.read() == data[-10:]
    with zipfile.ZipFile(stream) as first, zipfile.ZipFile(stored_inner(first, stream)) as second:
        assert second.read("audio/one.wav") == b"example audio bytes"


def test_grouping_links_real_synthetic_speakers_and_duplicates():
    rows = [
        {"source": "AIHUB", "speaker_id": "a", "sha256": "1", "pcm_sha256": "1", "label": "real"},
        {"source": "VITS-AIHUB", "speaker_id": "a", "sha256": "2", "pcm_sha256": "2", "label": "synthetic"},
        {"source": "VITS-AIHUB", "speaker_id": "b", "sha256": "3", "pcm_sha256": "2", "label": "synthetic"},
        {"source": "MeloTTS", "speaker_id": "-", "sha256": "4", "pcm_sha256": "4", "label": "synthetic"},
    ]
    assigned = assign_groups(rows)
    assert len({r["group"] for r in assigned[:3]}) == 1
    assert len({r["split"] for r in assigned[:3]}) == 1
    assert assigned[-1]["split"] == "test"


def test_publisher_spelling_alias_is_source_scoped():
    assert archive_filename({"filename": "MeloTTS_906.wav", "source": "MeloTTS"}) == "MellowTTS_906.wav"
    assert archive_filename({"filename": "MeloTTS_906.wav", "source": "AIHUB"}) == "MeloTTS_906.wav"
