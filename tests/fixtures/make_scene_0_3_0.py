"""Recreate tests/fixtures/scene_0_3_0.blend with the released RainFX 0.3.0.

    unzip rainfx-0.3.0.zip -d /tmp/v03/rainfx
    blender -b --factory-startup --python tests/fixtures/make_scene_0_3_0.py -- /tmp/v03 out.blend

Heavy rain from the Add Emitter button (demo surface + Suzanne colliders),
wetness, distant rain and lens drops on, 12 frames played, saved.
"""
import sys; sys.path.insert(0, sys.argv[-2])
import bpy, rainfx
from rainfx.scene import emitter as em
print("VERSION_SRC", rainfx.__file__)
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.frame_start, sc.frame_end = 1, 48
rainfx.register()
cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam")); sc.collection.objects.link(cam); sc.camera = cam
cam.location = (0, -14, 2.5); cam.rotation_euler = (1.45, 0, 0)
s = sc.rainfx
s.preset = "heavy_rain"
assert bpy.ops.rainfx.add_emitter() == {"FINISHED"}
s.wetness = True
s.distant_rain = True
s.lens_drops = True
bpy.ops.rainfx.post()
for f in range(1, 13): sc.frame_set(f)
bpy.ops.wm.save_as_mainfile(filepath=sys.argv[-1])
print("SAVED", [ (g.name, g.get("rainfx_version")) for g in bpy.data.node_groups if g.name.startswith("RainFX")])
