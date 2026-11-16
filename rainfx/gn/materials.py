"""Procedural materials. Created lazily and reused by name.

All inputs are set by socket *name* on the Principled BSDF (stable since 4.0:
``Transmission Weight``, ``Subsurface Weight``, ``Emission Color``).
"""
from __future__ import annotations

import bpy

from .. import compat
from ..core import physics as P

KINDS = ("water", "drop", "ice", "snow", "splash", "dew", "distant", "near")


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


MATERIAL_VERSION = 3   # 3 (1.0): streaks are translucent + Fresnel gloss (lit from behind, not diffuse), snow 35 % translucent; 2 (0.4): no emission, alpha jitter

# Principled values per kind. Rain is NOT self-lit: a drop shows the refracted
# surroundings (Garg & Nayar: ~94 % refracted, 6 % reflected at the rim), so in a
# dark scene rain is only seen where a light sits behind it (rainfx.add_backlight).
# Streaks use ROUGH transmission (0.35): a streak is one drop smeared over the
# exposure, so its refraction is blurred, and a lamp behind the rain can only
# glint through glossy (not perfectly sharp) refraction in Cycles. Rendered
# with roughness 0 the backlight lit the fog but not a single streak.
_VALUES = {
    "water": dict(Base_Color=(0.87, 0.93, 1.0, 1.0), Roughness=0.35, IOR=1.33, Alpha=0.18,
                  Transmission_Weight=0.9, Emission_Strength=0.0),
    "drop": dict(Base_Color=(0.95, 0.98, 1.0, 1.0), Roughness=0.01, IOR=1.33, Alpha=1.0,
                 Transmission_Weight=1.0),
    "splash": dict(Base_Color=(0.9, 0.95, 1.0, 1.0), Roughness=0.2, IOR=1.33, Alpha=0.45,
                   Transmission_Weight=0.85, Emission_Strength=0.0),
    "ice": dict(Base_Color=(0.92, 0.97, 1.0, 1.0), Roughness=0.12, IOR=1.31, Alpha=0.82,
                Transmission_Weight=0.7),
    "snow": dict(Base_Color=(0.985, 0.99, 1.0, 1.0), Roughness=0.95, Alpha=1.0,
                 Subsurface_Weight=0.32, Subsurface_Radius=(0.06, 0.09, 0.11)),
    "dew": dict(Base_Color=(1.0, 1.0, 1.0, 1.0), Roughness=0.0, IOR=1.33, Transmission_Weight=1.0),
    # far-field streak wall: flat and translucent, no transmission (EEVEE-cheap)
    "distant": dict(Base_Color=(0.87, 0.92, 1.0, 1.0), Roughness=0.4, Alpha=0.35, Emission_Strength=0.0),
    # foreground layer: wide, faint, blurry refraction - a near drop seen out of focus
    "near": dict(Base_Color=(0.9, 0.95, 1.0, 1.0), Roughness=0.5, IOR=1.33, Alpha=0.1,
                 Transmission_Weight=0.9, Emission_Strength=0.0),
}
# Streak-family kinds get their own shader instead of the Principled BSDF:
#   Mix(Transparent, Mix(Translucent, Glossy, Fresnel(1.33)), alpha)
# A raindrop shows a wide (~165 deg) view of what lies behind it, plus a weak
# specular rim (Garg & Nayar). Translucent gathers exactly that: light from the
# hemisphere behind the streak. So rain blazes with a lamp behind it, reads bright
# against dark walls by day (it passes on the bright sky behind and above) and
# vanishes against the sky itself, the way it does on film. The Principled
# version had 10% white diffuse, which lit every streak from every side and made
# rain look like a flat overlay.
_STREAK_KINDS = ("water", "splash", "distant", "near")
_GLOSS = {"water": 0.12, "splash": 0.08, "distant": 0.3, "near": 0.35}


