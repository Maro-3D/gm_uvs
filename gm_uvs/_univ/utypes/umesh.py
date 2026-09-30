# SPDX-FileCopyrightText: 2026 Oxicid
# SPDX-License-Identifier: GPL-3.0-or-later

import bpy
import copy
import bmesh
import typing  # noqa
import mathutils

from collections import defaultdict

from bmesh.types import BMFace, BMEdge, BMLoop

from .. import utils
from ..utypes import PyBMesh


class FakeBMesh:
    def __init__(self, isl):
        self.faces = isl


class UMesh:
    def __init__(self, bm, obj, is_edit_bm=True, verify_uv=True):
        self.bm: bmesh.types.BMesh | FakeBMesh = bm
        self.obj: bpy.types.Object = obj
        self.elem_mode = utils.NoInit()
        self.uv: bmesh.types.BMLayerItem = bm.loops.layers.uv.verify() if verify_uv else None
        self.is_edit_bm: bool = is_edit_bm
        # NOTE: Do not reset the tag after an update. Some operators check it after an update.
        self.update_tag: bool = True
        self.sync: bool = utils.sync()
        self._sync_invalidate: bool = False  # Need for 3D operators
        # self.islands_calc_type
        # self.islands_calc_subtype
        self.value: float | int | utils.NoInit | None = utils.NoInit()  # value for different purposes
        self.other = utils.NoInit()
        self.aspect: float = 1.0
        self.sequence: list[BMFace | BMEdge | BMLoop] | list['AdvIsland'] | typing.Any = []  # noqa

    def update(self, force=False):
        if not self.update_tag:
            return False
        if self.is_edit_bm:
            bmesh.update_edit_mesh(self.obj.data, loop_triangles=force, destructive=force)
        else:
            self.bm.to_mesh(self.obj.data)
        return True

    def fake_umesh(self, isl):
        """Need for calculate sub islands"""
        fake = UMesh(self.bm, self.obj, self.is_edit_bm)
        fake.update_tag = self.update_tag
        fake.sync = self.sync
        fake.value = self.value
        fake.aspect = self.aspect
        fake.bm = FakeBMesh(isl)
        return fake

    def free(self, force=False):
        if force or not self.is_edit_bm:
            self.bm.free()

    @property
    def sync_valid(self):
        if self._sync_invalidate:
            return False
        return getattr(self.bm, 'uv_select_sync_valid', False)

    @sync_valid.setter
    def sync_valid(self, state: bool):
        if hasattr(self.bm, 'uv_select_sync_valid'):
            self.bm.uv_select_sync_valid = state

    def sync_from_mesh_if_needed(self, sticky=''):
        if not self.bm.uv_select_sync_valid:
            if sticky:
                self.bm.uv_select_sync_from_mesh(sticky_select_mode=sticky)  # noqa
            else:
                self.bm.uv_select_sync_from_mesh()


    def check_uniform_scale(self, report=None, threshold=0.01) -> 'mathutils.Vector | None':
        _, _, scale = self.obj.matrix_world.decompose()
        if not utils.vec_isclose_to_uniform(scale, threshold):
            if report:
                report({'WARNING'}, f"The {self.obj.name!r} hasn't applied scale: X={scale.x:.4f}, Y={scale.y:.4f}, Z={scale.z:.4f}")
            return scale
        return None


    @property
    def is_full_face_selected(self):
        return PyBMesh.is_full_face_selected(self.bm)

    @property
    def is_full_face_selected_for_avoid_force_explicit_check(self):
        """In Vertex and Edge modes, BMFace.uv_select can be False and BMFace.select can be True.
        This check avoids problems with such behavior by forcing explicit checking of UV selection tags."""
        return PyBMesh.is_full_face_selected(self.bm) and self.sync and (not self.sync_valid or self.elem_mode == 'FACE')

    @property
    def is_full_face_deselected(self):
        return PyBMesh.fields(self.bm).totfacesel == 0


    @property
    def is_full_edge_deselected(self):
        return PyBMesh.is_full_edge_deselected(self.bm)


    @property
    def is_full_vert_deselected(self):
        return PyBMesh.is_full_vert_deselected(self.bm)

    @property
    def total_vert_sel(self):
        return PyBMesh.fields(self.bm).totvertsel

    @property
    def total_edge_sel(self):
        return PyBMesh.fields(self.bm).totedgesel

    @property
    def total_face_sel(self):
        return PyBMesh.fields(self.bm).totfacesel

    @property
    def total_corners(self):
        return PyBMesh.fields(self.bm).totloop

    def has_selected_uv_faces(self) -> bool:
        if not self.total_face_sel:
            return False

        if self.sync:
            if self.elem_mode == 'FACE' or not self.sync_valid:
                return bool(self.total_face_sel)
            if self.is_full_face_selected:
                return any(f.uv_select for f in self.bm.faces)
            return any(f.uv_select for f in self.bm.faces if not f.hide)

        if self.is_full_face_selected:
            return any(f.uv_select for f in self.bm.faces)
        else:
            return any(f.uv_select for f in self.bm.faces if f.select)

    def has_selected_uv_edges(self) -> bool:
        if self.sync:
            if not self.total_edge_sel:
                return False
            elif self.total_face_sel and (self.elem_mode == 'FACE' or not self.sync_valid):
                return True
            else:
                for e in self.bm.edges:
                    if e.select:
                        for crn in getattr(e, 'link_loops', ()):
                            if not crn.face.hide:
                                return True
                return False

        if not self.total_face_sel:
            return False

        if self.is_full_face_selected:
            return any(any(crn.uv_select_edge for crn in f.loops) for f in self.bm.faces)
        return any(any(crn.uv_select_edge for crn in f.loops) for f in self.bm.faces if f.select)

    def has_selected_uv_verts(self) -> bool:
        if self.sync:
            if not self.total_vert_sel:
                return False
            elif self.total_face_sel:
                return True
            else:
                for v in self.bm.verts:
                    if v.select:
                        for crn in getattr(v, 'link_loops', ()):
                            if not crn.face.hide:
                                return True
                return False

        if not self.total_face_sel:
            return False

        if self.is_full_face_selected:
            return any(any(crn.uv_select_vert for crn in f.loops) for f in self.bm.faces)
        return any(any(crn.uv_select_vert for crn in f.loops) for f in self.bm.faces if f.select)


    def has_visible_uv_faces(self) -> bool:
        if self.total_face_sel:
            return True
        if self.sync:
            return any(not f.hide for f in self.bm.faces)
        return False


    def set_corners_tag(self, state=True):
        if state:
            for f in self.bm.faces:
                for crn in f.loops:
                    crn.tag = True
        else:
            for f in self.bm.faces:
                for crn in f.loops:
                    crn.tag = False


    def verify_uv(self):
        layers_uv = self.bm.loops.layers.uv
        if not layers_uv:
            self.uv = layers_uv.new('UVMap')
        else:
            self.uv = self.bm.loops.layers.uv.verify()


    def __hash__(self):
        return hash(self.bm)

    def __del__(self):
        if not self.is_edit_bm:
            self.bm.free()


