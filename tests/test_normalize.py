"""Quadrify normalization across quad groups connected by a non-quad face."""
import sys
from itertools import product
from pathlib import Path

import bmesh
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gm_uvs


gm_uvs.register()
area = bpy.context.screen.areas[0]
area.type = "IMAGE_EDITOR"
area.ui_type = "UV"
region = next(region for region in area.regions if region.type == "UI")
# Recorded from the original add-on on Blender 5.0.1. In particular, preserve
# the existing order of normalization and texel scaling for connected groups.
expected_densities = {
    (False, False, False): (0.02460326, 0.02937918),
    (False, False, True): (0.0625, 0.0625),
    (False, True, False): (0.02937918, 0.02937918),
    (False, True, True): (0.07463233, 0.0625),
    (True, False, False): (0.02937918, 0.02937918),
    (True, False, True): (0.07463233, 0.0625),
    (True, True, False): (0.02937918, 0.02937918),
    (True, True, True): (0.07463233, 0.0625),
}

for shear, xy_scale, use_texel in product((False, True), repeat=3):
    if bpy.context.object and bpy.context.object.mode == "EDIT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    mesh = bpy.data.meshes.new("NormalizeTest")
    mesh.from_pydata(
        [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0),
         (2, 0, 0), (4, 0, 0), (4, 1, 0)],
        [], [(0, 1, 2, 3), (1, 4, 2), (4, 5, 6, 2)],
    )
    mesh.uv_layers.new()
    obj = bpy.data.objects.new("NormalizeTest", mesh)
    bpy.context.collection.objects.link(obj)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bm = bmesh.from_edit_mesh(mesh)
    uv = bm.loops.layers.uv.active
    for face in bm.faces:
        for loop in face.loops:
            x, y = loop.vert.co.xy
            loop[uv].uv = (0.1 + x * 0.12 + y * 0.03,
                           0.2 + y * 0.2 + x * 0.02)
    bpy.context.scene.tool_settings.use_uv_select_sync = True
    bpy.context.scene.tool_settings.mesh_select_mode = (False, False, True)
    bpy.context.scene.gm_uvs_univ_settings.use_texel = use_texel
    with bpy.context.temp_override(area=area, region=region):
        assert bpy.ops.uv.gm_uvs_quadrify(
            shear=shear, xy_scale=xy_scale, use_aspect=False, unlink=True,
        ) == {"FINISHED"}

    # Check both groups, including the multi-island averaging path that a
    # single-quad or connected all-quad grid cannot exercise.
    densities = []
    for face in bm.faces:
        if len(face.loops) != 4:
            continue
        area_uv = abs(sum(loop[uv].uv.cross(loop.link_loop_next[uv].uv)
                          for loop in face.loops)) / 2
        assert area_uv > 0
        densities.append(area_uv / face.calc_area())
    expected = expected_densities[shear, xy_scale, use_texel]
    assert all(abs(actual - baseline) < 1e-6
               for actual, baseline in zip(densities, expected)), densities

gm_uvs.unregister()
print("PASS: eight multi-group Quadrify shear, scale, and texel-density cases")
