"""Bundled UniV Weld regression; run with Blender --background --factory-startup."""
import sys
from pathlib import Path

import bmesh
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gm_uvs


def near(a, b, tolerance=1e-6):
    return abs(a - b) < tolerance


bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
gm_uvs.register()
assert "univ" not in sys.modules, "The test must not load the installed UniV extension"
area = bpy.context.screen.areas[0]
area.type = "IMAGE_EDITOR"
area.ui_type = "UV"
ui = next(region for region in area.regions if region.type == "UI")


def run_case(variant):
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    mesh = bpy.data.meshes.new("WeldTest")
    mesh.from_pydata(
        [(0, 0, 0), (1, 0, 0), (2, 0, 0),
         (0, 1, 0), (1, 1, 0), (2, 1, 0)],
        [], [(0, 1, 4, 3), (1, 2, 5, 4)],
    )
    mesh.uv_layers.new()
    obj = bpy.data.objects.new("WeldTest", mesh)
    bpy.context.collection.objects.link(obj)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bm = bmesh.from_edit_mesh(mesh)
    faces = list(bm.faces)
    uv_layer = bm.loops.layers.uv.active
    for face in faces:
        for loop in face.loops:
            x, y = loop.vert.co.xy
            shift = (
                0.3 if face is faces[1] and variant == "separate"
                else 0.1 if face is faces[1] and variant == "partial"
                    and loop.vert.index == 1
                else 0.0002 if face is faces[1] and variant == "distance"
                    and loop.vert.index == 1
                else 0.2 if face is faces[1] and variant == "paired"
                else 0.0
            )
            loop[uv_layer].uv = (0.1 + x * 0.2 + shift, 0.2 + y * 0.2)
    tools = bpy.context.scene.tool_settings
    tools.use_uv_select_sync = False
    tools.uv_select_mode = "EDGE"
    for face in faces:
        for loop in face.loops:
            loop.uv_select_edge = False
            loop.uv_select_vert = False
    shared = next(loop for loop in faces[0].loops
                  if loop.edge in set(faces[1].edges))
    shared.uv_select_edge = True
    shared.uv_select_vert = True
    shared.link_loop_next.uv_select_vert = True
    if variant == "paired":
        other = next(loop for loop in faces[1].loops if loop.edge is shared.edge)
        other.uv_select_edge = True
        other.uv_select_vert = True
        other.link_loop_next.uv_select_vert = True
    options = {}
    if variant == "distance":
        tools.uv_select_mode = "VERTEX"
        for face in faces:
            for loop in face.loops:
                loop.uv_select_vert = loop.vert.index == 1
        options = {"use_by_distance": True, "distance": 0.001,
                   "weld_by_distance_type": "ALL"}
    with bpy.context.temp_override(area=area, region=ui):
        assert bpy.ops.uv.gm_uvs_weld(**options) == {"FINISHED"}
    bm = bmesh.from_edit_mesh(mesh)
    bm.faces.ensure_lookup_table()
    return bm, list(bm.faces), bm.loops.layers.uv.active


for variant in ("separate", "partial", "paired", "distance"):
    bm, faces, uv_layer = run_case(variant)
    by_vertex = {
        vertex: [loop[uv_layer].uv.copy() for face in faces for loop in face.loops
                 if loop.vert.index == vertex]
        for vertex in (1, 4)
    }
    assert all((points[0] - points[1]).length < 1e-6
               for points in by_vertex.values()), variant
    if variant == "separate":
        assert near(faces[0].loops[1][uv_layer].uv.x, 0.3)
        assert near(faces[1].loops[1][uv_layer].uv.x, 0.5)
    if variant == "partial":
        assert near(faces[1].loops[0][uv_layer].uv.x, 0.3)
        assert near(faces[1].loops[1][uv_layer].uv.x, 0.5)
    if variant == "distance":
        assert near(by_vertex[1][0].x, 0.3001)

gm_uvs.unregister()
print("PASS: bundled UniV Weld, Stitch fallback, and distance mode")