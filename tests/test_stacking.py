"""Live matching, nonmatching islands, scale preview, persistent packed stacks."""
import sys
from pathlib import Path
import bpy
import bmesh
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gm_uvs
from gm_uvs.packing import records
gm_uvs.register()
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
mesh = bpy.data.meshes.new('StackTest')
verts = [(i*2+x,y,0) for i in range(3) for x,y in [(0,0),(1,0),(1,1),(0,1)]]
mesh.from_pydata(verts, [], [tuple(range(i*4,i*4+4)) for i in range(3)])
mesh.uv_layers.new()
obj = bpy.data.objects.new('StackTest', mesh)
bpy.context.collection.objects.link(obj)
obj.select_set(True)
bpy.context.view_layer.objects.active = obj
bpy.ops.object.mode_set(mode='EDIT')
bm = bmesh.from_edit_mesh(mesh)
uv = bm.loops.layers.uv.active
for i, face in enumerate(bm.faces):
    face.select_set(True)
    w,h = ((.2,.2),(.4,.4),(.3,.15))[i]
    for loop, (x,y) in zip(face.loops, [(0,0),(w,0),(w,h),(0,h)]):
        loop[uv].uv = (i+x,y) if i != 1 else (i-y,x)
area = bpy.context.screen.areas[0]
area.type = 'IMAGE_EDITOR'
area.ui_type = 'UV'
region = next(r for r in area.regions if r.type == 'WINDOW')
with bpy.context.temp_override(area=area, region=region):
    bpy.context.scene.tool_settings.use_uv_select_sync = True
    bpy.ops.uv.select_all(action='SELECT')
    bpy.ops.uv.gm_uvs_pack_layer(action='ADD')
    bpy.ops.uv.gm_uvs_pack_layer(action='ASSIGN')
    layer = bpy.context.scene.gm_uvs_pack_layers[0]
    layer.stack_matching = True

    def points():
        return [{(round(l[uv].uv.x,5),round(l[uv].uv.y,5)) for l in f.loops} for f in bm.faces]

    p = points()
    assert p[0] == p[1] and p[0] != p[2], p
    layer.max_scale = .5
    p = points()
    assert p[0] == p[1]
    for _ in range(2):
        assert bpy.ops.uv.gm_uvs_pack() == {'FINISHED'}
        p = points()
        assert p[0] == p[1] and p[0] != p[2]
        assert abs(bpy.context.scene.gm_uvs_pack_coverage-2.125) < 1e-4, bpy.context.scene.gm_uvs_pack_coverage
    layer.stack_matching = False
    layer.max_scale = 1
    widths = [max(l[uv].uv.x for l in f.loops)-min(l[uv].uv.x for l in f.loops) for f in bm.faces]
    assert abs(widths[0]-.2) < 1e-5 and abs(widths[1]-.4) < 1e-5, widths
    bpy.ops.uv.gm_uvs_pack()
    p = points()
    assert p[0] != p[1]
gm_uvs.unregister()
print('PASS: live matching stacks, unmatched islands, limits, unique coverage, unstacked packing')
