"""Native UV scaling after layer selection on shared mesh vertices."""
import sys
from pathlib import Path
import bpy
import bmesh
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gm_uvs
gm_uvs.register()
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
mesh = bpy.data.meshes.new('SharedVertices')
mesh.from_pydata([(0,0,0),(1,0,0),(2,0,0),(0,1,0),(1,1,0),(2,1,0)], [], [(0,1,4,3),(1,2,5,4)])
mesh.uv_layers.new()
obj = bpy.data.objects.new('SharedVertices', mesh)
bpy.context.collection.objects.link(obj)
obj.select_set(True)
bpy.context.view_layer.objects.active = obj
bpy.ops.object.mode_set(mode='EDIT')
bm = bmesh.from_edit_mesh(mesh)
uv = bm.loops.layers.uv.active
attr = bm.faces.layers.int.new('gm_pack_' + uv.name)
bm.faces.ensure_lookup_table()
layer = bpy.context.scene.gm_uvs_pack_layers.add()
layer.uid = 123
for i, face in enumerate(bm.faces):
    face[attr] = 123 if i == 0 else 0
    for loop, p in zip(face.loops, [(0,0),(.3,0),(.3,.3),(0,.3)]):
        loop[uv].uv = (p[0]+i*.5, p[1])
initial = [[loop[uv].uv.copy() for loop in f.loops] for f in bm.faces]
area = bpy.context.screen.areas[0]
area.type = 'IMAGE_EDITOR'
area.ui_type = 'UV'
region = next(r for r in area.regions if r.type == 'WINDOW')
with bpy.context.temp_override(area=area, region=region):
    for sync in (False, True):
        for mode in ((True,False,False),(False,True,False),(False,False,True)):
            tools = bpy.context.scene.tool_settings
            tools.use_uv_select_sync = sync
            tools.mesh_select_mode = mode
            for face, coords in zip(bm.faces, initial):
                for loop, p in zip(face.loops, coords):
                    loop[uv].uv = p
            bpy.ops.uv.gm_uvs_pack_layer(action='SELECT', layer_uid=123)
            bpy.ops.transform.resize(value=(2,2,2), center_override=(0,0,0))
            for i, face in enumerate(bm.faces):
                for loop, p in zip(face.loops, initial[i]):
                    expected = p * (2 if i == 0 else 1)
                    assert (loop[uv].uv-expected).length < 1e-6, (sync, mode, i, tuple(loop[uv].uv), tuple(expected))
from gm_uvs import packing
for name in ('VIEW2D_OT_pan', 'VIEW2D_OT_zoom', 'IMAGE_OT_view_pan',
             'IMAGE_OT_view_zoom', 'TRANSFORM_OT_resize'):
    assert packing._overlay_modal_is_safe(SimpleNamespace(bl_idname=name))
assert not packing._overlay_modal_is_safe(SimpleNamespace(bl_idname='MESH_OT_extrude_region_move'))
modal_context = SimpleNamespace(
    space_data=SimpleNamespace(type='IMAGE_EDITOR', mode='UV'),
    mode='EDIT_MESH', scene=SimpleNamespace(gm_uvs_pack_show_colors=True, gm_uvs_pack_layers=[]),
    window=SimpleNamespace(modal_operators=[SimpleNamespace(bl_idname='TRANSFORM_OT_resize')], as_pointer=lambda: 987),
    region=SimpleNamespace(view2d=None))
with patch.object(packing, 'bpy', SimpleNamespace(context=modal_context)), \
     patch.object(packing, 'records', side_effect=AssertionError('Acquired mesh during transform')):
    assert packing.overlay_geometry(modal_context) == []
gm_uvs.unregister()
print('PASS: native UV scale preserves layer islands in all sync mesh modes')
