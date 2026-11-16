"""Rain backlight: a hard light behind the rain, shining back toward the camera.

Rain is close to invisible unless it is lit from behind ("front-light snow,
back-light rain"): a drop refracts the light source toward the lens and the
streak flares. This places one spot light beyond the rain, off the lens axis,
from the active camera and the emitter. Re-running moves the same light;
``remove_backlight`` deletes it. Placement maths lives in
``core.physics.backlight_placement`` (unit-tested without Blender).
"""
from __future__ import annotations

import math

import bpy
from mathutils import Vector

from ..core import physics as P
from . import emitter as em

LIGHT_NAME = "RainFX Backlight"

# colour, beam elevation (deg), side angle (deg)
STYLES = {
    "STREET": ((1.0, 0.72, 0.45), 30.0, 20.0),   # sodium/tungsten street lamp
    "MOON": ((0.62, 0.74, 1.0), 40.0, 25.0),     # cool night rim
    "NEUTRAL": ((1.0, 1.0, 1.0), 30.0, 20.0),    # daylight / overcast rim
}
STYLE_ITEMS = (
    ("STREET", "Street Lamp", "Warm hard light, as from a street lamp behind the rain"),
    ("MOON", "Moonlight", "Cool rim light from higher up"),
    ("NEUTRAL", "Neutral", "White rim light for daylight or overcast shots"),
)


def _target(camera: bpy.types.Object, emitter: bpy.types.Object | None) -> Vector:
    """Point in the rain the camera looks at: along the view axis, as far as the emitter."""
    cam = camera.matrix_world.translation
    fwd = (camera.matrix_world.to_quaternion() @ Vector((0.0, 0.0, -1.0))).normalized()
    if emitter is not None:
        d = (emitter.matrix_world.translation - cam).to_2d().length
    else:
        d = 10.0
    d = min(max(d, 4.0), 30.0)
    return cam + fwd * d


def create_backlight(scene: bpy.types.Scene, camera: bpy.types.Object, emitter: bpy.types.Object | None = None,
                     box=(16.0, 16.0, 10.0), style: str = "STREET", strength: float = 1.0) -> bpy.types.Object:
    color, elevation, azimuth = STYLES.get(style, STYLES["STREET"])
    target = _target(camera, emitter)
    distance = max(8.0, 0.8 * max(box[0], box[1]))
    loc, aim, _beam = P.backlight_placement(tuple(camera.matrix_world.translation), tuple(target),
                                            distance, azimuth_deg=azimuth, elevation_deg=elevation)
    ld = bpy.data.lights.get(LIGHT_NAME) or bpy.data.lights.new(LIGHT_NAME, "SPOT")
    ld.type = "SPOT"
    ld.color = color
    # about 3 W/m^2 at the aim point whatever the distance (P = E * 4 pi d^2)
    ld.energy = strength * 3.0 * 4.0 * math.pi * distance * distance
    half = 0.5 * math.hypot(box[0], box[1])
    ld.spot_size = min(math.radians(150.0), 2.0 * math.atan2(half, distance) * 1.2)
    ld.spot_blend = 0.4
    ld.shadow_soft_size = 0.1          # hard source: crisp streak highlights
    obj = bpy.data.objects.get(LIGHT_NAME)
    if obj is None:
        obj = bpy.data.objects.new(LIGHT_NAME, ld)
        em.ensure_collection(scene, em.ROOT_NAME).objects.link(obj)
    obj.data = ld
    obj.location = loc
    direction = Vector(aim) - Vector(loc)
    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = direction.to_track_quat("-Z", "Y")   # spots shine along -Z
    if hasattr(obj, "visible_camera"):
        obj.visible_camera = False     # never a bright disc in frame
    obj["rainfx_backlight"] = style
    return obj


def remove_backlight() -> bool:
    obj = bpy.data.objects.get(LIGHT_NAME)
    if obj is None:
        return False
    ld = obj.data
    bpy.data.objects.remove(obj, do_unlink=True)
    if ld is not None and ld.users == 0:
        bpy.data.lights.remove(ld)
    return True
