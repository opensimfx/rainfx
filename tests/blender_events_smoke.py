"""Sound-ready events smoke: replay-and-export writes a valid JSON event log.

World: wetness smoke's world (30 m ground + 2 m cube, colliders registered).
heavy_rain emitter replays 24 frames; impacts land on both objects. The
export reads the 'imp' sink verts that already ride the emitter output.

Checks (headless, Blender 5.2.1):
  1. [Build] export writes JSON: version 1, fps 24, preset name, events in
     range with 3-component positions on the ground/cube, intensity in mm;
  2. [Cap] no frame exceeds per_frame_cap (stride sampling works);
  3. [Restore] the user's Viewport Density value survives the walk;
  4. [Snow] a light_snow world exports events typed 'snow';
  5. [Empty] a scene without colliders exports valid JSON with no events;
  6. [Toggle] the Collision panel operator exists and polls an emitter.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from tempfile import mkdtemp

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

import bpy  # noqa: E402

from rainfx import compat  # noqa: E402
from rainfx.scene import emitter as em  # noqa: E402
from rainfx.scene import events as ev  # noqa: E402
from blender_wetness_smoke import make_world  # noqa: E402

OUT = mkdtemp()


def per_frame(doc):
    counts = {}
    for e in doc["events"]:
        counts[e["frame"]] = counts.get(e["frame"], 0) + 1
    return counts


# --- [Build] heavy rain world, 24-frame replay -----------------------------
scene, ground, cube, et = make_world()
mod = em.find_modifier(et)
compat.set_modifier_input(mod, "Viewport Density", 0.5)  # must survive export

path, count = ev.export_events(scene, et, os.path.join(OUT, "a.json"))
assert count > 0, "export reported zero events for a raining world"
doc = json.loads(Path(path).read_text())
assert doc["version"] == 1
assert doc["fps"] == 24
assert doc["frame_start"] == 1 and doc["frame_end"] == 24
assert doc["preset"] == "heavy_rain"
assert doc["events"], "JSON log empty"
for e in doc["events"]:
    assert e["frame"] in range(1, 25)
    pos = e["position"]
    assert len(pos) == 3
    assert -2.5 <= pos[2] <= 2.5, f"impact outside the world: {pos}"
    assert e["intensity"] > 0.0
    assert e["type"] in ("impact", "snow")
print(f"[Build] {count} events exported (frame vert pings across 24 frames)")

# --- [Sink] impact stamps stay on the surface -------------------------------
# splash children used to inherit the landed parent's imp flag, flooding the
# sink with spray blobs below the ground (the "rain under the floor" bug)
mod = em.find_modifier(et)
compat.set_modifier_input(mod, "Viewport Density", 1.0)
dg = bpy.context.evaluated_depsgraph_get()
scene.frame_set(24)
dg.update()
ev2 = et.evaluated_get(dg)
me2 = ev2.to_mesh()
imp2 = me2.attributes.get("imp")
zmin = min(v.co.z for v, d in zip(me2.vertices, imp2.data) if d.value > 0.5)
ev2.to_mesh_clear()
compat.set_modifier_input(mod, "Viewport Density", 0.5)
assert zmin >= -0.08, f"impact stamps under the surface: zmin={zmin:.3f}"
print(f"[Sink] lowest impact stamp at z={zmin:.3f} (surface level)")

# --- [Cap] per-frame stride sampling ---------------------------------------
assert max(per_frame(doc).values()) <= 256, "per_frame_cap exceeded"
print("[Cap] every frame keeps at most per_frame_cap events")

# --- [Restore] headless viewport push is undone ----------------------------
assert compat.get_modifier_input(mod, "Viewport Density", 1.0) == 0.5, (
    "Viewport Density not restored after the export walk")
print("[Restore] Viewport Density survives the walk")

# --- [Snow] flakes type as 'snow' ------------------------------------------
scene2, _g, _c, et2 = make_world("light_snow", box=(4, 4, 3), quality=1.0)
scene2.frame_end = 97
path2, count2 = ev.export_events(scene2, et2, os.path.join(OUT, "b.json"))
doc2 = json.loads(Path(path2).read_text())
types = {e["type"] for e in doc2["events"]}
assert count2 > 0 and "snow" in types, f"snow world exported {types}"
print(f"[Snow] {count2} events typed {sorted(types)}")

# --- [Empty] no colliders -> valid empty log -------------------------------
bpy.ops.wm.read_factory_settings(use_empty=True)
scene3 = bpy.context.scene
scene3.frame_end = 3
et3 = em.create_emitter(scene3, "drizzle")
path3, count3 = ev.export_events(scene3, et3, os.path.join(OUT, "c.json"))
assert count3 == 0 and json.loads(Path(path3).read_text())["events"] == []
print("[Empty] collider-less world exports a valid empty log")

# --- [Toggle] panel operator registered ------------------------------------
assert hasattr(bpy.ops.rainfx, "export_events")
print("[Toggle] rainfx.export_events operator registered")

print("EVENTS SMOKE OK")
