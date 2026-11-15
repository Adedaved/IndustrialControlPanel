"""Build the CP-04 model, documentation images, textures, and GLB in Blender 4.5."""

import argparse
from itertools import product
from pathlib import Path
from random import Random
import struct
import sys
import zlib

import bpy
from mathutils import Vector


def png_chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def write_coating_maps(directory):
    """Write repeatable 4K maps for the powder-coated enclosure."""
    size = 4096
    rng = Random(41)
    grain = [[rng.randrange(-6, 7) for _ in range(256)] for _ in range(256)]

    for name in ("base-color", "roughness", "metallic"):
        rows = []
        for strip in grain:
            if name == "base-color":
                row = bytes(value + noise for noise in strip for value in (46, 57, 67))
                channels = 2
            elif name == "roughness":
                row = bytes(151 + noise * 2 for noise in strip)
                channels = 0
            else:
                row = bytes(256)
                channels = 0
            rows.append(b"\0" + row * (size // 256))
        header = struct.pack(">IIBBBBB", size, size, 8, channels, 0, 0, 0)
        image = b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", header)
        image += png_chunk(b"IDAT", zlib.compress(b"".join(rows) * (size // 256)))
        image += png_chunk(b"IEND", b"")
        (directory / f"coating-{name}.png").write_bytes(image)


def material(name, color, roughness=0.45, metallic=0.0, emission=0.0):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1)
    mat.use_nodes = True
    shader = mat.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color, 1)
    shader.inputs["Roughness"].default_value = roughness
    shader.inputs["Metallic"].default_value = metallic
    shader.inputs["Emission Color"].default_value = (*color, 1)
    shader.inputs["Emission Strength"].default_value = emission
    return mat


def coating(directory):
    mat = material("Graphite powder coat", (0.028, 0.041, 0.056), 0.6)
    for image_name, socket in (("base-color", "Base Color"), ("roughness", "Roughness"),
                               ("metallic", "Metallic")):
        image = bpy.data.images.load(str(directory / f"coating-{image_name}.png"))
        if socket != "Base Color":
            image.colorspace_settings.name = "Non-Color"
        image.pack()
        node = mat.node_tree.nodes.new("ShaderNodeTexImage")
        node.image = image
        node.label = socket
        node.location = (-340, 240 - 260 * len(mat.node_tree.links))
        mat.node_tree.links.new(node.outputs["Color"],
                                mat.node_tree.nodes["Principled BSDF"].inputs[socket])
    return mat


def finish(name, mat, bevel=0.0, smooth=False):
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(mat)
    if bevel:
        modifier = obj.modifiers.new("Manufactured edge radius", "BEVEL")
        modifier.width = bevel
        modifier.segments = 3
        modifier.harden_normals = True
    if smooth:
        for face in obj.data.polygons:
            face.use_smooth = True
        normal = obj.modifiers.new("Weighted surface normals", "WEIGHTED_NORMAL")
        normal.keep_sharp = True
    return obj


def box(name, location, size, mat, bevel=0.0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    bpy.context.object.scale = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return finish(name, mat, bevel, bool(bevel))


def cylinder(name, x, y, z, radius, depth, mat, bevel=0.001, sides=48):
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=sides, radius=radius, depth=depth, location=(x, y, z),
        rotation=(1.5707963267948966, 0, 0),
    )
    return finish(name, mat, bevel, True)


def legend(text, x, z, size, mat, y=-0.0812, center=False):
    bpy.ops.object.text_add(location=(x, y, z), rotation=(1.5707963267948966, 0, 0))
    obj = bpy.context.object
    obj.data.body = text
    obj.data.size = size
    obj.data.align_x = "CENTER" if center else "LEFT"
    obj.data.resolution_u = 3
    obj.data.materials.append(mat)
    bpy.ops.object.convert(target="MESH")
    obj.name = f"Legend | {text}"
    return obj


def unwrap_box(obj):
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(island_margin=0.027, area_weight=0.0)
    bpy.ops.object.mode_set(mode="OBJECT")


def model(directory):
    graphite = coating(directory)
    face = material("Satin blue-grey aluminium", (0.17, 0.22, 0.26), 0.36, 0.48)
    black = material("Gasket and insulating polymer", (0.012, 0.018, 0.021), 0.53)
    alloy = material("Nickel-plated hardware", (0.35, 0.43, 0.49), 0.25, 0.83)
    ink = material("White silkscreen", (0.76, 0.85, 0.91), 0.62)
    amber = material("Safety yellow", (0.93, 0.46, 0.024), 0.34)
    red = material("Emergency red", (0.78, 0.026, 0.023), 0.3)
    green = material("Run indicator lens", (0.025, 0.55, 0.26), 0.29, emission=0.7)
    cyan = material("Display characters", (0.10, 0.79, 0.94), 0.3, emission=1.2)

    for x, z in product((-0.169, 0.169), (0.017, 0.306)):
        box("Enclosure mounting tab", (x, 0.052, z), (0.067, 0.011, 0.031), alloy, 0.005)
    enclosure = box("Die-cast rear enclosure", (0, 0, 0.161),
                    (0.39, 0.139, 0.304), graphite, 0.010)
    unwrap_box(enclosure)
    box("Faceplate perimeter gasket", (0, -0.0695, 0.161), (0.384, 0.008, 0.298), black, 0.006)
    fascia = box("Removable front fascia", (0, -0.076, 0.161),
                 (0.378, 0.010, 0.292), face, 0.004)
    unwrap_box(fascia)

    for x, z in product((-0.173, 0.173), (0.031, 0.291)):
        cylinder("Captive screw washer", x, -0.0814, z, 0.0074, 0.002, black)
        cylinder("Captive screw head", x, -0.083, z, 0.0058, 0.0022, alloy, 0.00045)
        box("Screw drive mark", (x, -0.0843, z), (0.006, 0.00035, 0.0012), black)

    legend("CP-04  /  CONTROL STATION", -0.151, 0.279, 0.014, ink)
    box("Header rule", (0, -0.0816, 0.271), (0.302, 0.001, 0.0012), amber)
    box("Display bezel", (-0.060, -0.087, 0.211), (0.187, 0.013, 0.081), black, 0.007)
    box("Display lens", (-0.060, -0.0936, 0.211), (0.167, 0.0018, 0.062),
        material("Smoked display window", (0.008, 0.022, 0.035), 0.23), 0.0025)
    legend("SYSTEM READY", -0.134, 0.214, 0.015, cyan, y=-0.095)
    legend("RACK 04   |   LOCAL", -0.134, 0.192, 0.010, ink, y=-0.095)

    for z, label, lens in ((0.232, "RUN", green), (0.205, "FAULT", red), (0.178, "SERVICE", amber)):
        cylinder("Indicator bezel", 0.073, -0.086, z, 0.009, 0.011, black)
        cylinder(f"{label} indicator", 0.073, -0.093, z, 0.0068, 0.006, lens)
        legend(label, 0.090, z - 0.004, 0.010, ink)

    cylinder("Emergency stop safety collar", 0.108, -0.087, 0.105, 0.034, 0.012, amber)
    cylinder("Emergency stop stem", 0.108, -0.101, 0.105, 0.013, 0.020, black)
    cylinder("Emergency stop mushroom", 0.108, -0.119, 0.105, 0.023, 0.021, red, 0.003)
    legend("EMERGENCY STOP", 0.108, 0.055, 0.011, ink, center=True)
    for x, label, mat in ((-0.116, "START", green), (-0.050, "RESET", amber)):
        cylinder("Switch retaining nut", x, -0.087, 0.108, 0.017, 0.012, black)
        cylinder(f"{label} button", x, -0.095, 0.108, 0.0133, 0.010, mat, 0.002)
        legend(label, x, 0.079, 0.010, ink, center=True)

    for x in (-0.124, -0.075):
        cylinder("Service connector hex nut", x, -0.086, 0.047, 0.011, 0.010, alloy, sides=6)
        cylinder("Service connector insert", x, -0.092, 0.047, 0.0078, 0.003, black)
        for dx, dz in ((0, -0.003), (-0.003, 0.002), (0.003, 0.002)):
            cylinder("Connector contact", x + dx, -0.0935, 0.047 + dz,
                     0.00085, 0.001, alloy, 0, sides=12)
    legend("I/O", -0.050, 0.043, 0.009, ink)
    return fascia, enclosure


def aim(obj, target):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()


def camera(name, position, target, framing):
    bpy.ops.object.camera_add(location=position)
    cam = bpy.context.object
    cam.name = name
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = framing
    aim(cam, target)
    return cam


def lamp(name, position, power, size, color):
    bpy.ops.object.light_add(type="AREA", location=position)
    light = bpy.context.object
    light.name = name
    light.data.energy = power
    light.data.shape = "DISK"
    light.data.size = size
    light.data.color = color
    aim(light, (0, 0, 0.15))


def render(scene, cam, path):
    scene.camera = cam
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def uv_evidence(obj, title, path):
    mesh = obj.data
    uv = mesh.uv_layers.active.data
    faces = []
    for face in mesh.polygons:
        points = " ".join(f"{55 + uv[i].uv.x * 490:.2f},{565 - uv[i].uv.y * 490:.2f}"
                          for i in face.loop_indices)
        faces.append(f'<polygon points="{points}"/>')
    path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="600" height="615" viewBox="0 0 600 615">'
        '<rect width="600" height="615" fill="#111b25"/>'
        '<text x="54" y="45" fill="#f0f4fb" font-family="sans-serif" font-size="20">'
        f'CP-04 / {title} base-mesh UVs</text>'
        '<rect x="55" y="75" width="490" height="490" fill="#192b3b" stroke="#607e95"/>'
        '<g fill="#2a5f74" fill-opacity=".7" stroke="#8bdcef" stroke-width="2">'
        + "".join(faces) + '</g><text x="55" y="588" fill="#a9bece" font-family="sans-serif" '
        'font-size="13">0–1 UV space · base cage before bevel</text></svg>\n',
        encoding="utf-8",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--skip-renders", action="store_true")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    root = args.output.resolve()
    for folder in ("assets", "textures", "renders"):
        (root / folder).mkdir(parents=True, exist_ok=True)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.world = bpy.data.worlds.new("Studio ambient")
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs[0].default_value = (0.12, 0.15, 0.20, 1)
    scene.world.node_tree.nodes["Background"].inputs[1].default_value = 0.38
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 24
    scene.cycles.use_denoising = True
    scene.render.resolution_x = 1100
    scene.render.resolution_y = 900
    scene.render.resolution_percentage = 100

    write_coating_maps(root / "textures")
    scene.view_settings.exposure = -0.65

    fascia, enclosure = model(root / "textures")
    asset_objects = list(scene.objects)
    bpy.ops.object.select_all(action="DESELECT")
    for obj in asset_objects:
        obj.select_set(True)
    bpy.ops.export_scene.gltf(filepath=str(root / "assets" / "CP-04.glb"),
                              use_selection=True, export_apply=True)
    uv_evidence(fascia, "Fascia", root / "renders" / "uv-fascia.svg")
    uv_evidence(enclosure, "Enclosure", root / "renders" / "uv-enclosure.svg")

    floor = box("Studio floor", (0, 0, -0.026), (200, 200, 0.030),
        material("Studio slate", (0.048, 0.070, 0.095), 0.8))
    lamp("Large softbox", (-0.44, -0.51, 0.69), 58, 0.50, (0.85, 0.93, 1))
    lamp("Front fill", (0.41, -0.38, 0.40), 31, 0.34, (1, 0.85, 0.69))
    lamp("Rear rim", (0.28, 0.30, 0.57), 72, 0.30, (0.61, 0.78, 1))
    front = camera("Front elevation", (0, -1.4, 0.162), (0, 0, 0.162), 0.55)
    angled = camera("Hero three-quarter", (0.65, -1.0, 0.48), (0, 0, 0.154), 0.57)
    close = camera("Emergency stop detail", (0.33, -0.69, 0.21), (0.079, -0.08, 0.117), 0.24)

    scene.camera = angled
    scene.render.filepath = "//../renders/angled.png"
    bpy.ops.object.select_all(action="DESELECT")
    fascia.select_set(True)
    bpy.context.view_layer.objects.active = fascia
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                area.spaces.active.region_3d.view_perspective = "CAMERA"
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(root / "assets" / "CP-04.blend"))
    if not args.skip_renders:
        for cam, filename in ((front, "front.png"), (angled, "angled.png"), (close, "close-up.png")):
            floor.hide_render = cam == front
            render(scene, cam, root / "renders" / filename)

        clay = material("Topology surface", (0.35, 0.43, 0.50), 0.75)
        line = material("Topology edge", (0.006, 0.01, 0.02), 0.8)
        for obj in asset_objects:
            if obj.name.startswith("Legend |") or obj.name.startswith("Screw drive mark"):
                obj.hide_render = True
                continue
            obj.data.materials[0] = clay
            obj.data.materials.append(line)
            wire = obj.modifiers.new("Topology overlay", "WIREFRAME")
            wire.thickness = 0.00033
            wire.use_replace = False
            wire.material_offset = 1
        render(scene, angled, root / "renders" / "wireframe.png")


if __name__ == "__main__":
    main()
