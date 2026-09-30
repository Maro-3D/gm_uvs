"""Run in foreground Blender: validates the real GPU path missed by background tests."""
import sys
import traceback
from pathlib import Path
import bpy
from mathutils import Vector
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gm_uvs

gm_uvs.register()
drawn = set()
failures = []


def verify():
    try:
        from gm_uvs._univ import draw
        from gm_uvs._univ.draw import LinesDrawSimple, DotLinesDrawSimple
        assert draw.POLYLINE_UNIFORM_COLOR_2D is not None
        area = max(bpy.context.screen.areas, key=lambda area: area.width * area.height)
        area.type = "IMAGE_EDITOR"
        area.ui_type = "UV"
        for cls in (LinesDrawSimple, DotLinesDrawSimple):
            callback = cls.draw_callback_px.__func__

            def checked_callback(draw_class, callback=callback):
                try:
                    callback(draw_class)
                    drawn.add(draw_class.__name__)
                except Exception:
                    failures.append(traceback.format_exc())

            cls.draw_callback_px = classmethod(checked_callback)
            cls.draw_register([Vector((0, 0)), Vector((1, 1))])
            assert cls.batch is not None
        area.tag_redraw()
        bpy.app.timers.register(finish, first_interval=0.5)
    except Exception:
        traceback.print_exc()
        bpy.ops.wm.quit_blender()


def finish():
    try:
        from gm_uvs._univ.draw import LinesDrawSimple, DotLinesDrawSimple
        assert not failures, "\n".join(failures)
        assert drawn == {"LinesDrawSimple", "DotLinesDrawSimple"}, drawn
        gm_uvs.unregister()
        for cls in (LinesDrawSimple, DotLinesDrawSimple):
            assert cls.handler is None
            assert not bpy.app.timers.is_registered(cls.uv_area_draw_timer)
        # Disabling immediately after enabling must cancel shader startup too.
        gm_uvs.register()
        assert bpy.app.timers.is_registered(gm_uvs._init_shaders)
        gm_uvs.unregister()
        assert not bpy.app.timers.is_registered(gm_uvs._init_shaders)
        print("PASS: GPU shader batches and draw-handler cleanup", flush=True)
    except Exception:
        traceback.print_exc()
    finally:
        bpy.ops.wm.quit_blender()

bpy.app.timers.register(verify, first_interval=1.0)
