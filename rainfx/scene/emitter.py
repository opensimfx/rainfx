"""Scene-level operations independent of the UI (callable from tests / scripts)."""
from __future__ import annotations

from pathlib import Path

import bpy

from .. import compat
from ..core import presets as presets_mod
from ..gn import dew, materials, precip

COLLIDERS_NAME = "RainFX Colliders"
ROOT_NAME = "RainFX"
MOD_NAME = "RainFX"
_DATA = Path(__file__).resolve().parent.parent / "data" / "presets.json"

_cache: dict[str, presets_mod.Preset] | None = None


def all_presets(reload: bool = False) -> dict[str, presets_mod.Preset]:
    global _cache
    if _cache is None or reload:
        try:
            user = compat.user_dir()
        except Exception:
            user = None
        _cache = presets_mod.load_dirs(_DATA, Path(user) if user else None)
    return _cache


# ----------------------------------------------------------------- collections
def ensure_collection(scene: bpy.types.Scene, name: str, parent: bpy.types.Collection | None = None):
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
        (parent or scene.collection).children.link(col)
    elif col.name not in (parent or scene.collection).children:
        try:
            (parent or scene.collection).children.link(col)
        except RuntimeError:
            pass
    return col


def colliders_collection(scene: bpy.types.Scene) -> bpy.types.Collection:
    col = ensure_collection(scene, COLLIDERS_NAME)
    col.hide_render = False
    return col


# -------------------------------------------------------------------- emitters
def is_emitter(obj) -> bool:
    return obj is not None and bool(obj.get("rainfx_emitter"))


def find_modifier(obj) -> bpy.types.NodesModifier | None:
    for m in obj.modifiers:
        if m.type == "NODES" and m.name == MOD_NAME:
            return m
    return None


def create_emitter(scene: bpy.types.Scene, preset_id: str = "moderate_rain",
                   location=(0.0, 0.0, 0.0), name: str = "RainFX Emitter",
                   quality: float = None, box=None):
    root = ensure_collection(scene, ROOT_NAME)
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([(0.0, 0.0, 0.0)], [], [])          # one vertex; real geometry comes from nodes
    obj = bpy.data.objects.new(name, mesh)
    obj.location = location
    obj.hide_select = False
    obj["rainfx_emitter"] = True
    root.objects.link(obj)
    mod = obj.modifiers.new(MOD_NAME, "NODES")
    colliders_collection(scene)
    kw = {k: v for k, v in (("quality", quality), ("box", box)) if v is not None}
    apply_preset(obj, scene, preset_id, **kw)
    return obj
