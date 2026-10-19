"""Optional compositing chain (soft bloom for lightning / fog glow).

Rules:
* never modify a scene that already has compositing nodes -> returns None
* 5.0+ uses ``scene.compositing_node_group`` and a Group Output; older
  versions use ``scene.node_tree`` and a Composite node
* node settings that differ between versions are wrapped in try/except so a
  missing option degrades to defaults instead of failing the operator
"""
from __future__ import annotations

import random

import bpy


from .. import compat


def create_post(scene: bpy.types.Scene, glare_strength: float = 0.25):
    existing = compat.get_compositing_tree(scene, create=False)
    if existing is not None and len(existing.nodes) > 0:
        return None
    tree = compat.get_compositing_tree(scene, create=True)
    for n in list(tree.nodes):
        tree.nodes.remove(n)
    tree["rainfx_post"] = 1

    rl = tree.nodes.new("CompositorNodeRLayers")
    glare = tree.nodes.new("CompositorNodeGlare")
    if compat.IS_5_0_PLUS:
        out = tree.nodes.new("NodeGroupOutput")
        tree.interface.new_socket(name="Image", in_out="OUTPUT", socket_type="NodeSocketColor")
        out_in = out.inputs["Image"]
    else:
        out = tree.nodes.new("CompositorNodeComposite")
        out_in = out.inputs["Image"]
    rl.location, glare.location, out.location = (-400, 0), (-100, 0), (200, 0)

    for setter in (
        lambda: setattr(glare, "glare_type", "FOG_GLOW"),                       # <= 4.5
        lambda: setattr(glare.inputs["Type"], "default_value", "Fog Glow"),     # 5.0+ menu socket
        lambda: setattr(glare.inputs["Strength"], "default_value", glare_strength),
        lambda: setattr(glare.inputs["Threshold"], "default_value", 1.0),
    ):
        try:
            setter()
        except (AttributeError, TypeError, KeyError, ValueError):
            pass

    tree.links.new(rl.outputs["Image"], glare.inputs["Image"])
    tree.links.new(glare.outputs["Image"], out_in)
    return tree


# --------------------------------------------------------------------------
# Lens interaction: rain/wet lens optics via a Displace stage driven by two
# drifting droplet maps. Lives only in RainFX's own post chain (foreign
# compositing trees stay untouched, same rule as create_post).
# Displacement convention (Blender docs): map red channel -> X offset,
# green -> Y offset, both in pixels; Transform repeat-wraps the maps so the
# driven fall drift loops forever.

LENS_A = "RainFX Lens Drops A"
LENS_B = "RainFX Lens Drops B"
_LENS_SIZE = 128  # droplet field resolution (square): 256px+ generated
                  # maps sample as black in the 5.2 compositor — keep 128


def _lens_image(name: str, seed: int, strength: float) -> bpy.types.Image:
    """Build (or restrength) one droplet displacement map: ~30 blobs, a few
    stretched into drip streaks; RGB = radial push, alpha = droplet mask."""
    img = bpy.data.images.get(name)
    if img is not None and abs(float(img.get("rainfx_strength", -1.0)) - strength) <= 0.02:
        return img
    w = h = _LENS_SIZE
    buf = [0.0] * (w * h * 4)
    rng = random.Random(seed * 7919 + 13)
    amp = 4.0 * strength
    for _ in range(30):
        cx, cy = rng.random(), rng.random()
        r = rng.uniform(0.03, 0.09)
        ry = r * (rng.uniform(3.0, 7.0) if rng.random() < 0.25 else 1.0)
        x0 = max(0, int((cx - r) * w))
        x1 = min(w, int((cx + r) * w) + 1)
        y0 = max(0, int((cy - ry) * h))
        y1 = min(h, int((cy + ry) * h) + 1)
        for py in range(y0, y1):
            ny = (py / h - cy) / ry
            for px in range(x0, x1):
                nx = (px / w - cx) / r
                d2 = nx * nx + ny * ny
                if d2 >= 1.0:
                    continue
                s = (1.0 - d2 ** 0.5) ** 0.7
                i = (py * w + px) * 4
                buf[i] = nx * amp * s          # R -> X displacement
                buf[i + 1] = ny * amp * s      # G -> Y displacement
                buf[i + 3] = max(buf[i + 3], s)  # alpha mask, blob union
    if img is None:
        # float_buffer is required: a byte image saturates signed displacement
        # (values >1 clamp to 1.0, negatives clamp to 0) and many seeds render
        # the Displace stage as an exact no-op
        img = bpy.data.images.new(name, w, h, alpha=True, float_buffer=True)
    img.pixels.foreach_set(buf)
    img["rainfx_strength"] = strength
    return img


