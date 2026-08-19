#!/usr/bin/env python3
"""Export Unitree G1 motion files (.npz/.pkl) as animated GLB.

``export_mocap_bvh_glb.py`` only accepts Dongbu BVH + prop CSV captures.
This script is the G1 counterpart:

  NPZ input:
    key ``qpos`` with shape (T, 7+D)
      [:, :3]  root position xyz (meters, MuJoCo Z-up)
      [:, 3:7] root quaternion wxyz
      [:, 7:]  hinge joints, matching the MJCF

  PKL input (editor format):
    dict with ``fps``, ``root_pos`` (T,3), ``root_rot`` (T,4 xyzw), ``dof_pos`` (T,D)

Example (use the mjvis env that already has mujoco):

  conda activate mjvis
  python scripts/export_g1_qpos_glb.py \\
    --input /home/fly/FlyCode/Tennis/TennisViserAnnotation/data/retarget1/FQ_1qu_pingji_neijiao_T7_correct_g1_mujoco_qpos.npz \\
    --xml /home/fly/FlyCode/Tennis/TennisViserAnnotation/unitree_g1/g1_mocap_27dof.xml \\
    --out static/glb/forehand.glb
"""

from __future__ import annotations

import argparse
import json
import math
import pickle
import re
import struct
from pathlib import Path
from typing import Iterable

import numpy as np

try:
    import mujoco
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "Need mujoco. Activate the mjvis env: conda activate mjvis"
    ) from exc


COMPONENT_FLOAT = 5126
COMPONENT_USHORT = 5123
COMPONENT_UINT = 5125
ARRAY_BUFFER = 34962
ELEMENT_ARRAY_BUFFER = 34963
MODE_TRIANGLES = 4

# MuJoCo Z-up -> glTF / Three.js Y-up: rotate -90 deg about X.
_HALF = math.sqrt(0.5)
Q_ZUP_TO_YUP = (_HALF, -_HALF, 0.0, 0.0)


class CompatUnpickler(pickle.Unpickler):
    """Compatible unpickler for numpy module path differences."""

    def find_class(self, module, name):
        if module == "numpy.core.multiarray" and hasattr(np, "_core"):
            module = "numpy._core.multiarray"
        elif module == "numpy._core.multiarray" and not hasattr(np, "_core"):
            module = "numpy.core.multiarray"
        return super().find_class(module, name)


def sanitize_name(name: str) -> str:
    name = re.sub(r"[^0-9A-Za-z._-]+", "_", name.strip())
    return name.strip("_") or "motion"


def quat_mul(a, b):
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return (
        aw * bw - ax * bx - ay * by - az * bz,
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
    )


def zup_to_yup_pos(p):
    return (float(p[0]), float(p[2]), float(-p[1]))


def zup_to_yup_quat(q_wxyz):
    return quat_mul(Q_ZUP_TO_YUP, tuple(float(v) for v in q_wxyz))


def mat3_to_quat_wxyz(mat9: np.ndarray) -> tuple[float, float, float, float]:
    quat = np.zeros(4, dtype=np.float64)
    mujoco.mju_mat2Quat(quat, np.asarray(mat9, dtype=np.float64).reshape(9))
    return (float(quat[0]), float(quat[1]), float(quat[2]), float(quat[3]))


def stabilize_quats(quats: list[tuple[float, float, float, float]]):
    out = [quats[0]]
    for q in quats[1:]:
        prev = out[-1]
        if prev[0] * q[0] + prev[1] * q[1] + prev[2] * q[2] + prev[3] * q[3] < 0:
            q = (-q[0], -q[1], -q[2], -q[3])
        out.append(q)
    return out


