# Anatomical acceptance checklist (ТЗ раздел 8)

Signed off by a licensed anatomist against the finished model, cross-checked
with `metadata/skull_metadata.json` and a real specimen/atlas. Do not check
an item without inspecting the actual mesh — this checklist tracks
inspection, it does not substitute for it.

Acceptance requires: all items present and morphologically recognizable,
<1% discrepancy in structure presence, craniometric report attached and
passing, canals/foramina verified as through-going, model disassembles into
separate bones and reassembles correctly, 60+ fps at working LOD.

## Per-bone structure presence (generate one block per `bones[]` entry)

- [ ] Bone present as an independent, correctly named/ID'd object
- [ ] All structures listed for this bone in `skull_metadata.json` are
      present on the mesh and morphologically recognizable
- [ ] Surface detail (foramina, canaliculi, vascular grooves) visible at
      working LOD (baked normal map) and on the high-poly reference
- [ ] Bone reconnects correctly to its neighbors (no gaps/overlaps at
      suture lines)

## Structural checks

- [ ] Every `canal`/`foramen` entry has a verified through-going path with
      entry and exit points matching real anatomy
- [ ] Sinus/cavity volumes (frontal, sphenoid, maxillary, ethmoid cells,
      mastoid cells) are hollow, internally structured, not solid stand-ins
- [ ] Venous sinus grooves (transverse, sigmoid) and meningeal vessel
      grooves are present on internal surfaces
- [ ] Sutures (coronal, sagittal, lambdoid, squamous, sphenofrontal, etc.)
      are modeled as separate, isolatable structures with realistic
      serration
- [ ] Mandible separates from the skull as an independent object, forms a
      correct TMJ articulation, and is riggable for open/close and lateral
      movement

## Sign-off

- Reviewer: ______________________
- Credentials/affiliation: ______________________
- Date: ______________________
- Overall verdict (accept / reject / conditional): ______________________
- Notes on discrepancies found: ______________________