def apply_lens(scene: bpy.types.Scene, strength: float = 1.0):
    """Insert (or refresh) the droplet-lens stage in the RainFX post chain.

    Returns the compositing tree, or None when the scene carries a foreign
    compositing setup (then nothing is touched).
    """
    tree = compat.get_compositing_tree(scene, create=False)
    if tree is None or len(tree.nodes) == 0:
        tree = create_post(scene)
        if tree is None:
            return None
    elif not tree.get("rainfx_post") and not any(
            n.get("rainfx_lens") for n in tree.nodes):
        return None
    # refresh droplet maps for the new strength (cheap no-op when unchanged)
    img_a = _lens_image(LENS_A, 1, strength)
    img_b = _lens_image(LENS_B, 2, strength)
    if any(n.get("rainfx_lens") for n in tree.nodes):
        return tree  # already installed: maps were refreshed above
    rl = next((n for n in tree.nodes if n.bl_idname == "CompositorNodeRLayers"), None)
    glare = next((n for n in tree.nodes if n.bl_idname == "CompositorNodeGlare"), None)
    if rl is None or glare is None:
        return None

    ia = tree.nodes.new("CompositorNodeImage")
    ib = tree.nodes.new("CompositorNodeImage")
    ta = tree.nodes.new("CompositorNodeTransform")
    tb = tree.nodes.new("CompositorNodeTransform")
    aover = tree.nodes.new("CompositorNodeAlphaOver")
    disp = tree.nodes.new("CompositorNodeDisplace")
    ia.location, ib.location = (-320, -220), (-320, -360)
    ta.location, tb.location = (-220, -220), (-220, -360)
    aover.location, disp.location = (-150, -280), (-250, 60)

    for n, img in ((ia, img_a), (ib, img_b)):
        n["rainfx_lens"] = 1
        n.image = img
    for n in (ta, tb, aover, disp):
        n["rainfx_lens"] = 1
    for tr in (ta, tb):
        for ext in ("Extension X", "Extension Y"):
            try:
                tr.inputs[ext].default_value = "REPEAT"
            except (TypeError, ValueError):
                pass
    # map drift: negative Y translates the droplet field downward each frame
    for tr, rate in ((ta, "frame * -0.35"), (tb, "frame * -0.85")):
        drv = tr.inputs["Y"].driver_add("default_value")
        drv.driver.expression = rate
    try:
        aover.inputs["Factor"].default_value = 1.0
    except (AttributeError, TypeError):
        pass

    lk = tree.links.new
    lk(ia.outputs["Image"], ta.inputs["Image"])
    lk(ib.outputs["Image"], tb.inputs["Image"])
    lk(ta.outputs["Image"], aover.inputs["Background"])
    lk(tb.outputs["Image"], aover.inputs["Foreground"])
    lk(aover.outputs["Image"], disp.inputs["Displacement"])
    lk(rl.outputs["Image"], disp.inputs["Image"])
    lk(disp.outputs["Image"], glare.inputs["Image"])
    # keep our own chain recognizable for future lens refreshes / removals
    tree["rainfx_post"] = 1
    return tree


def remove_lens(scene: bpy.types.Scene) -> int:
    """Strip lens nodes, relink the bare chain, drop the droplet maps."""
    tree = compat.get_compositing_tree(scene, create=False)
    if tree is None:
        return 0
    doomed = [n for n in tree.nodes if n.get("rainfx_lens")]
    for n in doomed:
        tree.nodes.remove(n)
    if doomed:
        rl = next((n for n in tree.nodes if n.bl_idname == "CompositorNodeRLayers"), None)
        glare = next((n for n in tree.nodes if n.bl_idname == "CompositorNodeGlare"), None)
        if rl is not None and glare is not None and not glare.inputs["Image"].is_linked:
            tree.links.new(rl.outputs["Image"], glare.inputs["Image"])
        for name in (LENS_A, LENS_B):
            img = bpy.data.images.get(name)
            if img is not None and img.users == 0:
                try:
                    bpy.data.images.remove(img)
                except (RuntimeError, ReferenceError):
                    pass
    return len(doomed)
