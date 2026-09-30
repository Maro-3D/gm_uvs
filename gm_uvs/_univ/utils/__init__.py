# SPDX-FileCopyrightText: 2026 Oxicid
# SPDX-License-Identifier: GPL-3.0-or-later

"""Shared context, settings, and geometry helpers for Quadrify and Weld."""
import bpy
import typing
from math import pi
from mathutils import Vector
from mathutils.geometry import intersect_point_line_segment
from itertools import groupby

if typing.TYPE_CHECKING:
    from .. import utypes


T_mesh_select_modes = typing.Literal['VERT', 'EDGE', 'FACE']
T_uv_select_modes = typing.Literal['VERT', 'EDGE', 'FACE', 'ISLAND']

from .selection import (
    face_select_get_func,
    face_invisible_get_func,
    edge_select_linked_set_func,
    edge_select_get_func,
    vert_select_get_func,
    shared_crn,
    is_flipped_3d,
    is_pair,
    is_pair_with_flip,
    set_faces_tag,
    is_boundary_non_sync,
    is_boundary_sync,
    is_boundary_with_flip_check_non_sync,
    is_boundary_with_flip_check_sync,
    is_boundary_func,
    is_visible_func,
    is_invisible_func,
    calc_visible_uv_faces_iter,
)
from .geometry import (
    calc_face_area_3d,
    calc_face_area_uv,
    calc_signed_face_area_uv,
    weld_crn_edge_by_idx,
    point_inside_face,
    linked_crn_uv,
    linked_crn_to_vert_pair_with_seam,
    linked_crn_uv_by_face_tag_unordered_included,
    linked_crn_uv_by_idx_unordered,
    linked_crn_uv_by_idx_unordered_included,
    linked_crn_uv_by_island_index_unordered_included,
    linked_crn_uv_by_island_index_unordered,
    all_equal,
    argmin,
    vec_isclose,
    vec_isclose_to_uniform,
    vec_isclose_to_zero,
    clamp,
    closest_pt_to_line,
    np_vec_dot,
    np_vec_normalized,
)


def get_aspect_ratio(umesh=None):
    """Aspect Y. Used for multiply by Y axis."""
    if umesh:
        # Aspect from checker
        for m in umesh.obj.modifiers:
            if isinstance(m, bpy.types.NodesModifier) and m.name.startswith('UniV Checker'):
                gn_mod = GN(m, print_missed_socket=True)
                if 'Socket_1' in gn_mod:
                    mtl = gn_mod['Socket_1']
                    if mtl:
                        for node in mtl.node_tree.nodes:
                            if node.bl_idname == 'ShaderNodeTexImage':
                                image = node.image
                                if image:
                                    image_width, image_height = image.size
                                    if image_height:
                                        return image_width / image_height
                break
        # Aspect from material
        mtl = umesh.obj.active_material
        if mtl and getattr(mtl, 'use_nodes', True):
            active_node = mtl.node_tree.nodes.active
            if active_node and active_node.bl_idname == 'ShaderNodeTexImage':
                image = active_node.image
                if image:
                    image_width, image_height = image.size
                    if image_height:
                        return image_width / image_height
        return 1.0

    # Aspect from active area
    area = bpy.context.area
    if area and area.type == 'IMAGE_EDITOR':
        space_data = area.spaces.active
        if space_data and space_data.image:
            image_width, image_height = space_data.image.size
            if image_height:
                return image_width / image_height
    else:
        # Aspect from VIEW3D
        for area in bpy.context.screen.areas:
            if not area.type == 'IMAGE_EDITOR':
                continue
            space_data = area.spaces.active
            if space_data and space_data.image:
                image_width, image_height = space_data.image.size
                if image_height:
                    return image_width / image_height
    return 1.0


def get_select_mode_mesh() -> T_mesh_select_modes:
    mode = bpy.context.scene.tool_settings.mesh_select_mode
    if mode[0]:
        return 'VERT'
    elif mode[1]:
        return 'EDGE'
    else:
        return 'FACE'


def set_select_mode_mesh(mode: T_mesh_select_modes):
    if get_select_mode_mesh() == mode:
        return
    if mode == 'VERT':
        bpy.context.tool_settings.mesh_select_mode[:] = True, False, False
    elif mode == 'EDGE':
        bpy.context.tool_settings.mesh_select_mode[:] = False, True, False
    elif mode == 'FACE':
        bpy.context.tool_settings.mesh_select_mode[:] = False, False, True
    else:
        raise TypeError(f"Mode: '{mode}' not found in ('VERT', 'EDGE', 'FACE')")


