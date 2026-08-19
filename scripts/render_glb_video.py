#!/usr/bin/env python3
"""Offline-render animated GLB files to MP4.

This script is meant to be launched from a normal Python interpreter. It then
re-executes itself inside Blender (headless) to import the GLB animation and
write a video. Requires the local Blender 3.3 install and ffmpeg.

Examples:

  conda activate mjvis
  python scripts/render_glb_video.py \\
    --glb static/glb/serve/fq_deyue.glb \\
    --out static/videos/adapt/glb_preview/fq_deyue.mp4

  python scripts/render_glb_video.py \\
    --glb-dir static/glb/rally \\
    --out-dir static/videos/adapt/glb_preview/rally

  python scripts/render_glb_video.py \\
    --glb path/to/clip.glb \\
    --out path/to/clip.mp4 \\
    --follow xy
"""

from __future__ import annotations

import argparse
import math
import shutil
import subprocess
import sys
from pathlib import Path


DEFAULT_BLENDER = Path("/home/fly/Apps/blender-3.3.21-linux-x64/blender")
DEFAULT_FFMPEG = Path("/home/fly/miniconda3/envs/tennis_env/bin/ffmpeg")


def blender_argv() -> list[str]:
    if "--" in sys.argv:
        return sys.argv[sys.argv.index("--") + 1 :]
    return sys.argv[1:]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--glb", type=Path, help="Single GLB file")
    parser.add_argument("--glb-dir", type=Path, help="Directory of GLB files")
    parser.add_argument("--out", type=Path, help="Output mp4 for --glb")
    parser.add_argument("--out-dir", type=Path, help="Output directory for --glb-dir")
    parser.add_argument("--blender", type=Path, default=DEFAULT_BLENDER)
    parser.add_argument("--ffmpeg", type=Path, default=DEFAULT_FFMPEG)
    parser.add_argument("--engine", choices=("BLENDER_EEVEE", "CYCLES"), default="BLENDER_EEVEE")
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--samples", type=int, default=128, help="EEVEE TAA / Cycles samples")
    parser.add_argument("--crf", type=int, default=14, help="ffmpeg x264 quality; lower is sharper")
    parser.add_argument("--camera-scale", type=float, default=0.95, help="Extra padding on the fitted camera distance")
    parser.add_argument("--lens", type=float, default=35.0, help="Camera focal length in mm; smaller = wider FOV")
    parser.add_argument(
        "--follow",
        choices=("off", "xy", "xyz"),
        default="off",
        help="Camera follow: off=static, xy=track ground motion, xyz=also track height",
    )
    parser.add_argument("--end-frame", type=int, default=0, help="Optional last frame (0 = use GLB action length)")
    parser.add_argument("--keep-frames", action="store_true", help="Keep PNG frames after encoding")
    return parser


def collect_jobs(args: argparse.Namespace) -> list[tuple[Path, Path]]:
    jobs: list[tuple[Path, Path]] = []
    if args.glb:
        out = args.out
        if out is None:
            out_dir = args.out_dir or Path("static/videos/adapt/glb_preview")
            out = out_dir / (args.glb.stem + ".mp4")
        jobs.append((args.glb.expanduser().resolve(), out.expanduser()))
    if args.glb_dir:
        glb_dir = args.glb_dir.expanduser().resolve()
        out_dir = (args.out_dir or Path("static/videos/adapt/glb_preview") / glb_dir.name).expanduser()
        for src in sorted(glb_dir.glob("*.glb")):
            jobs.append((src, out_dir / (src.stem + ".mp4")))
    if not jobs:
        raise SystemExit("Pass --glb or --glb-dir")
    return jobs


def run_outside_blender() -> int:
    args = build_parser().parse_args()
    blender = args.blender.expanduser()
    if not blender.exists():
        raise SystemExit(f"Blender not found: {blender}")
    jobs = collect_jobs(args)
    script = Path(__file__).resolve()
    for src, dst in jobs:
        dst.parent.mkdir(parents=True, exist_ok=True)
        print(f"render {src.name} -> {dst}")
        cmd = [
            str(blender),
            "--background",
            "--python",
            str(script),
            "--",
            "--glb",
            str(src),
            "--out",
            str(dst),
            "--engine",
            args.engine,
            "--width",
            str(args.width),
            "--height",
            str(args.height),
            "--fps",
            str(args.fps),
            "--samples",
            str(args.samples),
            "--crf",
            str(args.crf),
            "--camera-scale",
            str(args.camera_scale),
            "--lens",
            str(args.lens),
            "--follow",
            args.follow,
            "--ffmpeg",
            str(args.ffmpeg),
            "--end-frame",
            str(args.end_frame),
        ]
        if args.keep_frames:
            cmd.append("--keep-frames")
        subprocess.run(cmd, check=True)
    print(f"done {len(jobs)} video(s)")
    return 0


