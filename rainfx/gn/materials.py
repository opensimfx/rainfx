"""Procedural materials. Created lazily and reused by name.

All inputs are set by socket *name* on the Principled BSDF (stable since 4.0:
``Transmission Weight``, ``Subsurface Weight``, ``Emission Color``).
"""
from __future__ import annotations

import bpy

from .. import compat

KINDS = ("water", "drop", "ice", "snow", "splash", "dew", "distant")


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
    if kind == "water":      # streaks: faint glassy core so thin volumes self-shade
        _set(bsdf, Base_Color=(0.87, 0.93, 1.0, 1.0), Roughness=0.0, IOR=1.33, Alpha=0.18,
             Transmission_Weight=0.9, Emission_Color=(0.37, 0.42, 0.5, 1.0), Emission_Strength=0.03)
    elif kind == "drop":     # close-up variant: real refraction, no fake transparency
        _set(bsdf, Base_Color=(0.95, 0.98, 1.0, 1.0), Roughness=0.01, IOR=1.33, Alpha=1.0,
             Transmission_Weight=1.0)
    elif kind == "splash":
        _set(bsdf, Base_Color=(0.9, 0.95, 1.0, 1.0), Roughness=0.02, IOR=1.33, Alpha=0.45,
             Transmission_Weight=0.85, Emission_Color=(0.45, 0.5, 0.58, 1.0), Emission_Strength=0.04)
    elif kind == "ice":      # hail/pellets: milky fracture look
        _set(bsdf, Base_Color=(0.92, 0.97, 1.0, 1.0), Roughness=0.12, IOR=1.31, Alpha=0.82,
             Transmission_Weight=0.7)
    elif kind == "snow":
        _set(bsdf, Base_Color=(0.985, 0.99, 1.0, 1.0), Roughness=0.95, Alpha=1.0,
             Subsurface_Weight=0.32, Subsurface_Radius=(0.06, 0.09, 0.11))
    elif kind == "dew":
        _set(bsdf, Base_Color=(1.0, 1.0, 1.0, 1.0), Roughness=0.0, IOR=1.33,
             Transmission_Weight=1.0)
    elif kind == "distant":  # far-field streak wall: flat and translucent,
        # no transmission - thousands of instances must stay EEVEE-cheap
        _set(bsdf, Base_Color=(0.87, 0.92, 1.0, 1.0), Roughness=0.4, Alpha=0.35,
             Emission_Color=(0.45, 0.5, 0.6, 1.0), Emission_Strength=0.05)
    if hasattr(mat, "surface_render_method"):       # EEVEE (4.2+)
        mat.surface_render_method = "BLENDED" if kind in ("water", "splash", "drop", "distant") else "DITHERED"
    return mat


def material_for_mode(material_kind: str) -> tuple[bpy.types.Material, bpy.types.Material]:
    """(drop material, splash material) for a preset's ``material`` field."""
    return get_material(material_kind), get_material("splash")


