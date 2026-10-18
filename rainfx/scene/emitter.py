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
                   location=(0.0, 0.0, 0.0), name: str = "RainFX Emitter"):
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
    apply_preset(obj, scene, preset_id)
    return obj


def apply_preset(obj, scene, preset_id: str, quality: float = 1.0, box=(16.0, 16.0, 10.0),
                 intensity: float = 1.0, wind_mult: float = 1.0, seed: int = 0, overrides: dict | None = None,
                 follow=None, follow_offset=(0.0, 0.0, 0.0)):
    """Write a preset into the emitter's Geometry Nodes modifier. Returns derived dict."""
    p = all_presets()[preset_id]
    mod = find_modifier(obj) or obj.modifiers.new(MOD_NAME, "NODES")
    mod.node_group = dew.ensure_group() if p.mode == "dew" else precip.ensure_group()
    obj["rainfx_preset"] = preset_id
    drop_mat, splash_mat = materials.material_for_mode(p.material)
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