class GlbBuilder:
    def __init__(self):
        self.bin = bytearray()
        self.buffer_views = []
        self.accessors = []
        self.meshes = []
        self.nodes = []
        self.materials = []
        self.animation_samplers = []
        self.animation_channels = []

    def align(self):
        while len(self.bin) % 4:
            self.bin.append(0)

    def add_view(self, data: bytes, target: int | None = None) -> int:
        self.align()
        offset = len(self.bin)
        self.bin.extend(data)
        view = {"buffer": 0, "byteOffset": offset, "byteLength": len(data)}
        if target is not None:
            view["target"] = target
        self.buffer_views.append(view)
        return len(self.buffer_views) - 1

    def accessor(self, view: int, component: int, type_: str, count: int, mins=None, maxs=None) -> int:
        acc = {"bufferView": view, "componentType": component, "count": count, "type": type_}
        if mins is not None:
            acc["min"] = mins
        if maxs is not None:
            acc["max"] = maxs
        self.accessors.append(acc)
        return len(self.accessors) - 1

    def add_float_accessor(self, values: Iterable[float], type_: str, mins=None, maxs=None) -> int:
        vals = list(values)
        view = self.add_view(struct.pack("<" + "f" * len(vals), *vals), ARRAY_BUFFER)
        return self.accessor(
            view,
            COMPONENT_FLOAT,
            type_,
            len(vals) // {"SCALAR": 1, "VEC3": 3, "VEC4": 4}[type_],
            mins,
            maxs,
        )

    def add_index_accessor(self, values: Iterable[int]) -> int:
        vals = list(values)
        if max(vals, default=0) > 65535:
            view = self.add_view(struct.pack("<" + "I" * len(vals), *vals), ELEMENT_ARRAY_BUFFER)
            return self.accessor(view, COMPONENT_UINT, "SCALAR", len(vals))
        view = self.add_view(struct.pack("<" + "H" * len(vals), *vals), ELEMENT_ARRAY_BUFFER)
        return self.accessor(view, COMPONENT_USHORT, "SCALAR", len(vals))

    def add_material(self, name: str, color: list[float]) -> int:
        self.materials.append({
            "name": name,
            "pbrMetallicRoughness": {
                "baseColorFactor": color,
                "metallicFactor": 0.05,
                "roughnessFactor": 0.62,
            },
            "doubleSided": True,
        })
        return len(self.materials) - 1

    def add_mesh(self, positions: list[float], indices: list[int], material: int) -> int:
        xs, ys, zs = positions[0::3], positions[1::3], positions[2::3]
        pos_acc = self.add_float_accessor(
            positions, "VEC3", [min(xs), min(ys), min(zs)], [max(xs), max(ys), max(zs)]
        )
        idx_acc = self.add_index_accessor(indices)
        self.meshes.append({
            "primitives": [{
                "attributes": {"POSITION": pos_acc},
                "indices": idx_acc,
                "mode": MODE_TRIANGLES,
                "material": material,
            }]
        })
        return len(self.meshes) - 1

    def add_mesh_node(self, name: str, mesh_index: int, translation=None, rotation_wxyz=None) -> int:
        node = {"name": name, "mesh": mesh_index}
        if translation is not None:
            node["translation"] = [float(translation[0]), float(translation[1]), float(translation[2])]
        if rotation_wxyz is not None:
            q = rotation_wxyz
            node["rotation"] = [float(q[1]), float(q[2]), float(q[3]), float(q[0])]
        self.nodes.append(node)
        return len(self.nodes) - 1

    def add_node_trs(self, node: int, times: list[float], translations, rotations):
        time_acc = self.add_float_accessor(times, "SCALAR", [min(times)], [max(times)])
        t_acc = self.add_float_accessor([v for p in translations for v in p], "VEC3")
        r_acc = self.add_float_accessor(
            [v for q in rotations for v in [q[1], q[2], q[3], q[0]]],
            "VEC4",
        )
        t_sampler = len(self.animation_samplers)
        self.animation_samplers.append({"input": time_acc, "output": t_acc, "interpolation": "LINEAR"})
        self.animation_channels.append({
            "sampler": t_sampler,
            "target": {"node": node, "path": "translation"},
        })
        r_sampler = len(self.animation_samplers)
        self.animation_samplers.append({"input": time_acc, "output": r_acc, "interpolation": "LINEAR"})
        self.animation_channels.append({
            "sampler": r_sampler,
            "target": {"node": node, "path": "rotation"},
        })

    def write(self, path: Path):
        animations = []
        if self.animation_samplers:
            animations.append({
                "name": "qpos",
                "samplers": self.animation_samplers,
                "channels": self.animation_channels,
            })
        gltf = {
            "asset": {"version": "2.0", "generator": "AdaPT G1 qpos exporter"},
            "scene": 0,
            "scenes": [{"nodes": list(range(len(self.nodes)))}],
            "nodes": self.nodes,
            "meshes": self.meshes,
            "materials": self.materials,
            "animations": animations,
            "buffers": [{"byteLength": len(self.bin)}],
            "bufferViews": self.buffer_views,
            "accessors": self.accessors,
        }
        json_bytes = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
        while len(json_bytes) % 4:
            json_bytes += b" "
        self.align()
        total = 12 + 8 + len(json_bytes) + 8 + len(self.bin)
        blob = bytearray()
        blob += struct.pack("<III", 0x46546C67, 2, total)
        blob += struct.pack("<I4s", len(json_bytes), b"JSON") + json_bytes
        blob += struct.pack("<I4s", len(self.bin), b"BIN\x00") + self.bin
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(blob)


