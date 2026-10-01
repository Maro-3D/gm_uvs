"""Real S/mouse/confirm UV transform with a redraw between every event.

Run foreground Blender with --enable-event-simulate.
"""
import sys
import traceback
from pathlib import Path
import bpy
import bmesh
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gm_uvs
from gm_uvs import packing

gm_uvs.register()
state = {}
errors = []
modal_draws = []
original_records = packing.records
original_geometry = packing.overlay_geometry


def checked_records(context):
    if context.window and context.window.modal_operators:
        errors.append('Overlay acquired an edit BMesh during a modal transform')
    return original_records(context)


def checked_geometry(context):
    try:
        result = original_geometry(context)
        if context.window and context.window.modal_operators:
            modal_draws.append(result)
        return result
    except Exception:
        errors.append(traceback.format_exc())
        return []


packing.records = checked_records
packing.overlay_geometry = checked_geometry


def setup():
    try:
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        mesh = bpy.data.meshes.new('ModalUV')
        mesh.from_pydata([(0,0,0),(1,0,0),(2,0,0),(0,1,0),(1,1,0),(2,1,0)], [], [(0,1,4,3),(1,2,5,4)])
        mesh.uv_layers.new()
        obj = bpy.data.objects.new('ModalUV', mesh)
        bpy.context.collection.objects.link(obj)
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode='EDIT')
        bm = bmesh.from_edit_mesh(mesh)
        uv = bm.loops.layers.uv.active
        attr = bm.faces.layers.int.new('gm_pack_' + uv.name)
        for i, face in enumerate(bm.faces):
            face[attr] = 123 if i == 0 else 0
            for loop, p in zip(face.loops, [(0,0),(.3,0),(.3,.3),(0,.3)]):
                loop[uv].uv = (p[0]+i*.5, p[1])
        layer = bpy.context.scene.gm_uvs_pack_layers.add()
        layer.uid = 123
        area = max(bpy.context.screen.areas, key=lambda a: a.width*a.height)
        area.type = 'IMAGE_EDITOR'
        area.ui_type = 'UV'
        region = next(r for r in area.regions if r.type == 'WINDOW')
        tools = bpy.context.scene.tool_settings
        tools.use_uv_select_sync = True
        tools.mesh_select_mode = (True, False, False)
        with bpy.context.temp_override(area=area, region=region):
            bpy.ops.uv.gm_uvs_pack_layer(action='SELECT', layer_uid=123)
        state.update(mesh=mesh, bm=bm, uv=uv, area=area, region=region, step=0)
        state['points'] = [loop[uv].uv for face in bm.faces for loop in face.loops]
        state['initial'] = [p.copy() for p in state['points']]
        state['x'], state['y'] = region.x+region.width//2, region.y+region.height//2
        bpy.app.timers.register(step, first_interval=.5)
    except Exception:
        traceback.print_exc()
        bpy.ops.wm.quit_blender()


def step():
    try:
        window = bpy.context.window_manager.windows[0]
        x, y = state['x'], state['y']
        n = state['step']
        if n == 0:
            window.event_simulate(type='MOUSEMOVE', value='NOTHING', x=x, y=y)
        elif n == 1:
            with bpy.context.temp_override(window=window, area=state['area'], region=state['region']):
                result = bpy.ops.transform.resize('INVOKE_DEFAULT')
                assert result == {'RUNNING_MODAL'}, result
        elif n in (2, 3, 4):
            assert any(op.bl_idname == 'TRANSFORM_OT_resize' for op in window.modal_operators), list(window.modal_operators)
            window.event_simulate(type='MOUSEMOVE', value='NOTHING', x=x+40*(n-1), y=y+20*(n-1))
        elif n == 5:
            window.event_simulate(type='LEFTMOUSE', value='PRESS', x=x+120, y=y+60)
            window.event_simulate(type='LEFTMOUSE', value='RELEASE', x=x+120, y=y+60)
        elif n == 6:
            state['pan_start'] = len(modal_draws)
            with bpy.context.temp_override(window=window, area=state['area'], region=state['region']):
                result = bpy.ops.view2d.pan('INVOKE_DEFAULT')
                assert result == {'RUNNING_MODAL'}, result
        elif n == 7:
            assert any(op.bl_idname == 'VIEW2D_OT_pan' for op in window.modal_operators)
            window.event_simulate(type='MOUSEMOVE', value='NOTHING', x=x+170, y=y+90)
        elif n == 8:
            window.event_simulate(type='MIDDLEMOUSE', value='RELEASE', x=x+170, y=y+90)
        else:
            points = [p.copy() for p in state['points']]
            initial = state['initial']
            assert all((a-b).length < 1e-6 for a,b in zip(points[4:], initial[4:])), 'Other island moved'
            edges = [(points[(i+1)%4]-points[i]).length for i in range(4)]
            assert max(edges)-min(edges) < 1e-5, edges
            assert abs(edges[0]-.3) > 1e-4, 'Mouse did not scale UVs'
            assert not errors, errors
            assert modal_draws and all(g for g in modal_draws), 'Colors disappeared during scale'
            assert modal_draws[0] != modal_draws[-1], 'Colors did not follow mouse scaling'
            assert len(modal_draws) > state['pan_start'], 'Overlay did not draw during pan'
            print('PASS: interactive scaling and middle-mouse pan keep layer colors visible', flush=True)
            gm_uvs.unregister()
            bpy.ops.wm.quit_blender()
            return None
        state['step'] += 1
        state['area'].tag_redraw()
        return .3
    except Exception:
        traceback.print_exc()
        bpy.ops.wm.quit_blender()
        return None


bpy.app.timers.register(setup, first_interval=1)
