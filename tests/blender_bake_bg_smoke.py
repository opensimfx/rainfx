"""Background-bake smoke: child Blender bakes the disk cache while the
parent session stays interactive, and the parent's playback consumes the
child's blobs byte-identically.

Checks (headless, Blender 5.2.1):
  1. launch() spawns a second headless Blender on the saved .blend and the
     poll loop observes monotonic blob progress up to the frame count;
  2. after the child exits, the bake folder holds exactly one blob per frame
     and the parent's playback over the range matches the pre-bake walk
     state (positions identical — the child's cache is the parent's cache);
  3. a second launch while one is running is refused (single-flight);
  4. finish() reaps the child and clears the module state.
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
et = em.create_emitter(sc, "heavy_rain", location=(0, 0, 8))
em.apply_preset(et, sc, "heavy_rain", quality=0.05, box=(16, 16, 10))
mod = em.find_modifier(et)
compat.set_modifier_input(mod, "Output Mode", 1)
sc.frame_start, sc.frame_end = 1, 10
sc.frame_set(1)
bpy.ops.wm.save_as_mainfile(filepath=str(OUT))

# pre-bake reference walk
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

sc.frame_set(1)
dg = bpy.context.evaluated_depsgraph_get()
worst = 0.0
for f, want in zip(range(1, 11), pre):
    sc.frame_set(f)
    dg.update()
    ev = et.evaluated_get(dg)
    me = ev.to_mesh()
    got = [tuple(round(c, 5) for c in v.co) for v in me.vertices][:8]
    ev.to_mesh_clear()
    for a, b in zip(got, want):
        worst = max(worst, max(abs(x - y) for x, y in zip(a, b)))
assert worst < 1e-4, f"post-bake playback differs by {worst}"
print(f"[Play] parent playback matches sim (max delta {worst:.2e})")

code = baker.finish(handle)
assert baker.active() is None, "module state not cleared"
print(f"[Reap] child returncode {code}, module state cleared")

bpy.ops.rainfx.bake_delete()
assert list(Path(mod.bake_directory).rglob("*.blob")) == [], "delete left blobs"
print("BG BAKE SMOKE OK")
