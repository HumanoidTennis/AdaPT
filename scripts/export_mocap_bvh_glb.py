#!/usr/bin/env python3
"""Export Dongbu BVH + prop CSV captures as lightweight animated GLB files.

The exporter intentionally avoids Blender and third-party Python packages so it
can run in this project environment. It visualizes the BVH performer as a
keyframed skeleton-line mesh and each prop_*.csv as an animated primitive.
"""

from __future__ import annotations

import argparse
import base64
import csv
import json
import math
import re
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


COMPONENT_FLOAT = 5126
COMPONENT_USHORT = 5123
ARRAY_BUFFER = 34962
ELEMENT_ARRAY_BUFFER = 34963
DEFAULT_ASSET_DIR = Path("/home/lightcone/workspace/projects/g1_retarget/assets")


@dataclass
class Joint:
    name: str
    offset: tuple[float, float, float]
    channels: list[str] = field(default_factory=list)
    parent: int = -1
    children: list[int] = field(default_factory=list)
    channel_start: int = 0


@dataclass
class BvhMotion:
    joints: list[Joint]
    edges: list[tuple[int, int]]
    frame_time: float
    frames: list[list[float]]


def sanitize_name(name: str) -> str:
    name = re.sub(r"[^0-9A-Za-z._-]+", "_", name.strip())
    return name.strip("_") or "motion"


def read_bvh(path: Path, max_frames: int, stride: int) -> BvhMotion:
    lines = path.read_text(errors="ignore").splitlines()
    joints: list[Joint] = []
    edges: list[tuple[int, int]] = []
    stack: list[int] = []
    channel_cursor = 0
    motion_line = None
    pending_joint = None

    i = 0
    while i < len(lines):
        raw = lines[i].strip()
        parts = raw.split()
        if not parts:
            i += 1
            continue
        if parts[0] == "MOTION":
            motion_line = i
            break
        if parts[0] in {"ROOT", "JOINT"}:
            parent = stack[-1] if stack else -1
            pending_joint = Joint(name=sanitize_name(parts[1]), offset=(0.0, 0.0, 0.0), parent=parent)
            joints.append(pending_joint)
            if parent >= 0:
                joints[parent].children.append(len(joints) - 1)
                edges.append((parent, len(joints) - 1))
        elif parts[0] == "End" and parts[1] == "Site":
            parent = stack[-1]
            pending_joint = Joint(name=f"{joints[parent].name}_end", offset=(0.0, 0.0, 0.0), parent=parent)
            joints.append(pending_joint)
            joints[parent].children.append(len(joints) - 1)
            edges.append((parent, len(joints) - 1))
        elif parts[0] == "{":
            if pending_joint is not None:
                stack.append(len(joints) - 1)
                pending_joint = None
        elif parts[0] == "}":
            if stack:
                stack.pop()
        elif parts[0] == "OFFSET":
            joints[-1].offset = (float(parts[1]) / 100.0, float(parts[2]) / 100.0, float(parts[3]) / 100.0)
        elif parts[0] == "CHANNELS":
            count = int(parts[1])
            joints[-1].channels = parts[2:2 + count]
            joints[-1].channel_start = channel_cursor
            channel_cursor += count
        i += 1

    if motion_line is None:
        raise ValueError(f"{path} has no MOTION section")

    frames_line = lines[motion_line + 1].split()
    frame_time_line = lines[motion_line + 2].split()
    total_frames = int(frames_line[-1])
    frame_time = float(frame_time_line[-1])
    frames = []
    for idx, line in enumerate(lines[motion_line + 3:motion_line + 3 + total_frames]):
        if idx % stride != 0:
            continue
        frames.append([float(v) for v in line.split()])
        if len(frames) >= max_frames:
            break
    return BvhMotion(joints=joints, edges=edges, frame_time=frame_time * stride, frames=frames)


def quat_mul(a, b):
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return (
        aw * bw - ax * bx - ay * by - az * bz,
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
    )


