"""
Procedural PLACEHOLDER skull mesh — for pipeline/viewer testing only.

THIS IS NOT AN ANATOMICALLY VALIDATED MODEL. It is built from primitives
(spheres, boxes, boolean cuts) to approximate rough skull proportions so
that downstream tooling (glTF export, LOD switching, metadata↔mesh-name
wiring, viewer integration) can be exercised before real CT-derived
geometry exists. It must never be presented as satisfying the TOR's
accuracy requirements (section 0, section 8) — those require the real
CT-reconstruction pipeline described in ../pipeline/README.md.

Run inside Blender (tested against Blender 4.x):
    blender --background --python generate_placeholder_skull.py -- \\
        --out ../exports/placeholder_skull.glb

Produces two top-level objects, matching the two `movable`-relevant groups
in metadata/skull_metadata.json (cranium is fixed, mandible is separate so
it can later be rigged for open/close):
    - placeholder_cranium   (neurocranium + viscerocranium, fused)
    - placeholder_mandible  (separate object, positioned at approx TMJ height)
"""
import argparse
import sys

import bpy


def parse_args():
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="../exports/placeholder_skull.glb")
    return parser.parse_args(argv)


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def boolean_diff(target, cutter, apply=True):
    mod = target.modifiers.new(name="cut", type="BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.object = cutter
    if apply:
        bpy.context.view_layer.objects.active = target
        bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.data.objects.remove(cutter, do_unlink=True)


def build_cranium():
    # Rough neurocranium: ellipsoid, ~185mm long x 150mm wide x 135mm tall
    bpy.ops.mesh.primitive_uv_sphere_add(radius=1.0, location=(0, 0, 0.09))
    cranium = bpy.context.active_object
    cranium.name = "placeholder_cranium"
    cranium.scale = (0.0925, 0.075, 0.0675)  # meters -> ~185x150x135mm bbox
    bpy.ops.object.transform_apply(scale=True)

    # Hollow it (skull is a shell, not solid) via a solidify modifier instead
    # of a boolean cavity, to keep it watertight and cheap.
    solid = cranium.modifiers.new(name="shell", type="SOLIDIFY")
    solid.thickness = -0.006  # ~6mm compact+cancellous placeholder thickness
    bpy.context.view_layer.objects.active = cranium
    bpy.ops.object.modifier_apply(modifier=solid.name)

    # Orbits: two spherical cuts at the front for eye sockets
    for side, x in (("l", -0.03), ("r", 0.03)):
        bpy.ops.mesh.primitive_uv_sphere_add(
            radius=0.021, location=(x, -0.085, 0.10)
        )
        orbit = bpy.context.active_object
        orbit.name = f"cutter_orbit_{side}"
        boolean_diff(cranium, orbit)

    # Foramen magnum: cylindrical cut at the base
    bpy.ops.mesh.primitive_cylinder_add(
        radius=0.017, depth=0.05, location=(0, 0.01, 0.02)
    )
    fm = bpy.context.active_object
    fm.name = "cutter_foramen_magnum"
    boolean_diff(cranium, fm)

    # Nasal cavity: small cut below/between orbits
    bpy.ops.mesh.primitive_cube_add(size=0.03, location=(0, -0.09, 0.06))
    nasal = bpy.context.active_object
    nasal.name = "cutter_nasal_cavity"
    nasal.scale = (0.5, 1.2, 1.6)
    bpy.ops.object.transform_apply(scale=True)
    boolean_diff(cranium, nasal)

    return cranium


def build_mandible():
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, -0.06, -0.055))
    mandible = bpy.context.active_object
    mandible.name = "placeholder_mandible"
    mandible.scale = (0.075, 0.03, 0.018)
    bpy.ops.object.transform_apply(scale=True)

    bevel = mandible.modifiers.new(name="bevel", type="BEVEL")
    bevel.width = 0.012
    bevel.segments = 4
    bpy.context.view_layer.objects.active = mandible
    bpy.ops.object.modifier_apply(modifier=bevel.name)

    return mandible


def main():
    args = parse_args()
    clear_scene()

    cranium = build_cranium()
    mandible = build_mandible()

    for obj in (cranium, mandible):
        obj.select_set(True)
    bpy.context.view_layer.objects.active = cranium

    bpy.ops.export_scene.gltf(
        filepath=args.out,
        export_format="GLB",
        use_selection=False,
    )
    print(f"Wrote placeholder skull to {args.out}")


if __name__ == "__main__":
    main()
