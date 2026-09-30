# SPDX-FileCopyrightText: 2026 Oxicid
# SPDX-License-Identifier: GPL-3.0-or-later

"""Temporary UV seam and stitch overlays used by Weld."""
import bpy
import gpu
import mathutils
import numpy.typing as npt
from time import perf_counter as time
from gpu_extras.batch import batch_for_shader


POLYLINE_UNIFORM_COLOR_2D = None
VK_ENABLED = False


def init_shaders():
    global POLYLINE_UNIFORM_COLOR_2D, VK_ENABLED
    VK_ENABLED = gpu.platform.backend_type_get() == 'VULKAN'
    POLYLINE_UNIFORM_COLOR_2D = gpu.shader.from_builtin(
        'POLYLINE_UNIFORM_COLOR' if VK_ENABLED else 'UNIFORM_COLOR')


def set_line_width(width):
    if not VK_ENABLED:
        gpu.state.line_width_set(width)


def set_line_width_vk(shader, width=2.0):
    if VK_ENABLED:
        shader.uniform_float('viewportSize', gpu.state.viewport_get()[2:])
        shader.uniform_float('lineWidth', width)


def blend_set_alpha():
    gpu.state.blend_set('ALPHA')


def blend_set_none():
    gpu.state.blend_set('NONE')


class LinesDrawSimple:
    start_time = time()
    max_draw_time = 1.5
    handler: None = None
    shader: gpu.types.GPUShader | None = None
    batch: gpu.types.GPUBatch | None = None
    color: tuple = (1, 1, 0, 1)
    # target_area: bpy.types.Area = None

    @classmethod
    def draw_register(cls, data: list[mathutils.Vector] | npt.NDArray, color: tuple = (1, 1, 0, 1)):
        if not data:
            return
        cls.start_time = time()
        cls.color = color

        cls.shader = POLYLINE_UNIFORM_COLOR_2D
        cls.batch = batch_for_shader(cls.shader, 'LINES', {"pos": data})

        sima = bpy.types.SpaceImageEditor
        if not (cls.handler is None):
            sima.draw_handler_remove(cls.handler, 'WINDOW')

        cls.handler = sima.draw_handler_add(cls.draw_callback_px, (), 'WINDOW', 'POST_VIEW')
        bpy.app.timers.register(cls.uv_area_draw_timer)

    @classmethod
    def uv_area_draw_timer(cls):
        if cls.handler is None:
            cls.max_draw_time = 1.5
            return None
        counter = time() - cls.start_time

        if counter < cls.max_draw_time:
            return 0.2
        bpy.types.SpaceImageEditor.draw_handler_remove(cls.handler, 'WINDOW')

        for a in bpy.context.screen.areas:
            if a.type == 'IMAGE_EDITOR' and a.ui_type == 'UV':
                a.tag_redraw()

        cls.handler = None
        cls.max_draw_time = 1.5
        return None

    @classmethod
    def draw_callback_px(cls):
        if bpy.context.area.ui_type != 'UV':
            return

        set_line_width(2)
        blend_set_alpha()

        cls.shader.bind()
        cls.shader.uniform_float("color", cls.color)
        set_line_width_vk(cls.shader)
        cls.batch.draw(cls.shader)

        set_line_width(1)
        blend_set_none()


class DotLinesDrawSimple(LinesDrawSimple):
    start_time = time()
    max_draw_time = 1.5
    handler: None = None
    shader: gpu.types.GPUShader | None = None
    batch: gpu.types.GPUBatch | None = None
    color: tuple = (0, 1, 1, 1)
    # target_area: bpy.types.Area = None

    @classmethod
    def draw_register(cls, data: list[mathutils.Vector] | npt.NDArray, color: tuple = (0, 1, 1, 1)):
        if not data:
            return
        cls.start_time = time()
        cls.color = color

        if not cls.shader:
            cls.create_shader_info()

        arc_lengths = []
        arc_lengths_append = arc_lengths.append
        it = iter(data)
        for a in it:
            b = next(it)
            arc_lengths_append(0)
            arc_lengths_append((a - b).length)

        cls.batch = batch_for_shader(cls.shader, 'LINES', {"pos": data, 'arc_length': arc_lengths})

        sima = bpy.types.SpaceImageEditor
        if not (cls.handler is None):
            sima.draw_handler_remove(cls.handler, 'WINDOW')

        cls.handler = sima.draw_handler_add(cls.draw_callback_px, (), 'WINDOW', 'POST_VIEW')
        bpy.app.timers.register(cls.uv_area_draw_timer)


    @classmethod
    def draw_callback_px(cls):
        area = bpy.context.area
        if area.ui_type != 'UV':
            return

        set_line_width(3)
        blend_set_alpha()

        cls.shader.bind()

        from . import utypes
        reg = next(r for r in area.regions if r.type == 'WINDOW')
        zoom = utypes.View2D.get_zoom(reg.view2d) / 10

        matrix = gpu.matrix.get_projection_matrix()
        cls.shader.uniform_float("vpm", matrix)
        cls.shader.uniform_float("color", cls.color)
        cls.shader.uniform_float("scale", zoom)
        # set_line_width_vk(cls.shader)  # TODO: Dot shader not support line_width
        cls.batch.draw(cls.shader)

        set_line_width(1)
        blend_set_none()

    @classmethod
    def create_shader_info(cls):
        vert_out = gpu.types.GPUStageInterfaceInfo("my_interface")
        vert_out.smooth('FLOAT', "v_arc_length")

        shader_info = gpu.types.GPUShaderCreateInfo()
        shader_info.push_constant('MAT4', "vpm")
        shader_info.push_constant('FLOAT', "scale")
        shader_info.push_constant('VEC4', "color")
        shader_info.vertex_in(0, 'VEC2', "pos")
        shader_info.vertex_in(1, 'FLOAT', "arc_length")
        shader_info.vertex_out(vert_out)
        shader_info.fragment_out(0, 'VEC4', "out_color")

        shader_info.vertex_source(
            "void main()"
            "{"
            "  v_arc_length = arc_length;"
            "  gl_Position = vpm * vec4(pos, 0.0f, 1.0f);"
            "}"
        )

        shader_info.fragment_source(
            "void main()"
            "{"
            "  if (mod(v_arc_length, 1.0 / scale) > 0.4 / scale) discard;"
            "  out_color = color;"
            "}"
        )

        cls.shader = gpu.shader.create_from_info(shader_info)


def extract_edges_with_seams(umesh: 'utypes.UMesh'):
    edges = []
    edges_append = edges.append

    if umesh.is_full_face_selected:
        for e in umesh.bm.edges:
            if e.seam and hasattr(e, 'link_loops'):
                edges_append(e)
    else:
        if umesh.sync:
            for e in umesh.bm.edges:
                if e.seam and hasattr(e, 'link_loops'):
                    edges_append(e)
        else:
            if umesh.is_full_face_deselected:
                return []
            for e in umesh.bm.edges:
                if e.seam and hasattr(e, 'link_loops'):
                    edges_append(e)
    return edges
