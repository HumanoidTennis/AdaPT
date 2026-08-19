#!/usr/bin/env python3
"""Export lightweight GLBs for the 7 Dataset gallery cards.

Full-resolution clips in static/glb/{rally,serve} are left untouched.
These previews trim to the on-page loop window, downsample mocap to 30 Hz,
and weld visual meshes onto a coarse voxel grid.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from export_g1_qpos_glb import export_motion

DATA = Path("/home/fly/FlyCode/Tennis/TennisViserAnnotation/data")
XML_LEFT = Path("/home/fly/FlyCode/Tennis/TennisViserAnnotation/unitree_g1/g1_mocap_27dof.xml")
XML_RIGHT = Path("/home/fly/FlyCode/Tennis/TennisViserAnnotation/unitree_g1/g1_mocap_27dof_federer.xml")
OUT_DIR = ROOT / "static/glb/preview"

PREVIEWS = [
    {
        "out": "forehand.glb",
        "input": DATA / "retarget_rally/g1_video/nadal/forehand.pkl",
        "xml": XML_LEFT,
        "stride": 1,
        "start_time": 0.0,
        "end_time": None,
    },
    {
        "out": "backhand.glb",
        "input": DATA / "retarget_rally/g1_video/nadal/backhand.pkl",
        "xml": XML_LEFT,
        "stride": 1,
        "start_time": 0.0,
        "end_time": None,
    },
    {
        "out": "slice.glb",
        "input": DATA / "retarget_rally/g1_video/nadal/slice.pkl",
        "xml": XML_LEFT,
        "stride": 1,
        "start_time": 0.0,
        "end_time": None,
    },
    {
        "out": "drop.glb",
        "input": DATA / "retarget_rally/g1_mocap/p1/FD_zhengshou_zhixian_53_faqiuji_T1_mujoco_qpos.npz",
        "xml": XML_LEFT,
        "stride": 4,
        "start_time": 10.0,
        "end_time": 30.0,
    },
    {
        "out": "volley.glb",
        "input": DATA / "retarget_rally/g1_mocap/p1/JJ_zhengshou_zhixian_56_faqiuji_T1_mujoco_qpos.npz",
        "xml": XML_LEFT,
        "stride": 4,
        "start_time": 10.0,
        "end_time": 30.0,
    },
    {
        "out": "flat_serve.glb",
        "input": DATA / "retarge_serve/mocap/p1/FQ_1qu_pingji_neijiao_T1_mujoco_qpos.npz",
        "xml": XML_LEFT,
        "stride": 4,
        "start_time": 5.0,
        "end_time": 20.0,
    },
    {
        "out": "topspin_serve.glb",
        "input": DATA / "retarge_serve/mocap/p2/FQ_1qu_shangxuan_zhongjian_T1_mujoco_qpos.npz",
        "xml": XML_RIGHT,
        "stride": 4,
        "start_time": 10.0,
        "end_time": 30.0,
    },
]


def main() -> int:
    missing = [clip["input"] for clip in PREVIEWS if not clip["input"].exists()]
    if missing:
        raise SystemExit("Missing source files:\n" + "\n".join(f"  {path}" for path in missing))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for clip in PREVIEWS:
        out_path = OUT_DIR / clip["out"]
        print(f"preview {clip['out']} <- {clip['input'].name}")
        export_motion(
            clip["input"],
            clip["xml"],
            out_path,
            fps_override=None,
            stride=clip["stride"],
            max_frames=36000,
            recenter=True,
            start_time=clip["start_time"],
            end_time=clip["end_time"],
            mesh_voxel=0.008,
        )
        print(f"  size={out_path.stat().st_size / 1024 / 1024:.2f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
