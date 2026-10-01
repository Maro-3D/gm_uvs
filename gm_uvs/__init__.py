"""GM UVs entry point and Blender registration."""
import bpy
from bpy.props import BoolProperty, PointerProperty

from .transform import GMUVS_OT_align, GMUVS_OT_gravity, GMUVS_OT_mirror, GMUVS_OT_align_edge
from ._univ.quadrify import UNIV_OT_Quadrify
from ._univ.weld import UNIV_OT_Weld
from .ui import GMUVS_PT_main
from ._univ.preferences import GMUVS_PG_univ_settings
from ._univ import draw
from . import packing


class GMUVS_OT_quadrify(UNIV_OT_Quadrify):
    bl_idname = "uv.gm_uvs_quadrify"
    bl_label = "Quadrify"


class GMUVS_OT_weld(UNIV_OT_Weld):
    bl_idname = "uv.gm_uvs_weld"
    bl_label = "Weld UVs"


CLASSES = (
    GMUVS_PG_univ_settings, GMUVS_OT_align, GMUVS_OT_gravity, GMUVS_OT_mirror, GMUVS_OT_align_edge,
    GMUVS_OT_quadrify, GMUVS_OT_weld, *packing.CLASSES, GMUVS_PT_main,
)
QUADRIFY_SETTINGS = (
    ("gm_uvs_quad_mark_seams", "Mark Seams"),
    ("gm_uvs_quad_correct_aspect", "Correct Aspect"),
    ("gm_uvs_quad_scale_independently", "Scale Independently"),
)


def _init_shaders():
    draw.init_shaders()


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    packing.register_properties()
    bpy.types.Scene.gm_uvs_univ_settings = PointerProperty(type=GMUVS_PG_univ_settings)
    for name, label in QUADRIFY_SETTINGS:
        setattr(bpy.types.Scene, name, BoolProperty(name=label, default=True))
    if not bpy.app.background:
        bpy.app.timers.register(_init_shaders)


def _clear_draw_handlers():
    for draw_class in (draw.LinesDrawSimple, draw.DotLinesDrawSimple):
        timer = draw_class.uv_area_draw_timer
        if bpy.app.timers.is_registered(timer):
            bpy.app.timers.unregister(timer)
        if draw_class.handler is not None:
            bpy.types.SpaceImageEditor.draw_handler_remove(draw_class.handler, "WINDOW")
            draw_class.handler = None


def unregister():
    packing.unregister_properties()
    _clear_draw_handlers()
    if bpy.app.timers.is_registered(_init_shaders):
        bpy.app.timers.unregister(_init_shaders)
    for name, _label in reversed(QUADRIFY_SETTINGS):
        delattr(bpy.types.Scene, name)
    del bpy.types.Scene.gm_uvs_univ_settings
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
