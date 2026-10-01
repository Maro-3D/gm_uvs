"""Layer assignment, constrained packing, bounds, coverage, and lifecycle."""
import sys
from pathlib import Path
import bpy
import bmesh

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gm_uvs
from gm_uvs.packing import records, arrange

gm_uvs.register()
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
mesh = bpy.data.meshes.new('PackingTest')
mesh.from_pydata([(0,0,0),(1,0,0),(1,1,0),(0,1,0),
                  (2,0,0),(3,0,0),(3,1,0),(2,1,0)], [], [(0,1,2,3),(4,5,6,7)])
mesh.uv_layers.new()
obj = bpy.data.objects.new('PackingTest', mesh)
bpy.context.collection.objects.link(obj)
obj.select_set(True)
bpy.context.view_layer.objects.active = obj
bpy.ops.object.mode_set(mode='EDIT')
bm = bmesh.from_edit_mesh(mesh)
uv = bm.loops.layers.uv.active
for i, face in enumerate(bm.faces):
    face.select_set(True)
    face.uv_select = i == 0
    for loop, p in zip(face.loops, [(0,0),(.4,0),(.4,.4),(0,.4)]):
        loop[uv].uv = p
        loop.uv_select_vert = i == 0
        loop.uv_select_edge = i == 0
bmesh.update_edit_mesh(mesh)
area = bpy.context.screen.areas[0]
area.type = 'IMAGE_EDITOR'
area.ui_type = 'UV'
region = next(r for r in area.regions if r.type == 'WINDOW')
with bpy.context.temp_override(area=area, region=region):
    bpy.context.scene.tool_settings.use_uv_select_sync = False
    bpy.context.scene.tool_settings.uv_select_mode = 'FACE'
    for i, face in enumerate(bm.faces):
        face.uv_select = i == 0
        for loop in face.loops:
            loop.uv_select_vert = i == 0
            loop.uv_select_edge = i == 0
    bmesh.update_edit_mesh(mesh)
    assert bpy.ops.uv.gm_uvs_pack_layer(action='ADD') == {'FINISHED'}
    bpy.context.scene.gm_uvs_pack_layers[0].max_scale = .5
    assert bpy.ops.uv.gm_uvs_pack_layer(action='ASSIGN') == {'FINISHED'}
    items = records(bpy.context)
    assert sorted(r[5] != 0 for r in items) == [False, True]
    # Preview changes size immediately, then restores without accumulating.
    layer = bpy.context.scene.gm_uvs_pack_layers[0]
    for value in (.25, .75, 1.0, .5):
        layer.max_scale = value
        for _, _, uv, _, loops, uid in records(bpy.context):
            width = max(loop[uv].uv.x for loop in loops)-min(loop[uv].uv.x for loop in loops)
            assert abs(width - (.4*value if uid else .4)) < 1e-5
    uid = bpy.context.scene.gm_uvs_pack_layers[0].uid
    for sync in (False, True):
        bpy.context.scene.tool_settings.use_uv_select_sync = sync
        assert bpy.ops.uv.gm_uvs_pack_layer(action='SELECT', layer_uid=uid) == {'FINISHED'}
        for _, _, _, faces, loops, assigned in records(bpy.context):
            assert all(loop.uv_select_vert == (assigned == uid) for loop in loops)
            assert all(loop.uv_select_edge == (assigned == uid) for loop in loops)
            if sync:
                assert all(face.select == (assigned == uid) for face in faces)
    from gm_uvs.packing import overlay_geometry
    geometry = overlay_geometry(bpy.context)
    assert len(geometry) == 1
    assert len(geometry[0][1]) == 8 and len(geometry[0][2]) == 6
    assert bpy.ops.uv.gm_uvs_pack() == {'FINISHED'}
    # One square at half size, one unchanged: .04 + .16 = 20%.
    assert abs(bpy.context.scene.gm_uvs_pack_coverage - 20) < 1e-4
    assert bpy.ops.uv.gm_uvs_pack() == {'FINISHED'}
    assert abs(bpy.context.scene.gm_uvs_pack_coverage - 20) < 1e-4, 'Repeated pack compounded scale limit'
    for _, _, uv, _, loops, uid in records(bpy.context):
        coords = [loop[uv].uv for loop in loops]
        assert all(-1e-6 <= value <= 1+1e-6 for p in coords for value in p)
        width = max(p.x for p in coords)-min(p.x for p in coords)
        assert abs(width - (.2 if uid else .4)) < 1e-5
    layer.max_scale = 1.0
    for _, _, uv, _, loops, uid in records(bpy.context):
        width = max(loop[uv].uv.x for loop in loops)-min(loop[uv].uv.x for loop in loops)
        assert abs(width-.4) < 1e-5, 'Original size did not restore after packing'
    # Eye hides assigned faces and packing ignores them; reveal preserves
    # unrelated and independently hidden faces.
    layer.visible = False
    assert len(records(bpy.context)) == 1
    assert all(r[5] == 0 for r in records(bpy.context))
    assert bpy.ops.uv.gm_uvs_pack() == {'FINISHED'}
    assert abs(bpy.context.scene.gm_uvs_pack_coverage-16) < 1e-4
    layer.visible = True
    assert len(records(bpy.context)) == 2
    assigned_faces = [f for _, _, _, faces, _, assigned in records(bpy.context) if assigned for f in faces]
    for face in assigned_faces:
        face.hide_set(True)
    layer.visible = False
    layer.visible = True
    assert len(records(bpy.context)) == 1, 'Revealed independently hidden faces'
    for face in bm.faces:
        face.hide_set(False)
    layer.visible = False
    assert bpy.ops.uv.gm_uvs_pack_layer(action='SELECT', layer_uid=uid) == {'FINISHED'}
    assert layer.visible and len(records(bpy.context)) == 2
    layer.visible = False
    assert bpy.ops.uv.gm_uvs_pack_layer(action='REMOVE') == {'FINISHED'}
    assert len(records(bpy.context)) == 2, 'Removing layer left its islands hidden'
    assert all(r[5] == 0 for r in records(bpy.context))

# Dense arrangements remain disjoint, including rotation and varying caps.
sizes = [(.17, .09, 1)] * 30
placements = arrange(sizes, 1, .003, True)
assert placements is not None
boxes = []
for i, (x, y, turn, scale) in placements.items():
    w, h, _ = sizes[i]
    if turn:
        w, h = h, w
    boxes.append((x, y, x+w*scale, y+h*scale))
for i, a in enumerate(boxes):
    for b in boxes[i+1:]:
        assert a[2] <= b[0]+1e-8 or b[2] <= a[0]+1e-8 or a[3] <= b[1]+1e-8 or b[3] <= a[1]+1e-8
gm_uvs.unregister()
assert not hasattr(bpy.types.Scene, 'gm_uvs_pack_layers')
print('PASS: packing layers, limits, coverage, bounds, non-overlap, cleanup')
