# Pipeline stages (ТЗ раздел 2, 9)

Each subfolder corresponds to one stage of the mandatory five-stage
production pipeline. They are currently empty scaffolding — populating them
requires the real inputs listed in TOR section 1 (a licensed/anonymized
high-resolution CT series) and the corresponding specialist tooling, none of
which this repository can supply on its own.

| Folder | Stage | Input | Output | Tooling |
|---|---|---|---|---|
| `01_ct_dataset/` | 1a | Licensed/anonymized DICOM, slice ≤0.5–0.625mm (≤0.3mm for cribriform plate / petrous bone) | — | — |
| `02_segmentation/` | 1b | RAW/uncompressed DICOM | Raw high-poly mesh (millions of polys) | 3D Slicer / Materialise Mimics / Simpleware |
| `03_bone_separation/` | 2 | Raw mesh | 23 bones + mandible + hyoid, each a named independent object; sutures as separate structures | manual cut along suture lines, anatomist-guided |
| `04_retopology/` | 3 | Separated high-poly bones | Clean quad topology, subdivision-ready; fine detail (cribriform foramina, petrous canaliculi, vascular grooves) baked to normal maps | ZBrush / Blender retopology |
| `05_canals_cavities/` | 4 | Retopologized bones | Through-going canals/foramina matching real entry/exit points; sinus cavity volumes (frontal, sphenoid, maxillary, ethmoid cells); venous sinus / meningeal vessel grooves | manual reconstruction against CT + atlas |
| `06_validation/` | 5 | Finished model | Signed acceptance protocol; craniometric report; <1% structural discrepancy vs atlas/specimen | licensed anatomist review |

`01_ct_dataset/` and `exports/` are intentionally left untracked (`.gitkeep`
only) — real patient-derived DICOM data and large binary exports don't
belong in this repo without an explicit data-handling agreement.
