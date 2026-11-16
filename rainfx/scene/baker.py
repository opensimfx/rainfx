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
    et = bpy.data.objects.get($EMITTER)
    mod = et.modifiers.get($MODIFIER) if et is not None else None
    if mod is None:
        print("bake failed: emitter or RainFX modifier not found")
        raise SystemExit(1)
    mod.bake_target = 'DISK'
    mod.bake_directory = str(storage)
    for b in mod.bakes:
        b.use_custom_simulation_frame_range = True
        b.frame_start = $FS
        b.frame_end = $FE
    # wetness helpers bake in the same pass; this Blender runs without the
    # add-on, so load RainFX's wetness module for the frame handler that
    # feeds them the impacts
    import sys, importlib
    sys.path.insert(0, $PKG_PARENT)
    wet = importlib.import_module($PKG_NAME + ".scene.wetness")
    bpy.app.handlers.frame_change_post.append(wet._on_frame)
    objs = [et]
    for ob_name, m_name, d in $HELPERS:
        ob = bpy.data.objects.get(ob_name)
        m = ob.modifiers.get(m_name) if ob is not None else None
        if m is not None:
            wet.prepare_bake(m, 'DISK', d, $FS, $FE)
            objs.append(ob)
    bpy.context.view_layer.objects.active = et
    for ob in objs:
        ob.select_set(True)
    try:
        with bpy.context.temp_override(object=et, active_object=et,
                                       selected_objects=objs):
            bpy.ops.object.simulation_nodes_cache_bake(selected=True)
    except Exception as exc:  # pragma: no cover - surfaced via exit code
        print(f"bake failed: {exc}")
        raise SystemExit(1)
    """)


def progress(handle: dict) -> tuple[bool, int]:
    """(still_running, finished_frames) for a launched background bake.

    Counts only blobs written since the launch, so files left by an earlier
    bake in the same folder do not show as progress.
    """
    running = handle["proc"].poll() is None
    t0 = handle.get("t0", 0.0)
    done = 0
    for f in handle["dir"].rglob("*.blob"):
        if f.relative_to(handle["dir"]).parts[:1] == ("wetness",):
            continue                  # the wetness helpers' caches: progress is the emitter's
        try:
            if f.stat().st_mtime >= t0:
                done += 1
        except OSError:
            pass
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
    if mod is None:
        raise RuntimeError("the active object has no RainFX modifier")
    if not mod.bake_directory:
        mod.bake_directory = os.path.join(os.path.dirname(filepath),
                                          ob.name + "_rainfx_bake")
    storage = bpy.path.abspath(mod.bake_directory)
    # the parent reads what the child writes: same disk target and range
    mod.bake_target = "DISK"
    for b in mod.bakes:
        b.use_custom_simulation_frame_range = True
        b.frame_start, b.frame_end = int(frame_start), int(frame_end)

    # wetness helpers bake alongside, each into its own folder; the parent
    # points them at the same folders so it reads what the child writes
    from . import wetness
    helpers = []
    for h_ob, h_mod in wetness.helpers(scene):
        d = wetness.helper_bake_dir(storage, h_ob)
        wetness.prepare_bake(h_mod, "DISK", d, frame_start, frame_end)
        helpers.append((h_ob.name, h_mod.name, d))
    pkg_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # repr() makes valid Python literals of any path or name (Windows
    # backslashes, quotes); the child bakes this emitter, not the first one
    script = (CHILD_SCRIPT.replace("$BAKE_DIR", repr(storage))
              .replace("$EMITTER", repr(ob.name)).replace("$MODIFIER", repr(mod.name))
              .replace("$HELPERS", repr(helpers))
              .replace("$PKG_PARENT", repr(os.path.dirname(pkg_dir)))
              .replace("$PKG_NAME", repr(os.path.basename(pkg_dir)))
              .replace("$FS", str(int(frame_start))).replace("$FE", str(int(frame_end))))
    fd, child_path = tempfile.mkstemp(prefix="rainfx_bake_", suffix=".py")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(script)
    # the child bakes a copy of the scene as it is now, not as last saved; the
    # copy sits next to the .blend so relative texture and cache paths resolve
    folder, base = os.path.split(filepath)
    snapshot = os.path.join(folder, f".{os.path.splitext(base)[0]}_rainfx_bake_{os.getpid()}.blend")
    bpy.ops.wm.save_as_mainfile(filepath=snapshot, copy=True, compress=False)
    import time
    t0 = time.time() - 1.0   # mtime granularity
    proc = subprocess.Popen(
        [sys_arg0(), "-b", snapshot, "--factory-startup", "--python", child_path],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    from pathlib import Path
    _ACTIVE = {"proc": proc, "script": child_path, "snapshot": snapshot, "t0": t0,
               "dir": Path(storage),
               "expected": frame_end - frame_start + 1}
    return _ACTIVE


def sys_arg0() -> str:  # pragma: no cover - trivial indirection for stubbing
    """The running Blender executable (``sys.executable`` is the bundled Python)."""
    import sys
    return bpy.app.binary_path or sys.argv[0]


def stop() -> None:
    """Stop a running background bake (add-on disabled or updated mid-bake)."""
    handle = _ACTIVE
    if handle is None:
        return
    proc = handle["proc"]
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    finish(handle)


def finish(handle: dict) -> int | None:
    """Reap the child once its exit is observed."""
    handle["proc"].poll()
    code = handle["proc"].returncode
    for path in (handle["script"], handle.get("snapshot")):
        if path:
            try:
                os.unlink(path)
            except OSError:
                pass
    global _ACTIVE
    if _ACTIVE is handle:
        _ACTIVE = None
    return code