def _normalize_qpos_shape(qpos: np.ndarray, nq: int, source_path: Path) -> np.ndarray:
    if qpos.ndim != 2 or qpos.shape[1] < 7:
        raise ValueError(f"{source_path}: qpos must be (T, >=7), got {qpos.shape}")
    if qpos.shape[1] < nq:
        raise ValueError(f"{source_path}: qpos width {qpos.shape[1]} < model.nq {nq}")
    if qpos.shape[1] > nq:
        qpos = qpos[:, :nq]
    return qpos


def load_qpos_from_npz(npz_path: Path, nq: int) -> tuple[np.ndarray, float]:
    with np.load(npz_path, allow_pickle=True) as data:
        keys = list(data.keys())
        if "qpos" not in data:
            raise KeyError(f"{npz_path} has no 'qpos' key. keys={keys}")
        qpos = np.asarray(data["qpos"], dtype=np.float64)
        if "fps" in data:
            fps = float(np.asarray(data["fps"]).reshape(-1)[0])
        elif "sample_dt" in data:
            dt = float(np.asarray(data["sample_dt"]).reshape(-1)[0])
            fps = 1.0 / dt if dt > 1e-9 else 120.0
        else:
            fps = 120.0
    return _normalize_qpos_shape(qpos, nq, npz_path), fps


def load_qpos_from_pkl(pkl_path: Path, nq: int) -> tuple[np.ndarray, float]:
    with pkl_path.open("rb") as file:
        try:
            raw = pickle.load(file)
        except (ModuleNotFoundError, AttributeError) as exc:
            if "numpy" not in str(exc) and "_core" not in str(exc):
                raise
            file.seek(0)
            raw = CompatUnpickler(file).load()
    if not isinstance(raw, dict):
        raise TypeError(f"{pkl_path}: expected dict in pkl, got {type(raw)}")
    for key in ("root_pos", "root_rot", "dof_pos"):
        if key not in raw:
            raise KeyError(f"{pkl_path}: missing key '{key}'")
    root_pos = np.asarray(raw["root_pos"], dtype=np.float64)
    root_rot_xyzw = np.asarray(raw["root_rot"], dtype=np.float64)
    dof_pos = np.asarray(raw["dof_pos"], dtype=np.float64)
    fps = float(raw.get("fps", 30.0))
    if root_pos.ndim != 2 or root_pos.shape[1] != 3:
        raise ValueError(f"{pkl_path}: root_pos shape must be (T,3), got {root_pos.shape}")
    if root_rot_xyzw.ndim != 2 or root_rot_xyzw.shape[1] != 4:
        raise ValueError(f"{pkl_path}: root_rot shape must be (T,4), got {root_rot_xyzw.shape}")
    if dof_pos.ndim != 2:
        raise ValueError(f"{pkl_path}: dof_pos must be 2D, got {dof_pos.shape}")
    frames = root_pos.shape[0]
    if root_rot_xyzw.shape[0] != frames or dof_pos.shape[0] != frames:
        raise ValueError(
            f"{pkl_path}: frame mismatch root_pos={root_pos.shape[0]} root_rot={root_rot_xyzw.shape[0]} dof={dof_pos.shape[0]}"
        )
    root_rot_wxyz = root_rot_xyzw[:, [3, 0, 1, 2]]
    qpos = np.concatenate([root_pos, root_rot_wxyz, dof_pos], axis=1)
    return _normalize_qpos_shape(qpos, nq, pkl_path), fps


