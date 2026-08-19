#!/usr/bin/env python3
"""Crop 16:9 Federer/Nadal serve baseline videos to the center 9:16 region."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


DEFAULT_FFMPEG = "/home/fly/miniconda3/envs/tennis_env/bin/ffmpeg"
DEFAULT_FFPROBE = "/home/fly/miniconda3/envs/tennis_env/bin/ffprobe"
DEFAULT_INPUT = Path("static/videos/adapt/baselines/serve")
NAME_PREFIXES = ("federer_", "nadal_")


def find_binary(preferred: str, name: str) -> str:
    path = Path(preferred)
    if path.exists():
        return str(path)
    found = shutil.which(name)
    if found:
        return found
    raise FileNotFoundError(f"Cannot find {name}. Pass --ffmpeg / --ffprobe.")


def probe_size(ffprobe: str, src: Path) -> tuple[int, int]:
    result = subprocess.run(
        [
            ffprobe,
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "csv=p=0:s=x",
            str(src),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    width_text, height_text = result.stdout.strip().split("x")
    return int(width_text), int(height_text)


def crop_filter(width: int, height: int) -> str:
    crop_w = round(height * 9 / 16)
    crop_w += crop_w % 2  # even width for yuv420p; 1216 for 2160p
    crop_x = ((width - crop_w) // 2) // 2 * 2
    return f"crop={crop_w}:{height}:{crop_x}:0"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=None, help="Defaults to <input-dir>/portrait")
    parser.add_argument("--ffmpeg", default=DEFAULT_FFMPEG)
    parser.add_argument("--ffprobe", default=DEFAULT_FFPROBE)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    ffmpeg = find_binary(args.ffmpeg, "ffmpeg")
    ffprobe = find_binary(args.ffprobe, "ffprobe")
    input_dir = args.input_dir.resolve()
    output_dir = (args.output_dir or (input_dir / "portrait")).resolve()

    sources = sorted(
        path for path in input_dir.glob("*.mp4")
        if path.name.startswith(NAME_PREFIXES)
    )
    if not sources:
        print(f"No Federer/Nadal mp4 files in {input_dir}", file=sys.stderr)
        return 1

    output_dir.mkdir(parents=True, exist_ok=True)
    for src in sources:
        width, height = probe_size(ffprobe, src)
        vf = crop_filter(width, height)
        dst = output_dir / src.name
        print(f"{src.name}: {width}x{height} -> {vf}")
        if args.dry_run:
            continue
        subprocess.run(
            [
                ffmpeg, "-y", "-i", str(src),
                "-vf", vf,
                "-c:v", "libx264", "-crf", "18", "-preset", "fast",
                "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                "-an",
                str(dst),
            ],
            check=True,
        )
        print(f"  wrote {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