def frame_range_from_actions(fps: int) -> tuple[int, int]:
    import bpy

    start = 1.0
    end = 1.0
    found = False
    for action in bpy.data.actions:
        a, b = action.frame_range
        if not found:
            start, end = float(a), float(b)
            found = True
        else:
            start = min(start, float(a))
            end = max(end, float(b))
    if not found or end <= start:
        return 1, max(2, fps)
    return max(1, int(round(start))), max(2, int(round(end)))


def scene_bounds():
    import bpy
    from mathutils import Vector

    mn = Vector((math.inf, math.inf, math.inf))
    mx = Vector((-math.inf, -math.inf, -math.inf))
    depsgraph = bpy.context.evaluated_depsgraph_get()
    found = False
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH":
            continue
        if obj.name.startswith("Floor"):
            continue
        evaluated = obj.evaluated_get(depsgraph)
        for corner in evaluated.bound_box:
            world = evaluated.matrix_world @ Vector(corner)
            mn.x, mn.y, mn.z = min(mn.x, world.x), min(mn.y, world.y), min(mn.z, world.z)
            mx.x, mx.y, mx.z = max(mx.x, world.x), max(mx.y, world.y), max(mx.z, world.z)
            found = True
    if not found:
        return Vector((-0.5, -0.5, 0.0)), Vector((0.5, 0.5, 1.8))
    return mn, mx


