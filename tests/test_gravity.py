"""Native Gravity regression: run with Blender --background --factory-startup."""
import sys
from pathlib import Path
import bpy
import bmesh
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gm_uvs

gm_uvs.register()
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
mesh = bpy.data.meshes.new("GravityTest")
mesh.from_pydata(
    [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0),
     (2, 0, 0), (3, 0, 0), (3, 1, 0), (2, 1, 0)],
    [], [(0, 1, 2, 3), (4, 5, 6, 7)],
)
mesh.uv_layers.new()
obj = bpy.data.objects.new("GravityTest", mesh)
bpy.context.collection.objects.link(obj)
obj.select_set(True)
bpy.context.view_layer.objects.active = obj
bpy.ops.object.mode_set(mode="EDIT")
bm = bmesh.from_edit_mesh(mesh)
bm.faces.ensure_lookup_table()
layer = bm.loops.layers.uv.active
first, second = bm.faces[0], bm.faces[1]
for loop in first.loops:
    x, y = loop.vert.co.xy
    loop[layer].uv = (0.4 - y * 0.2, 0.3 + x * 0.2)
for loop in second.loops:
    x, y = loop.vert.co.xy
    loop[layer].uv = (0.5 + (x - 2) * 0.2, 0.5 + y * 0.2)
before_second = [tuple(loop[layer].uv) for loop in second.loops]
center_before = sum((loop[layer].uv for loop in first.loops), Vector((0, 0))) / 4
first.select_set(True)
second.select_set(False)
bpy.context.scene.tool_settings.use_uv_select_sync = True
bpy.context.scene.tool_settings.mesh_select_mode = (False, False, True)
area = bpy.context.screen.areas[0]
area.type = "IMAGE_EDITOR"
area.ui_type = "UV"
ui = next(r for r in area.regions if r.type == "UI")
with bpy.context.temp_override(area=area, region=ui):
    assert bpy.ops.uv.gm_uvs_gravity(axis="Z") == {"FINISHED"}
# Check the face's world X and Y directions now point along UV U and V.
by_vertex = {loop.vert.index: loop[layer].uv.copy() for loop in first.loops}
right = by_vertex[1] - by_vertex[0]
up = by_vertex[3] - by_vertex[0]
assert right.x > 0 and abs(right.y) < 1e-5, tuple(right)
assert up.y > 0 and abs(up.x) < 1e-5, tuple(up)
center_after = sum((loop[layer].uv for loop in first.loops), Vector((0, 0))) / 4
assert (center_after - center_before).length < 1e-5
assert before_second == [tuple(loop[layer].uv) for loop in second.loops]
gm_uvs.unregister()
print("PASS: native Z Gravity rotates selected island, preserves pivot and unselected island")