class UMeshes:
    def __init__(self, umeshes=None, *, report=None):
        if umeshes is None:
            self._sel_ob_with_uv()
        else:
            self.umeshes: list[UMesh] = umeshes
        self.report_obj = report
        self.sync: bool = utils.sync()
        self._elem_mode: typing.Literal['VERT', 'EDGE', 'FACE', 'ISLAND'] = self._elem_mode_init()
        self.is_edit_mode = bpy.context.mode == 'EDIT_MESH'

    def report(self, info_type={'INFO'}, info="No uv for manipulate"):  # noqa
        if self.report_obj is None:
            print(info_type, info)
            return
        self.report_obj(info_type, info)

    def update(self, force=False, info_type={'INFO'}, info="No uv for manipulate"):  # noqa #pylint: disable=dangerous-default-value
        if sum(umesh.update(force=force) for umesh in self.umeshes):
            return {'FINISHED'}
        if info:
            self.report(info_type, info)
        return {'CANCELLED'}

    def silent_update(self):
        for umesh in self:
            umesh.update()

    @property
    def update_tag(self):
        return any(umesh.update_tag for umesh in self)

    @update_tag.setter
    def update_tag(self, value):
        for umesh in self:
            umesh.update_tag = value

    @property
    def elem_mode(self):
        return self._elem_mode

    @elem_mode.setter
    def elem_mode(self, mode: typing.Literal['VERT', 'EDGE', 'FACE', 'ISLAND']):
        if self._elem_mode != mode:
            self._elem_mode = mode
            if self.sync:
                utils.set_select_mode_mesh(mode)  # noqa
                for umesh in self:
                    umesh.bm.select_mode = {mode}
            else:
                utils.set_select_mode_uv(mode)
            for umesh in self.umeshes:
                umesh.elem_mode = mode

    def _elem_mode_init(self):
        mode = utils.get_select_mode_mesh() if self.sync else utils.get_select_mode_uv()
        for umesh in self.umeshes:
            umesh.elem_mode = mode
        return mode


    def verify_uv(self):
        for umesh in self:
            umesh.verify_uv()


    def free(self, force=False):
        """self.umeshes save refs in init in OT classes, so it's necessary to free memory"""
        for umesh in self:
            umesh.free(force)


    def _sel_ob_with_uv(self):
        bmeshes = []
        if bpy.context.mode == 'EDIT_MESH':
            for obj in bpy.context.objects_in_mode_unique_data:
                if obj.data.uv_layers:
                    bm = bmesh.from_edit_mesh(obj.data)
                    if bm.faces:
                        bmeshes.append(UMesh(bm, obj))
        else:
            data_and_objects: defaultdict[bpy.types.Mesh, list[bpy.types.Object]] = defaultdict(list)

            for obj in bpy.context.selected_objects:
                if obj.type == 'MESH' and obj.data.uv_layers and obj.data.polygons:
                    data_and_objects[obj.data].append(obj)

            for data, objs in data_and_objects.items():
                bm = bmesh.new()
                bm.from_mesh(data)
                bmeshes.append(UMesh(bm, objs[0], False))
        self.umeshes = bmeshes


    @classmethod
    def calc(cls, report=None, verify_uv=True):
        """ Get umeshes without uv but with faces"""
        bmeshes = []
        if bpy.context.mode == 'EDIT_MESH':
            for obj in bpy.context.objects_in_mode_unique_data:
                bm = bmesh.from_edit_mesh(obj.data)
                if bm.faces:
                    bmeshes.append(UMesh(bm, obj, verify_uv=verify_uv))
        else:
            data_and_objects: defaultdict[bpy.types.Mesh, list[bpy.types.Object]] = defaultdict(list)

            for obj in bpy.context.selected_objects:
                if obj.type == 'MESH' and obj.data.polygons:
                    data_and_objects[obj.data].append(obj)

            for data, objs in data_and_objects.items():
                bm = bmesh.new()
                bm.from_mesh(data)
                objs.sort(key=lambda a: a.name)
                bmeshes.append(UMesh(bm, objs[0], False, verify_uv))
        return cls(bmeshes, report=report)


    def filtered_by_selected_and_visible_uv_by_context(self):
        if self.elem_mode == 'VERT':
            return self.filtered_by_selected_and_visible_uv_verts()
        elif self.elem_mode == 'EDGE':
            return self.filtered_by_selected_and_visible_uv_edges()
        else:
            return self.filtered_by_selected_and_visible_uv_faces()


    def filtered_by_selected_and_visible_uv_verts(self) -> tuple['UMeshes', 'UMeshes']:
        """NOTE: Do not use this in edge mode (and face ???), as there may be cases where 'flush_select' is not called,
        resulting in invisible selected vertices even when all edges are deselected. """
        selected = []
        visible = []
        for umesh in self:
            if umesh.has_selected_uv_verts():
                selected.append(umesh)
            else:
                visible.append(umesh)
        if not selected:
            for umesh2 in reversed(visible):
                if not umesh2.has_visible_uv_faces():
                    visible.remove(umesh2)

        u1 = copy.copy(self)
        u2 = copy.copy(self)
        u1.umeshes = selected
        u2.umeshes = visible
        return u1, u2

    def filtered_by_selected_and_visible_uv_edges(self) -> tuple['UMeshes', 'UMeshes']:
        selected = []
        visible = []
        for umesh in self:
            if umesh.has_selected_uv_edges():
                selected.append(umesh)
            else:
                visible.append(umesh)
        if not selected:
            for umesh2 in reversed(visible):
                if not umesh2.has_visible_uv_faces():
                    visible.remove(umesh2)

        u1 = copy.copy(self)
        u2 = copy.copy(self)
        u1.umeshes = selected
        u2.umeshes = visible
        return u1, u2

    def filtered_by_selected_and_visible_uv_faces(self) -> tuple['UMeshes', 'UMeshes']:
        """Warning: if bmesh has selected faces, non-selected might be without visible faces"""
        selected = []
        visible = []
        for umesh in self:
            if umesh.has_selected_uv_faces():
                selected.append(umesh)
            else:
                visible.append(umesh)
        if not selected:
            for umesh2 in reversed(visible):
                if not umesh2.has_visible_uv_faces():
                    visible.remove(umesh2)

        u1 = copy.copy(self)
        u2 = copy.copy(self)
        u1.umeshes = selected
        u2.umeshes = visible
        return u1, u2


    def __iter__(self) -> typing.Iterator[UMesh]:
        return iter(self.umeshes)

    def __getitem__(self, item) -> UMesh:
        return self.umeshes[item]

    def __len__(self):
        return len(self.umeshes)

    def __bool__(self):
        return bool(self.umeshes)

    def __str__(self):
        return f"UMeshes Count = {len(self.umeshes)}"