def _build_streak(mat, kind: str) -> None:
    nt = mat.node_tree
    nt.nodes.clear()
    vals = _VALUES[kind]
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    tr = nt.nodes.new("ShaderNodeBsdfTranslucent")
    tr.inputs["Color"].default_value = vals["Base_Color"]
    gl = nt.nodes.new("ShaderNodeBsdfGlossy")
    gl.inputs["Roughness"].default_value = _GLOSS[kind]
    fr = nt.nodes.new("ShaderNodeFresnel")
    fr.inputs["IOR"].default_value = 1.33
    body = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(fr.outputs["Fac"], body.inputs[0])
    nt.links.new(tr.outputs[0], body.inputs[1])
    nt.links.new(gl.outputs[0], body.inputs[2])
    clear = nt.nodes.new("ShaderNodeBsdfTransparent")
    final = nt.nodes.new("ShaderNodeMixShader")
    final["rainfx_streak_mix"] = True
    nt.links.new(clear.outputs[0], final.inputs[1])
    nt.links.new(body.outputs[0], final.inputs[2])
    nt.links.new(final.outputs[0], out.inputs["Surface"])
    for i, n in enumerate((tr, gl, fr, body, clear, final, out)):
        n.location = (-600 + 170 * i, 0 if i % 2 else -180)
    alpha = _streak_alpha_chain(mat, vals.get("Alpha", 1.0))
    nt.links.new(alpha, final.inputs[0])


def _streak_alpha_chain(mat, alpha0: float):
    """alpha0 * per-instance jitter (0.6-1.4) * Fresnel rim (0.75-1.5), clamped.

    Real streaks differ in brightness (drop size, oscillation phase) and a
    drop transmits at its centre but reflects at its rim, so a uniform alpha
    reads as plastic rods. Object Info Random is unique per GN instance.
    """
    nt = mat.node_tree
    info = nt.nodes.new("ShaderNodeObjectInfo")
    jit = nt.nodes.new("ShaderNodeMath")
    jit.operation = "MULTIPLY_ADD"                 # rand * 0.8 + 0.6
    jit.inputs[1].default_value = 0.8
    jit.inputs[2].default_value = 0.6
    nt.links.new(info.outputs["Random"], jit.inputs[0])
    fres = nt.nodes.new("ShaderNodeFresnel")
    fres.inputs["IOR"].default_value = 1.33
    rim = nt.nodes.new("ShaderNodeMath")
    rim.operation = "MULTIPLY_ADD"                 # F * 0.75 + 0.75
    rim.inputs[1].default_value = 0.75
    rim.inputs[2].default_value = 0.75
    nt.links.new(fres.outputs["Fac"], rim.inputs[0])
    m1 = nt.nodes.new("ShaderNodeMath")
    m1.operation = "MULTIPLY"
    nt.links.new(jit.outputs[0], m1.inputs[0])
    nt.links.new(rim.outputs[0], m1.inputs[1])
    m2 = nt.nodes.new("ShaderNodeMath")
    m2.operation = "MULTIPLY"
    m2.use_clamp = True
    m2.inputs[1].default_value = alpha0
    m2["rainfx_streak_alpha_out"] = True
    nt.links.new(m1.outputs[0], m2.inputs[0])
    for i, n in enumerate((info, fres, jit, rim, m1, m2)):
        n.location = (-1500 + 150 * i, -420 - (i % 2) * 160)
        n["rainfx_streak_alpha"] = True
    return m2.outputs[0]


