# Skull Anatomy Pipeline — scaffold

This directory scaffolds the production pipeline described in the TOR
("Эталонная 3D-модель черепа человека", раздел 0–9): a medically-accurate
skull model reconstructed from real CT data, ретопологизированная and
validated by a licensed anatomist.

## What's real here, and what isn't

**Real / usable as-is:**
- `metadata/` — a JSON Schema plus a generated metadata file covering all 23
  bones + подъязычная кость and 157 named structures (processes, foramina,
  canals, fossae, sutures, cavities) from TOR section 3, each with TA2 Latin
  name, Russian name (Гайворонский-style), description, and — where
  applicable — the nerves/vessels that pass through it. This is static
  anatomical nomenclature (TA2 / standard atlases), not per-specimen data.
- `pipeline/06_validation/` — templates for the craniometric report and the
  anatomical acceptance checklist from TOR sections 4 and 8, ready to fill in
  once real geometry exists.
- `blender/generate_placeholder_skull.py` — a procedural stand-in mesh
  (primitive-based) for exercising the downstream pipeline: export formats,
  LOD switching, viewer/UI integration, metadata↔mesh-name wiring.

**Not real, and cannot be made real without external input:**
- Any actual skull geometry claiming anatomical accuracy. TOR section 0 is
  explicit that this requires reconstruction from a real, licensed/
  anonymized high-resolution CT dataset (section 1), processed through
  segmentation software (3D Slicer / Mimics / Simpleware), sculpted/
  retopologized by a 3D artist, and signed off by a licensed anatomist
  (section 2, stage 5). None of that exists in this repository. The
  `blender/` placeholder mesh is explicitly NOT anatomically validated and
  must never be presented as meeting the TOR's 99%-accuracy bar.

## Layout

```
skull-anatomy-pipeline/
  metadata/
    schema/skull_metadata.schema.json   # JSON Schema (raздел 6)
    generate_metadata.py                # source of truth, regenerates the JSON below
    skull_metadata.json                 # generated: 23 bones, 157 structures
  pipeline/
    01_ct_dataset/        # stage 1 input: raw DICOM series (not tracked in git)
    02_segmentation/       # stage 1 output: raw high-poly segmented mesh
    03_bone_separation/    # stage 2 output: 23 bones + mandible as separate objects
    04_retopology/         # stage 3 output: clean quad topology + normal maps
    05_canals_cavities/    # stage 4 output: through-going canals, sinus volumes
    06_validation/         # stage 5: craniometry report + acceptance checklist templates
  blender/
    generate_placeholder_skull.py   # procedural stub mesh for pipeline testing
  exports/                 # glTF/GLB, OBJ/FBX, STL outputs (not tracked in git)
```

## Regenerating metadata

```
cd metadata
python3 generate_metadata.py --validate
```

Edit `generate_metadata.py` (not the generated `.json`) to add/correct
structures — it's the source of truth and keeps IDs, TA2 names, and Russian
names in one place instead of hand-edited JSON drifting from the schema.
