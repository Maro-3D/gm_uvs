"""Run with Blender --background --factory-startup --python-exit-code 1."""
import sys
from pathlib import Path

import bmesh
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gm_uvs


def near(a, b, tolerance=1e-5):
    return (a - b).length < tolerance


bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
mesh = bpy.data.meshes.new("QuadWeldTest")
mesh.from_pydata(
    [(0, 0, 0), (1, 0, 0), (2, 0, 0),
     (0, 1, 0), (1, 1, 0), (2, 1, 0)],
    [], [(0, 1, 4, 3), (1, 2, 5, 4)],
)
mesh.uv_layers.new()
obj = bpy.data.objects.new("QuadWeldTest", mesh)
bpy.context.collection.objects.link(obj)
obj.select_set(True)
bpy.context.view_layer.objects.active = obj
bpy.ops.object.mode_set(mode="EDIT")
area = bpy.context.screen.areas[0]
area.type = "IMAGE_EDITOR"
area.ui_type = "UV"
ui = next(region for region in area.regions if region.type == "UI")
bm = bmesh.from_edit_mesh(mesh)
bm.faces.ensure_lookup_table()
uv = bm.loops.layers.uv.active
faces = list(bm.faces)
for face in faces:
    face.select_set(True)
    for loop in face.loops:
        x, y = loop.vert.co.xy
        loop[uv].uv = (0.1 + 0.2 * x + 0.03 * y, 0.2 + 0.2 * y + 0.02 * x)
bpy.context.scene.tool_settings.use_uv_select_sync = True
bpy.context.scene.tool_settings.mesh_select_mode = (False, False, True)
bpy.ops.mesh.select_all(action='SELECT')
gm_uvs.register()
with bpy.context.temp_override(area=area, region=ui):
    assert bpy.ops.uv.gm_uvs_quadrify() == {"FINISHED"}
for face in faces:
    points = [loop[uv].uv.copy() for loop in face.loops]
    for index in range(4):
        edge = points[(index + 1) % 4] - points[index]
        assert abs(edge.x) < 1e-5 or abs(edge.y) < 1e-5, (index, tuple(edge))
for vertex_index in (1, 4):
    points = [loop[uv].uv.copy() for face in faces for loop in face.loops
              if loop.vert.index == vertex_index]
    assert near(points[0], points[1]), [tuple(point) for point in points]

shared = next(loop for loop in faces[0].loops if loop.edge in set(faces[1].edges))

# Scale Independently changes the UV proportions; Correct Aspect uses image pixels.
assert bpy.context.scene.gm_uvs_quad_mark_seams
assert bpy.context.scene.gm_uvs_quad_correct_aspect
assert bpy.context.scene.gm_uvs_quad_scale_independently
for vert in bm.verts:
    vert.co.x *= 2
bpy.context.scene.tool_settings.use_uv_select_sync = False
bpy.context.scene.tool_settings.uv_select_mode = "VERTEX"
for face in faces:
    face.select_set(True)
for face in faces:
    for loop in face.loops:
        loop.uv_select_vert = face is faces[0]
        loop.uv_select_edge = face is faces[0]
    face.uv_select = face is faces[0]
image = bpy.data.images.new("AspectTest", width=512, height=256)
area.spaces.active.image = image
material = bpy.data.materials.new('AspectMaterial')
material.use_nodes = True
node = material.node_tree.nodes.new('ShaderNodeTexImage')
node.image = image
material.node_tree.nodes.active = node
mesh.materials.append(material)

def reset_square():
    for loop in faces[0].loops:
        x, y = loop.vert.co.xy
        loop[uv].uv = (0.1 + x * 0.1, 0.1 + y * 0.2)

def uv_ratio():
    points = [loop[uv].uv for loop in faces[0].loops]
    return ((max(p.x for p in points) - min(p.x for p in points)) /
            (max(p.y for p in points) - min(p.y for p in points)))

reset_square()
with bpy.context.temp_override(area=area, region=ui):
    assert bpy.ops.uv.gm_uvs_quadrify(mark_seam=False,
        xy_scale=False, use_aspect=True) == {"FINISHED"}
assert abs(uv_ratio() - 1.0) < 1e-4, uv_ratio()
reset_square()
with bpy.context.temp_override(area=area, region=ui):
    assert bpy.ops.uv.gm_uvs_quadrify(mark_seam=False,
        xy_scale=True, use_aspect=False) == {"FINISHED"}
assert abs(uv_ratio() - 2.0) < 1e-4, uv_ratio()
reset_square()
with bpy.context.temp_override(area=area, region=ui):
    assert bpy.ops.uv.gm_uvs_quadrify(mark_seam=False,
        xy_scale=True, use_aspect=True) == {"FINISHED"}
assert abs(uv_ratio() - 1.0) < 1e-4, uv_ratio()

# Mark Seams follows the option on a selected quad's split boundary.
shared.edge.seam = False
reset_square()
with bpy.context.temp_override(area=area, region=ui):
    assert bpy.ops.uv.gm_uvs_quadrify(mark_seam=True,
        xy_scale=True, use_aspect=True) == {"FINISHED"}
assert shared.edge.seam
shared.edge.seam = False
reset_square()
with bpy.context.temp_override(area=area, region=ui):
    assert bpy.ops.uv.gm_uvs_quadrify(mark_seam=False,
        xy_scale=True, use_aspect=True) == {"FINISHED"}
assert not shared.edge.seam

gm_uvs.unregister()
print("PASS: UniV Quadrify options and UV grid layout")