"""Blender version compatibility. Every API that changed between 4.2 and 5.2
is wrapped here so the rest of the add-on never branches on version numbers.

Changes handled (see docs/BLENDER_INTEGRATION.md):
* 5.2  Geometry Nodes modifier inputs moved from ``modifier[identifier]`` custom
       properties to ``modifier.properties.inputs.<identifier>.value``.
* 5.0  ``scene.node_tree`` removed -> ``scene.compositing_node_group``.
* 5.0  EEVEE engine id ``BLENDER_EEVEE_NEXT`` -> ``BLENDER_EEVEE``.
* 5.0  ``material.use_nodes`` / ``world.use_nodes`` deprecated (always True).
* 5.0  ``action.fcurves`` removed (slotted actions) -> keyframes via keyframe_insert.
"""
from __future__ import annotations

import bpy

VERSION = bpy.app.version
IS_5_0_PLUS = VERSION >= (5, 0, 0)
IS_5_2_PLUS = VERSION >= (5, 2, 0)


def eevee_engine_id() -> str:
    return "BLENDER_EEVEE" if IS_5_0_PLUS else "BLENDER_EEVEE_NEXT"


# ---------------------------------------------------------------- GN modifier IO
def socket_identifier(node_group: bpy.types.NodeTree, socket_name: str) -> str | None:
    for item in node_group.interface.items_tree:
        if item.item_type == "SOCKET" and item.in_out == "INPUT" and item.name == socket_name:
            return item.identifier
    return None


def set_modifier_input(mod: bpy.types.NodesModifier, socket_name: str, value) -> bool:
    """Set a Geometry Nodes group input on ``mod`` by *socket name*.

    Returns False (never raises) if the socket does not exist, so a preset can
    carry more keys than the installed node group version understands."""
    ng = mod.node_group
    if ng is None:
        return False
    ident = socket_identifier(ng, socket_name)
    if ident is None:
        return False
    props = getattr(mod, "properties", None) if IS_5_2_PLUS else None
    if props is not None:
        try:
            getattr(props.inputs, ident).value = value
            return True
        except (AttributeError, TypeError, KeyError):
            pass  # fall through to the legacy path
    try:
        mod[ident] = value
        # Make sure the viewport refreshes (legacy path does not always tag the depsgraph).
        mod.id_data.update_tag()
        return True
    except (TypeError, KeyError):
        return False


def get_modifier_input(mod: bpy.types.NodesModifier, socket_name: str, default=None):
    ng = mod.node_group
    ident = socket_identifier(ng, socket_name) if ng else None
    if ident is None:
        return default
    props = getattr(mod, "properties", None) if IS_5_2_PLUS else None
    if props is not None:
        try:
            return getattr(props.inputs, ident).value
        except (AttributeError, KeyError):
            pass
    try:
        return mod[ident]
    except KeyError:
        return default


# --------------------------------------------------------------------- materials
def new_material(name: str) -> bpy.types.Material:
    mat = bpy.data.materials.new(name)
    if not IS_5_0_PLUS:
        mat.use_nodes = True  # creates default Principled; deprecated no-op from 5.0
    return mat


# ------------------------------------------------------------------- compositing
def get_compositing_tree(scene: bpy.types.Scene, create: bool = False):
    """Return the scene compositing node tree (or None).

    5.0+: ``scene.compositing_node_group`` (a node group of type CompositorNodeTree).
    <5.0: ``scene.node_tree`` guarded by ``scene.use_nodes``."""
    if IS_5_0_PLUS:
        tree = scene.compositing_node_group
        if tree is None and create:
            tree = bpy.data.node_groups.new("RainFX Post", "CompositorNodeTree")
            scene.compositing_node_group = tree
        return tree
    if create and not scene.use_nodes:
        scene.use_nodes = True
    return scene.node_tree if scene.use_nodes else None


# ------------------------------------------------------------------- misc helpers
def user_dir() -> str:
    """Per-user writable directory for RainFX (user presets). Extension-aware."""
    pkg = __package__ or "rainfx"
    try:
        return bpy.utils.extension_path_user(pkg, path="presets", create=True)
    except Exception:
        import os
        path = os.path.join(bpy.utils.user_resource("CONFIG"), "rainfx_presets")
        os.makedirs(path, exist_ok=True)
        return path
