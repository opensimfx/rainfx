"""Upgrade smoke: a scene saved by RainFX 0.3.0 opens and upgrades cleanly.

The fixture (tests/fixtures/scene_0_3_0.blend, made by
tests/fixtures/make_scene_0_3_0.py with the released 0.3.0 add-on) has heavy
rain, wetness, distant rain and lens drops.

Checks (desktop Blender 5.2.3):
  1. [Open] the file plays as saved before anything is touched: rain,
     distant rain, and wetness keeps accumulating (persistent handler);
  2. [Touch] changing the preset rebuilds every stale node group without a
     crash (a remapped group kept the old simulation state and crashed
     Blender), no modifier is left without its group, rain still falls and
     the wetness helpers run on the new face-corner domain;
  3. [Lens] the 0.3 lens stage is rebuilt with the blur inside drops.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import bpy  # noqa: E402

import rainfx  # noqa: E402
from rainfx.gn import distant, precip  # noqa: E402
from rainfx.gn import wetness as gwet  # noqa: E402
from rainfx.scene import emitter as em  # noqa: E402
from rainfx.scene import wetness as wet  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "scene_0_3_0.blend"


def counts(sc):
    dg = bpy.context.evaluated_depsgraph_get()
    out = {}
    for o in sc.objects:
        if em.is_emitter(o) or o.name.startswith("RainFX Distant"):
            ev = o.evaluated_get(dg)
            out[o.name] = len(ev.to_mesh().vertices)
            ev.to_mesh_clear()
    return out


def wet_state(sc):
    dg = bpy.context.evaluated_depsgraph_get()
    out = {}
    for o in sc.objects:
        if wet._find_wet_mod(o):
            ev = o.evaluated_get(dg)
            a = ev.to_mesh().attributes.get("rainfx_wet")
            out[o.name] = (a.domain, max((d.value for d in a.data), default=0.0)) if a else (None, 0.0)
            ev.to_mesh_clear()
    return out


def main():
    rainfx.register()
    bpy.ops.wm.open_mainfile(filepath=str(FIXTURE))
    sc = bpy.context.scene
    versions = {g.name: g.get("rainfx_version") for g in bpy.data.node_groups}
    assert versions.get(precip.GROUP_NAME) == 8, f"fixture is not a 0.3.0 scene: {versions}"

    for f in range(1, 25):
        sc.frame_set(f)
    c = counts(sc)
    w = wet_state(sc)
    assert c.get("RainFX Emitter", 0) > 100 and c.get("RainFX Distant", 0) > 1000, f"0.3 scene renders no rain: {c}"
    assert w.get("RainFX Suzanne", (None, 0))[1] > 0.5, f"wetness stopped in the reopened 0.3 scene: {w}"
    print(f"[Open] plays as saved: {c}; Suzanne wet {w['RainFX Suzanne'][1]:.2f}")

    sc.rainfx.preset = "downpour"   # live update: the first touch rebuilds everything
    for f in range(1, 25):
        sc.frame_set(f)
    versions = {g.name: g.get("rainfx_version") for g in bpy.data.node_groups if g.name.startswith("RainFX")}
    assert versions[precip.GROUP_NAME] == precip.GROUP_VERSION, versions
    assert versions[gwet.GROUP_NAME] == gwet.GROUP_VERSION, versions
    assert versions[distant.GROUP_NAME] == distant.GROUP_VERSION, versions
    assert not any("(stale)" in n for n in versions), versions
    missing = [(o.name, m.name) for o in bpy.data.objects for m in o.modifiers
               if m.type == "NODES" and m.node_group is None]
    assert not missing, f"modifiers left without a node group: {missing}"
    c = counts(sc)
    w = wet_state(sc)
    assert c.get("RainFX Emitter", 0) > 100, f"no rain after the upgrade: {c}"
    dom, val = w.get("RainFX Suzanne", (None, 0.0))
    assert dom == "CORNER" and val > 0.5, f"wetness after the upgrade: {w}"
    print(f"[Touch] groups rebuilt to {versions}; rain {c}; Suzanne wet {val:.2f} on {dom}")

    post = bpy.data.node_groups.get("RainFX Post")
    tree = post if post is not None else sc.compositing_node_group
    kinds = {n.bl_idname for n in tree.nodes if n.get("rainfx_lens")}
    n_lens = sum(1 for n in tree.nodes if n.get("rainfx_lens"))
    assert "CompositorNodeBlur" in kinds and n_lens == 9, f"lens stage not upgraded: {n_lens} {kinds}"
    print(f"[Lens] 0.3 stage rebuilt: {n_lens} nodes with the blur inside drops")
    print("PASS upgrade smoke")


main()
