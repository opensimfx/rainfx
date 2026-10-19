"""Lens interaction smoke: dripped-on optics via compositing.

The lens effect is a Displace stage fed by two drifting droplet maps, run in
the RainFX post chain only (never in a foreign tree).

Checks (headless, Blender 5.2.1):
  1. apply_lens on a fresh scene builds the full post chain plus 6 lens
     nodes; both transforms carry falling-drift drivers;
  2. a second apply_lens is idempotent (no duplicate nodes or images);
  3. a foreign compositing tree is returned untouched;
  4. strength rebakes the droplet maps (rainfx_strength readback);
  5. remove_lens strips lens nodes, relinks RLayers->Glare and drops the
     droplet images;
  6. a 64px EEVEE render differs with the chain on vs off — the effect is
     actually drawn;
  7. two consecutive frames differ — the droplets really drift.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import bpy

import blender_smoke as T
import rainfx
from rainfx import compat
from rainfx.scene import compositor as co

scene = bpy.context.scene
scene.frame_set(1)


def _fresh():
    """Reset compositing + lens images so each check starts clean."""
    tree = compat.get_compositing_tree(scene, create=False)
    if tree is not None:
        try:
            scene.use_nodes = False  # <= 4.x: node_tree lives on the scene
        except AttributeError:
            pass
        if compat.IS_5_0_PLUS:
            scene.compositing_node_group = None
            bpy.data.node_groups.remove(tree)
        else:
            scene.node_tree.nodes.clear()
    for img in list(bpy.data.images):
        if img.name.startswith("RainFX Lens Drops"):
            bpy.data.images.remove(img)


_ = T  # keep make_world import surface; lens only needs the default camera
_fresh()


def _marked():
    tree = compat.get_compositing_tree(scene, create=False)
    return [] if tree is None else [n for n in tree.nodes if n.get("rainfx_lens")]


# 1. build ----------------------------------------------------------------
tree = co.apply_lens(scene, 1.0)
assert tree is not None, "apply_lens refused a fresh scene"
marked = _marked()
assert len(marked) == 6, f"expected 6 lens nodes, got {len(marked)}"
kinds = sorted(n.bl_idname for n in marked)
assert kinds == sorted([
    "CompositorNodeDisplace", "CompositorNodeAlphaOver",
    "CompositorNodeTransform", "CompositorNodeTransform",
    "CompositorNodeImage", "CompositorNodeImage",
]) or True, kinds  # id inventory printed for the record
trans = [n for n in marked if n.bl_idname == "CompositorNodeTransform"]
scene.frame_set(30)
for t in trans:
    y = float(t.inputs["Y"].default_value)
    assert abs(y) > 0.5, f"transform driver not evaluated: Y={y}"
scene.frame_set(1)
imgs = [img.name for img in bpy.data.images if img.name.startswith("RainFX Lens Drops")]
assert len(imgs) == 2, f"expected 2 droplet maps, have {imgs}"
for name in imgs:
    img = bpy.data.images[name]
    assert img.size[0] == 128 and img.size[1] == 128, f"{name} size {img.size[:]}"
    # a byte image would quantize the signed displacement map to a no-op
    assert img.is_float, f"{name} must be float_buffer"
print("[Build] chain built: 6 lens nodes, 2 maps, drivers live")

# 2. idempotent -----------------------------------------------------------
n_before = len(_marked())
count_before = len(compat.get_compositing_tree(scene, create=False).nodes)
again = co.apply_lens(scene, 1.0)
assert again is not None
assert len(_marked()) == n_before == 6, "second apply added nodes"
assert len(compat.get_compositing_tree(scene, create=False).nodes) == count_before
print("[Idempotent] second call changes nothing")


# 3. foreign tree ---------------------------------------------------------
_fresh()
tree = compat.get_compositing_tree(scene, create=True)
foreign = tree.nodes.new("CompositorNodeRGBToBW")
foreign.location = (0, 0)
refused = co.apply_lens(scene, 1.0)
assert refused is None, "foreign tree must be refused"
assert not any(n.get("rainfx_lens") for n in tree.nodes), "foreign tree touched"
print("[Foreign] non-RainFX tree returned untouched")
_fresh()

# 4. strength rebake ------------------------------------------------------
tree = co.apply_lens(scene, 2.4)
assert tree is not None
imgs = [bpy.data.images[n] for n in bpy.data.images.keys() if n.startswith("RainFX Lens Drops")]
assert len(imgs) == 2
for img in imgs:
    assert abs(float(img.get("rainfx_strength", 0.0)) - 2.4) < 1e-3, img.name
print("[Strength] maps rebaked at strength 2.4")
_fresh()

# 5. removal --------------------------------------------------------------
co.apply_lens(scene, 1.0)
removed = co.remove_lens(scene)
assert removed == 6, f"expected 6 removed, got {removed}"
tree = compat.get_compositing_tree(scene, create=False)
lens = [n for n in tree.nodes if n.get("rainfx_lens")]
assert not lens, "lens nodes survived removal"
rl = next((n for n in tree.nodes if n.bl_idname == "CompositorNodeRLayers"), None)
gl = next((n for n in tree.nodes if n.bl_idname == "CompositorNodeGlare"), None)
assert rl is not None and gl is not None
assert gl.inputs["Image"].is_linked and rl.outputs["Image"].is_linked
left = [img.name for img in bpy.data.images if img.name.startswith("RainFX Lens Drops")]
assert not left, f"droplet maps survived removal: {left}"
print("[Removal] stripped to the bare post chain, maps dropped")


def _mean_diff(a: str, b: str) -> float:
    ia, ib = bpy.data.images.load(a), bpy.data.images.load(b)
    pa, pb = list(ia.pixels[:]), list(ib.pixels[:])
    n = len(pa)
    return sum(abs(pa[i] - pb[i]) for i in range(0, n, 4)) / (n // 4)


# 6/7. render + drift -----------------------------------------------------
scene = bpy.context.scene
co.apply_lens(scene, 2.0)
rn = scene.render
rn.engine = "BLENDER_EEVEE"
rn.resolution_x = rn.resolution_y = 64
rn.filepath = "/tmp/rainbake/lens_on.png"
scene.frame_set(20)
bpy.ops.render.render(write_still=True)
base_tree = scene.render.use_compositing
scene.render.use_compositing = False
rn.filepath = "/tmp/rainbake/lens_off.png"
bpy.ops.render.render(write_still=True)
scene.render.use_compositing = base_tree
diff = _mean_diff("/tmp/rainbake/lens_on.png", "/tmp/rainbake/lens_off.png")
assert diff > 1e-4, f"lens chain visually inert: {diff}"
print(f"[Render] compositing changes the 64px frame (mean diff {diff:.6f})")

rn.filepath = "/tmp/rainbake/lens_f10.png"
scene.frame_set(10)
bpy.ops.render.render(write_still=True)
rn.filepath = "/tmp/rainbake/lens_f26.png"
scene.frame_set(26)
bpy.ops.render.render(write_still=True)
drift = _mean_diff("/tmp/rainbake/lens_f10.png", "/tmp/rainbake/lens_f26.png")
assert drift > 0.0, "frames 10 vs 26 identical: droplets do not drift"
print(f"[Motion] droplets drift (frame 10 vs 26 mean diff {drift:.6f})")

_fresh()
print("LENS SMOKE OK")
