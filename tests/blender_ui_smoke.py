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
        print("PASS ui smoke")
    finally:
        rainfx.unregister()


main()
