"""Builds dist/rainfx-<version>.zip, an installable Blender extension.

    python tools/build_extension.py

Blender's own validator is the authority:
    blender --command extension validate dist/rainfx-0.1.0.zip
    blender --command extension build --source-dir rainfx --output-dir dist
"""
import re
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
pkg = root / "rainfx"
version = re.search(r'^version\s*=\s*"([^"]+)"', (pkg / "blender_manifest.toml").read_text(), re.M).group(1)
out = root / "dist"
out.mkdir(exist_ok=True)
target = out / f"rainfx-{version}.zip"
with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
    for f in sorted(pkg.rglob("*")):
        if f.is_file() and "__pycache__" not in f.parts and f.suffix != ".pyc":
            z.write(f, f.relative_to(pkg).as_posix())     # manifest must sit at the zip root
print("built", target, f"{target.stat().st_size/1024:.0f} KiB")
