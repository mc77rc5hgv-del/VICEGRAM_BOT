# Placeholder skull generator

`generate_placeholder_skull.py` builds a rough, primitive-based stand-in
mesh (two objects: `placeholder_cranium`, `placeholder_mandible`) — useful
for testing the export pipeline, LOD switching, and viewer/UI integration
before real CT-derived geometry exists.

**Disclaimer:** this mesh is not anatomically validated. It approximates
overall skull proportions with spheres/boxes and boolean cuts for the
orbits, foramen magnum, and nasal cavity — it does not represent real bone
boundaries, sutures, canals, or sinus architecture, and must not be used to
claim compliance with the TOR's accuracy requirements.

## Requirements

Blender 4.x (not bundled in this repo/session — install separately).

## Usage

```
blender --background --python generate_placeholder_skull.py -- --out ../exports/placeholder_skull.glb
```

Output is a `.glb` with two top-level objects, matching the
`mesh_ref`-eligible split in `metadata/skull_metadata.json` between the
fixed cranium and the movable mandible (`mandibula.movable == true`).