def quat_axis(axis: str, deg: float):
    rad = math.radians(deg) * 0.5
    c, s = math.cos(rad), math.sin(rad)
    if axis == "X":
        return (c, s, 0.0, 0.0)
    if axis == "Y":
        return (c, 0.0, s, 0.0)
    return (c, 0.0, 0.0, s)


def rotate_vec(q, v):
    w, x, y, z = q
    vx, vy, vz = v
    # q * v * q^-1, expanded.
    tx = 2.0 * (y * vz - z * vy)
    ty = 2.0 * (z * vx - x * vz)
    tz = 2.0 * (x * vy - y * vx)
    return (
        vx + w * tx + (y * tz - z * ty),
        vy + w * ty + (z * tx - x * tz),
        vz + w * tz + (x * ty - y * tx),
    )


def add_vec(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def frame_joint_positions(motion: BvhMotion, values: list[float]) -> list[tuple[float, float, float]]:
    positions = [(0.0, 0.0, 0.0)] * len(motion.joints)
    rotations = [(1.0, 0.0, 0.0, 0.0)] * len(motion.joints)
    for i, joint in enumerate(motion.joints):
        local_pos = joint.offset
        local_rot = (1.0, 0.0, 0.0, 0.0)
        start = joint.channel_start
        for c, channel in enumerate(joint.channels):
            value = values[start + c]
            if channel.endswith("position"):
                axis = channel[0]
                idx = {"X": 0, "Y": 1, "Z": 2}[axis]
                local_pos = tuple((value / 100.0 if n == idx else local_pos[n]) for n in range(3))
            elif channel.endswith("rotation"):
                local_rot = quat_mul(local_rot, quat_axis(channel[0], value))
        if joint.parent >= 0:
            positions[i] = add_vec(positions[joint.parent], rotate_vec(rotations[joint.parent], local_pos))
            rotations[i] = quat_mul(rotations[joint.parent], local_rot)
        else:
            positions[i] = local_pos
            rotations[i] = local_rot
    return positions


def read_prop_csv(path: Path, max_frames: int, stride: int) -> tuple[list[tuple[float, float, float]], list[tuple[float, float, float, float]]]:
    positions = []
    rotations = []
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader):
            if idx % stride != 0:
                continue
            positions.append((float(row["px"]), float(row["py"]), float(row["pz"])))
            rotations.append((float(row["qw"]), float(row["qx"]), float(row["qy"]), float(row["qz"])))
            if len(positions) >= max_frames:
                break
    return positions, rotations


