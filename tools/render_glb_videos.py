#!/usr/bin/env python3
"""Batch-render GLB animation previews to MP4 with Blender."""

from __future__ import annotations

import argparse
import math
import re
import sys
from pathlib import Path

import bpy
from mathutils import Vector


PROP_ORANGE = (0.95, 0.33, 0.06, 1.0)
PALETTE = {
    "red": (0.91, 0.30, 0.25, 1.0),
    "green": (0.18, 0.58, 0.35, 1.0),
    "blue": (0.19, 0.43, 0.78, 1.0),
    "yellow": (0.87, 0.66, 0.18, 1.0),
    "neutral": (0.45, 0.52, 0.62, 1.0),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--glb-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--max-seconds", type=float, default=8.0)
    parser.add_argument("--min-seconds", type=float, default=3.0)
    parser.add_argument("--samples", type=int, default=28)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--only", default="")
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = []
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    glbs = sorted(args.glb_root.rglob("*.glb"))
    if args.only:
        pattern = re.compile(args.only)
        glbs = [path for path in glbs if pattern.search(path.as_posix())]

    args.output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Found {len(glbs)} GLB files under {args.glb_root}")

    for index, glb_path in enumerate(glbs, start=1):
        relative = glb_path.relative_to(args.glb_root)
        output_name = "__".join(relative.with_suffix("").parts) + ".mp4"
        output_path = args.output_dir / output_name
        if output_path.exists() and not args.overwrite:
            print(f"[{index}/{len(glbs)}] skip existing {output_path.name}")
            continue

        print(f"[{index}/{len(glbs)}] render {relative} -> {output_path.name}")
        if args.dry_run:
            continue
        render_one(glb_path, output_path, args)


def render_one(glb_path: Path, output_path: Path, args: argparse.Namespace) -> None:
    reset_scene()
    scene = bpy.context.scene
    setup_render(scene, args)
    setup_world(scene)

    bpy.ops.import_scene.gltf(filepath=str(glb_path))
    imported = list(bpy.context.selected_objects)
    root_objects = [obj for obj in imported if obj.parent is None]
    for obj in imported:
        if obj.type == "MESH":
            obj.select_set(True)

    polish_materials(imported)
    setup_ground()
    setup_lights()

    frame_start, frame_end = get_animation_range(args)
    scene.frame_start = frame_start
    scene.frame_end = frame_end
    scene.frame_set(frame_start)

    bounds_min, bounds_max = animated_bounds(root_objects or imported, frame_start, frame_end, args.samples)
    setup_camera(scene, bounds_min, bounds_max, args.width / args.height)

    scene.render.filepath = str(output_path)
    bpy.ops.render.render(animation=True, write_still=False)


def reset_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    for collection in (
        bpy.data.meshes,
        bpy.data.materials,
        bpy.data.textures,
        bpy.data.images,
        bpy.data.actions,
        bpy.data.cameras,
        bpy.data.lights,
    ):
        for item in list(collection):
            if item.users == 0:
                collection.remove(item)


def setup_render(scene: bpy.types.Scene, args: argparse.Namespace) -> None:
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.eevee.taa_render_samples = 32
    scene.eevee.use_raytracing = False
    scene.render.resolution_x = args.width
    scene.render.resolution_y = args.height
    scene.render.fps = args.fps
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "Filmic"
    scene.view_settings.look = "Medium High Contrast"
    scene.view_settings.exposure = 0.0
    scene.view_settings.gamma = 1.0
    scene.render.image_settings.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"
    scene.render.ffmpeg.constant_rate_factor = "MEDIUM"
    scene.render.ffmpeg.ffmpeg_preset = "GOOD"


def setup_world(scene: bpy.types.Scene) -> None:
    scene.world = bpy.data.worlds.new("World") if scene.world is None else scene.world
    scene.world.color = (0.965, 0.972, 0.985)


def setup_ground() -> None:
    bpy.ops.mesh.primitive_plane_add(size=30, location=(0, 0, 0))
    ground = bpy.context.object
    ground.name = "preview_ground"
    material = bpy.data.materials.new("preview_ground_checker")
    material.use_nodes = True
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (0.86, 0.88, 0.91, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.86
    ground.data.materials.append(material)


def setup_lights() -> None:
    bpy.ops.object.light_add(type="AREA", location=(0, -3, 5))
    key = bpy.context.object
    key.name = "preview_key_light"
    key.data.energy = 450
    key.data.size = 5

    bpy.ops.object.light_add(type="SUN", location=(4, -5, 7))
    sun = bpy.context.object
    sun.name = "preview_soft_sun"
    sun.rotation_euler = (math.radians(48), 0, math.radians(38))
    sun.data.energy = 1.0


def get_animation_range(args: argparse.Namespace) -> tuple[int, int]:
    starts: list[float] = []
    ends: list[float] = []
    for action in bpy.data.actions:
        start, end = action.frame_range
        starts.append(start)
        ends.append(end)

    start = max(1, int(math.floor(min(starts) if starts else 1)))
    natural_end = int(math.ceil(max(ends) if ends else start + args.min_seconds * args.fps))
    min_end = start + int(round(args.min_seconds * args.fps))
    max_end = start + int(round(args.max_seconds * args.fps))
    end = max(min_end, min(natural_end, max_end))
    return start, max(start + 1, end)


def animated_bounds(objects: list[bpy.types.Object], start: int, end: int, sample_count: int) -> tuple[Vector, Vector]:
    mins = Vector((float("inf"), float("inf"), float("inf")))
    maxs = Vector((float("-inf"), float("-inf"), float("-inf")))
    steps = max(2, sample_count)
    scene = bpy.context.scene

    for sample in range(steps):
        frame = round(start + (end - start) * sample / (steps - 1))
        scene.frame_set(frame)
        depsgraph = bpy.context.evaluated_depsgraph_get()
        for obj in objects:
            update_bounds_from_object(obj, depsgraph, mins, maxs)

    if not math.isfinite(mins.x):
        mins = Vector((-1, -1, 0))
        maxs = Vector((1, 1, 2))
    return mins, maxs


def update_bounds_from_object(obj: bpy.types.Object, depsgraph: bpy.types.Depsgraph, mins: Vector, maxs: Vector) -> None:
    for child in obj.children:
        update_bounds_from_object(child, depsgraph, mins, maxs)
    if obj.type not in {"MESH", "ARMATURE", "EMPTY"}:
        return
    if obj.type != "MESH":
        return

    evaluated = obj.evaluated_get(depsgraph)
    matrix = evaluated.matrix_world
    for corner in evaluated.bound_box:
        point = matrix @ Vector(corner)
        mins.x = min(mins.x, point.x)
        mins.y = min(mins.y, point.y)
        mins.z = min(mins.z, point.z)
        maxs.x = max(maxs.x, point.x)
        maxs.y = max(maxs.y, point.y)
        maxs.z = max(maxs.z, point.z)


def setup_camera(scene: bpy.types.Scene, bounds_min: Vector, bounds_max: Vector, aspect: float) -> None:
    center = (bounds_min + bounds_max) * 0.5
    size = bounds_max - bounds_min
    radius = max(size.length * 0.5, 1.0)

    bpy.ops.object.camera_add()
    camera = bpy.context.object
    camera.name = "preview_camera"
    camera.data.lens = 42
    camera.data.sensor_width = 32

    vertical_fov = camera.data.angle_y
    horizontal_fov = 2 * math.atan(math.tan(vertical_fov / 2) * aspect)
    distance = max(
        radius / math.sin(vertical_fov / 2),
        radius / math.sin(horizontal_fov / 2),
    ) * 0.88

    target = Vector((center.x, center.y, center.z + max(size.z * 0.04, 0.05)))
    direction = Vector((1.08, -1.2, 0.54)).normalized()
    camera.location = target + direction * distance
    look_at(camera, target)
    camera.data.clip_start = max(0.01, distance / 160)
    camera.data.clip_end = max(50, distance * 10)
    scene.camera = camera


def look_at(obj: bpy.types.Object, target: Vector) -> None:
    direction = target - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def polish_materials(objects: list[bpy.types.Object]) -> None:
    for obj in objects:
        if obj.type != "MESH":
            continue
        names = collect_names(obj)
        is_prop = is_prop_object(names)
        is_overlay = is_overlay_object(names)
        if not is_prop and not is_overlay:
            continue
        for slot in obj.material_slots:
            if not slot.material:
                continue
            material = slot.material.copy()
            material.use_nodes = True
            color = PROP_ORANGE if is_prop else pick_color(material)
            apply_principled_color(material, color, is_overlay)
            slot.material = material


def collect_names(obj: bpy.types.Object) -> str:
    parts = [obj.name or ""]
    if obj.parent:
        parts.append(obj.parent.name or "")
    for slot in obj.material_slots:
        if slot.material:
            parts.append(slot.material.name or "")
    return " ".join(parts).lower()


def is_prop_object(names: str) -> bool:
    return (
        re.search(r"(^|[_\s])box($|[_\s\d])", names) is not None
        or "carrybox" in names
        or "object_box" in names
        or "soccer" in names
        or "ball" in names
    )


def is_overlay_object(names: str) -> bool:
    return any(token in names for token in ("visual_", "seg_", "trajectory", "path"))


def pick_color(material: bpy.types.Material) -> tuple[float, float, float, float]:
    color = get_principled_color(material)
    r, g, b = color[:3]
    if r > 0.55 and g > 0.45 and b < 0.35:
        return PALETTE["yellow"]
    if g >= r and g >= b:
        return PALETTE["green"]
    if b >= r and b >= g:
        return PALETTE["blue"]
    if r >= g and r >= b:
        return PALETTE["red"]
    return PALETTE["neutral"]


def get_principled_color(material: bpy.types.Material) -> tuple[float, float, float, float]:
    if not material.use_nodes:
        return material.diffuse_color
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    if not bsdf:
        return material.diffuse_color
    return tuple(bsdf.inputs["Base Color"].default_value)


def apply_principled_color(
    material: bpy.types.Material,
    color: tuple[float, float, float, float],
    transparent: bool,
) -> None:
    material.diffuse_color = color
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = 0.9
        bsdf.inputs["Metallic"].default_value = 0.0
        bsdf.inputs["Alpha"].default_value = 0.96 if transparent else 1.0
    material.use_nodes = True
    material.blend_method = "BLEND" if transparent else "OPAQUE"


if __name__ == "__main__":
    main()