def animation_bounds(start: int, end: int) -> tuple:
    import bpy
    from mathutils import Vector

    span = max(1, end - start)
    step = max(1, min(8, span // 48))
    mn = Vector((math.inf, math.inf, math.inf))
    mx = Vector((-math.inf, -math.inf, -math.inf))
    frames = list(range(start, end + 1, step))
    if frames[-1] != end:
        frames.append(end)
    for frame in frames:
        bpy.context.scene.frame_set(frame)
        a, b = scene_bounds()
        mn.x, mn.y, mn.z = min(mn.x, a.x), min(mn.y, a.y), min(mn.z, a.z)
        mx.x, mx.y, mx.z = max(mx.x, b.x), max(mx.y, b.y), max(mx.z, b.z)
    return mn, mx


def follow_anchor():
    import bpy
    from mathutils import Vector

    depsgraph = bpy.context.evaluated_depsgraph_get()
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH":
            continue
        if obj.name.lower().startswith("pelvis"):
            return obj.evaluated_get(depsgraph).matrix_world.translation.copy()
    mn, mx = scene_bounds()
    return (mn + mx) * 0.5


def character_size(start: int, end: int):
    import bpy
    from mathutils import Vector

    span = max(1, end - start)
    step = max(1, span // 24)
    size = Vector((0.8, 0.8, 1.4))
    floor_z = math.inf
    for frame in list(range(start, end + 1, step)) + [end]:
        bpy.context.scene.frame_set(frame)
        mn, mx = scene_bounds()
        delta = mx - mn
        size.x, size.y, size.z = max(size.x, delta.x), max(size.y, delta.y), max(size.z, delta.z)
        floor_z = min(floor_z, float(mn.z))
    if not math.isfinite(floor_z):
        floor_z = 0.0
    return size, floor_z


def camera_distance(size, camera_scale: float, lens_mm: float, width: int, height: int) -> float:
    aspect = max(width / max(height, 1), 0.1)
    sensor_w = 36.0
    sensor_h = sensor_w / aspect
    half_v = math.atan((sensor_h * 0.5) / max(lens_mm, 1.0))
    half_h = math.atan((sensor_w * 0.5) / max(lens_mm, 1.0))
    dist_v = (size.z * 0.62) / max(math.tan(half_v), 1e-4)
    dist_h = (max(size.x, size.y) * 0.55) / max(math.tan(half_h), 1e-4)
    return max(dist_v, dist_h, 1.6) * camera_scale


def create_camera(lens_mm: float, distance: float):
    import bpy
    from mathutils import Vector

    cam_data = bpy.data.cameras.new("RenderCam")
    cam_data.lens = lens_mm
    cam_data.sensor_fit = "HORIZONTAL"
    cam_data.sensor_width = 36.0
    cam_data.clip_start = 0.05
    cam_data.clip_end = max(80.0, distance * 5.0)
    cam = bpy.data.objects.new("RenderCam", cam_data)
    bpy.context.scene.collection.objects.link(cam)
    target = bpy.data.objects.new("CamTarget", None)
    bpy.context.scene.collection.objects.link(target)
    track = cam.constraints.new(type="TRACK_TO")
    track.target = target
    track.track_axis = "TRACK_NEGATIVE_Z"
    track.up_axis = "UP_Y"
    bpy.context.scene.camera = cam
    return cam, target, Vector((1.15, -1.65, 0.62)).normalized()


def place_camera(cam, target, look, size, distance, direction) -> None:
    target.location = look
    cam.location = look + direction * distance


def setup_static_camera(mn, mx, camera_scale: float, lens_mm: float, width: int, height: int) -> None:
    from mathutils import Vector

    pad = (mx - mn) * 0.06
    mn = mn - pad
    mx = mx + pad
    mx.z += (mx.z - mn.z) * 0.12
    center = (mn + mx) * 0.5
    size = mx - mn
    distance = camera_distance(size, camera_scale, lens_mm, width, height)
    cam, target, direction = create_camera(lens_mm, distance)
    look = Vector((center.x, center.y, mn.z + size.z * 0.34))
    place_camera(cam, target, look, size, distance, direction)


def setup_follow_camera(
    start: int,
    end: int,
    follow_mode: str,
    camera_scale: float,
    lens_mm: float,
    width: int,
    height: int,
) -> None:
    import bpy
    from mathutils import Vector

    size, _floor_z = character_size(start, end)
    size = size.copy()
    size.z *= 1.12
    distance = camera_distance(size, camera_scale, lens_mm, width, height)
    cam, target, direction = create_camera(lens_mm, distance)

    bpy.context.scene.frame_set(start)
    rest = follow_anchor()
    look_z_offset = size.z * 0.18
    for frame in range(start, end + 1):
        bpy.context.scene.frame_set(frame)
        anchor = follow_anchor()
        look = Vector((anchor.x, anchor.y, anchor.z + look_z_offset))
        if follow_mode == "xy":
            look.z = rest.z + look_z_offset
        place_camera(cam, target, look, size, distance, direction)
        cam.keyframe_insert(data_path="location", frame=frame)
        target.keyframe_insert(data_path="location", frame=frame)
    for obj in (cam, target):
        if obj.animation_data and obj.animation_data.action:
            for fcurve in obj.animation_data.action.fcurves:
                for key in fcurve.keyframe_points:
                    key.interpolation = "LINEAR"


def setup_scene_look(floor_z: float) -> None:
    import bpy

    world = bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.031, 0.035, 0.047, 1.0)
    bg.inputs[1].default_value = 1.0

    sun_data = bpy.data.lights.new("Sun", "SUN")
    sun_data.energy = 4.0
    sun_data.angle = math.radians(18)
    sun = bpy.data.objects.new("Sun", sun_data)
    bpy.context.scene.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(48), math.radians(12), math.radians(35))

    fill_data = bpy.data.lights.new("Fill", "AREA")
    fill_data.energy = 80
    fill_data.size = 6
    fill = bpy.data.objects.new("Fill", fill_data)
    bpy.context.scene.collection.objects.link(fill)
    fill.location = (-3.5, 2.5, 4.0)
    fill.rotation_euler = (math.radians(-35), math.radians(-20), 0)

    bpy.ops.mesh.primitive_plane_add(size=48, location=(0, 0, floor_z - 0.002))
    floor = bpy.context.active_object
    floor.name = "Floor"
    mat = bpy.data.materials.new("FloorMat")
    mat.use_nodes = True
    princ = mat.node_tree.nodes["Principled BSDF"]
    princ.inputs["Base Color"].default_value = (0.07, 0.08, 0.10, 1.0)
    princ.inputs["Roughness"].default_value = 0.86
    floor.data.materials.append(mat)


def configure_eevee(scene, samples: int) -> None:
    eevee = scene.eevee
    eevee.taa_render_samples = max(64, samples)
    eevee.use_gtao = True
    eevee.gtao_distance = 0.35
    eevee.gtao_factor = 0.75
    eevee.gtao_quality = 1.0
    eevee.use_ssr = True
    eevee.use_ssr_refraction = True
    eevee.ssr_quality = 1.0
    eevee.use_soft_shadows = True
    eevee.shadow_cube_size = "2048"
    eevee.shadow_cascade_size = "2048"
    eevee.use_bloom = False
    scene.view_settings.view_transform = "Filmic"
    scene.view_settings.look = "Medium High Contrast"
    scene.render.filter_size = 1.5
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    scene.render.image_settings.compression = 15


def configure_cycles(scene, samples: int) -> None:
    import bpy

    scene.cycles.samples = max(64, samples)
    scene.cycles.use_denoising = True
    scene.cycles.device = "CPU"
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "CUDA"
        prefs.get_devices()
        gpu_found = False
        for device in prefs.devices:
            is_gpu = "CPU" not in device.type
            device.use = is_gpu
            gpu_found = gpu_found or is_gpu
        if gpu_found:
            scene.cycles.device = "GPU"
    except Exception:
        scene.cycles.device = "CPU"


def encode_frames(frame_dir: Path, out_path: Path, fps: int, ffmpeg: Path, crf: int) -> None:
    ffmpeg_bin = str(ffmpeg) if ffmpeg.exists() else (shutil.which("ffmpeg") or "")
    if not ffmpeg_bin:
        raise SystemExit("ffmpeg not found")
    pattern = str(frame_dir / "frame_%04d.png")
    cmd = [
        ffmpeg_bin,
        "-y",
        "-framerate",
        str(fps),
        "-i",
        pattern,
        "-c:v",
        "libx264",
        "-preset",
        "slow",
        "-profile:v",
        "high",
        "-pix_fmt",
        "yuv420p",
        "-crf",
        str(crf),
        "-movflags",
        "+faststart",
        str(out_path),
    ]
    subprocess.run(cmd, check=True)


def run_inside_blender() -> int:
    import bpy

    args = build_parser().parse_args(blender_argv())
    if not args.glb or not args.out:
        raise SystemExit("Blender mode requires --glb and --out")
    glb = args.glb.expanduser().resolve()
    out = args.out.expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    # glTF keyframes are stored in seconds. Blender converts them with the
    # scene fps *at import time*. Factory default is 24, so fps must be set
    # before importing or a 120Hz clip will play 24/30 too fast.
    scene.render.fps = args.fps
    scene.render.fps_base = 1.0
    bpy.ops.import_scene.gltf(filepath=str(glb))

    scene.render.engine = args.engine
    scene.render.resolution_x = args.width
    scene.render.resolution_y = args.height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    if args.engine == "CYCLES":
        configure_cycles(scene, args.samples)
    else:
        configure_eevee(scene, args.samples)

    start, end = frame_range_from_actions(args.fps)
    full_end = end
    if args.end_frame and args.end_frame > 0:
        end = min(end, args.end_frame)
    scene.frame_start = start
    scene.frame_end = end

    mn, mx = animation_bounds(start, full_end)
    setup_scene_look(float(mn.z))
    if args.follow == "off":
        setup_static_camera(mn, mx, args.camera_scale, args.lens, args.width, args.height)
    else:
        setup_follow_camera(
            start, end, args.follow, args.camera_scale, args.lens, args.width, args.height
        )
    bpy.context.scene.frame_set(start)
    frame_dir = out.parent / f".frames_{out.stem}"
    if frame_dir.exists():
        shutil.rmtree(frame_dir)
    frame_dir.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(frame_dir / "frame_")

    duration = (end - start + 1) / max(args.fps, 1)
    print(
        f"Blender render {glb.name} frames {start}-{end} "
        f"({duration:.2f}s @ {args.fps}fps {args.width}x{args.height}, "
        f"follow={args.follow}) engine={args.engine} samples={args.samples}"
    )
    bpy.ops.render.render(animation=True)
    encode_frames(frame_dir, out, args.fps, args.ffmpeg, args.crf)
    if not args.keep_frames:
        shutil.rmtree(frame_dir, ignore_errors=True)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    try:
        import bpy  # noqa: F401
        in_blender = True
    except ImportError:
        in_blender = False
    raise SystemExit(run_inside_blender() if in_blender else run_outside_blender())
