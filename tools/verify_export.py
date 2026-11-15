"""Reopen the editable project, reimport the GLB, and compare the two assets."""

import argparse
import json
from pathlib import Path
import struct
import sys

import bpy
from mathutils import Vector


def measure(objects):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    meshes = [obj.evaluated_get(depsgraph) for obj in objects if obj.type == "MESH"]
    corners = [obj.matrix_world @ Vector(corner) for obj in meshes for corner in obj.bound_box]
    return {
        "mesh_objects": len(meshes),
        "materials": sorted({slot.material.name for obj in meshes
                             for slot in obj.material_slots if slot.material}),
        "bounds_m": {
            "min": [round(min(corner[i] for corner in corners), 6) for i in range(3)],
            "max": [round(max(corner[i] for corner in corners), 6) for i in range(3)],
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    root = args.root.resolve()
    bpy.ops.wm.open_mainfile(filepath=str(root / "assets" / "CP-04.blend"))
    source = measure(obj for obj in bpy.context.scene.objects if obj.name != "Studio floor")
    images = sorted(
        (image for image in bpy.data.images if image.name.startswith("coating-")),
        key=lambda image: image.name,
    )
    maps = {image.name: list(image.size) for image in images if image.packed_file}
    if len(maps) != 3 or any(dimensions != [4096, 4096] for dimensions in maps.values()):
        raise ValueError(f"Expected three packed 4K images, found {maps}")

    export = root / "assets" / "CP-04.glb"
    with export.open("rb") as stream:
        magic, version, length, chunk_length, chunk_type = struct.unpack("<4sIII4s", stream.read(20))
        if (magic, version, length, chunk_type) != (b"glTF", 2, export.stat().st_size, b"JSON"):
            raise ValueError("Invalid GLB header")
        manifest = json.loads(stream.read(chunk_length))
    if len(manifest.get("images", [])) < 2 or any("uri" in image for image in manifest["images"]):
        raise ValueError("Expected embedded GLB colour and metallic-roughness images")

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(export))
    imported = measure(bpy.context.scene.objects)
    if source["mesh_objects"] != imported["mesh_objects"]:
        raise ValueError("GLB round-trip changed mesh object count")
    if source["materials"] != imported["materials"]:
        raise ValueError("GLB round-trip changed the set of material names")
    for bound in ("min", "max"):
        if any(abs(a - b) > 0.0001 for a, b in
               zip(source["bounds_m"][bound], imported["bounds_m"][bound])):
            raise ValueError("GLB round-trip changed bounds by more than 0.1 mm")
    result = {
        "blender": bpy.app.version_string,
        "result": "pass",
        "source": source,
        "glb_reimport": imported,
        "packed_source_maps_px": maps,
        "embedded_glb_images": len(manifest["images"]),
    }
    directory = root / "reports"
    directory.mkdir(exist_ok=True)
    (directory / "export-verification.json").write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
