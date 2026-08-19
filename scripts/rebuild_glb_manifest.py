#!/usr/bin/env python3
"""Rebuild the local GLB manifest with dataset and VLM groups."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


VLM_PREFIXES = ("corl_", "vlm_", "heart_", "letters_")
BALANCED_TOTAL = 49
BALANCED_SKILLS = ("carry_box", "push_box", "slide_box", "carry_ball", "kick_ball")
BALANCED_BASE_PER_SKILL = BALANCED_TOTAL // len(BALANCED_SKILLS)
BALANCED_EXTRA_SKILLS = BALANCED_TOTAL % len(BALANCED_SKILLS)


def title_from_stem(stem: str) -> str:
    words = stem.replace("_", " ").split()
    return " ".join(words[:8]) if words else stem


def infer_group(path: Path) -> str:
    stem = path.stem.lower()
    if stem.startswith(VLM_PREFIXES):
        return "vlm"
    return "dataset"


def infer_category_and_case(stem: str) -> tuple[str, str]:
    parts = stem.split("_")
    if stem.startswith("soccer_mocap_"):
        body = stem[len("soccer_mocap_"):]
        marker = "_MWVOPT_"
        return "ball", body.split(marker, 1)[0] if marker in body else parts[2]
    if stem.startswith("box_mocap_"):
        body = stem[len("box_mocap_"):]
        marker = "_data_MWV_"
        if marker in body:
            return "box", body.split(marker, 1)[0]
        marker = "_MWVOPT_"
        return "box", body.split(marker, 1)[0] if marker in body else f"{parts[2]}_{parts[3]}"
    if stem.startswith("data_MWV_"):
        return "box", "move_case1"
    return "other", "other"


def infer_skill(category: str, case: str) -> str:
    if category == "ball":
        return "kick_ball" if "kick" in case.lower() else "carry_ball"
    if case.startswith("push"):
        return "push_box"
    if case.startswith("punt"):
        return "slide_box"
    if case.startswith("move"):
        return "carry_box"
    return "other"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--glb-dir", type=Path, default=Path("static/glb"))
    parser.add_argument("--manifest", type=Path, default=Path("static/glb/manifest.json"))
    args = parser.parse_args()

    items = []
    for glb in sorted(args.glb_dir.glob("*.glb")):
        group = infer_group(glb)
        category, case = infer_category_and_case(glb.stem)
        items.append(
            {
                "id": glb.stem,
                "title": title_from_stem(glb.stem),
                "file": glb.name,
                "source": glb.name,
                "group": group,
                "category": category,
                "case": case,
                "skill": infer_skill(category, case),
            }
        )

    balanced_dataset = []
    seen_skills = {}
    for skill_index, skill in enumerate(BALANCED_SKILLS):
        skill_quota = BALANCED_BASE_PER_SKILL + (1 if skill_index < BALANCED_EXTRA_SKILLS else 0)
        for item in items:
            if item["group"] != "dataset" or item["skill"] != skill:
                continue
            count = seen_skills.get(skill, 0)
            if count >= skill_quota:
                break
            balanced_dataset.append({**item, "group": "dataset_balanced"})
            seen_skills[skill] = count + 1

    for item in items:
        if len(balanced_dataset) >= BALANCED_TOTAL:
            break
        if item["group"] != "dataset" or item["skill"] == "other":
            continue
        if any(existing["id"] == item["id"] for existing in balanced_dataset):
            continue
        balanced_dataset.append({**item, "group": "dataset_balanced"})

    groups = {
        "dataset": [item for item in items if item["group"] == "dataset"],
        "dataset_balanced": balanced_dataset,
        "vlm": [item for item in items if item["group"] == "vlm"],
    }
    manifest = {
        "title": "Unitree G1 Dongbu BVH + Object Motion Sequences",
        "robot": "Unitree G1",
        "task": "Dongbu mocap BVH with props",
        "items": items,
        "groups": groups,
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(
        f"wrote {args.manifest} with "
        f"{len(groups['dataset'])} dataset item(s), "
        f"{len(groups['dataset_balanced'])} balanced item(s), "
        f"{len(groups['vlm'])} vlm item(s)"
    )


if __name__ == "__main__":
    main()
