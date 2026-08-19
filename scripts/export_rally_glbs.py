#!/usr/bin/env python3
"""Export G1 rally retarget clips to static/glb/rally and refresh the dataset manifest."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from export_g1_qpos_glb import export_motion  # noqa: E402

DATA_ROOT = Path("/home/fly/FlyCode/Tennis/TennisViserAnnotation/data/retarget_video_rally")
XML_LEFT = Path("/home/fly/FlyCode/Tennis/TennisViserAnnotation/unitree_g1/g1_mocap_27dof.xml")
XML_RIGHT = Path("/home/fly/FlyCode/Tennis/TennisViserAnnotation/unitree_g1/g1_mocap_27dof_federer.xml")
OUT_DIR = ROOT / "static/glb/rally"
MANIFEST = ROOT / "static/glb/manifest.json"
SERVE_DIR = ROOT / "static/glb/serve"

PLAYER_XML = {
    "nadal": XML_LEFT,
    "federer": XML_RIGHT,
    "djokovic": XML_RIGHT,
    "deyue": XML_RIGHT,
}


def sanitize(name: str) -> str:
    return re.sub(r"[^0-9A-Za-z._-]+", "_", name).strip("_") or "clip"


def detect_player(path: Path) -> str | None:
    text = str(path).lower()
    for player in ("nadal", "federer", "djokovic", "deyue"):
        if player in text:
            return player
    return None


def collect_g1_clips() -> list[Path]:
    clips = []
    for path in sorted(DATA_ROOT.rglob("*")):
        if path.suffix.lower() not in {".pkl", ".npz"}:
            continue
        if not any(part.startswith("g1_") for part in path.parts):
            continue
        clips.append(path)
    return clips


def glb_item(rel_file: str, group: str, category: str) -> dict:
    stem = Path(rel_file).stem
    player = detect_player(Path(rel_file)) or "unknown"
    return {
        "id": stem,
        "title": stem.replace("_", " "),
        "file": rel_file,
        "source": rel_file,
        "group": group,
        "category": category,
        "case": player,
        "skill": category,
        "player": player,
    }


def write_manifest(rally_files: list[str]) -> None:
    rally_items = [glb_item(f"rally/{name}", "dataset_balanced", "rally") for name in rally_files]
    serve_files = sorted(p.name for p in SERVE_DIR.glob("*.glb")) if SERVE_DIR.exists() else []
    serve_items = [glb_item(f"serve/{name}", "serve", "serve") for name in serve_files]
    manifest = {
        "title": "AdaPT G1 tennis motion preview",
        "robot": "Unitree G1",
        "task": "Video-retargeted rally clips on Unitree G1",
        "items": rally_items + serve_items,
        "groups": {
            "dataset_balanced": rally_items,
            "rally": rally_items,
            "serve": serve_items,
        },
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {MANIFEST}  rally={len(rally_items)} serve={len(serve_items)}")


def main() -> int:
    clips = collect_g1_clips()
    if not clips:
        raise SystemExit(f"No G1 pkl/npz files under {DATA_ROOT}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    exported: list[str] = []
    for src in clips:
        player = detect_player(src)
        if player is None:
            print(f"skip (unknown player): {src}")
            continue
        xml = PLAYER_XML[player]
        rel = src.relative_to(DATA_ROOT)
        out_name = sanitize("__".join(rel.with_suffix("").parts)) + ".glb"
        out_path = OUT_DIR / out_name
        print(f"export {player:8s}  xml={xml.name}  {src.name} -> {out_name}")
        export_motion(
            src,
            xml,
            out_path,
            fps_override=None,
            stride=1,
            max_frames=360,
            recenter=True,
        )
        exported.append(out_name)
    write_manifest(exported)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
