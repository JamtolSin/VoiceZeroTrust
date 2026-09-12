"""CLI: build labelled pairs, then run a fixed-threshold acoustic benchmark."""
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("HF_HOME", str(ROOT / ".runtime/huggingface"))
os.environ.setdefault("TTS_HOME", str(ROOT / ".runtime/models"))
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".runtime/matplotlib"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    collect = sub.add_parser("collect")
    collect.add_argument("directory", type=Path)
    collect.add_argument("output", type=Path)
    collect.add_argument("--consent", action="store_true")
    collect.add_argument("--rights", required=True)
    collect.add_argument("--source", required=True)
    build = sub.add_parser("build")
    build.add_argument("manifest", type=Path)
    build.add_argument("output", type=Path)
    build.add_argument("--accept-model-license", action="store_true")
    run = sub.add_parser("run")
    run.add_argument("manifest", type=Path)
    run.add_argument("output", type=Path)
    run.add_argument("--split", choices=["smoke", "validation", "test"], default="test")
    run.add_argument("--threshold", type=float, default=0.5)
    args = parser.parse_args()
    if args.command == "run":
        os.environ["HF_HOME"] = str(ROOT / ".runtime/detection/models")
    from src.evaluation.pipeline import build_pairs, collect_local, evaluate
    if args.command == "collect":
        print(collect_local(args.directory, args.output, consent=args.consent, rights=args.rights, source=args.source))
        return 0
    if args.command == "build":
        from src.synthesizer import QwenSynthesizer
        _, failures = build_pairs(args.manifest, args.output, QwenSynthesizer(), license_confirmed=args.accept_model_license)
        return 2 if failures else 0
    report = evaluate(args.manifest, args.output, threshold=args.threshold, split=args.split)
    print(report["metrics"])
    return 0 if report["pipeline_ok"] and report["all_classified"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
