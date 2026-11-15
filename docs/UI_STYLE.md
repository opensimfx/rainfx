# OpenSimFX UI conventions

One layout language for BlastFX, RainFX, FlowFX and AtmosFX, so a user who knows one
add-on can find their way around the others. AtmosFX's panel structure is the reference;
property layout follows Blender's own editors.

## Placement

- 3D Viewport sidebar (N), tab = product name (`bl_category = "BlastFX"`, ...).
- One main panel, `<PRODUCT>_PT_main`, labelled with the product name. Everything else
  is a sub-panel (`bl_parent_id = "<PRODUCT>_PT_main"`).

## Main panel

Top to bottom:

1. Preset selector (dropdown), with a one-line description when the preset has one.
2. The primary action ("Create Blast", "Add Rain", ...) as a large button
   (`scale_y = 1.4`).
3. Once something exists: its name/status and per-object actions (Rebuild, Duplicate).
4. The destructive action (Remove) last, after a separator, `TRASH` icon.

## Sub-panels

Standard names, in this order when they exist. Product-specific setup panels come first
and are open; the standard tail panels are closed by default (`DEFAULT_CLOSED`):

| Order | Panel | Holds |
|---|---|---|
| 1 | product-specific setup ("Explosion", "Time and Place", ...) | the main controls |
| 2 | "Components" or per-component panels | on/off toggles (in the panel header when the component has its own panel) |
| 3 | "Look" / "Shading and Output" | appearance-only controls |
| 4 | "Cache and Bake" | quality, bake / cancel / free, progress and cache status |
| 5 | "Readout" | derived values with units, read-only |
| 6 | "Diagnostics" | validation results and warnings |
| 7 | "Preset Files" | save / import / export presets |

## Layout rules

- Every panel sets `layout.use_property_split = True` and
  `layout.use_property_decorate = False` (label on the left, as in Blender's editors).
- Related properties go in `column(align=True)`; checkbox groups use
  `column(heading="...", align=True)`.
- Shared base classes per add-on: `_Base` (space, region, category) and `_Sub`
  (`bl_parent_id`, `DEFAULT_CLOSED`).
- Destructive operators (Remove, Free, Delete) sit at the bottom of their panel after a
  separator, `TRASH` icon. Cancel uses `CANCEL`.
- Warnings: a box with `alert = True` and the `ERROR` icon. Hints: one line with the
  `INFO` icon.
- Readouts: label on the left, value with units on the right
  (`split(factor=0.5)`), no editable fields.
- Titles in Title Case; panel names use "and" ("Cache and Bake").
