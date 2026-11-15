"""Render a RainFX preset to a PNG in desktop Blender.

  /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup \
      --python tools/render_preview.py -- <preset_id> <out.png> [samples]

Presets: dew, drizzle, light_rain, moderate_rain, heavy_rain, downpour,
         wind_driven_rain, thunderstorm, freezing_rain, sleet, hailstorm,
         light_snow, heavy_snow, blizzard
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

ROOT = Path(__file__).resolve().parent.parent
EXT = ROOT / "rainfx"


def load_package():
    import importlib.util

    if "rainfx" in sys.modules:
        return sys.modules["rainfx"]
    spec = importlib.util.spec_from_file_location("rainfx", EXT / "__init__.py", submodule_search_locations=[str(EXT)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules["rainfx"] = mod
    spec.loader.exec_module(mod)
    return mod


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for collection in list(bpy.data.collections):
        if collection.name != "Collection" and collection.users == 0:
            bpy.data.collections.remove(collection)


def sky_world():
    world = bpy.data.worlds.new("RainFX Sky")
    bpy.context.scene.world = world
    world.use_nodes = True
    tree = world.node_tree
    tree.nodes.clear()
    out = tree.nodes.new("ShaderNodeOutputWorld")
    bg = tree.nodes.new("ShaderNodeBackground")
    sky = tree.nodes.new("ShaderNodeTexSky")
    sky.sky_type = "MULTIPLE_SCATTERING"
    sky.sun_elevation = 0.35
    sky.sun_rotation = 2.2
    tree.links.new(sky.outputs[0], bg.inputs[0])
    # Overcast: a dim sky so the drops read against it (a bright clear sky hid them).
    bg.inputs[1].default_value = 0.12
    tree.links.new(bg.outputs[0], out.inputs[0])


def sun_lamp(strength=0.6):
    data = bpy.data.lights.new("RainFX Sun", "SUN")
    data.energy = strength
    data.angle = 0.02
    obj = bpy.data.objects.new("RainFX Sun", data)
    bpy.context.scene.collection.objects.link(obj)
    obj.rotation_euler = (np.pi / 2 - 0.35, 0.0, 2.2)
    return obj


def ground(size=50.0):
    mesh = bpy.data.meshes.new("RainFX Ground")
    mesh.from_pydata(
        [(-size, -size, -0.02), (size, -size, -0.02), (size, size, -0.02), (-size, size, -0.02)],
        [], [(0, 1, 2, 3)]
    )
    mesh.update()
    obj = bpy.data.objects.new("RainFX Ground", mesh)
    bpy.context.scene.collection.objects.link(obj)
    mat = bpy.data.materials.new("RainFX Ground")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.03, 0.03, 0.032, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.35  # wet
    obj.data.materials.append(mat)
    return obj


def camera_in_volume(emitter, box):
    """A shot from inside the rain: eye height near the volume's front edge, looking across it.

    Placed from the Volume setting (X, Y, height around the emitter), not from the
    emitter's evaluated geometry, which is empty before the simulation runs, and
    from inside the box rather than outside it, the way rain is filmed.
    """
    sx, sy, _sz = (float(v) for v in box)
    origin = Vector(emitter.location)
    data = bpy.data.cameras.new("RainFX Camera")
    data.lens = 35
    cam = bpy.data.objects.new("RainFX Camera", data)
    bpy.context.scene.collection.objects.link(cam)
    cam.location = origin + Vector((-0.25 * sx, -0.42 * sy, 1.7))
    target = origin + Vector((0.1 * sx, 0.3 * sy, 1.2))
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = cam
    return cam


def main(argv):
    preset_id = argv[0] if argv else "moderate_rain"
    out = Path(argv[1]) if len(argv) > 1 else ROOT / "docs" / "img" / f"{preset_id}.png"
    samples = int(argv[2]) if len(argv) > 2 else 64

    rainfx = load_package()
    rainfx.register()
    from rainfx.scene.emitter import all_presets

    if preset_id not in all_presets():
        raise SystemExit(f"Unknown preset: {preset_id}")

    clear_scene()
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.render.resolution_x, scene.render.resolution_y = 960, 540
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(out)

    # Rain needs time to fill the volume
    scene.frame_start, scene.frame_end = 1, 60
    bpy.context.preferences.filepaths.use_relative_paths = False

    # The emitter comes with the add-on's demo ground and monkey as colliders,
    # so drops land and splash; the wide ground below is only the horizon.
    scene.rainfx.preset = preset_id
    bpy.ops.rainfx.add_emitter()
    emitter = bpy.context.active_object
    ground()
    demo = bpy.data.materials.get("RainFX Demo")  # the demo ground and monkey: dark, wet-looking
    if demo is not None and demo.use_nodes:
        bsdf = demo.node_tree.nodes.get("Principled BSDF")
        if bsdf is not None:
            bsdf.inputs["Base Color"].default_value = (0.05, 0.05, 0.055, 1.0)
            bsdf.inputs["Roughness"].default_value = 0.3

    sky_world()
    sun_lamp()
    camera_in_volume(emitter, scene.rainfx.box)

    # Fill the volume: a packed bake (no saved .blend needed) up to the render frame.
    scene.frame_set(1)
    bpy.ops.rainfx.bake(packed=True, frame_start=1, frame_end=40)

    # Render at a frame with steady rain
    scene.frame_set(40)

    out.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    bpy.ops.render.render(write_still=True)
    print(f"rendered {out} in {time.time() - t0:.1f}s", flush=True)

    save = os.environ.get("RAINFX_SAVE_BLEND")
    if save:
        bpy.ops.wm.save_as_mainfile(filepath=save)
        print(f"saved {save}", flush=True)

    rainfx.unregister()
    return 0


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    code = main(argv)
    sys.stdout.flush()
    import os
    os._exit(code)