def _build_snow(mat) -> None:
    """Principled snow (white, rough, subsurface) mixed 35 % with Translucent.

    A flake is a thin aggregate of ice crystals: it scatters light through
    itself, so it glows when a lamp or bright sky is behind it instead of
    reading as an opaque grey speck.
    """
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    _set(bsdf, **_VALUES["snow"])
    tr = nt.nodes.new("ShaderNodeBsdfTranslucent")
    tr.inputs["Color"].default_value = (0.97, 0.98, 1.0, 1.0)
    mix = nt.nodes.new("ShaderNodeMixShader")
    mix.inputs[0].default_value = SNOW_TRANSLUCENCY
    nt.links.new(bsdf.outputs[0], mix.inputs[1])
    nt.links.new(tr.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    for i, n in enumerate((bsdf, tr, mix, out)):
        n.location = (-600 + 300 * i, 0)


SNOW_TRANSLUCENCY = 0.35


def _apply_kind(mat, kind: str) -> None:
    if kind in _STREAK_KINDS:
        _build_streak(mat, kind)
    elif kind == "snow":
        _build_snow(mat)
    else:
        bsdf = _principled(mat)
        _set(bsdf, **_VALUES.get(kind, {}))
    if hasattr(mat, "surface_render_method"):       # EEVEE (4.2+)
        mat.surface_render_method = "BLENDED" if kind in ("water", "splash", "drop", "distant", "near") else "DITHERED"
    mat["rainfx_mat_version"] = MATERIAL_VERSION


def get_material(kind: str) -> bpy.types.Material:
    """RainFX material for ``kind``; created once, upgraded in place when an
    older RainFX version made it (values are reset to the current look)."""
    name = f"RainFX {kind.capitalize()}"
    mat = bpy.data.materials.get(name)
    if mat is not None:
        if mat.get("rainfx_mat_version", 1) < MATERIAL_VERSION and mat.use_nodes:
            _apply_kind(mat, kind)
        return mat
    mat = compat.new_material(name)
    _apply_kind(mat, kind)
    return mat


def material_for_mode(material_kind: str) -> tuple[bpy.types.Material, bpy.types.Material]:
    """(drop material, splash material) for a preset's ``material`` field."""
    return get_material(material_kind), get_material("splash")


WET_VERSION = 3   # 3 (1.0): wet roughness tends to the water film's 0.18; 2 (0.4): porosity darkening, puddle normals, ring ripples
WET_FILM_ROUGHNESS = 0.18

PUDDLE_SCALE = 0.5        # noise scale of the puddle height map (features ~2 m across)

RIPPLES_NAME = "RainFX Ripples"
RIPPLES_VERSION = 1
RIPPLE_CELL_M = 0.25      # one ring per cell and layer per cycle; rings reach half a cell
RIPPLE_DEPTH_M = 0.0008   # bump height of a ring crest
# Lagarde, "Water drop 2b": four ring layers, time multipliers and offsets, x1.6 speed
_RIPPLE_LAYERS = ((1.0, 0.0), (0.85, 0.2), (0.93, 0.45), (1.13, 0.7))
_RIPPLE_SPEED = 1.6


def ensure_ripples_group(scene: bpy.types.Scene | None = None) -> bpy.types.NodeTree:
    """Shader group "RainFX Ripples": Height of procedural rain rings on water.

    Per layer i (Lagarde 2b): Voronoi cells in world XY (one cell per
    RIPPLE_CELL_M), x = 1 - distance / half a cell, a random phase per cell,
    drop = fract(phase + t * 1.6 * mult_i), height = clamp(0.2 + 0.8 W - drop)
    * x * sin(clamp((drop - 1 + x) * 9, 0, 3) * pi): a ring of 1.5 waves runs
    outward and fades as it ages. Layer i only shows when 4 W > i, so light rain
    has one sparse layer and a downpour all four. W is the "Weight" value node
    inside the group (set_ripple_weight); time comes from a frame / fps driver.
    """
    ng = bpy.data.node_groups.get(RIPPLES_NAME)
    if ng is not None and ng.get("rainfx_version") == RIPPLES_VERSION:
        return ng
    if ng is None:
        ng = bpy.data.node_groups.new(RIPPLES_NAME, "ShaderNodeTree")
    else:
        ng.nodes.clear()
        for item in list(ng.interface.items_tree):
            ng.interface.remove(item)
    ng["rainfx_version"] = RIPPLES_VERSION
    ng.interface.new_socket("Height", in_out="OUTPUT", socket_type="NodeSocketFloat")
    nodes, links = ng.nodes, ng.links
    out = nodes.new("NodeGroupOutput")
    out.location = (1800, 0)

    def math(op, a, b=None, c=None, clamp=False, loc=(0, 0)):
        n = nodes.new("ShaderNodeMath")
        n.operation = op
        n.use_clamp = clamp
        n.location = loc
        for i, v in enumerate((a, b, c)):
            if v is None:
                continue
            if isinstance(v, (int, float)):
                n.inputs[i].default_value = v
            else:
                links.new(v, n.inputs[i])
        return n.outputs[0]

    t = nodes.new("ShaderNodeValue")
    t.label = "Time (s)"
    t.location = (-1400, 300)
    drv = t.outputs[0].driver_add("default_value").driver
    sc = scene or bpy.context.scene
    if sc is not None:
        var = drv.variables.new()
        var.name = "fps"
        var.type = "SINGLE_PROP"
        var.targets[0].id_type = "SCENE"
        var.targets[0].id = sc
        var.targets[0].data_path = "render.fps"
        drv.expression = "frame / max(fps, 1)"
    else:
        drv.expression = "frame / 24"
    w = nodes.new("ShaderNodeValue")
    w.label = "Weight"
    w["rainfx_ripple_weight"] = True
    w.outputs[0].default_value = 0.5
    w.location = (-1400, 100)
    geo = nodes.new("ShaderNodeNewGeometry")
    geo.location = (-1400, -100)
    cell = nodes.new("ShaderNodeVectorMath")
    cell.operation = "SCALE"
    cell.inputs[3].default_value = 1.0 / RIPPLE_CELL_M
    cell.location = (-1220, -100)
    links.new(geo.outputs["Position"], cell.inputs[0])
    fade_base = math("MULTIPLY_ADD", w.outputs[0], 0.8, 0.2, loc=(-1220, 100))  # 0.2 + 0.8 W
    total = None
    for i, (mult, off) in enumerate(_RIPPLE_LAYERS):
        y = -300 * i
        sh = nodes.new("ShaderNodeVectorMath")
        sh.operation = "ADD"
        sh.inputs[1].default_value = (off, off * 0.7, 0.0)
        sh.location = (-1040, y)
        links.new(cell.outputs[0], sh.inputs[0])
        vor = nodes.new("ShaderNodeTexVoronoi")
        vor.voronoi_dimensions = "2D"
        vor.feature = "F1"
        vor.location = (-880, y)
        vor.inputs["Scale"].default_value = 1.0
        links.new(sh.outputs[0], vor.inputs["Vector"])
        sepc = nodes.new("ShaderNodeSeparateColor")
        sepc.location = (-700, y - 120)
        links.new(vor.outputs["Color"], sepc.inputs[0])
        x = math("MULTIPLY_ADD", vor.outputs["Distance"], -2.0, 1.0, clamp=True, loc=(-700, y))
        tt = math("MULTIPLY", t.outputs[0], _RIPPLE_SPEED * mult, loc=(-540, y + 80))
        drop = math("FRACT", math("ADD", sepc.outputs[0], tt, loc=(-380, y + 80)), loc=(-220, y + 80))
        tfrac = math("ADD", math("SUBTRACT", drop, 1.0, loc=(-60, y + 80)), x, loc=(100, y + 80))
        wave = math("SINE", math("MULTIPLY", math("MINIMUM", math("MAXIMUM", math(
            "MULTIPLY", tfrac, 9.0, loc=(260, y + 80)), 0.0, loc=(420, y + 80)), 3.0, loc=(580, y + 80)),
            3.141592653589793, loc=(740, y + 80)), loc=(900, y + 80))
        fade = math("SUBTRACT", fade_base, drop, clamp=True, loc=(100, y - 80))
        h = math("MULTIPLY", math("MULTIPLY", fade, x, loc=(900, y - 80)), wave, loc=(1060, y))
        lw = math("MULTIPLY_ADD", w.outputs[0], 4.0, float(-i), clamp=True, loc=(1060, y - 140))
        h = math("MULTIPLY", h, lw, loc=(1220, y))
        total = h if total is None else math("ADD", total, h, loc=(1400, y))
    links.new(total, out.inputs["Height"])
    return ng


def set_ripple_weight(weight: float) -> bool:
    """Ring-ripple intensity 0..1 (physics.ripple_weight of the rain rate) for every
    wet material at once; False when no material uses ripples yet."""
    ng = bpy.data.node_groups.get(RIPPLES_NAME)
    if ng is None:
        return False
    for n in ng.nodes:
        if n.get("rainfx_ripple_weight"):
            n.outputs[0].default_value = min(max(weight, 0.0), 1.0)
            return True
    return False


def _source(nt, socket, node_type, value):
    """Output socket currently feeding ``socket``, or a constant node holding
    its default value. Keeps textured materials textured when wetness is wired."""
    if socket.is_linked:
        return socket.links[0].from_socket
    n = nt.nodes.new(node_type)
    if node_type == "ShaderNodeRGB":
        n.outputs[0].default_value = tuple(value)
    else:
        n.outputs[0].default_value = value
    return n.outputs[0]


def wire_wetness(mat: bpy.types.Material) -> bool:
    """Link the per-face "rainfx_wet"/"rainfx_pool" attributes into a material.

    Wet look after Lagarde ("Water drop 3a/3b", physically based wet surfaces):

    * albedo x lerp(1, 0.2 x porosity, wetness) - darker but the same hue;
      porosity from roughness and metalness (smooth or metal surfaces don't
      darken, rough stone and asphalt do);
    * roughness -> lerp(rough, min(rough, 0.18), wet) x (1 - 0.95 pool) - a
      water film fills the surface texture (long light streaks on wet
      asphalt), standing water is a near mirror (water F0 0.02 comes from the
      Principled IOR);
    * standing water fills the low spots of a world-space noise height map
      first (Lagarde's flood level), so puddles have organic edges on any
      mesh, and high spots dry first;
    * pooled faces drop the material's normal map toward the flat surface
      normal and get ring ripples (shared "RainFX Ripples" group; rings only
      where water stands, more of them in heavier rain).

    Linked Base Color / Roughness / Normal inputs (textures) are kept and fed
    through the chain. The per-vertex "rainfx_snow" attribute then mixes a
    snow-cover white IN OVER the wet look (snow wins) and lifts roughness.
    Idempotent (tagged with a custom prop); the wiring stays when wetness is
    toggled off since a zero attribute is a no-op.
    """
    if mat is None or mat.get("rainfx_wet") or not mat.use_nodes:
        return False
    nt = mat.node_tree
    bsdf = _principled(mat)
    x0, y0 = bsdf.location.x - 400, bsdf.location.y - 120
    base_in, rough_in, norm_in = bsdf.inputs["Base Color"], bsdf.inputs["Roughness"], bsdf.inputs["Normal"]
    rough_est = 0.7 if rough_in.is_linked else rough_in.default_value
    metal_in = bsdf.inputs.get("Metallic")
    metal_est = 0.0 if metal_in is None or metal_in.is_linked else metal_in.default_value
    darken = 1.0 - P.wet_albedo_factor(P.wet_porosity(rough_est, metal_est))  # 0 .. 0.8

    albedo = _source(nt, base_in, "ShaderNodeRGB", base_in.default_value)
    rough_src = _source(nt, rough_in, "ShaderNodeValue", rough_in.default_value)
    norm_src = norm_in.links[0].from_socket if norm_in.is_linked else None

    def node(t, loc, **props):
        n = nt.nodes.new(t)
        n.location = loc
        for k, v in props.items():
            setattr(n, k, v)
        return n

    def math(op, a, b, loc, c=None):
        n = node("ShaderNodeMath", loc, operation=op)
        for i, v in enumerate((a, b) if c is None else (a, b, c)):
            if isinstance(v, (int, float)):
                n.inputs[i].default_value = v
            else:
                nt.links.new(v, n.inputs[i])
        return n.outputs[0]

    wet_a = node("ShaderNodeAttribute", (x0 - 400, y0), attribute_name="rainfx_wet").outputs["Fac"]
    pool_a = node("ShaderNodeAttribute", (x0 - 400, y0 - 160), attribute_name="rainfx_pool").outputs["Fac"]
    snow = node("ShaderNodeAttribute", (x0, y0 - 320), attribute_name="rainfx_snow").outputs["Fac"]

    # puddle shape (Lagarde 3b flood level): a world-space noise "height map" h;
    # standing water fills the low spots first, puddle = (1.2 pool - h) / 0.15,
    # so puddles get organic edges whatever the mesh resolution; high spots also
    # dry first (convex before concave): wet = 1.3 wet - 0.3 h
    pos = node("ShaderNodeNewGeometry", (x0 - 760, y0 - 360))
    hn = node("ShaderNodeTexNoise", (x0 - 600, y0 - 360))
    hn.inputs["Scale"].default_value = PUDDLE_SCALE
    hn.inputs["Detail"].default_value = 3.0
    hn.inputs["Roughness"].default_value = 0.55
    nt.links.new(pos.outputs["Position"], hn.inputs["Vector"])
    hmap = node("ShaderNodeMapRange", (x0 - 420, y0 - 360))
    hmap.inputs["From Min"].default_value = 0.3
    hmap.inputs["From Max"].default_value = 0.7
    nt.links.new(hn.outputs["Fac"], hmap.inputs["Value"])
    h = hmap.outputs["Result"]
    level = math("SUBTRACT", math("MULTIPLY", pool_a, 1.2, (x0 - 240, y0 - 200)), h, (x0 - 120, y0 - 200))
    pool = math("MULTIPLY", level, 1.0 / 0.15, (x0 - 20, y0 - 160))
    pool.node.use_clamp = True
    wet = math("MULTIPLY_ADD", h, -0.3, (x0 - 20, y0), math("MULTIPLY", wet_a, 1.3, (x0 - 240, y0 + 40)))
    wet.node.use_clamp = True
    look = math("MAXIMUM", wet, pool, (x0 + 160, y0 + 20))

    # albedo * (1 - look * darken): Mix MULTIPLY with black B gives A * (1 - fac)
    mix = node("ShaderNodeMix", (x0 + 200, y0 + 60), data_type="RGBA", blend_type="MULTIPLY")
    nt.links.new(math("MULTIPLY", look, darken, (x0 + 180, y0 + 140)), mix.inputs[0])
    nt.links.new(albedo, mix.inputs[6])
    mix.inputs[7].default_value = (0.0, 0.0, 0.0, 1.0)
    # ...snow cover stacked AFTER water: snow wins over the wet look
    smix = node("ShaderNodeMix", (x0 + 420, y0 + 100), data_type="RGBA")
    smix.inputs[7].default_value = (0.93, 0.95, 1.0, 1.0)  # snow-cover white
    nt.links.new(mix.outputs[2], smix.inputs[6])
    nt.links.new(snow, smix.inputs[0])
    nt.links.new(smix.outputs[2], base_in)

    # a water film fills the surface texture: wet roughness tends to the film's
    # own (WET_FILM_ROUGHNESS) whatever the dry value, which is what smears
    # street lamps into long streaks on wet asphalt; smoother stays smoother
    film_r = math("MINIMUM", rough_src, WET_FILM_ROUGHNESS, (x0 + 20, y0 - 60))
    r = math("MULTIPLY_ADD", math("SUBTRACT", film_r, rough_src, (x0 + 180, y0 - 20)), wet,
             (x0 + 340, y0 - 60), rough_src)                                # lerp(rough, film, wet)
    mirror = math("MULTIPLY_ADD", pool, -0.95, (x0 + 180, y0 - 200), 1.0)  # 1 - 0.95 pool
    r = math("MULTIPLY", r, mirror, (x0 + 500, y0 - 60))
    r = math("ADD", r, math("MULTIPLY", snow, 0.5, (x0 + 340, y0 - 300)), (x0 + 660, y0 - 60))  # snow roughens
    nt.links.new(math("MINIMUM", r, 1.0, (x0 + 820, y0 - 60)), rough_in)

    # ring ripples on pooled faces only (Lagarde 2b; shared "RainFX Ripples" group,
    # ring count follows the rain rate through set_ripple_weight)
    rip = node("ShaderNodeGroup", (bsdf.location.x - 460, bsdf.location.y - 420))
    rip.node_tree = ensure_ripples_group()
    bump = node("ShaderNodeBump", (rip.location.x + 220, rip.location.y))
    bump.inputs["Distance"].default_value = RIPPLE_DEPTH_M
    nt.links.new(rip.outputs["Height"], bump.inputs["Height"])
    nt.links.new(pool, bump.inputs["Strength"])
    if norm_src is not None:   # standing water hides the surface's normal map
        geo = node("ShaderNodeNewGeometry", (bump.location.x - 360, bump.location.y - 300))
        flat = node("ShaderNodeMix", (bump.location.x - 180, bump.location.y - 220), data_type="VECTOR")
        nt.links.new(pool, flat.inputs[0])
        nt.links.new(norm_src, flat.inputs[4])
        nt.links.new(geo.outputs["Normal"], flat.inputs[5])
        nt.links.new(flat.outputs[1], bump.inputs["Normal"])
    nt.links.new(bump.outputs["Normal"], norm_in)
    mat["rainfx_wet"] = WET_VERSION
    return True