def wire_wetness(mat: bpy.types.Material) -> bool:
    """Link the per-face "rainfx_wet"/"rainfx_pool" attributes into a material.

    Wet/pool look (5.2 Principled has no 'Wet Amount'): Base Color pulled
    toward a dark pool colour and roughness pulled down wherever max(wet,
    pool) rises (the classic wet-surface cue); pooled faces also get a
    procedural ripple bump (noise texture, Object coords, W sampled along a
    frame-driven value so the pattern drifts). The per-vertex "rainfx_snow"
    attribute then mixes a snow-cover white IN OVER the wet look (snow
    wins) and lifts roughness instead of lowering it. Idempotent (tagged
    with a custom prop); the wiring stays when wetness is toggled off since
    a zero attribute is a no-op.
    """
    if mat is None or mat.get("rainfx_wet") or not mat.use_nodes:
        return False
    nt = mat.node_tree
    bsdf = _principled(mat)
    rough0 = bsdf.inputs["Roughness"].default_value
    if rough0 > 0.85:                        # fully matte surfaces barely change
        rough0 = 0.85
    attr = nt.nodes.new("ShaderNodeAttribute")
    attr.attribute_name = "rainfx_wet"
    attr.location = (bsdf.location.x - 400, bsdf.location.y - 120)
    wet = attr.outputs["Fac"]
    pattr = nt.nodes.new("ShaderNodeAttribute")   # standing-water mask
    pattr.attribute_name = "rainfx_pool"
    pattr.location = (attr.location.x, attr.location.y - 160)
    pool = pattr.outputs["Fac"]
    cf = nt.nodes.new("ShaderNodeMath")           # shared look factor
    cf.operation = "MAXIMUM"
    cf.location = (attr.location.x + 160, attr.location.y + 20)
    nt.links.new(wet, cf.inputs[0])
    nt.links.new(pool, cf.inputs[1])
    look = cf.outputs[0]
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"                   # wet faces sink to a dark pool colour
    mix.inputs[6].default_value = tuple(bsdf.inputs["Base Color"].default_value)
    mix.inputs[7].default_value = (0.05, 0.06, 0.07, 1.0)
    mix.location = (attr.location.x + 200, attr.location.y + 60)
    nt.links.new(look, mix.inputs[0])
    # ...snow cover stacked AFTER water: snow wins over dark pool shading
    sattr = nt.nodes.new("ShaderNodeAttribute")  # per-vertex snow accumulation
    sattr.attribute_name = "rainfx_snow"
    sattr.location = (attr.location.x, attr.location.y - 320)
    snow = sattr.outputs["Fac"]
    smix = nt.nodes.new("ShaderNodeMix")
    smix.data_type = "RGBA"
    smix.inputs[7].default_value = (0.93, 0.95, 1.0, 1.0)  # snow-cover white
    smix.location = (mix.location.x + 220, mix.location.y + 40)
    nt.links.new(mix.outputs[2], smix.inputs[6])
    nt.links.new(snow, smix.inputs[0])
    nt.links.new(smix.outputs[2], bsdf.inputs["Base Color"])
    dark = nt.nodes.new("ShaderNodeMath")
    dark.operation = "MULTIPLY"
    dark.inputs[1].default_value = 0.85      # rough = rough0 * (1 - 0.85 * look)
    dark.location = (attr.location.x + 180, attr.location.y - 60)
    nt.links.new(look, dark.inputs[0])
    rem = nt.nodes.new("ShaderNodeMath")
    rem.operation = "SUBTRACT"
    rem.inputs[0].default_value = 1.0
    rem.location = (dark.location.x + 160, attr.location.y - 60)
    nt.links.new(dark.outputs[0], rem.inputs[1])
    rough = nt.nodes.new("ShaderNodeMath")
    rough.operation = "MULTIPLY"
    rough.inputs[0].default_value = rough0
    rough.location = (rem.location.x + 160, attr.location.y - 60)
    nt.links.new(rem.outputs[0], rough.inputs[1])
    # roughness LIFTS under snow: wet-chain rough + 0.5*snow, clamped
    sru = nt.nodes.new("ShaderNodeMath")
    sru.operation = "MULTIPLY"
    sru.inputs[1].default_value = 0.5
    sru.location = (attr.location.x + 240, attr.location.y - 140)
    nt.links.new(snow, sru.inputs[0])
    sra = nt.nodes.new("ShaderNodeMath")
    sra.operation = "ADD"
    sra.location = (sru.location.x + 160, attr.location.y - 140)
    nt.links.new(rough.outputs[0], sra.inputs[0])
    nt.links.new(sru.outputs[0], sra.inputs[1])
    sc = nt.nodes.new("ShaderNodeMath")
    sc.operation = "MINIMUM"
    sc.inputs[1].default_value = 1.0
    sc.location = (sra.location.x + 160, attr.location.y - 140)
    nt.links.new(sra.outputs[0], sc.inputs[0])
    nt.links.new(sc.outputs[0], bsdf.inputs["Roughness"])

    # ripple bump on pooled faces (noise pattern drifts with the frame driver)
    txco = nt.nodes.new("ShaderNodeTexCoord")
    txco.location = (bsdf.location.x - 640, bsdf.location.y - 260)
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 40.0
    noise.location = (txco.location.x + 360, txco.location.y)
    tval = nt.nodes.new("ShaderNodeValue")
    tval.location = (txco.location.x, txco.location.y + 140)
    tval.label = "RainFX time"
    drv = tval.outputs["Value"].driver_add("default_value")
    drv.driver.expression = "frame"
    drift = nt.nodes.new("ShaderNodeVectorMath")
    drift.operation = "ADD"
    drift.location = (tval.location.x + 180, txco.location.y + 60)
    b = nt.nodes.new("ShaderNodeCombineXYZ")  # 5.2 noise W socket is disabled
    b.location = (tval.location.x + 60, txco.location.y + 160)
    nt.links.new(tval.outputs["Value"], b.inputs["X"])
    nt.links.new(txco.outputs["Object"], drift.inputs[0])
    nt.links.new(b.outputs[0], drift.inputs[1])
    nt.links.new(drift.outputs[0], noise.inputs["Vector"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.15
    bump.location = (noise.location.x + 180, noise.location.y)
    nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    bst = nt.nodes.new("ShaderNodeMath")
    bst.operation = "MULTIPLY"               # bump only where water pools
    bst.inputs[1].default_value = 0.15
    bst.location = (bump.location.x, bump.location.y - 140)
    nt.links.new(pool, bst.inputs[0])
    nt.links.new(bst.outputs[0], bump.inputs["Strength"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    mat["rainfx_wet"] = True
    return True
