"""Farm smoke: a baked scene renders its rain and wetness without RainFX.

A render farm opens the .blend in a Blender without the add-on and renders
each frame on its own (no playback from the start). So the wetness helpers,
fed by a RainFX frame handler during playback, must be baked together with
the rain, and the drips (pure node group) must need nothing.

Checks (desktop Blender 5.2.3):
  1. [Control] unbaked, a fresh Blender without RainFX that jumps to the last
     frame has no simulated wetness on the cube (the evidence a farm would
     lose it);
  2. [Packed] after Bake (packed), the same jump shows rain, the cube's
     wetness from the simulated hits, and drips;
  3. [Background] a background bake to disk does the same (the child Blender
     loads the wetness handler itself).
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

import bpy  # noqa: E402

import rainfx  # noqa: E402
from rainfx.scene import baker  # noqa: E402
from rainfx.scene import emitter as em  # noqa: E402
from rainfx.scene import wetness as wet  # noqa: E402

import blender_wetness_smoke as W  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="rainfx_farm_"))
LAST = 24

CHECK = """
import bpy, json
sc = bpy.context.scene
sc.frame_set({last})
dg = bpy.context.evaluated_depsgraph_get()
cube = bpy.data.objects["Cube"]
me = cube.evaluated_get(dg).to_mesh()
a = me.attributes.get("rainfx_wet")
wet = max((d.value for d in a.data), default=0.0) if a else 0.0
cube.evaluated_get(dg).to_mesh_clear()
et = next(o for o in bpy.data.objects if o.get("rainfx_emitter"))
drops = sum(1 for i in dg.object_instances if i.is_instance and i.parent and i.parent.original == et)
dr = bpy.data.objects.get("RainFX Drips")
drips = sum(1 for i in dg.object_instances if dr and i.is_instance and i.parent and i.parent.original == dr)
addon = hasattr(bpy.types.Scene, "rainfx")
print("RESULT " + json.dumps(dict(wet=wet, drops=drops, drips=drips, addon=addon)))
"""


def fresh_blender(blend: Path) -> dict:
    """Open ``blend`` in a new Blender with factory settings (no RainFX) and jump to the last frame."""
    script = TMP / "check.py"
    script.write_text(CHECK.format(last=LAST))
    out = subprocess.run([bpy.app.binary_path, "-b", str(blend), "--factory-startup", "--python", str(script)],
                         capture_output=True, text=True, timeout=600).stdout
    line = next(l for l in out.splitlines() if l.startswith("RESULT "))
    return json.loads(line[len("RESULT "):])


def world():
    scene, ground, cube, emitter = W.make_world()
    scene.frame_start, scene.frame_end = 1, LAST
    scene.rainfx.preset = "heavy_rain"
    scene.rainfx.live_update = False
    scene.rainfx.wet_start = False          # wetness from the hits, not the ambient start level
    scene.rainfx.wetness = True
    wet.refresh(scene, True, radius=1.0, strength=0.9, dry_rate=0.0)
    from rainfx import compat               # ambient off: only simulated hits wet the cube
    for _ob, m in wet.helpers(scene):
        compat.set_modifier_input(m, "Ambient Wet", 0.0)
        compat.set_modifier_input(m, "Ambient Pool", 0.0)
    scene.rainfx.drips = True
    bpy.context.view_layer.objects.active = emitter
    emitter.select_set(True)
    return scene, cube, emitter


def main():
    rainfx.register()

    scene, cube, emitter = world()
    path = TMP / "unbaked.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(path))
    r = fresh_blender(path)
    assert not r["addon"], "the checker must run without RainFX"
    assert r["wet"] < 0.05, f"unbaked scene showed wetness without RainFX: {r}"
    print(f"[Control] unbaked, no RainFX, frame {LAST}: cube wet {r['wet']:.3f}")

    scene, cube, emitter = world()
    assert bpy.ops.rainfx.bake(packed=True, frame_start=1, frame_end=LAST) == {"FINISHED"}
    path = TMP / "packed.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(path))
    r = fresh_blender(path)
    assert r["wet"] > 0.3 and r["drops"] > 100 and r["drips"] > 0, f"packed bake incomplete without RainFX: {r}"
    print(f"[Packed] no RainFX, frame {LAST}: cube wet {r['wet']:.2f}, {r['drops']} rain instances, "
          f"{r['drips']} drip instances")

    scene, cube, emitter = world()
    path = TMP / "bg.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(path))
    handle = baker.launch(scene, emitter, 1, LAST)
    deadline = time.time() + 300
    while baker.progress(handle)[0] and time.time() < deadline:
        time.sleep(0.5)
    code = baker.finish(handle)
    assert code == 0, f"background bake exited with {code}"
    bpy.ops.wm.save_as_mainfile(filepath=str(path))
    r = fresh_blender(path)
    assert r["wet"] > 0.3 and r["drops"] > 100, f"background bake incomplete without RainFX: {r}"
    print(f"[Background] no RainFX, frame {LAST}: cube wet {r['wet']:.2f}, {r['drops']} rain instances")
    print("PASS farm smoke")


main()
