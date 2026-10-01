"""Selected edge aligns whole connected island without changing shape/selection."""
import sys
from pathlib import Path
from math import cos, sin
import bpy
import bmesh
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gm_uvs
gm_uvs.register()
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
mesh = bpy.data.meshes.new('EdgeAlignTest')
mesh.from_pydata([(0,0,0),(1,0,0),(2,0,0),(0,1,0),(1,1,0),(2,1,0),
                  (4,0,0),(5,0,0),(5,1,0),(4,1,0)], [], [(0,1,4,3),(1,2,5,4),(6,7,8,9)])
mesh.uv_layers.new()
obj = bpy.data.objects.new('EdgeAlignTest', mesh)
bpy.context.collection.objects.link(obj)
obj.select_set(True)
bpy.context.view_layer.objects.active = obj
bpy.ops.object.mode_set(mode='EDIT')
bm = bmesh.from_edit_mesh(mesh)
bm.faces.ensure_lookup_table()
uv = bm.loops.layers.uv.active
loops = [l for f in bm.faces for l in f.loops]
c,s = cos(.47),sin(.47)
for loop in loops:
    x,y = loop.vert.co.xy
    loop[uv].uv = (.2+.1*(c*x-s*y), .3+.1*(s*x+c*y))
for edge in bm.edges:
    if len(edge.link_faces) == 2:
        edge.seam = True  # A marked mesh seam does not split continuous UVs.
initial = [l[uv].uv.copy() for l in loops]
anchor = bm.faces[0].loops[0]
island = [l for f in list(bm.faces)[:2] for l in f.loops]
unrelated = [l for l in bm.faces[2].loops]
lengths = [(a[uv].uv-b[uv].uv).length for a in island for b in island]
area = bpy.context.screen.areas[0]
area.type = 'IMAGE_EDITOR'
area.ui_type = 'UV'
region = next(r for r in area.regions if r.type == 'WINDOW')
with bpy.context.temp_override(area=area, region=region):
    for sync in (False,True):
        for cache in ((False,True) if sync else (False,)):
            for direction,index in (('VERTICAL',0),('HORIZONTAL',1)):
                tools = bpy.context.scene.tool_settings
                tools.use_uv_select_sync = sync
                tools.mesh_select_mode = (False,True,False)
                tools.uv_select_mode = 'EDGE'
                for l,p in zip(loops,initial):
                    l[uv].uv = p
                for f in bm.faces:
                    f.select_set(not sync)
                    f.uv_select = False
                    for l in f.loops:
                        l.uv_select_edge = False
                        l.uv_select_vert = False
                for edge in bm.edges:
                    edge.select_set(False)
                if sync:
                    anchor.edge.select_set(True)
                    bm.select_flush_mode()
                    bm.select_history.clear()
                    bm.select_history.add(anchor.edge)
                anchor.uv_select_edge = True
                anchor.uv_select_vert = anchor.link_loop_next.uv_select_vert = True
                bm.uv_select_sync_valid = cache
                bmesh.update_edit_mesh(mesh)
                flags = [(l.uv_select_vert,l.uv_select_edge) for l in loops]
                assert bpy.ops.uv.gm_uvs_align_edge(direction=direction) == {'FINISHED'}
                delta = anchor.link_loop_next[uv].uv-anchor[uv].uv
                assert abs(delta[index]) < 1e-6, delta
                after = [(a[uv].uv-b[uv].uv).length for a in island for b in island]
                assert all(abs(a-b)<1e-6 for a,b in zip(lengths,after)), 'Island distorted'
                assert all((l[uv].uv-p).length<1e-6 for l,p in zip(unrelated,initial[-4:])), 'Unrelated island moved'
                assert flags == [(l.uv_select_vert,l.uv_select_edge) for l in loops]
gm_uvs.unregister()
print('PASS: whole island edge alignment, both axes, UV Sync/cache, seamless UV connectivity')