def load_qpos(input_path: Path, nq: int) -> tuple[np.ndarray, float]:
    suffix = input_path.suffix.lower()
    if suffix == ".npz":
        return load_qpos_from_npz(input_path, nq)
    if suffix == ".pkl":
        return load_qpos_from_pkl(input_path, nq)
    raise ValueError(f"Unsupported input format: {input_path} (expect .npz or .pkl)")


def visual_mesh_geoms(model: mujoco.MjModel) -> list[int]:
    geoms = []
    for geom_id in range(model.ngeom):
        if int(model.geom_type[geom_id]) != int(mujoco.mjtGeom.mjGEOM_MESH):
            continue
        if int(model.geom_group[geom_id]) != 1:
            continue
        geoms.append(geom_id)
    if not geoms:
        raise RuntimeError("No visual mesh geoms (group=1) found in XML")
    return geoms


def mesh_triangles(model: mujoco.MjModel, mesh_id: int) -> tuple[list[float], list[int]]:
    vert_adr = int(model.mesh_vertadr[mesh_id])
    vert_num = int(model.mesh_vertnum[mesh_id])
    face_adr = int(model.mesh_faceadr[mesh_id])
    face_num = int(model.mesh_facenum[mesh_id])
    verts = np.asarray(model.mesh_vert[vert_adr:vert_adr + vert_num], dtype=np.float64)
    faces = np.asarray(model.mesh_face[face_adr:face_adr + face_num], dtype=np.int32)
    if verts.size == 0 or faces.size == 0:
        raise ValueError(f"mesh {mesh_id} is empty")
    positions = [float(v) for v in verts.reshape(-1)]
    indices = [int(i) for i in faces.reshape(-1)]
    return positions, indices


def simplify_mesh(positions: list[float], indices: list[int], voxel: float) -> tuple[list[float], list[int]]:
    """Weld vertices onto a voxel grid so preview GLBs stay lightweight."""
    if voxel <= 0 or not positions or not indices:
        return positions, indices
    verts = np.asarray(positions, dtype=np.float64).reshape(-1, 3)
    faces = np.asarray(indices, dtype=np.int32).reshape(-1, 3)
    keys = np.round(verts / voxel).astype(np.int64)
    uniq, inverse = np.unique(keys, axis=0, return_inverse=True)
    mapped = inverse[faces]
    keep = (
        (mapped[:, 0] != mapped[:, 1])
        & (mapped[:, 1] != mapped[:, 2])
        & (mapped[:, 0] != mapped[:, 2])
    )
    mapped = mapped[keep]
    if mapped.size == 0:
        return positions, indices
    new_verts = uniq.astype(np.float64) * voxel
    return new_verts.reshape(-1).tolist(), mapped.reshape(-1).astype(int).tolist()


def is_racket_mesh(model: mujoco.MjModel, mesh_id: int) -> bool:
    name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_MESH, mesh_id) or ""
    lowered = name.lower()
    return "racket" in lowered or "23_25" in lowered or "deg" in lowered


