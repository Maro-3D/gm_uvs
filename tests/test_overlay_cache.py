"""Warm redraw reuse, native mesh updates, and history invalidation."""
import sys
from pathlib import Path
import bpy
import bmesh
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gm_uvs
from gm_uvs import packing
gm_uvs.register()
bpy.ops.object.mode_set(mode='EDIT')
area = bpy.context.screen.areas[0]
area.type = 'IMAGE_EDITOR'
area.ui_type = 'UV'
region = next(r for r in area.regions if r.type == 'WINDOW')
with bpy.context.temp_override(area=area, region=region):
    bpy.context.scene.tool_settings.use_uv_select_sync = True
    bpy.ops.uv.select_all(action='SELECT')
    bpy.ops.uv.gm_uvs_pack_layer(action='ADD')
    bpy.ops.uv.gm_uvs_pack_layer(action='ASSIGN')
    bpy.context.view_layer.update()
    first = packing.overlay_geometry(bpy.context)
    second = packing.overlay_geometry(bpy.context)
    assert first[0][1] is second[0][1], 'Warm redraw rebuilt coordinate data'
    old = list(first[0][1])
    bm = bmesh.from_edit_mesh(bpy.context.object.data)
    uv = bm.loops.layers.uv.active
    next(iter(bm.faces)).loops[0][uv].uv.x += .123
    bmesh.update_edit_mesh(bpy.context.object.data)
    bpy.context.view_layer.update()
    changed = packing.overlay_geometry(bpy.context)
    assert old != changed[0][1], 'Native UV coordinate changes did not invalidate cache'
    bpy.context.scene.tool_settings.use_uv_select_sync = False
    assert packing.overlay_geometry(bpy.context)
    bpy.ops.mesh.select_all(action='DESELECT')
    bpy.context.view_layer.update()
    assert not packing.overlay_geometry(bpy.context), 'Invisible unselected faces remained cached'
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.context.view_layer.update()
    assert packing.overlay_geometry(bpy.context)
    bpy.context.scene.tool_settings.use_uv_select_sync = True
    bpy.ops.uv.select_all(action='DESELECT')
    bpy.ops.uv.select_all(action='SELECT')
    bpy.context.view_layer.update()
    packing.overlay_geometry(bpy.context)
    packing._overlay_history_changed()
    assert not packing._overlay_sources and not packing._overlay_cache and not packing._overlay_batches
    assert packing.overlay_geometry(bpy.context)
gm_uvs.unregister()
print('PASS: overlay cache reuse, native UV update, history invalidation')
