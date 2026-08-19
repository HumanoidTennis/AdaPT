#!/usr/bin/env python3
"""Export serve and rally retarget motions to static/glb/{serve,rally}."""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

SERVE_ROOT = Path("/home/fly/FlyCode/Tennis/TennisViserAnnotation/data/retarge_serve")
RALLY_ROOT = Path("/home/fly/FlyCode/Tennis/TennisViserAnnotation/data/retarget_rally")
XML_LEFT = Path("/home/fly/FlyCode/Tennis/TennisViserAnnotation/unitree_g1/g1_mocap_27dof.xml")
XML_RIGHT = Path("/home/fly/FlyCode/Tennis/TennisViserAnnotation/unitree_g1/g1_mocap_27dof_federer.xml")
SERVE_OUT = ROOT / "static/glb/serve"
RALLY_OUT = ROOT / "static/glb/rally"
MANIFEST = ROOT / "static/glb/manifest.json"

LEFT_PLAYERS = {"nadal", "p1"}
RIGHT_PLAYERS = {"federer", "deyue", "djokovic", "p2", "p3"}
PLAYER_ORDER = ("nadal", "federer", "deyue", "djokovic", "p1", "p2", "p3")

SERVE_ALIASES = {
    "nadal_correct.pkl": "fq_nadal.glb",
    "federer_correct.pkl": "fq_federer.glb",
    "deyue_correct.pkl": "fq_deyue.glb",
}


def sanitize(name: str) -> str:
    return re.sub(r"[^0-9A-Za-z._-]+", "_", name).strip("_") or "clip"


def detect_player(path: Path) -> str | None:
    parts = [part.lower() for part in path.parts]
    text = "/".join(parts)
    for player in PLAYER_ORDER:
        if player in parts or f"serve_{player}" in text or f"_{player}" in f"_{path.stem.lower()}_":
            return player
    stem = path.stem.lower()
    for player in PLAYER_ORDER:
        if stem.startswith(player) or f"_{player}_" in f"_{stem}_":
            return player
    return None


def xml_for_player(player: str) -> Path:
    if player in LEFT_PLAYERS:
        return XML_LEFT
    if player in RIGHT_PLAYERS:
        return XML_RIGHT
    raise SystemExit(f"No handedness mapping for player={player}")


def collect_clips(root: Path) -> list[Path]:
    clips = []
    for path in sorted(root.rglob("*")):
        if path.suffix.lower() in {".pkl", ".npz"}:
            clips.append(path)
    return clips


def shorten_stem(stem: str) -> str:
    stem = re.sub(r"_mujoco_qpos$", "", stem)
    stem = re.sub(r"_correct_g1$", "", stem)
    stem = re.sub(r"_correct_wrist$", "", stem)
    stem = re.sub(r"_correct$", "", stem)
    return stem


def output_name(src: Path, data_root: Path) -> str:
    rel = src.relative_to(data_root)
    prefix = sanitize("_".join(rel.parts[:-1]))
    stem = sanitize(shorten_stem(src.stem))
    if prefix:
        return f"{prefix}_{stem}.glb"
    return f"{stem}.glb"


def glb_item(rel_file: str, group: str, category: str, player: str) -> dict:
    stem = Path(rel_file).stem
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


def export_one(src: Path, xml: Path, out_path: Path) -> None:
    from export_g1_qpos_glb import export_motion

    out_path.parent.mkdir(parents=True, exist_ok=True)
    export_motion(
        src,
        xml,
        out_path,
        fps_override=None,
        stride=1,
        max_frames=36000,
        recenter=True,
    )


def export_tree(data_root: Path, out_dir: Path, category: str) -> list[tuple[str, str]]:
    exported: list[tuple[str, str]] = []
    clips = collect_clips(data_root)
    if not clips:
        raise SystemExit(f"No pkl/npz files under {data_root}")
    for src in clips:
        player = detect_player(src)
        if player is None:
            print(f"skip (unknown player): {src}")
            continue
        xml = xml_for_player(player)
        name = output_name(src, data_root)
        out_path = out_dir / name
        print(f"export {category:5s} {player:8s}  xml={xml.name}  {src.name} -> {name}")
        export_one(src, xml, out_path)
        exported.append((name, player))
        alias = SERVE_ALIASES.get(src.name)
        if category == "serve" and alias and alias != name:
            alias_path = out_dir / alias
            shutil.copy2(out_path, alias_path)
            print(f"  alias {alias}")
            exported.append((alias, player))
    return exported


