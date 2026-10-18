# Research Sources

All pages below were retrieved through Firecrawl (search or scrape) while designing RainFX. "Used for" states exactly
what was taken from each. Anything not listed here is general knowledge and is labelled "textbook" or "modelled" in `PHYSICS.md`.

## Blender documentation and release notes

| Source | Used for |
|---|---|
| https://developer.blender.org/docs/release_notes/5.2/ | Overview of 5.2 changes |
| https://developer.blender.org/docs/release_notes/5.2/python_api/ | Geometry Nodes modifier inputs moved to `modifier.properties.inputs.<identifier>.value`; node socket identifier changes (Compare, Random Value) |
| https://developer.blender.org/docs/release_notes/5.2/geometry_nodes/ | Geometry Nodes changes in 5.2; Geometry Nodes modifiers on empties |
| https://developer.blender.org/docs/release_notes/5.2/physics/ | New experimental Geometry Nodes physics system (hair and cloth focus, Collider effector for closed meshes) |
| https://developer.blender.org/docs/release_notes/5.0/python_api/ | Compositor as node group (`compositing_node_group`), EEVEE engine id, `use_nodes` deprecation, `bpy.props` storage change |
| https://docs.blender.org/api/5.2/bpy.types.NodesModifier.html | `NodesModifier.properties` (read-only, may be `None`), `bakes`, `bake_directory`, `is_input_visible` |
| https://docs.blender.org/manual/en/latest/physics/index.html | Map of physics systems (emitter particles, collision, force fields, fluid, rigid body, simulation nodes) in the 5.2 LTS manual |
| https://docs.blender.org/manual/en/latest/physics/collision.html | Collision modifier settings for particles (permeability, stickiness, kill, damping, friction) |
| https://docs.blender.org/manual/en/latest/physics/particles/emitter/physics/newtonian.html | Newtonian particle physics: drag, Brownian, damping, size, mass, integrators |
| https://docs.blender.org/manual/en/latest/physics/simulation_nodes.html | Simulation nodes overview and baking |
| https://docs.blender.org/manual/en/latest/modeling/geometry_nodes/simulation/simulation_zone.html | Simulation zone semantics: named attributes only, inputs evaluated once vs every step, Delta Time |
| https://docs.blender.org/manual/en/latest/advanced/extensions/getting_started.html | Extension manifest schema 1.0.0, required fields, build and validate commands |

The 5.2.1 manual and API pages were read as "latest" / "5.2". Blender 5.2.1 itself could not be run.

## Physics

| Source | Used for |
|---|---|
| https://journals.ametsoc.org/view/journals/atot/39/3/JTECH-D-21-0049.1.pdf (J. Atmos. Oceanic Technol. 39) | Gunn and Kinzer (1949) terminal-velocity data have a maximum drop size of 5.8 mm |
| https://www.atmos.albany.edu/facstaff/rfovell/ATM562/gunn-marshall-1958.pdf | Marshall-Palmer intercept N0 = 8.0 x 10^3 m^-3 (per mm) for rain; Gunn and Kinzer terminal speeds |
| https://hess.copernicus.org/articles/5/615/2001/hess-5-615-2001.pdf | Marshall-Palmer parameterisation remains a realistic average drop-size distribution |
| https://www.nssl.noaa.gov/education/svrwx101/hail/ | Hail fall-speed bands: under 1 in 9-25 mph, 1-1.75 in 25-40 mph, 2-4 in 44-72 mph; natural hail slower than solid ice spheres |
| MDPI Geosciences 10(12):500 (hail review; found via search, page not re-fetched for this file) | `v = 9 D^0.8` (D in cm) hail terminal velocity relation |
| https://www.nachi.org/hail-damage-part4-31.htm | Counter-example: roofing source quotes about 50 mph for 1 in hail, much higher than NSSL; shows the spread in published hail speeds |
| https://journals.ametsoc.org/view/journals/apme/45/10/jam2406.1.pdf (J. Appl. Meteor. Climatol. 45) | Wet-snow particles of 2.4 mm or more fall at about 2 m/s (standard deviation 0.8) |
| https://tellusjournal.org/articles/10.16993/tellus.4127 | Large aggregate snowflakes with terminal velocities up to 1.5 m/s |
| https://www.opticalscientific.com/feeds/blog/standard-unit-rainfall-precipitation-wmo | WMO rain intensity categories: light 2.5 mm/h or less, moderate 2.6-7.5, heavy 7.6 or more, violent over 50 |
| https://community.wmo.int/site/knowledge-hub/programmes-and-initiatives/aviation/aviation-hazards-precipitation | Showers classed violent above 50 mm/h |

## Not sourced (entered from general knowledge)

- Marshall-Palmer slope `L = 4.1 R^-0.21`.
- Atlas et al. fit `v = 9.65 - 10.3 exp(-0.6 D)` and the Gunn-Kinzer reference values used in unit tests.
- Stokes law, air viscosity and density constants.
- All "modelled" items (gusts, splash, bounce, snow speed formula, hail drag factor 0.85).

## Web search availability

Firecrawl enforced a per-minute request limit during research; some scrapes were retried. Search results are excerpts; pages
were not read in full unless listed under Blender documentation above.
