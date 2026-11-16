# References and Licensing

## Licensing

RainFX is GPL-3.0-or-later and original work. It bundles no third-party code, node groups, textures or data.

## Research sources


Pages consulted while designing RainFX. "Used for" states exactly what was taken from each. Anything not listed here is general knowledge and is labelled "textbook" or "modelled" in `PHYSICS.md`.

### Blender documentation and release notes

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

The manual and API pages were read as "latest" / "5.2"; 1.0 was tested in Blender 5.2.3 and 5.2.4.

### Physics

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

### Look: streak optics, rain fog, wet surfaces, lighting

| Source | Used for |
|---|---|
| https://cave.cs.columbia.edu/Statics/publications/pdfs/Garg_IJCV07.pdf (Garg and Nayar, Vision and Rain, IJCV 2007) | A drop is a 165 degree lens, ~94 % refracted / 6 % reflected; a streak changes a pixel by at most ~4 % (beta < 0.039); visibility falls as 1/sqrt(exposure) |
| Gunn and Kinzer, *The Terminal Velocity of Fall for Water Droplets in Stagnant Air*, J. Meteorol. 6, 243-248 (1949), doi:10.1175/1520-0469(1949)006<0243:TTVOFF>2.0.CO;2; table as reproduced by Yusuf et al., LAUJET (2015) and Adams-Suberu et al. (2018); Hinkle, USDA ARS (1987) | Reference terminal speeds in `test_physics.py`: 4.03, 6.49, 8.06, 8.83, 9.09 m/s at 1-5 mm (checked against the reproduced table 2026-11-16; Hinkle gives the same 4.03 m/s at 1 mm, sea level) |
| https://en.wikipedia.org/wiki/Capillary_length (capillary length) and de Gennes, Brochard-Wyart, Quéré, *Capillarity and Wetting Phenomena* (Springer 2004), ch. 1 | l_c = sqrt(sigma / rho g) = 2.7 mm for water; a pendant drop detaches at a size set by l_c (drips 4-6 mm) |
| https://openaccess.thecvf.com/content_ICCV_2019/papers/Halder_Physics-Based_Rendering_for_Improving_Robustness_to_Rain_ICCV_2019_paper.pdf (Halder et al., ICCV 2019) | Rain extinction exp(-0.312 R^0.67 d), d in km |
| https://ams.confex.com/ams/pdfpapers/113177.pdf (Gultepe et al., visibility vs precipitation rate) | Cross-check: 10 mm/h rain gives 1-3 km visibility |
| https://seblagarde.wordpress.com/2012/12/10/observe-rainy-world/ | Observed rainy-world effects: wet = darker diffuse and brighter specular, non-porous materials do not darken, puddle mirror, halos in heavy rain, drops visible mainly when backlit |
| https://seblagarde.wordpress.com/2013/04/14/water-drop-3b-physically-based-wet-surfaces/ | Wet albedo factor lerp(1, 0.2, porosity), porosity from roughness, water F0 0.02, flat puddle normals |
| https://www.wevideo.com/blog/rain-videography | "Front light snow and backlight rain" (search excerpt) |
| https://www.rogerdeakins.com/forums/topic/lighting-a-rainy-night-scene/ | Street lights behind the action as the backlight for rain |

### Impacts and detail: splash threshold, crowns, spray, ripples, layers, lens

| Source | Used for |
|---|---|
| https://doi.org/10.1146/annurev.fluid.38.050304.092144 (Yarin, Drop Impact Dynamics, Annu. Rev. Fluid Mech. 38, 2006) | Splashing parameter K = We Oh^-2/5, wet-film threshold K_S = 2100 + 5880 H^1.44, crown radius ~ sqrt(t), crown height slope ~0.57, Worthington jet at ~116 ms |
| https://www.cambridge.org/core/journals/journal-of-fluid-mechanics/article/experimental-study-on-spray-in-the-atmospheric-surface-layer-by-raindrops-impacting-water-surface/5E8DDD97FF98111525F0AF950C9816B7 | Spray from raindrops on water: number density decays exponentially with height, maximum heights ~0.33-0.45 m |
| https://seblagarde.wordpress.com/2013/01/03/water-drop-2b-dynamic-rain-and-its-effects/ | Layered procedural ripple rings: ring factor sin(clamp(t 9, 0, 3) pi), four layers, time multipliers 1 / 0.85 / 0.93 / 1.13, x1.6 speed; rings only where water stands |
| https://beforesandafters.com/2020/03/11/when-you-need-to-comp-a-cg-creature-into-practical-rain-plates/ | Rain built as far, mid and near layers with matching depth of field |
| https://radiant-shaders.com/learn/rain-on-glass | Drops as lenses with a sharp/blurred split, drops taller than wide with a flat bottom, static and sliding drops with trails |

### Not sourced (entered from general knowledge)

- Marshall-Palmer slope `L = 4.1 R^-0.21`.
- Atlas et al. fit `v = 9.65 - 10.3 exp(-0.6 D)` and the Gunn-Kinzer reference values used in unit tests.
- Stokes law, air viscosity and density constants.
- All "modelled" items (gusts, splash, bounce, snow speed formula, hail drag factor 0.85).
