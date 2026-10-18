"""Procedural materials. Created lazily and reused by name.

All inputs are set by socket *name* on the Principled BSDF (stable since 4.0:
``Transmission Weight``, ``Subsurface Weight``, ``Emission Color``).
"""
from __future__ import annotations

import bpy

from .. import compat

KINDS = ("water", "ice", "snow", "splash", "dew")


def _principled(mat: bpy.types.Material):
    for n in mat.node_tree.nodes:
        if n.type == "BSDF_PRINCIPLED":
            return n
    return mat.node_tree.nodes.new("ShaderNodeBsdfPrincipled")


def _set(node, **vals):
    for k, v in vals.items():
        key = k.replace("_", " ")
        if key in node.inputs:
            node.inputs[key].default_value = v


def get_material(kind: str) -> bpy.types.Material:
    name = f"RainFX {kind.capitalize()}"
    mat = bpy.data.materials.get(name)
    if mat is not None:
        return mat
    mat = compat.new_material(name)
    bsdf = _principled(mat)
    if kind == "water":      # thin streaks: translucent, faintly bluish, alpha blended
        _set(bsdf, Base_Color=(0.85, 0.92, 1.0, 1.0), Roughness=0.05, IOR=1.33, Alpha=0.22,
             Transmission_Weight=0.6)
    elif kind == "splash":
        _set(bsdf, Base_Color=(0.9, 0.95, 1.0, 1.0), Roughness=0.05, IOR=1.33, Alpha=0.5,
             Transmission_Weight=0.8)
    elif kind == "ice":
        _set(bsdf, Base_Color=(0.9, 0.96, 1.0, 1.0), Roughness=0.15, IOR=1.31, Alpha=0.9,
             Transmission_Weight=0.7)
    elif kind == "snow":
        _set(bsdf, Base_Color=(0.97, 0.98, 1.0, 1.0), Roughness=0.9, Alpha=0.95,
             Subsurface_Weight=0.25)
    elif kind == "dew":
        _set(bsdf, Base_Color=(1.0, 1.0, 1.0, 1.0), Roughness=0.0, IOR=1.33,
             Transmission_Weight=1.0)
    if hasattr(mat, "surface_render_method"):       # EEVEE (4.2+)
        mat.surface_render_method = "BLENDED" if kind in ("water", "splash") else "DITHERED"
    return mat


def material_for_mode(material_kind: str) -> tuple[bpy.types.Material, bpy.types.Material]:
    """(drop material, splash material) for a preset's ``material`` field."""
    return get_material(material_kind), get_material("splash")
