import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import soundfile as sf

from src.evaluation.pipeline import build_pairs, collect_local, evaluate, read_manifest


def fixture_manifest(tmp_path):
    audio = tmp_path / "input.wav"
    sf.write(audio, np.sin(np.arange(48000) * .03) * .2, 16000)
    row = {"id": "a", "path": audio.name, "label": "real", "split": "test", "speaker_id": "s1",
           "consent": True, "source": "self recording", "rights": "consented evaluation", "transcript": "test"}
    manifest = tmp_path / "input.jsonl"
    manifest.write_text(json.dumps(row), encoding="utf-8")
    return manifest, row


def test_manifest_provenance_and_checksum(tmp_path):
    manifest, row = fixture_manifest(tmp_path)
    assert read_manifest(manifest)[0]["sha256"]
    row["consent"] = False
    manifest.write_text(json.dumps(row))
    with pytest.raises(ValueError, match="consent"):
        read_manifest(manifest)


def test_duplicates_rejected(tmp_path):
    manifest, row = fixture_manifest(tmp_path)
    manifest.write_text(json.dumps(row) + "\n" + json.dumps({**row, "id": "b"}))
    with pytest.raises(ValueError, match="Duplicate"):
        read_manifest(manifest)


def test_speaker_leakage(tmp_path):
    manifest, row = fixture_manifest(tmp_path)
    sf.write(tmp_path / "other.wav", np.zeros(16000), 16000)
    manifest.write_text(json.dumps(row) + "\n" + json.dumps({**row, "id": "b", "path": "other.wav", "split": "validation"}))
    with pytest.raises(ValueError, match="leakage"):
        read_manifest(manifest)


@pytest.mark.parametrize("score,error,ox", [(0.2, False, "O"), (0.8, False, "X"), (None, False, "보류"), (None, True, "보류")])
def test_evaluation_outcomes(tmp_path, score, error, ox):
    manifest, _ = fixture_manifest(tmp_path)
    class Detector:
        def analyze(self, *args, **kwargs):
            if error:
                raise RuntimeError("failed")
            return {"audio": {"duration_seconds": 3}, "acoustic": {"fake_score": score, "status": "분석 완료"}}
    output = tmp_path / "results"
    report = evaluate(manifest, output, service=Detector())
    assert report["pipeline_ok"] is not error
    assert json.loads((output / "predictions.json").read_text(encoding="utf-8"))[0]["ox"] == ox
    with pytest.raises(FileExistsError):
        evaluate(manifest, output, service=Detector())


def test_build_and_failure_checkpoint(tmp_path):
    manifest, _ = fixture_manifest(tmp_path)
    class Engine:
        name = "test"
        sample_rate = 16000
        def synthesize(self, reference, text, output, reference_text=""):
            sf.write(output, np.sin(np.arange(48000) * .06) * .2, 16000)
    result, failures = build_pairs(manifest, tmp_path / "dataset", Engine(), license_confirmed=True)
    assert not failures
    assert {r["label"] for r in read_manifest(result)} == {"real", "synthetic"}
    class Broken(Engine):
        def synthesize(self, *args, **kwargs):
            raise RuntimeError("test failure")
    result, failures = build_pairs(manifest, tmp_path / "failed", Broken(), license_confirmed=True)
    assert len(failures) == 1
    assert result.read_text() == ""


def test_collect_requires_transcript_and_explicit_rights(tmp_path):
    speaker = tmp_path / "inbox/speaker-001"
    speaker.mkdir(parents=True)
    sf.write(speaker / "sample.wav", np.ones(32000) * .1, 16000)
    output = tmp_path / "sources.jsonl"
    with pytest.raises(ValueError, match="consent"):
        collect_local(speaker.parent, output)
    with pytest.raises(ValueError, match="transcript"):
        collect_local(speaker.parent, output, consent=True, rights="test", source="self")
    (speaker / "sample.txt").write_text("test", encoding="utf-8")
    collect_local(speaker.parent, output, consent=True, rights="test", source="self")
    assert read_manifest(output)[0]["speaker_id"] == "speaker-001"
