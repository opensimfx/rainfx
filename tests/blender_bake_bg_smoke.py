"""Background-bake smoke: child Blender bakes the disk cache while the
parent session stays interactive, and the parent's playback consumes the
child's blobs byte-identically.

Checks (headless, Blender 5.2.1):
  1. launch() spawns a second headless Blender on the saved .blend and the
     poll loop observes monotonic blob progress up to the frame count;
  2. after the child exits, the bake folder holds exactly one blob per frame;
  3. a second launch while one is running is refused (single-flight);
  4. finish() reaps the child and clears the module state;
  5. the child bakes the scene as it is now (a change made after the last
     save is in the cache) and bakes the chosen emitter, not the first one;
  6. after saving and reopening, playback comes from the child's disk cache:
     changing the Seed does not move the baked particles.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

import bpy  # noqa: E402

import blender_smoke as T  # noqa: E402
import rainfx  # noqa: E402
from rainfx import compat  # noqa: E402
from rainfx.scene import baker  # noqa: E402
from rainfx.scene import emitter as em  # noqa: E402

OUT = Path("/tmp/rainbake/bg8.blend")
OUT.unlink(missing_ok=True)
import shutil  # noqa: E402

# wipe any bake residue from earlier smoke runs: every bake makes a NEW
# record-id subfolder under the bake directory, so stale blobs pile up
shutil.rmtree("/tmp/rainbake", ignore_errors=True)
Path("/tmp/rainbake").mkdir(exist_ok=True)  # rmtree removed the dir the save writes into

T.make_world()
sc = bpy.context.scene
rainfx.register()
decoy = em.create_emitter(sc, "light_rain", location=(30, 0, 8), name="Decoy Emitter")
et = em.create_emitter(sc, "heavy_rain", location=(0, 0, 8))
em.apply_preset(et, sc, "heavy_rain", quality=0.05, box=(16, 16, 10))
mod = em.find_modifier(et)
compat.set_modifier_input(mod, "Output Mode", 1)
sc.frame_start, sc.frame_end = 1, 10
sc.frame_set(1)
bpy.ops.wm.save_as_mainfile(filepath=str(OUT))

# reference walk of the state as saved (no wind)
dg = bpy.context.evaluated_depsgraph_get()
pre = []
for f in range(1, 11):
    sc.frame_set(f)
    dg.update()
    ev = et.evaluated_get(dg)
    me = ev.to_mesh()
    pre.append([tuple(round(c, 5) for c in v.co) for v in me.vertices][:8])
    ev.to_mesh_clear()
sc.frame_set(1)
# an unsaved change after the walk: the bake must contain it (the parent's
# live preview keeps its old cache until reset, so it is not the reference)
compat.set_modifier_input(mod, "Wind", (6.0, 0.0, 0.0))

et_name = et.name
handle = baker.launch(sc, et, 1, 10)
try:
    baker.launch(sc, et, 1, 10)
    raise AssertionError("double launch allowed")
except RuntimeError:
    print("[Flight] second launch refused while one runs")
running, done = baker.progress(handle)
assert running, "child not running right after launch"
last = done
deadline = time.time() + 120
while running and time.time() < deadline:
    time.sleep(0.5)
    running, done = baker.progress(handle)
    assert done >= last, "blob progress went backwards"
    last = done
assert not running, "background bake did not finish in 120 s"
blobs = list(handle["dir"].rglob("*.blob"))
assert len(blobs) == 10, f"expected 10 blobs, found {len(blobs)}"
print(f"[Bake] child baked 10/10 frames (last poll {done}/10)")


code = baker.finish(handle)
assert baker.active() is None, "module state not cleared"
print(f"[Reap] child returncode {code}, module state cleared")

# reopen: the saved file points at the disk cache the child wrote
bpy.ops.wm.save_as_mainfile(filepath=str(OUT))
bpy.ops.wm.open_mainfile(filepath=str(OUT))
sc = bpy.context.scene
et = bpy.data.objects[et_name]
mod = em.find_modifier(et)
assert em.find_modifier(bpy.data.objects["Decoy Emitter"]).bake_directory == "" or \
    not list(Path(bpy.path.abspath(em.find_modifier(bpy.data.objects["Decoy Emitter"]).bake_directory)).rglob("*.blob")), \
    "the decoy emitter was baked"


def walk_now():
    out = []
    dg = bpy.context.evaluated_depsgraph_get()
    for f in range(1, 11):
        sc.frame_set(f)
        ev = et.evaluated_get(dg)
        me = ev.to_mesh()
        out.append([tuple(round(c, 5) for c in v.co) for v in me.vertices][:8])
        ev.to_mesh_clear()
    return out


def delta(a, b):
    return max((abs(x - y) for fa, fb in zip(a, b) for va, vb in zip(fa, fb) for x, y in zip(va, vb)),
               default=0.0)


re1 = walk_now()
# +x wind drift: the baked particles move further in x than the saved state's
drift = lambda w: sum(b[0] - a[0] for a, b in zip(w[0], w[4]) if abs(b[0] - a[0]) < 4) / len(w[0])  # noqa: E731
d_state = drift(re1) - drift(pre)
assert d_state > 0.15, f"baked playback lacks the unsaved wind change (extra x drift {d_state:.3f} m)"
compat.set_modifier_input(mod, "Seed", 4242)
re2 = walk_now()
d_seed = delta(re2, re1)
assert d_seed < 1e-6, f"a Seed change moved baked particles ({d_seed}): playback is not from the cache"
print(f"[Reopen] playback from the child's cache: has the unsaved wind (+{d_state:.2f} m x drift by frame 5); "
      f"Seed change has no effect ({d_seed:.1e})")

bpy.ops.object.select_all(action="DESELECT")
bpy.context.view_layer.objects.active = et
et.select_set(True)
bpy.ops.rainfx.bake_delete()
assert list(Path(mod.bake_directory).rglob("*.blob")) == [], "delete left blobs"
print("BG BAKE SMOKE OK")
