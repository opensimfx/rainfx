"""RainFX - physically based weather for Blender (rain, hail, snow, dew).

Package layout and design: see docs/SYSTEM_DESIGN.md
"""
# NOTE: keep this module free of top-level bpy imports. rainfx.core must stay importable
# (and unit-testable) in a plain Python interpreter.


def register():
    from .ui import ops, panels, props
    props.register()
    ops.register()
    panels.register()


def unregister():
    from .ui import ops, panels, props
    panels.unregister()
    ops.unregister()
    props.unregister()
