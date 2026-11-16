"""RainFX - physically based weather for Blender (rain, hail, snow, dew).

Package layout and design: see docs/SYSTEM_DESIGN.md
"""
# NOTE: keep this module free of top-level bpy imports. rainfx.core must stay importable
# (and unit-testable) in a plain Python interpreter.


def register():
    from .scene import watch, wetness
    from .ui import ops, panels, props
    props.register()
    ops.register()
    panels.register()
    wetness.register()
    watch.register()


def unregister():
    from .scene import baker, watch, wetness
    from .ui import ops, panels, props
    # disabling or updating mid-bake: stop the child Blender and the progress
    # timer, which would otherwise fire into the unloaded add-on
    baker.stop()
    if bpy_timer_registered(ops._bg_tick):
        import bpy
        bpy.app.timers.unregister(ops._bg_tick)
    wetness.unregister()
    watch.unregister()
    panels.unregister()
    ops.unregister()
    props.unregister()


def bpy_timer_registered(fn) -> bool:
    import bpy
    return bpy.app.timers.is_registered(fn)
