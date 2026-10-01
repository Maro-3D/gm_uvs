"""Synthetic overlay CPU benchmark; run with Blender --background --python.

Reports warm ordinary redraw and pan/zoom preparation cost, not whole-app FPS.
"""
import sys
from pathlib import Path
from statistics import median
from time import perf_counter
from types import SimpleNamespace
import json
import bpy
import bmesh
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gm_uvs
from gm_uvs import packing
gm_uvs.register()
area = bpy.context.screen.areas[0]
area.type = 'IMAGE_EDITOR'
area.ui_type = 'UV'
region = next(r for r in area.regions if r.type == 'WINDOW')
layer = bpy.context.scene.gm_uvs_pack_layers.add()
layer.uid = 1
bpy.context.scene.tool_settings.use_uv_select_sync = True
for count in (1000, 10000):
    if bpy.context.object and bpy.context.object.mode == 'EDIT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    width, height = 100, count//100
    vertices = [(x/width,y/height,0) for y in range(height+1) for x in range(width+1)]
    faces = [(y*(width+1)+x,y*(width+1)+x+1,(y+1)*(width+1)+x+1,(y+1)*(width+1)+x)
             for y in range(height) for x in range(width)]
    mesh = bpy.data.meshes.new('OverlayBenchmark')
    mesh.from_pydata(vertices, [], faces)
    mesh.uv_layers.new()
    obj = bpy.data.objects.new('OverlayBenchmark', mesh)
    bpy.context.collection.objects.link(obj)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(mesh)
    uv = bm.loops.layers.uv.active
    attr = bm.faces.layers.int.new('gm_pack_' + uv.name)
    for face in bm.faces:
        face[attr] = 1
        face.select_set(True)
        for loop in face.loops:
            loop[uv].uv = loop.vert.co.xy
    bmesh.update_edit_mesh(mesh)
    with bpy.context.temp_override(area=area, region=region):
        start = perf_counter()
        packing.overlay_geometry(bpy.context)
        cold = (perf_counter()-start)*1000
        times = []
        for _ in range(5):
            start = perf_counter()
            packing.overlay_geometry(bpy.context)
            times.append((perf_counter()-start)*1000)
        context = SimpleNamespace(scene=bpy.context.scene, area=area, region=region,
            objects_in_mode_unique_data=bpy.context.objects_in_mode_unique_data,
            window=SimpleNamespace(as_pointer=bpy.context.window.as_pointer,
                modal_operators=[SimpleNamespace(bl_idname='VIEW2D_OT_pan')]))
        nav_times = []
        for _ in range(5):
            start = perf_counter()
            packing.overlay_geometry(context)
            nav_times.append((perf_counter()-start)*1000)
        context.window.modal_operators[0].bl_idname = 'TRANSFORM_OT_resize'
        transform_times = []
        for _ in range(5):
            packing._overlay_cache[packing._overlay_key(context)]['time'] = 0
            start = perf_counter()
            packing.overlay_geometry(context)
            transform_times.append((perf_counter()-start)*1000)
    print(json.dumps(dict(faces=count, cold_ms=round(cold,2), warm_ms=round(median(times),2),
                          navigation_ms=round(median(nav_times),2),
                          transform_refresh_ms=round(median(transform_times),2))), flush=True)
gm_uvs.unregister()
