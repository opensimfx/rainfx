"""Headless tests for the non-simulation scene helpers.

    python tests/blender_scene_smoke.py
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import bpy  # noqa: E402

import blender_smoke as T  # noqa: E402
from rainfx import compat  # noqa: E402
from rainfx.scene import atmosphere, compositor, emitter as em, legacy_particles, lighting  # noqa: E402


def test_lightning_schedule_pure():
    keys = lighting.flash_schedule(6, 24, 1, 600, seed=3)
    assert keys[0] == (1, 0.0)
    assert all(0.0 <= k[1] <= 1.0 for k in keys)
    frames = [k[0] for k in keys]
    assert frames == sorted(frames), "schedule must be monotonic"
    assert lighting.flash_schedule(6, 24, 1, 600, seed=3) == keys, "must be deterministic"
    assert len(lighting.flash_schedule(0, 24, 1, 600)) == 1


def test_atmosphere_and_revert():
    sc = T.make_world()
    sc.world = bpy.data.worlds.new("W")
    bg = next(n for n in sc.world.node_tree.nodes if n.type == "BACKGROUND")
    bg.inputs["Strength"].default_value = 1.0
    sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
    sun.data.energy = 4.0
    sc.collection.objects.link(sun)
    atmosphere.apply_lighting(sc, 0.3, 0.1)
    atmosphere.apply_lighting(sc, 0.3, 0.1)                      # idempotent
    assert abs(bg.inputs["Strength"].default_value - 0.3) < 1e-6
    assert abs(sun.data.energy - 0.4) < 1e-6
    atmosphere.revert_lighting(sc)
    assert abs(bg.inputs["Strength"].default_value - 1.0) < 1e-6 and abs(sun.data.energy - 4.0) < 1e-6
    fog = atmosphere.create_fog(sc, density=0.02)
    vol = next(n for n in fog.data.materials[0].node_tree.nodes if n.type == "VOLUME_SCATTER")
    assert abs(vol.inputs["Density"].default_value - 0.02) < 1e-6


def test_lightning_keys():
    sc = T.make_world()
    obj = lighting.create_lightning(sc, per_min=12, energy=1000.0, seed=2)
    ad = obj.data.animation_data
    assert ad is not None and ad.action is not None, "no animation created (5.x slotted action path)"
    sc.frame_set(1)
    seen = set()
    for f in range(1, sc.frame_end):
        sc.frame_set(f)
        seen.add(round(obj.data.energy, 3))
    assert len(seen) > 2 and max(seen) > 0, "flash never fired"


def test_compositor():
    sc = T.make_world()
    assert compositor.create_post(sc) is not None
    assert compositor.create_post(sc) is None, "must not overwrite an existing compositor tree"
    tree = compat.get_compositing_tree(sc)
    assert any(n.bl_idname == "CompositorNodeRLayers" for n in tree.nodes)


def test_compat_52_input_path():
    """Logic test of the 5.2 branch (modifier.properties.inputs.<id>.value) using a stand-in
    modifier. It validates our branching and fallback, not Blender 5.2 itself."""
    sc = T.make_world()
    ob = em.create_emitter(sc, "light_rain")
    real = em.find_modifier(ob)
    ident = compat.socket_identifier(real.node_group, "Count")

    class Slot:
        value = None

    class Inputs:
        pass

    inputs = Inputs()
    setattr(inputs, ident, Slot())

    class FakeMod:
        node_group = real.node_group
        properties = type("P", (), {"inputs": inputs})()
        id_data = ob

    old = compat.IS_5_2_PLUS
    compat.IS_5_2_PLUS = True
    try:
        fake = FakeMod()
        assert compat.set_modifier_input(fake, "Count", 1234)
        assert getattr(inputs, ident).value == 1234
        assert compat.get_modifier_input(fake, "Count") == 1234
        assert not compat.set_modifier_input(fake, "No Such Socket", 1)
        # properties unavailable -> legacy custom-property path on a real 5.0 modifier
        assert compat.set_modifier_input(real, "Count", 77) and compat.get_modifier_input(real, "Count") == 77
    finally:
        compat.IS_5_2_PLUS = old


def test_dew():
    sc = T.make_world()
    obj = em.create_emitter(sc, "dew")
    sc.frame_set(1)
    dg = bpy.context.evaluated_depsgraph_get()
    n = sum(1 for inst in dg.object_instances if inst.is_instance and inst.parent and inst.parent.original == obj)
    assert 100 < n <= 200000 * 1.15, f"dew bead count {n} outside [100, cap]"
    print("dew beads:", n)


def test_legacy_particles():
    sc = T.make_world()
    ob = legacy_particles.create_legacy_emitter(sc, "heavy_rain", size=(8, 8), height=6, quality=0.02, frame_end=120)
    sc.frame_set(1)
    rows = []
    for f in (20, 60, 100):
        sc.frame_set(f)
        eo = ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
        parts = list(eo.particle_systems[0].particles)
        alive = [p for p in parts if p.alive_state == "ALIVE"]
        born = sum(1 for p in parts if p.alive_state != "UNBORN")
        z = np.array([p.location[2] for p in alive]) if alive else np.zeros(0)
        rows.append((f, born, len(alive), float(z.min()) if len(z) else None))
        assert (z < -0.1).sum() == 0, "legacy particles passed through the ground collider"
    print("legacy (frame, born, alive, min_z):", rows)
    f, born, alive, _ = rows[-1]
    assert born > alive, "particles are never killed by the colliders"
    assert alive > 0


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