def get_select_mode_uv() -> T_uv_select_modes:
    mode = bpy.context.scene.tool_settings.uv_select_mode
    if mode == 'VERTEX':
        return 'VERT'
    return mode  # noqa


def set_select_mode_uv(mode: T_uv_select_modes):
    if get_select_mode_uv() == mode:
        return
    if mode == 'VERT':
        mode = 'VERTEX'
    bpy.context.scene.tool_settings.uv_select_mode = mode


def get_max_distance_from_px(px_size: int, view: bpy.types.View2D):
    return (Vector(view.region_to_view(0, 0)) - Vector(view.region_to_view(0, px_size))).length


def true_groupby(seq):
    """Groups and returns only identical elements"""
    seq = seq.copy()
    sorted_groups = []
    while True:
        if len(seq) <= 1:
            break

        tar_val = seq.pop()
        groups = []
        for i in range(len(seq) - 1, -1, -1):
            v = seq[i]
            if v == tar_val:
                groups.append(v)
                seq.pop(i)
        if groups:
            groups.append(tar_val)
            sorted_groups.append(groups)

    return sorted_groups


def split_by_similarity(lst, key=None):
    """It differs from Group By in that groups are strictly separated and not reversed.
        true_groupby:        1,0,1,1 -> [1,1,1],[0]
        split_by_similarity: 1,0,1,1 -> [1],[0],[1,1]"""
    if key:
        return [list(group) for _, group in groupby(lst, key=key)]
    else:
        return [list(group) for _, group in groupby(lst)]


class GN:
    def __init__(self, mod, print_missed_socket=False):
        self.mod = mod
        self.print_error = print_missed_socket

    def _missed_socket_print(self,exist, name):
        if not exist and self.print_error:
            import inspect
            caller_func_name = inspect.currentframe().f_back.f_back.f_code.co_name
            print(f"UniV: {caller_func_name}: Socket {name!r} in {self.mod.name!r} modifier was changed.")

    if bpy.app.version >= (5, 2, 0):
        def __contains__(self, name: str):
            exist = hasattr(self.mod.properties.inputs, name)
            self._missed_socket_print(exist, name)
            return exist
        def __setitem__(self, name: str, val):
            getattr(self.mod.properties.inputs, name).value = val
        def __getitem__(self, name: str):
            return getattr(self.mod.properties.inputs, name).value

    elif bpy.app.version >= (4, 0, 0):
        def __contains__(self, name: str):
            exist = name in self.mod
            self._missed_socket_print(exist, name)
            return exist
        def __setitem__(self,name: str, val):
            self.mod[name] = val
        def __getitem__(self, name: str):
            return self.mod[name]
    else:
        def __contains__(self, name: str):
            exist = name.replace('Input', 'Socket', 1) in self.mod
            self._missed_socket_print(exist, name)
            return exist
        def __setitem__(self, name: str, val):
            self.mod[name.replace('Input', 'Socket', 1)] = val
        def __getitem__(self, name: str):
            return self.mod[name.replace('Input', 'Socket', 1)]


class NoInit:
    def __getattribute__(self, item):
        raise AttributeError(f'Object not initialized')

    def __bool__(self):
        raise AttributeError(f'Object not initialized')

    def __len__(self):
        raise AttributeError(f'Object not initialized')


def set_global_texel(isl: 'utypes.AdvIsland', calc_bbox=True):
    from ..preferences import univ_settings
    if not univ_settings().use_texel:
        return False

    if isl.area_3d == -1.0:
        if isinstance(isl.umesh.value, Vector):
            isl.calc_area_3d(isl.umesh.value)
        else:
            isl.calc_area_3d()

    if isl.area_uv == -1.0:
        isl.calc_area_uv()

    if calc_bbox:
        isl.calc_bbox()

    # TODO: Double scale for small area island
    texture_size = (int(univ_settings().size_x) + int(univ_settings().size_y)) / 2
    res = isl.set_texel(univ_settings().texel_density, texture_size)
    return bool(res)


def sync():
    return bpy.context.scene.tool_settings.use_uv_select_sync


def find_min_rotate_angle(angle):
    return -(round(angle / (pi / 2)) * (pi / 2) - angle)


def get_mouse_pos(context, event):
    return Vector(context.region.view2d.region_to_view(event.mouse_region_x, event.mouse_region_y))
