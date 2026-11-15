# Contributing

- Physics and anything that can be computed without Blender belongs in `rainfx/core/` (no `bpy` imports) with a
  test in `tests/`. Blender code only applies those numbers to node groups and objects.
- All Blender-version-dependent API access goes through `rainfx/compat.py`, with a comment naming the release note.
- Presets live in the table in `tools/gen_presets.py`; run it and `tools/gen_preset_docs.py` and commit the output.
- Changing a node graph? Bump `GROUP_VERSION` in `gn/precip.py` or `gn/dew.py` so existing files rebuild the group.
- Before sending a change: `python -m pytest` and, with a `bpy`-capable interpreter, `python tests/blender_smoke.py`
  (see [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)).

## Repository conventions

Shared by every OpenSimFX add-on (BlastFX, RainFX, FlowFX, AtmosFX), so the repositories read the same.

```
README.md  CHANGELOG.md  CONTRIBUTING.md  LICENSE  pyproject.toml
.github/logo.png   the add-on's icon, shown in the README heading
<addon>/           the add-on; this folder is exactly what the extension zip contains
docs/              the same nine docs in every add-on (below)
docs/img/          README and documentation renders
tests/             pytest suites (pure Python) and headless Blender checks
tools/             build_extension.py, render_preview.py, gen_preset_docs.py, ...
examples/          example scenes or scripts (optional)
```

- **Naming:** in sentences, the Blender UI, READMEs, docs and the website, write the names in mixed case:
  **OpenSimFX**, **BlastFX**, **RainFX**, **FlowFX**, **AtmosFX**. Lowercase is only for the wordmark beside a logo
  (`opensimfx`) and for identifiers: repositories, Python packages, zip files, URLs and property names
  (`blastfx`, `dist/blastfx-0.2.0.zip`, `github.com/opensimfx`). The AtmosFX repository is `atomsfx` but its package
  and zip are `atmosfx`.
- **Build:** `python tools/build_extension.py` writes `dist/<addon>-<version>.zip`. `dist/` is never committed;
  release zips go on GitHub Releases.
- **Docs:** every add-on has exactly these nine, with these titles, listed in this order in the README:

  | File | Title | Contents |
  |---|---|---|
  | `USER_GUIDE.md` | User Guide | install, first use, every panel |
  | `PRESETS.md` | Presets | the preset library (generated) |
  | `PHYSICS.md` | Physics | the models and equations |
  | `SYSTEM_DESIGN.md` | System Design | architecture, data flow, public API, decisions |
  | `DEVELOPMENT.md` | Development and Testing | environment, test suites, build and release, renders |
  | `VALIDATION.md` | Validation | what was measured, what is not verified |
  | `REFERENCES.md` | References and Licensing | sources, licences, provenance |
  | `ROADMAP.md` | Roadmap | history and next steps |
  | `UI_STYLE.md` | OpenSimFX UI conventions | shared panel layout (identical everywhere) |

  New material goes into one of these, not a new file. Generated docs say so on their first lines; a generated part
  of a hand-written doc sits between `<!-- generated:<name> start/end -->` markers. Neither is edited by hand.
- **README sections, in order:** Features, Install, Quick start, Verification status (read this), Repository layout,
  Develop, Documentation, License. Renders go under the tagline with a caption that says how they were made.
- **Private notes:** research about third-party or commercial add-ons, notes on how research was done, and
  development leftovers go in `private/` (ignored by git), never in the published docs.
- **UI:** sidebar panels follow [docs/UI_STYLE.md](docs/UI_STYLE.md), identical in every add-on.
- **Changelog:** newest first, with an `## Unreleased` section on top.
- **Licence:** GPL-3.0-or-later. Original work only: no code, shaders, node groups, textures or data copied from
  other add-ons, including ones you own a licence for.
