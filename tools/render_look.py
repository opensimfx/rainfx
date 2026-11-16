"""Render RainFX in a small city street: the look bench and the README shots.

  /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup \
      --python tools/render_look.py -- <shot> <preset_id> <out.png> [samples] [frame]

Shots:
  street_night   eye-level street at night, rain backlit by sodium street lamps
  street_day     the same street under an overcast sky
  puddle         low camera on the wet asphalt: splashes, crowns, ring ripples
  wide           high wide view down the street (fog depth, distant rain)

The street is built here from boxes and procedural materials (no assets):
asphalt road on a 0.25 m grid (wetness needs vertices), curbs and pavements,
building fronts with lit windows, lamp posts. RainFX is set up the way a user
would: emitter, colliders, wetness, distant and foreground rain, atmosphere.
"""
from __future__ import annotations

import math
import os
import sys
import time
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parent.parent
EXT = ROOT / "rainfx"

SODIUM = (1.0, 0.62, 0.30)
LED = (0.85, 0.92, 1.0)


def load_package():
    import importlib.util

    if "rainfx" in sys.modules:
        return sys.modules["rainfx"]
    spec = importlib.util.spec_from_file_location("rainfx", EXT / "__init__.py",
                                                  submodule_search_locations=[str(EXT)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules["rainfx"] = mod
    spec.loader.exec_module(mod)
    return mod


# ----------------------------------------------------------------- materials
def _mat(name, color, rough, *, noise=0.0, scale=4.0, emission=None, strength=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = rough
    if noise > 0:
        tex = nt.nodes.new("ShaderNodeTexNoise")
        tex.inputs["Scale"].default_value = scale
        tex.inputs["Detail"].default_value = 8.0
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].color = tuple(c * (1 - noise) for c in color) + (1.0,)
        ramp.color_ramp.elements[1].color = tuple(min(1.0, c * (1 + noise)) for c in color) + (1.0,)
        nt.links.new(tex.outputs["Fac"], ramp.inputs["Fac"])
        nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
        bump = nt.nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = 0.15
        bump.inputs["Distance"].default_value = 0.002
        fine = nt.nodes.new("ShaderNodeTexNoise")
        fine.inputs["Scale"].default_value = 180.0
        nt.links.new(fine.outputs["Fac"], bump.inputs["Height"])
        nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    else:
        bsdf.inputs["Base Color"].default_value = tuple(color) + (1.0,)
    if emission is not None:
        bsdf.inputs["Emission Color"].default_value = tuple(emission) + (1.0,)
        bsdf.inputs["Emission Strength"].default_value = strength
    mat["rainfx_porosity"] = 0.8 if "Asphalt" in name or "Concrete" in name else 0.5
    return mat


def _box(name, size, loc, mat, coll):
    me = bpy.data.meshes.new(name)
    sx, sy, sz = (s / 2 for s in size)
    v = [(x, y, z) for x in (-sx, sx) for y in (-sy, sy) for z in (-sz, sz)]
    f = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    me.from_pydata(v, [], f)
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    ob.location = loc
    coll.objects.link(ob)
    return ob


def _grid(name, sx, sy, step, z, mat, coll, loc=(0.0, 0.0)):
    nx, ny = max(1, round(sx / step)), max(1, round(sy / step))
    me = bpy.data.meshes.new(name)
    verts = [(-sx / 2 + sx * i / nx, -sy / 2 + sy * j / ny, z) for j in range(ny + 1) for i in range(nx + 1)]
    k = nx + 1
    faces = [(j * k + i, j * k + i + 1, (j + 1) * k + i + 1, (j + 1) * k + i) for j in range(ny) for i in range(nx)]
    me.from_pydata(verts, [], faces)
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    ob.location = (loc[0], loc[1], 0.0)
    coll.objects.link(ob)
    return ob


def build_street(night: bool):
    """Road 8 m wide along +Y, pavements, building fronts, lamp posts. Returns colliders."""
    coll = bpy.data.collections.new("Street")
    bpy.context.scene.collection.children.link(coll)
    asphalt = _mat("Asphalt", (0.035, 0.034, 0.033), 0.75, noise=0.35, scale=3.0)
    concrete = _mat("Concrete", (0.16, 0.155, 0.15), 0.85, noise=0.25, scale=6.0)
    brick = _mat("Brick", (0.13, 0.06, 0.045), 0.8, noise=0.3, scale=2.0)
    plaster = _mat("Plaster", (0.30, 0.28, 0.25), 0.9, noise=0.2, scale=1.5)
    metal = _mat("Lamp Metal", (0.05, 0.05, 0.05), 0.4)
    metal["rainfx_porosity"] = 0.0
    win_lit = _mat("Window Lit", (0.02, 0.02, 0.02), 0.05, emission=(1.0, 0.7, 0.4), strength=3.0 if night else 0.4)
    win_dark = _mat("Window", (0.01, 0.012, 0.015), 0.03)

    road = _grid("Road", 8.0, 44.0, 0.25, 0.0, asphalt, coll, loc=(0.0, 14.0))
    side_l = _grid("Pavement L", 3.0, 44.0, 0.25, 0.15, concrete, coll, loc=(-5.5, 14.0))
    side_r = _grid("Pavement R", 3.0, 44.0, 0.25, 0.15, concrete, coll, loc=(5.5, 14.0))
    curbs = [_box(f"Curb {s}", (0.15, 44.0, 0.15), (s * 4.075, 14.0, 0.075), concrete, coll) for s in (-1, 1)]
    colliders = [road, side_l, side_r] + curbs

    import random
    rnd = random.Random(7)
    y = -6.0
    while y < 36.0:
        for side in (-1, 1):
            w = rnd.uniform(5.0, 9.0)
            h = rnd.uniform(9.0, 16.0)
            mat = brick if rnd.random() < 0.5 else plaster
            b = _box(f"Building {side} {y:.0f}", (4.0, w - 0.3, h), (side * 9.0, y + w / 2, h / 2), mat, coll)
            colliders.append(b)
            # windows on the street-facing wall
            for fl in range(1, int(h // 3.2)):
                for c in range(int((w - 1.0) // 1.8)):
                    lit = rnd.random() < (0.35 if night else 0.1)
                    _box(f"Win {side} {y:.0f} {fl} {c}", (0.05, 1.0, 1.4),
                         (side * 6.99, y + 1.2 + c * 1.8, fl * 3.2 + 0.4), win_lit if lit else win_dark, coll)
        y += w
    # lamp posts on alternating sides every 12 m, heads overhanging the road
    lamps = []
    for i, ly in enumerate((4.0, 16.0, 28.0)):
        side = -1 if i % 2 == 0 else 1
        x = side * 4.6
        _box(f"Lamp Post {i}", (0.14, 0.14, 6.0), (x, ly, 3.0), metal, coll)
        _box(f"Lamp Arm {i}", (1.4, 0.1, 0.1), (x - side * 0.7, ly, 6.0), metal, coll)
        head = _box(f"Lamp Head {i}", (0.5, 0.25, 0.08), (x - side * 1.3, ly, 5.95), metal, coll)
        tint = LED if i == 1 else SODIUM          # one modern LED head among the sodium ones
        glass = _mat(f"Lamp Glass {i}", (1, 1, 1), 0.2, emission=tint, strength=60.0 if night else 0.0)
        _box(f"Lamp Glass {i}", (0.42, 0.2, 0.02), (x - side * 1.3, ly, 5.9), glass, coll)
        if night:
            ld = bpy.data.lights.new(f"Lamp {i}", "SPOT")
            ld.color = tint
            ld.energy = 2500.0
            ld.spot_size = math.radians(130.0)
            ld.spot_blend = 0.6
            ld.shadow_soft_size = 0.15
            lo = bpy.data.objects.new(f"Lamp {i}", ld)
            lo.location = (x - side * 1.3, ly, 5.85)
            lo.rotation_euler = (0.0, 0.0, 0.0)   # spots shine down -Z
            coll.objects.link(lo)
            lamps.append(lo)
        colliders.append(head)
    return colliders, lamps


def world(night: bool):
    w = bpy.data.worlds.new("Street Sky")
    bpy.context.scene.world = w
    w.use_nodes = True
    nt = w.node_tree
    bg = nt.nodes["Background"]
    if night:
        bg.inputs["Color"].default_value = (0.012, 0.016, 0.03, 1.0)
        bg.inputs["Strength"].default_value = 1.0
    else:
        # overcast: a soft bright grey sky, no sun
        grad = nt.nodes.new("ShaderNodeTexGradient")
        grad.gradient_type = "EASING"
        mapping = nt.nodes.new("ShaderNodeMapping")
        coord = nt.nodes.new("ShaderNodeTexCoord")
        mapping.inputs["Rotation"].default_value = (0.0, -math.pi / 2, 0.0)
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].color = (0.30, 0.32, 0.34, 1.0)
        ramp.color_ramp.elements[1].color = (0.62, 0.65, 0.68, 1.0)
        nt.links.new(coord.outputs["Generated"], mapping.inputs["Vector"])
        nt.links.new(mapping.outputs["Vector"], grad.inputs["Vector"])
        nt.links.new(grad.outputs["Fac"], ramp.inputs["Fac"])
        nt.links.new(ramp.outputs["Color"], bg.inputs["Color"])
        bg.inputs["Strength"].default_value = 1.6


def camera(shot: str):
    data = bpy.data.cameras.new("Street Camera")
    cam = bpy.data.objects.new("Street Camera", data)
    bpy.context.scene.collection.objects.link(cam)
    if shot == "puddle":
        data.lens = 50
        cam.location = (0.8, 3.0, 0.32)
        target = (0.2, 9.0, 0.0)
    elif shot == "macro":
        # dew: a long lens a hand's width above the pavement edge, morning light
        data.lens = 100
        cam.location = (-4.3, 2.0, 0.32)
        target = (-4.3, 2.55, 0.15)
    elif shot == "wide":
        data.lens = 28
        cam.location = (-2.5, -6.0, 7.5)
        target = (0.5, 22.0, 1.5)
    else:
        data.lens = 35
        cam.location = (-1.6, -2.0, 1.6)
        target = (0.6, 20.0, 2.6)
    cam.rotation_euler = (Vector(target) - cam.location).to_track_quat("-Z", "Y").to_euler()
    data.dof.use_dof = shot in ("puddle", "macro")
    data.dof.focus_distance = 0.6 if shot == "macro" else 5.5
    data.dof.aperture_fstop = 4.0 if shot == "macro" else 2.8
    bpy.context.scene.camera = cam
    return cam


def main(argv):
    shot = argv[0] if argv else "street_night"
    preset_id = argv[1] if len(argv) > 1 else "heavy_rain"
    out = Path(argv[2]) if len(argv) > 2 else ROOT / "docs" / "img" / f"{shot}_{preset_id}.png"
    samples = int(argv[3]) if len(argv) > 3 else 96
    frame = int(argv[4]) if len(argv) > 4 else 48
    night = shot in ("street_night", "puddle") or os.environ.get("RAINFX_NIGHT") == "1"

    rainfx = load_package()
    rainfx.register()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if not hasattr(bpy.types.Scene, "rainfx"):
        rainfx.register()
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.samples = samples
    sc.cycles.use_denoising = True
    sc.cycles.max_bounces = 8
    sc.cycles.transparent_max_bounces = 24
    sc.render.resolution_x, sc.render.resolution_y = int(os.environ.get("RAINFX_W", 1280)), int(os.environ.get("RAINFX_H", 720))
    sc.render.fps = 24
    sc.frame_start, sc.frame_end = 1, max(frame, 2)
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Medium High Contrast"
    sc.render.filepath = str(out)

    world(night)
    colliders, lamps = build_street(night)
    cam = camera(shot)
    if shot == "macro":   # low morning sun from in front: dew sparkles against the light
        sun = bpy.data.objects.new("Morning Sun", bpy.data.lights.new("Morning Sun", "SUN"))
        sun.data.energy = 3.0
        sun.data.color = (1.0, 0.85, 0.65)
        sun.data.angle = math.radians(1.0)
        sun.rotation_euler = (math.radians(78), 0.0, math.radians(180))
        sc.collection.objects.link(sun)

    from rainfx.scene import emitter as em
    from rainfx.ui import ops
    s = sc.rainfx
    s.preset = preset_id
    s.box = (14.0, 18.0, 9.0)
    s.with_atmosphere = True
    s.with_lightning = preset_id == "thunderstorm"
    s.distant_rain = True
    ob = em.create_emitter(sc, preset_id, location=(0.0, 7.0, 0.0))
    if preset_id == "dew":    # dew: collide only what is photographed (the bead budget is per collider area)
        colliders = [o for o in colliders if o.name == "Pavement L"]
    em.add_colliders(sc, colliders)
    bpy.context.view_layer.objects.active = ob
    ops.apply_all(bpy.context, ob)
    s.wetness = True
    if hasattr(s, "wet_start"):
        s.wet_start = os.environ.get("RAINFX_WET_START", "1") == "1"
    s.foreground_rain = shot != "wide"
    s.drips = os.environ.get("RAINFX_DRIPS", "1") == "1"
    if not night and "add_backlight" in dir(bpy.ops.rainfx) and os.environ.get("RAINFX_BACKLIGHT"):
        bpy.ops.rainfx.add_backlight()
    if shot != "wide" and os.environ.get("RAINFX_LENS"):
        s.lens_drops = True

    t0 = time.time()
    for f in range(1, frame + 1):
        sc.frame_set(f)
    print(f"SIM {frame} frames {time.time() - t0:.0f}s", flush=True)
    hook = os.environ.get("RAINFX_HOOK")      # dev: a script run just before the render
    if hook:
        exec(compile(Path(hook).read_text(), hook, "exec"), {"bpy": bpy, "sc": sc})
    t0 = time.time()
    out.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.render.render(write_still=True)
    print(f"RENDERED {out} {time.time() - t0:.0f}s", flush=True)
    save = os.environ.get("RAINFX_SAVE_BLEND")
    if save:
        bpy.ops.wm.save_as_mainfile(filepath=save)
    return 0


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    code = main(argv)
    sys.stdout.flush()
    os._exit(code)