class GlbBuilder:
    def __init__(self):
        self.bin = bytearray()
        self.buffer_views = []
        self.accessors = []
        self.meshes = []
        self.nodes = []
        self.animations = []

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
        return self.accessor(view, COMPONENT_FLOAT, type_, len(vals) // {"SCALAR": 1, "VEC3": 3, "VEC4": 4}[type_], mins, maxs)

    def add_u16_accessor(self, values: Iterable[int]) -> int:
        vals = list(values)
        view = self.add_view(struct.pack("<" + "H" * len(vals), *vals), ELEMENT_ARRAY_BUFFER)
        return self.accessor(view, COMPONENT_USHORT, "SCALAR", len(vals))

    def add_mesh_node(self, name: str, positions: list[float], indices: list[int], mode: int, color: list[float]) -> int:
        mesh_index = self.add_mesh(positions, indices, mode, color)
        node = {"name": name, "mesh": mesh_index}
        self.nodes.append(node)
        return len(self.nodes) - 1

    def add_mesh(self, positions: list[float], indices: list[int], mode: int, color: list[float]) -> int:
        xs, ys, zs = positions[0::3], positions[1::3], positions[2::3]
        pos_acc = self.add_float_accessor(positions, "VEC3", [min(xs), min(ys), min(zs)], [max(xs), max(ys), max(zs)])
        idx_acc = self.add_u16_accessor(indices)
        mesh = {
            "primitives": [{
                "attributes": {"POSITION": pos_acc},
                "indices": idx_acc,
                "mode": mode,
                "material": 0 if color[0] < 0.8 else 1,
            }]
        }
        self.meshes.append(mesh)
        return len(self.meshes) - 1

    def add_mesh_instance_node(self, name: str, mesh_index: int) -> int:
        self.nodes.append({"name": name, "mesh": mesh_index})
        return len(self.nodes) - 1

    def add_animation(self, node: int, times: list[float], translations=None, rotations=None, scales=None):
        samplers = []
        channels = []
        time_acc = self.add_float_accessor(times, "SCALAR", [min(times)], [max(times)])
        if translations:
            out = self.add_float_accessor([v for p in translations for v in p], "VEC3")
            samplers.append({"input": time_acc, "output": out, "interpolation": "LINEAR"})
            channels.append({"sampler": len(samplers) - 1, "target": {"node": node, "path": "translation"}})
        if rotations:
            out = self.add_float_accessor([v for q in rotations for v in [q[1], q[2], q[3], q[0]]], "VEC4")
            samplers.append({"input": time_acc, "output": out, "interpolation": "LINEAR"})
            channels.append({"sampler": len(samplers) - 1, "target": {"node": node, "path": "rotation"}})
        if scales:
            out = self.add_float_accessor([v for s in scales for v in s], "VEC3")
            samplers.append({"input": time_acc, "output": out, "interpolation": "LINEAR"})
            channels.append({"sampler": len(samplers) - 1, "target": {"node": node, "path": "scale"}})
        if samplers:
            self.animations.append({"name": "mocap", "samplers": samplers, "channels": channels})

    def write(self, path: Path):
        gltf = {
            "asset": {"version": "2.0", "generator": "OmniContact BVH CSV exporter"},
            "scene": 0,
            "scenes": [{"nodes": list(range(len(self.nodes)))}],
            "nodes": self.nodes,
            "meshes": self.meshes,
            "materials": [
                {
                    "name": "skeleton_blue",
                    "pbrMetallicRoughness": {"baseColorFactor": [0.12, 0.35, 0.9, 1], "roughnessFactor": 0.65},
                    "alphaMode": "OPAQUE",
                },
                {
                    "name": "object_orange",
                    "pbrMetallicRoughness": {"baseColorFactor": [0.95, 0.45, 0.12, 1], "roughnessFactor": 0.55},
                    "alphaMode": "OPAQUE",
                    "doubleSided": True,
                },
            ],
            "animations": self.animations,
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
        path.write_bytes(blob)


def cube_geometry(size: float = 0.35):
    s = size / 2
    positions = [
        -s, -s, -s, s, -s, -s, s, s, -s, -s, s, -s,
        -s, -s, s, s, -s, s, s, s, s, -s, s, s,
    ]
    indices = [
        0, 1, 2, 0, 2, 3, 4, 6, 5, 4, 7, 6,
        0, 4, 5, 0, 5, 1, 3, 2, 6, 3, 6, 7,
        1, 5, 6, 1, 6, 2, 0, 3, 7, 0, 7, 4,
    ]
    return positions, indices


def read_obj_mesh(path: Path) -> tuple[list[float], list[int]]:
    """Read a simple OBJ mesh, converting centimeter vertices to meters."""
    vertices: list[tuple[float, float, float]] = []
    indices: list[int] = []
    for raw in path.read_text(errors="ignore").splitlines():
        parts = raw.strip().split()
        if not parts:
            continue
        if parts[0] == "v" and len(parts) >= 4:
            vertices.append((float(parts[1]) / 100.0, float(parts[2]) / 100.0, float(parts[3]) / 100.0))
        elif parts[0] == "f" and len(parts) >= 4:
            face = []
            for token in parts[1:]:
                vertex_index = int(token.split("/")[0])
                if vertex_index < 0:
                    vertex_index = len(vertices) + vertex_index + 1
                face.append(vertex_index - 1)
            for i in range(1, len(face) - 1):
                indices.extend([face[0], face[i], face[i + 1]])
    if not vertices or not indices:
        raise ValueError(f"{path} has no supported OBJ geometry")
    return [value for vertex in vertices for value in vertex], indices


def prop_asset_path(prop_csv: Path, asset_dir: Path) -> Path | None:
    name = prop_csv.stem
    if name.startswith("prop_"):
        name = name[len("prop_"):]
    candidates = [asset_dir / f"{name}.obj"]
    if name.startswith("SoccerBall"):
        candidates.append(asset_dir / f"ScoccerBall{name[len('SoccerBall'):]}.obj")
    if name.startswith("ScoccerBall"):
        candidates.append(asset_dir / f"SoccerBall{name[len('ScoccerBall'):]}.obj")
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def bone_bar_geometry(thickness: float = 0.035):
    # Unit-length bar aligned with local +Y. Animated scale.y sets bone length.
    x = z = thickness / 2
    y0, y1 = -0.5, 0.5
    positions = [
        -x, y0, -z, x, y0, -z, x, y1, -z, -x, y1, -z,
        -x, y0, z, x, y0, z, x, y1, z, -x, y1, z,
    ]
    indices = [
        0, 1, 2, 0, 2, 3, 4, 6, 5, 4, 7, 6,
        0, 4, 5, 0, 5, 1, 3, 2, 6, 3, 6, 7,
        1, 5, 6, 1, 6, 2, 0, 3, 7, 0, 7, 4,
    ]
    return positions, indices


def sub_vec(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def mul_vec(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def vec_len(v):
    return math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])


def normalize(v):
    length = vec_len(v)
    if length < 1e-8:
        return (0.0, 1.0, 0.0)
    return (v[0] / length, v[1] / length, v[2] / length)


def quat_from_y_to_vec(v):
    target = normalize(v)
    dot = max(-1.0, min(1.0, target[1]))
    if dot > 0.9999:
        return (1.0, 0.0, 0.0, 0.0)
    if dot < -0.9999:
        return (0.0, 1.0, 0.0, 0.0)
    axis = (target[2], 0.0, -target[0])
    axis = normalize(axis)
    angle = math.acos(dot) * 0.5
    s = math.sin(angle)
    return (math.cos(angle), axis[0] * s, axis[1] * s, axis[2] * s)


def capture_category_case(capture_dir: Path, input_root: Path) -> tuple[str, str]:
    rel = capture_dir.relative_to(input_root).parts
    if len(rel) >= 2 and rel[0] == "box_mocap":
        return "box", rel[1]
    if len(rel) >= 2 and rel[0] == "soccer_mocap":
        return "ball", rel[1]
    return "other", rel[0] if rel else "other"


def export_capture(capture_dir: Path, input_root: Path, out_dir: Path, max_frames: int, stride: int, asset_dir: Path) -> dict | None:
    bvh = capture_dir / "motion_actor.bvh"
    props = sorted(capture_dir.glob("prop_*.csv"))
    if not bvh.exists() or not props:
        return None
    rel_name = "_".join(capture_dir.relative_to(input_root).parts)
    name = sanitize_name(rel_name)
    out_file = out_dir / f"{name}.glb"
    motion = read_bvh(bvh, max_frames=max_frames, stride=stride)
    times = [i * motion.frame_time for i in range(len(motion.frames))]

    builder = GlbBuilder()
    joint_positions_per_frame = [frame_joint_positions(motion, frame) for frame in motion.frames]
    root_first = joint_positions_per_frame[0][0]
    ground_y = min(position[1] for position in joint_positions_per_frame[0])
    scene_origin = (root_first[0], ground_y, root_first[2])
    joint_positions_per_frame = [
        [sub_vec(position, scene_origin) for position in frame]
        for frame in joint_positions_per_frame
    ]

    bone_pos, bone_idx = bone_bar_geometry(0.018)
    bone_mesh = builder.add_mesh(bone_pos, bone_idx, 4, [0.12, 0.35, 0.9, 1])
    for edge_i, (a, b) in enumerate(motion.edges):
        node = builder.add_mesh_instance_node(f"bvh_bone_{motion.joints[a].name}_to_{motion.joints[b].name}", bone_mesh)
        translations = []
        rotations = []
        scales = []
        for frame in joint_positions_per_frame:
            start = frame[a]
            end = frame[b]
            delta = sub_vec(end, start)
            length = max(vec_len(delta), 1e-5)
            translations.append(add_vec(start, mul_vec(delta, 0.5)))
            rotations.append(quat_from_y_to_vec(delta))
            scales.append((1.0, length, 1.0))
        builder.add_animation(node, times, translations=translations, rotations=rotations, scales=scales)

    fallback_pos, fallback_idx = cube_geometry(0.3)
    for prop in props:
        prop_positions, prop_rotations = read_prop_csv(prop, max_frames=max_frames, stride=stride)
        if not prop_positions:
            continue 
        prop_positions = [sub_vec(position, scene_origin) for position in prop_positions]
        asset = prop_asset_path(prop, asset_dir)
        if asset:
            prop_pos, prop_idx = read_obj_mesh(asset)
        else:
            prop_pos, prop_idx = fallback_pos, fallback_idx
        node = builder.add_mesh_node(sanitize_name(prop.stem), prop_pos, prop_idx, 4, [0.95, 0.45, 0.12, 1])
        n = min(len(times), len(prop_positions))
        builder.add_animation(node, times[:n], translations=prop_positions[:n], rotations=prop_rotations[:n])

    out_dir.mkdir(parents=True, exist_ok=True)
    builder.write(out_file)
    return {
        "id": out_file.stem,
        "title": capture_dir.parent.name + "/" + capture_dir.name,
        "file": out_file.name,
        "source": str(capture_dir),
        "category": capture_category_case(capture_dir, input_root)[0],
        "case": capture_category_case(capture_dir, input_root)[1],
    }


def discover_captures(root: Path, limit: int | None, per_case_limit: int | None, categories: set[str] | None) -> list[Path]:
    captures = []
    per_case_counts: dict[tuple[str, str], int] = {}
    for bvh in root.rglob("motion_actor.bvh"):
        d = bvh.parent
        if not list(d.glob("prop_*.csv")):
            continue
        category, case = capture_category_case(d, root)
        if categories and category not in categories:
            continue
        key = (category, case)
        if per_case_limit is not None:
            count = per_case_counts.get(key, 0)
            if count >= per_case_limit:
                continue
            per_case_counts[key] = count + 1
        captures.append(d)
    captures.sort()
    return captures[:limit] if limit else captures


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-root", type=Path, default=Path("/home/lightcone/workspace/data/motions/g1/dongbu/mocap_data"))
    parser.add_argument("--out-dir", type=Path, default=Path("static/glb"))
    parser.add_argument("--manifest", type=Path, default=Path("static/glb/manifest.json"))
    parser.add_argument("--max-frames", type=int, default=360)
    parser.add_argument("--stride", type=int, default=6)
    parser.add_argument("--limit", type=int, default=24)
    parser.add_argument("--asset-dir", type=Path, default=DEFAULT_ASSET_DIR)
    parser.add_argument("--per-case-limit", type=int, default=None)
    parser.add_argument("--categories", default="", help="Comma-separated categories: box,ball")
    args = parser.parse_args()

    items = []
    categories = {value.strip() for value in args.categories.split(",") if value.strip()} or None
    for capture in discover_captures(args.input_root, args.limit, args.per_case_limit, categories):
        try:
            item = export_capture(capture, args.input_root, args.out_dir, args.max_frames, args.stride, args.asset_dir)
            if item:
                items.append(item)
                print(f"exported {item['file']}")
        except Exception as exc:
            print(f"skip {capture}: {exc}")

    existing = []
    if args.manifest.exists():
        existing = json.loads(args.manifest.read_text()).get("items", [])
    by_id = {item.get("id"): item for item in existing}
    for item in items:
        by_id[item["id"]] = item
    manifest = {
        "title": "Unitree G1 Dongbu BVH + Object Motion Sequences",
        "robot": "Unitree G1",
        "task": "Dongbu mocap BVH with props",
        "items": list(by_id.values()),
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(f"wrote {args.manifest} with {len(manifest['items'])} item(s)")


if __name__ == "__main__":
    main()
