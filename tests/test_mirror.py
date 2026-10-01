"""Horizontal/vertical UV mirrors preserve bounds and reverse on second use."""
import sys
from pathlib import Path
import bpy
import bmesh
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gm_uvs
gm_uvs.register()
bpy.ops.object.mode_set(mode='EDIT')
obj = bpy.context.object
bm = bmesh.from_edit_mesh(obj.data)
uv = bm.loops.layers.uv.active
loops = [l for f in bm.faces for l in f.loops]
initial = [l[uv].uv.copy() for l in loops]
area = bpy.context.screen.areas[0]
area.type = 'IMAGE_EDITOR'
area.ui_type = 'UV'
region = next(r for r in area.regions if r.type == 'WINDOW')
with bpy.context.temp_override(area=area, region=region):
    for sync in (False, True):
        bpy.context.scene.tool_settings.use_uv_select_sync = sync
        bpy.ops.uv.select_all(action='SELECT')
        for axis, index in (('X', 0), ('Y', 1)):
            total = min(p[index] for p in initial)+max(p[index] for p in initial)
            assert bpy.ops.uv.gm_uvs_mirror(axis=axis) == {'FINISHED'}
            for loop, p in zip(loops, initial):
                expected = p.copy()
                expected[index] = total-p[index]
                assert (loop[uv].uv-expected).length < 1e-6
            bpy.ops.uv.gm_uvs_mirror(axis=axis)
            assert all((l[uv].uv-p).length < 1e-6 for l,p in zip(loops, initial))
gm_uvs.unregister()
print('PASS: Mirror X/Y and restore with UV Sync on/off')
