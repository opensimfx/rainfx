"""Background baking: run the bake op in a second Blender process.

Blender's data API is main-thread only, so a true "different thread" is a
second headless Blender baking the same already-saved .blend file while the
parent session polls the disk cache for progress: the sim zone writes one
*bake_directory/<record>/blobs/<frame>_00000.blob per frame, so the live
fraction is blob-count-over-expected — no progress file needed.

Disk bakes only; *packed* caches keep the legacy in-process path (a second
process cannot write into the parent's bpy.data, and the parent reports a
counted finish when its child exits; a single-flight guard keeps two child
bakes from racing on the same scene file).
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import textwrap

import bpy

from . import emitter as em

# one background bake at a time per Blender session
_ACTIVE: dict | None = None

CHILD_SCRIPT = textwrap.dedent("""\
    import bpy
    from pathlib import Path
    storage = Path($BAKE_DIR)
    try:
        storage.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    et = None
    for ob in bpy.data.objects:
        if ob.get("rainfx_emitter") and ob.modifiers:
            et = ob
            break
    if et is not None:
        mod = et.modifiers[0]
        mod.bake_target = 'DISK'
        mod.bake_directory = str(storage)
        for b in mod.bakes:
            b.use_custom_simulation_frame_range = True
            b.frame_start = $FS
            b.frame_end = $FE
        bpy.context.view_layer.objects.active = et
        et.select_set(True)
        try:
            with bpy.context.temp_override(object=et, active_object=et,
                                           selected_objects=[et]):
                bpy.ops.object.simulation_nodes_cache_bake(selected=True)
        except Exception as exc:  # pragma: no cover - surfaced via exit code
            print(f"bake failed: {exc}")
            raise SystemExit(1)
    """)


def progress(handle: dict) -> tuple[bool, int]:
    """(still_running, finished_frames) for a launched background bake."""
    running = handle["proc"].poll() is None
    done = len(list(handle["dir"].rglob("*.blob")))
    return running, min(done, handle["expected"])


def active() -> dict | None:
    return _ACTIVE


def launch(scene: bpy.types.Scene, ob: bpy.types.Object,
           frame_start: int, frame_end: int) -> dict:
    """Spawn a headless Blender child that bakes the current file to disk."""
    global _ACTIVE
    if _ACTIVE is not None and _ACTIVE["proc"].poll() is None:
        raise RuntimeError("a background bake is already running")
    filepath = bpy.data.filepath
    if not filepath:
        raise RuntimeError("Save the .blend first for a disk bake")

    mod = em.find_modifier(ob)
    if not mod.bake_directory:
        mod.bake_directory = os.path.join(os.path.dirname(filepath),
                                          ob.name + "_rainfx_bake")
    storage = bpy.path.abspath(mod.bake_directory)

    script = CHILD_SCRIPT.replace("$BAKE_DIR", f'"{storage}"').replace(
        "$FS", str(int(frame_start))).replace("$FE", str(int(frame_end)))
    _, child_path = tempfile.mkstemp(prefix="rainfx_bake_", suffix=".py")
    with open(child_path, "w", encoding="utf-8") as fh:
        fh.write(script)
    proc = subprocess.Popen(
        [sys_arg0(), "-b", filepath, "--factory-startup", "--python", child_path],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    from pathlib import Path
    _ACTIVE = {"proc": proc, "script": child_path,
               "dir": Path(storage),
               "expected": frame_end - frame_start + 1}
    return _ACTIVE


def sys_arg0() -> str:  # pragma: no cover - trivial indirection for stubbing
    import sys
    return sys.argv[0]


def finish(handle: dict) -> None:
    """Reap the child once its exit is observed."""
    handle["proc"].poll()
    code = handle["proc"].returncode
    try:
        os.unlink(handle["script"])
    except OSError:
        pass
    global _ACTIVE
    if _ACTIVE is handle:
        _ACTIVE = None
    return code
