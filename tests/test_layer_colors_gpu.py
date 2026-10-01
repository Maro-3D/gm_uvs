"""Foreground Blender test for persistent UV layer overlay and cleanup."""
import sys
import traceback
from pathlib import Path
import bpy
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gm_uvs
from gm_uvs import packing

failures = []
drawn = []
original = packing.draw_layer_colors


def checked_draw():
    try:
        original()
        if packing._overlay_shader is not None:
            drawn.append(True)
    except Exception:
        failures.append(traceback.format_exc())


packing.draw_layer_colors = checked_draw
gm_uvs.register()


def setup():
    try:
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        area = max(bpy.context.screen.areas, key=lambda a: a.width*a.height)
        area.type = 'IMAGE_EDITOR'
        area.ui_type = 'UV'
        region = next(r for r in area.regions if r.type == 'WINDOW')
        with bpy.context.temp_override(area=area, region=region):
            bpy.context.scene.tool_settings.use_uv_select_sync = True
            bpy.ops.uv.gm_uvs_pack_layer(action='ADD')
            bpy.ops.uv.gm_uvs_pack_layer(action='ASSIGN')
        area.tag_redraw()
        bpy.app.timers.register(finish, first_interval=1)
    except Exception:
        traceback.print_exc()
        bpy.ops.wm.quit_blender()


def finish():
    try:
        assert not failures, '\n'.join(failures)
        assert drawn, 'Layer overlay never drew'
        gm_uvs.unregister()
        assert packing._overlay_handler is None
        assert packing._overlay_shader is None
        gm_uvs.register()
        assert packing._overlay_handler is not None
        gm_uvs.unregister()
        assert packing._overlay_handler is None
        print('PASS: layer color GPU drawing and repeated cleanup', flush=True)
    except Exception:
        traceback.print_exc()
    finally:
        bpy.ops.wm.quit_blender()


bpy.app.timers.register(setup, first_interval=1)
