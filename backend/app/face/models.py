"""Download + verify the face engine model files.

Usage::

    python -m app.face.models            # download into FACE_MODEL_DIR
    python -m app.face.models --check    # verify existing files only

Both files come from the official OpenCV model zoo (Apache-2.0) and are pinned
by sha256 so a tampered or truncated download is rejected loudly.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import urllib.request
from pathlib import Path

from app.core.config import BACKEND_DIR, get_settings

MODELS: dict[str, tuple[str, str]] = {
    # name -> (url, sha256)
    "face_detection_yunet_2023mar.onnx": (
        "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/"
        "models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
        "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
    ),
    "face_recognition_sface_2021dec.onnx": (
        "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/"
        "models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
        "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79",
    ),
}


def model_dir() -> Path:
    return Path(get_settings().face_model_dir)


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_models(directory: Path | None = None) -> list[str]:
    """Return a list of problems (empty = all present and correct)."""
    d = directory or model_dir()
    problems: list[str] = []
    for name, (_url, digest) in MODELS.items():
        p = d / name
        if not p.exists():
            problems.append(f"missing: {p}")
        elif p.stat().st_size < 1024:
            problems.append(f"truncated: {p} ({p.stat().st_size} bytes)")
        elif sha256_of(p) != digest:
            problems.append(f"checksum mismatch: {p}")
    return problems


def download(directory: Path | None = None) -> dict[str, Path]:
    d = directory or model_dir()
    d.mkdir(parents=True, exist_ok=True)
    out: dict[str, Path] = {}
    for name, (url, digest) in MODELS.items():
        dest = d / name
        if dest.exists() and sha256_of(dest) == digest:
            out[name] = dest
            continue
        print(f"downloading {name} ...")
        urllib.request.urlretrieve(url, dest)
        actual = sha256_of(dest)
        if actual != digest:
            dest.unlink(missing_ok=True)
            raise RuntimeError(
                f"checksum mismatch for {name}: expected {digest}, got {actual}"
            )
        out[name] = dest
        print(f"  ok ({dest.stat().st_size:,} bytes)")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify only, no download")
    args = parser.parse_args(argv)
    if args.check:
        problems = verify_models()
        if problems:
            print("face model problems:")
            for p in problems:
                print(f"  - {p}")
            return 1
        print("face models OK")
        return 0
    download()
    print("all face models verified in", model_dir())
    print("(default dir:", BACKEND_DIR / "face_models", ")")
    return 0


if __name__ == "__main__":
    sys.exit(main())
