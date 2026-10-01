"""Up/down operators preserve layer identity and settings."""
import sys
from pathlib import Path
import bpy
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gm_uvs
gm_uvs.register()
bpy.ops.object.mode_set(mode='EDIT')
area = bpy.context.screen.areas[0]
area.type = 'IMAGE_EDITOR'
area.ui_type = 'UV'
region = next(r for r in area.regions if r.type == 'WINDOW')
scene = bpy.context.scene
for i in range(3):
    item = scene.gm_uvs_pack_layers.add()
    item.uid = i+1
    item.name = f'Layer {i+1}'
    item.color = (i/3, .2, .5)
before = {p.uid: (p.name, tuple(p.color), p.max_scale, p.visible, p.stack_matching) for p in scene.gm_uvs_pack_layers}
with bpy.context.temp_override(area=area, region=region):
    assert bpy.ops.uv.gm_uvs_pack_layer(action='UP') == {'CANCELLED'}
    assert bpy.ops.uv.gm_uvs_pack_layer(action='DOWN') == {'FINISHED'}
    assert [p.uid for p in scene.gm_uvs_pack_layers] == [2,1,3]
    assert scene.gm_uvs_pack_layer_index == 1
    assert bpy.ops.uv.gm_uvs_pack_layer(action='DOWN') == {'FINISHED'}
    assert scene.gm_uvs_pack_layer_index == 2
    assert bpy.ops.uv.gm_uvs_pack_layer(action='DOWN') == {'CANCELLED'}
    assert bpy.ops.uv.gm_uvs_pack_layer(action='UP') == {'FINISHED'}
    assert [p.uid for p in scene.gm_uvs_pack_layers] == [2,1,3]
assert {p.uid: (p.name, tuple(p.color), p.max_scale, p.visible, p.stack_matching) for p in scene.gm_uvs_pack_layers} == before
gm_uvs.unregister()
print('PASS: up/down reordering, boundaries, active index and settings')