def export_motion(
    input_path: Path,
    xml_path: Path,
    out_path: Path,
    *,
    fps_override: float | None,
    stride: int,
    max_frames: int,
    recenter: bool,
    start_time: float = 0.0,
    end_time: float | None = None,
    mesh_voxel: float = 0.0,
) -> None:
    model = mujoco.MjModel.from_xml_path(str(xml_path))
    data = mujoco.MjData(model)
    qpos, fps = load_qpos(input_path, model.nq)
    if fps_override:
        fps = float(fps_override)
    start_frame = max(0, int(round(max(0.0, start_time) * fps)))
    last_frame = qpos.shape[0]
    if end_time is not None and end_time > start_time:
        last_frame = min(last_frame, int(round(end_time * fps)) + 1)
    frame_ids = list(range(start_frame, last_frame, max(1, stride)))[:max_frames]
    if not frame_ids:
        raise ValueError(
            f"{input_path}: no frames in [{start_time:g}, {end_time}]s "
            f"(fps={fps:g}, T={qpos.shape[0]})"
        )
    times = [i * stride / fps for i in range(len(frame_ids))]
    geoms = visual_mesh_geoms(model)

    translations = {geom_id: [] for geom_id in geoms}
    rotations = {geom_id: [] for geom_id in geoms}
    origin = np.zeros(3, dtype=np.float64)
    min_z = None

    for step, frame_id in enumerate(frame_ids):
        data.qpos[:] = qpos[frame_id]
        mujoco.mj_forward(model, data)
        if recenter and step == 0:
            origin[0] = float(qpos[frame_id, 0])
            origin[1] = float(qpos[frame_id, 1])
            zs = [float(data.geom_xpos[g][2]) for g in geoms]
            origin[2] = min(zs)
            min_z = origin[2]
        for geom_id in geoms:
            pos = np.asarray(data.geom_xpos[geom_id], dtype=np.float64) - origin
            quat = mat3_to_quat_wxyz(data.geom_xmat[geom_id])
            translations[geom_id].append(zup_to_yup_pos(pos))
            rotations[geom_id].append(zup_to_yup_quat(quat))

    builder = GlbBuilder()
    robot_mat = builder.add_material("g1_body", [0.72, 0.76, 0.82, 1.0])
    dark_mat = builder.add_material("g1_dark", [0.18, 0.20, 0.24, 1.0])
    racket_mat = builder.add_material("racket", [0.7, 0.7, 0.7, 1.0])
    mesh_cache: dict[int, int] = {}

    for geom_id in geoms:
        mesh_id = int(model.geom_dataid[geom_id])
        if mesh_id not in mesh_cache:
            positions, indices = mesh_triangles(model, mesh_id)
            voxel = mesh_voxel
            if voxel > 0 and is_racket_mesh(model, mesh_id):
                voxel = min(voxel, 0.004)
            positions, indices = simplify_mesh(positions, indices, voxel)
            rgba = [float(v) for v in model.geom_rgba[geom_id][:4]]
            if is_racket_mesh(model, mesh_id):
                material = racket_mat
            elif sum(rgba[:3]) < 1.2:
                material = dark_mat
            else:
                material = robot_mat
            mesh_cache[mesh_id] = builder.add_mesh(positions, indices, material)
        body_id = int(model.geom_bodyid[geom_id])
        body_name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body_id) or f"body_{body_id}"
        quats = stabilize_quats(rotations[geom_id])
        node = builder.add_mesh_node(
            f"{sanitize_name(body_name)}_{geom_id}",
            mesh_cache[mesh_id],
            translation=translations[geom_id][0],
            rotation_wxyz=quats[0],
        )
        builder.add_node_trs(node, times, translations[geom_id], quats)

    builder.write(out_path)
    print(
        f"wrote {out_path}  frames={len(frame_ids)}/{qpos.shape[0]}  "
        f"fps={fps:g} stride={stride} geoms={len(geoms)}  "
        f"origin_z={0.0 if min_z is None else min_z:.3f}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=None, help="Input motion file (.npz qpos or .pkl)")
    parser.add_argument("--npz", type=Path, default=None, help="Backward compatibility alias of --input")
    parser.add_argument("--xml", type=Path, required=True, help="G1 MJCF, e.g. unitree_g1/g1_mocap_27dof.xml")
    parser.add_argument("--out", type=Path, required=True, help="Output .glb path")
    parser.add_argument("--fps", type=float, default=None, help="Override fps (default: file fps, else 120)")
    parser.add_argument("--stride", type=int, default=4, help="Keep every Nth frame")
    parser.add_argument("--max-frames", type=int, default=36000)
    parser.add_argument("--start-time", type=float, default=0.0, help="Clip start in seconds")
    parser.add_argument("--end-time", type=float, default=None, help="Clip end in seconds")
    parser.add_argument("--mesh-voxel", type=float, default=0.0, help="Weld vertices onto this grid (meters) for lighter previews")
    parser.add_argument("--no-recenter", action="store_true", help="Keep original world origin")
    args = parser.parse_args()
    input_path = args.input or args.npz
    if input_path is None:
        parser.error("one of --input / --npz is required")
    export_motion(
        input_path.expanduser().resolve(),
        args.xml.expanduser().resolve(),
        args.out.expanduser(),
        fps_override=args.fps,
        stride=max(1, args.stride),
        max_frames=args.max_frames,
        recenter=not args.no_recenter,
        start_time=max(0.0, args.start_time),
        end_time=args.end_time,
        mesh_voxel=max(0.0, args.mesh_voxel),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
