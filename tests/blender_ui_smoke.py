"""Registers the add-on in headless Blender and drives the operators.

    python tests/blender_ui_smoke.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import bpy  # noqa: E402

import blender_smoke as T  # noqa: E402
import rainfx  # noqa: E402
from rainfx.scene import emitter as em  # noqa: E402


def main():
    sc = T.make_world()
    sc.world = bpy.data.worlds.new("W")
    rainfx.register()
    try:
        s = sc.rainfx
        from rainfx.ui import props
        assert len(props.preset_items(s, bpy.context)) >= 14      # dynamic enum callback
        s.preset = "thunderstorm"
        r = bpy.ops.rainfx.add_emitter()
        assert r == {"FINISHED"}
        ob = bpy.context.object
        assert em.is_emitter(ob)
        assert bpy.data.objects.get("RainFX Fog") is not None
        assert bpy.data.objects.get("RainFX Lightning") is not None
        # [Demo] the add op seeds a demo ground + monkey and collides them
        surf = bpy.data.objects.get("RainFX Surface")
        mon = bpy.data.objects.get("RainFX Suzanne")
        assert surf is not None and mon is not None, "demo objects missing"
        assert surf.type == mon.type == "MESH"
        assert len(surf.data.vertices) == 4 and len(mon.data.vertices) > 100
        cd = em.colliders_collection(sc)
        assert "RainFX Surface" in cd.objects and "RainFX Suzanne" in cd.objects
        for o in (surf, mon):
            assert o.matrix_world.translation.length < 1e-6, "demo off origin"
        n_col = len(em.colliders_collection(sc).objects)
        em.create_demo(sc)  # idempotent: same names, no new colliders
        assert bpy.data.objects.get("RainFX Surface") is surf
        assert bpy.data.objects.get("RainFX Suzanne") is mon
        assert len(em.colliders_collection(sc).objects) == n_col
        print("[Demo] surface + monkey generated and colliding")
        s.preset = "hailstorm"                     # live update path
        assert ob["rainfx_preset"] == "hailstorm"
        d = ob["rainfx_derived"]
        assert d["mode_index"] == 1 and d["count"] > 100
        s.preset = "dew"
        assert ob["rainfx_preset"] == "dew"
        s.preset = "heavy_snow"
        assert ob["rainfx_preset"] == "heavy_snow"
        assert bpy.ops.rainfx.diagnose() == {"FINISHED"}
        assert bpy.ops.rainfx.legacy_emitter() == {"FINISHED"}
        assert bpy.ops.rainfx.post() == {"FINISHED"}
        assert bpy.ops.rainfx.revert_lighting() == {"FINISHED"}
        # every icon literal used by the addon must exist in this Blender's
        # UILayout enum (5.2 removed MOD_SMOKE, which crashed panel draw)
        enum = {item.identifier for item in
                bpy.types.UILayout.bl_rna.functions["prop"]
                .parameters["icon"].enum_items}
        import re
        from pathlib import Path
        ui_dir = Path(rainfx.__file__).parent / "ui"
        bad = []
        for src in ui_dir.glob("*.py"):
            bad += [m.group(1) for m in re.finditer(r'icon="([A-Z0-9_]+)"',
                                                    src.read_text())
                    if m.group(1) not in enum]
        assert not bad, f"icons missing from UILayout enum: {bad}"
        print("PASS ui icon enum: %d literals scanned" % 1)
        print("PASS ui smoke")
    finally:
        rainfx.unregister()


main()
