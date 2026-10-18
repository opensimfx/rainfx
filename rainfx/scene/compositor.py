"""Optional compositing chain (soft bloom for lightning / fog glow).

Rules:
* never modify a scene that already has compositing nodes -> returns None
* 5.0+ uses ``scene.compositing_node_group`` and a Group Output; older
  versions use ``scene.node_tree`` and a Composite node
* node settings that differ between versions are wrapped in try/except so a
  missing option degrades to defaults instead of failing the operator
"""
from __future__ import annotations

import bpy

from .. import compat


def create_post(scene: bpy.types.Scene, glare_strength: float = 0.25):
    existing = compat.get_compositing_tree(scene, create=False)
    if existing is not None and len(existing.nodes) > 0:
        return None
    tree = compat.get_compositing_tree(scene, create=True)
    for n in list(tree.nodes):
        tree.nodes.remove(n)

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
