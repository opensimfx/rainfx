"""Sound-ready impact events: replay the emitter's frame range as JSON.

Walks scene.frame_start..scene.frame_end once, reading the impact sink that
already rides the emitter output every frame (point verts flagged 'imp' by
the precipitation group — the same stream the wetness handler consumes), and
writes a self-contained JSON log for audio middleware:

    {"version": 1, "fps": 24, "frame_start": 1, "frame_end": 200,
     "preset": "heavy_rain", "vt_mean_ms": 9.13, "sample_stride": 3,
     "events": [{"frame": 12, "position": [x, y, z],
                 "intensity": 2.4, "type": "impact"}, ...]}

'intensity' is the landing drop's diameter in mm (rain loudness tracks drop
size; scale to taste in the audio layer). Positions are emitter-local;
multiply by the emitter matrix_world when the layer is follow-mounted.
No new GN group and no cache: the replay is the deterministic sim stepping
per frame, so exports match bakes and reruns. Per frame at most
``per_frame_cap`` events are kept (even stride sampling over the sink verts
for that frame).
"""
from __future__ import annotations

import json
import os

import bpy

from .. import compat
from . import emitter as em

DEFAULT_FILENAME = "rainfx_impact_events.json"


def _emitter():
    for ob in bpy.data.objects:
        if em.is_emitter(ob):
            return ob
    return None


def _read_hits(me, stride: int):
    """Impacts of evaluated emitter mesh: (position, intensity, relevant type)."""
    imp = me.attributes.get("imp")
    if imp is None:
        return []
    snow = me.attributes.get("snow")
    diam = me.attributes.get("diameter")
    sd = snow.data if snow is not None else None
    dd = diam.data if diam is not None else None
    out = []
    idxs = [i for i, d in enumerate(imp.data) if d.value > 0.5]
    for i in idxs[::stride]:
        etype = "snow" if sd is not None and sd[i].value > 0.5 else "impact"
        out.append(([round(c, 3) for c in me.vertices[i].co],
                    round(dd[i].value, 3) if dd is not None else 1.0,
                    etype))
    return out


def export_events(scene: bpy.types.Scene, et: bpy.types.Object | None = None,
                  path: str = "", frame_start: int | None = None,
                  frame_end: int | None = None, per_frame_cap: int = 256):
    """Replay the frame range and write impact events. Returns (path, count)."""
    if et is None:
        et = _emitter()
    if et is None:
        raise ValueError("no RainFX emitter in the scene")
    mod = em.find_modifier(et)
    if mod is None:
        raise ValueError("emitter has no RainFX modifier")
    fs = scene.frame_start if frame_start is None else int(frame_start)
    fe = scene.frame_end if frame_end is None else int(frame_end)
    if fe < fs:
        fs, fe = fe, fs

    path = os.path.abspath(path) if path else os.path.join(
        compat.user_dir(), DEFAULT_FILENAME)
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    # headless evaluation zeroes spawn points at the viewport residence
    # multiplier, so push 1.0 for the walk and restore the user's value after
    vd_orig = compat.get_modifier_input(mod, "Viewport Density", 1.0)
    compat.set_modifier_input(mod, "Viewport Density", 1.0)

    events = []
    stride = 1
    try:
        dg = bpy.context.evaluated_depsgraph_get()
        for f in range(fs, fe + 1):
            scene.frame_set(f)
            dg.update()
            ev = et.evaluated_get(dg)
            me = ev.to_mesh()
            try:
                hits = _read_hits(me, 1)  # count first, then downsample
            finally:
                ev.to_mesh_clear()
            stride = -(-len(hits) // per_frame_cap) or 1  # ceil, so len/stride <= cap
            for pos, intensity, etype in hits[::stride]:
                events.append({"frame": f, "position": pos,
                               "intensity": intensity, "type": etype})
    finally:
        compat.set_modifier_input(mod, "Viewport Density", vd_orig)

    doc = {
        "version": 1,
        "fps": round(scene.render.fps, 0),
        "frame_start": fs,
        "frame_end": fe,
        "preset": et.get("rainfx_preset", ""),
        "vt_mean_ms": (et.get("rainfx_derived") or {}).get("vt_mean_ms"),
        "sample_stride": stride,
        "events": events,
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh)
    return path, len(events)
