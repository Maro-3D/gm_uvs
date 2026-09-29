"""Run in foreground Blender: validates the real GPU path missed by background tests."""
import sys
import traceback
from pathlib import Path
import bpy
from mathutils import Vector
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gm_uvs

gm_uvs.register()


def verify():
    try:
        from gm_uvs._univ.draw import shaders, LinesDrawSimple, DotLinesDrawSimple
        assert shaders.POLYLINE_UNIFORM_COLOR_2D is not None
        for cls in (LinesDrawSimple, DotLinesDrawSimple):
            cls.draw_register([Vector((0, 0)), Vector((1, 1))])
            assert cls.batch is not None
        gm_uvs.unregister()
        for cls in (LinesDrawSimple, DotLinesDrawSimple):
            assert cls.handler is None
        print("PASS: GPU shader batches and draw-handler cleanup", flush=True)
    except Exception:
        traceback.print_exc()
    finally:
        bpy.ops.wm.quit_blender()

bpy.app.timers.register(verify, first_interval=1.0)