def unique_serve(serve: list[tuple[str, str]]) -> list[tuple[str, str]]:
    seen: set[str] = set()
    unique: list[tuple[str, str]] = []
    preferred = [
        "fq_nadal.glb",
        "fq_federer.glb",
        "fq_deyue.glb",
        "mocap_p1_FQ_1qu_pingji_neijiao_T7.glb",
        "mocap_p1_FQ_1qu_pingji_neijiao_T1.glb",
        "mocap_p1_FQ_1qu_shangxuan_zhongjian_T1.glb",
        "mocap_p2_FQ_1qu_pingji_zhongjian_T1.glb",
        "mocap_p2_FQ_1qu_shangxuan_zhongjian_T1.glb",
        "mocap_p3_FQ_1qu_pingji_zhongjian_T1.glb",
        "mocap_p3_FQ_1qu_shangxuan_zhongjian_T1.glb",
    ]
    by_name = {name: player for name, player in serve}
    for name in preferred:
        if name in by_name and name not in seen:
            unique.append((name, by_name[name]))
            seen.add(name)
    for name, player in serve:
        if name in seen or name.startswith("video_serve_"):
            continue
        unique.append((name, player))
        seen.add(name)
        if len(unique) == 10:
            break
    return unique[:10]


def interleave_grid(rally: list[tuple[str, str]], serve: list[tuple[str, str]]) -> list[dict]:
    def is_rally_video(name: str) -> bool:
        return "_video_" in name or name.startswith("g1_video_")

    mocap = [(name, player) for name, player in rally if not is_rally_video(name)]
    video = [(name, player) for name, player in rally if is_rally_video(name)]
    # 7x5 grid: left 5 columns are rally -> 25 slots.
    # Force last 2 rows (10 slots) to be video, first 3 rows (15 slots) to be mocap.
    rally_grid = mocap[:15] + video[:10]
    if len(rally_grid) < 25:
        rest = mocap[15:] + video[10:]
        rally_grid.extend(rest[: 25 - len(rally_grid)])

    rally_items = [glb_item(f"rally/{name}", "dataset_balanced", "rally", player) for name, player in rally_grid]
    serve_items = [glb_item(f"serve/{name}", "dataset_balanced", "serve", player) for name, player in serve]
    grid: list[dict] = []
    rally_i = 0
    serve_i = 0
    for _row in range(5):
        for _col in range(5):
            if rally_i < len(rally_items):
                grid.append(rally_items[rally_i])
                rally_i += 1
        for _col in range(2):
            if serve_i < len(serve_items):
                grid.append(serve_items[serve_i])
                serve_i += 1
    return grid


def write_manifest(rally: list[tuple[str, str]], serve: list[tuple[str, str]]) -> None:
    rally = sort_rally(rally)
    serve_unique = unique_serve(serve)
    grid_items = interleave_grid(rally, serve_unique)
    rally_items = [glb_item(f"rally/{name}", "rally", "rally", player) for name, player in rally]
    serve_items = [glb_item(f"serve/{name}", "serve", "serve", player) for name, player in serve_unique]
    manifest = {
        "title": "AdaPT G1 tennis motion preview",
        "robot": "Unitree G1",
        "task": "35 G1 clips in a 7x5 grid: rally left 5 columns, serve right 2 columns",
        "layout": {"columns": 7, "rows": 5, "rally_columns": 5, "serve_columns": 2},
        "items": grid_items,
        "groups": {
            "dataset_balanced": grid_items,
            "rally": rally_items,
            "serve": serve_items,
        },
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {MANIFEST}  grid={len(grid_items)} rally={len(rally_items)} serve={len(serve_items)}")


def sort_rally(items: list[tuple[str, str]]) -> list[tuple[str, str]]:
    def is_video(name: str) -> bool:
        return "_video_" in name or name.startswith("g1_video_")

    mocap = [(name, player) for name, player in items if not is_video(name)]
    video = [(name, player) for name, player in items if is_video(name)]
    mocap.sort(key=lambda item: item[0])
    video.sort(key=lambda item: item[0])
    return mocap + video


def clips_from_dir(folder: Path) -> list[tuple[str, str]]:
    items = []
    for path in sorted(folder.glob("*.glb")):
        player = detect_player(path) or "unknown"
        items.append((path.name, player))
    return items


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest-only", action="store_true", help="Rebuild manifest from existing GLBs")
    args = parser.parse_args()
    if args.manifest_only:
        rally = clips_from_dir(RALLY_OUT)
        serve = clips_from_dir(SERVE_OUT)
        write_manifest(rally, serve)
        return 0
    rally = export_tree(RALLY_ROOT, RALLY_OUT, "rally")
    serve = export_tree(SERVE_ROOT, SERVE_OUT, "serve")
    write_manifest(rally, serve)
    print(f"done rally={len(rally)} serve={len(serve)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