def apply_preset(obj, scene, preset_id: str, quality: float = 1.0, box=(16.0, 16.0, 10.0),
                 intensity: float = 1.0, wind_mult: float = 1.0, seed: int = 0, overrides: dict | None = None,
                 follow=None, follow_offset=(0.0, 0.0, 0.0), refraction: bool = False):
    """Write a preset into the emitter's Geometry Nodes modifier. Returns derived dict."""
    p = all_presets()[preset_id]
    mod = find_modifier(obj) or obj.modifiers.new(MOD_NAME, "NODES")
    mod.node_group = dew.ensure_group() if p.mode == "dew" else precip.ensure_group()
    obj["rainfx_preset"] = preset_id
    kind = "drop" if refraction and p.mode != "dew" else p.material
    drop_mat, splash_mat = materials.material_for_mode(kind)
    col = colliders_collection(scene)
    S = lambda k, v: compat.set_modifier_input(mod, k, v)  # noqa: E731
    S("Colliders", col)
    S("Seed", seed)
    S("Follow Object", follow if follow is not None else obj)  # empty follow == fixed volume
    S("Origin Offset", tuple(follow_offset))
    if p.mode == "dew":
        S("Density", p.dew_density_m2 * intensity)
        S("D Min", p.d_min_mm)
        S("D Max", p.d_max_mm)
        S("Min Normal Z", p.dew_min_normal_z)
        S("Bead Material", materials.get_material("dew"))
        obj["rainfx_derived"] = {}
        return {"mode_index": 3}
    d = presets_mod.derive(p, tuple(box), quality=quality * intensity)
    wv = tuple(c * wind_mult for c in d["wind_vec"])
    obj["rainfx_wind"] = wv  # far layer reads applied wind without re-deriving
    vals = {
        "Mode": d["mode_index"], "Count": d["count"], "Box Size": tuple(box),
        "D Min": p.d_min_mm, "D Max": p.d_max_mm, "Lambda": d["lambda"],
        "Speed Scale": p.speed_scale, "Snow Speed": p.snow_speed_ms,
        "Wind": wv, "Gust Strength": p.gust_strength * wind_mult, "Gust Scale": p.gust_scale_m,
        "Gust Speed": p.gust_speed_ms, "Inertia": p.inertia,
        "Restitution": p.restitution, "Max Bounces": p.max_bounces,
        "Splash Amount": p.splash_amount, "Splash Speed": p.splash_speed,
        "Splash Life Min": p.splash_life_min, "Splash Life Max": p.splash_life_max,
        "Splash Size": p.splash_size, "Shutter": p.shutter_s, "Visual Scale": p.visual_scale,
        "Drop Material": drop_mat, "Splash Material": splash_mat,
    }
    if overrides:
        vals.update(overrides)
    for k, v in vals.items():
        S(k, v)
    obj["rainfx_derived"] = {k: v for k, v in d.items() if isinstance(v, (int, float))}
    return d


# ------------------------------------------------------------------- colliders
def add_colliders(scene: bpy.types.Scene, objects) -> int:
    col = colliders_collection(scene)
    n = 0
    for o in objects:
        if o.type not in {"MESH"} or is_emitter(o):
            continue
        if o.name not in col.objects:
            col.objects.link(o)
            n += 1
    return n


def remove_colliders(scene: bpy.types.Scene, objects) -> int:
    col = colliders_collection(scene)
    n = 0
    for o in objects:
        if o.name in col.objects:
            col.objects.unlink(o)
            n += 1
    return n


def create_demo(scene: bpy.types.Scene) -> None:
    """Seed a demo ground plane + Suzanne collider so a fresh add shows rain working.

    Idempotent by name (re-running the Add Weather Emitter operator never
    duplicates them); both join the collider collection via add_colliders so the
    user sees impacts immediately, and the swap route is the ones in the UI:
    select your own mesh and use Collision > Add Colliders, or just delete the
    demo objects.
    """
    col = ensure_collection(scene, ROOT_NAME)
    mat = bpy.data.materials.get("RainFX Demo")
    if mat is None:
        mat = bpy.data.materials.new("RainFX Demo")
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf is not None:
            bsdf.inputs["Base Color"].default_value = (0.55, 0.55, 0.55, 1.0)
            bsdf.inputs["Roughness"].default_value = 0.9

    ob = bpy.data.objects.get("RainFX Surface")
    if ob is None:
        me = bpy.data.meshes.new("RainFX Surface")
        me.from_pydata(((-10, -10, 0), (10, -10, 0), (10, 10, 0), (-10, 10, 0)),
                       [], [(0, 1, 2, 3)])
        me.validate()
        ob = bpy.data.objects.new("RainFX Surface", me)
        col.objects.link(ob)
        ob.data.materials.append(mat)
    mo = bpy.data.objects.get("RainFX Suzanne")
    if mo is None:
        try:
            bpy.ops.mesh.primitive_monkey_add(size=2, location=(0, 0, 0))
            mo = bpy.context.active_object
            mo.name = "RainFX Suzanne"
            for c in list(mo.users_collection):
                c.objects.unlink(mo)
            col.objects.link(mo)
        except RuntimeError:  # poll failures (e.g. headless edge) keep the demo minimal
            mo = None
    if mo is not None and not mo.data.materials:
        mo.data.materials.append(mat)
    add_colliders(scene, [o for o in (ob, mo) if o is not None])
