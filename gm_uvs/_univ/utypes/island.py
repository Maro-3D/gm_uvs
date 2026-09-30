# SPDX-FileCopyrightText: 2026 Oxicid
# SPDX-License-Identifier: GPL-3.0-or-later


import bmesh
import math
import typing
import itertools
import numpy as np

from mathutils import Vector, Matrix
from mathutils.geometry import area_tri

from bmesh.types import BMFace, BMLoop

from .. import utils
from . import umesh as _umesh
from . import BBox


class FaceIsland:
    def __init__(self, faces: list[BMFace] | typing.Iterable[BMFace], umesh: _umesh.UMesh):
        self.faces: list[BMFace] | typing.Iterable[BMFace] = faces
        self.umesh: _umesh.UMesh = umesh
        self.value: float | int | Vector = -1  # value for different purposes

    def move(self, delta: Vector) -> bool:
        if utils.vec_isclose_to_zero(delta):
            return False

        uv = self.umesh.uv
        for face in self.faces:
            for crn in face.loops:
                crn[uv].uv += delta
        return True

    def set_position(self, to: Vector, _from: Vector = None):
        if _from is None:
            _from = self.calc_bbox().min
        return self.move(to - _from)


    def rotate(self, angle: float, pivot: Vector, aspect: float = 1.0) -> bool:
        """Rotate a list of faces by angle (in radians) around a pivot
        :param angle: Angle in radians
        :param pivot: Pivot
        :param aspect: Aspect Ratio = Width / Height
        """
        if math.isclose(angle, 0, abs_tol=0.0001):
            return False
        uv = self.umesh.uv

        if aspect != 1.0:
            rot_matrix = Matrix.Rotation(angle, 2)
            rot_matrix[0][1] = aspect * rot_matrix[0][1]
            rot_matrix[1][0] = rot_matrix[1][0] / aspect

            diff = pivot - (pivot @ rot_matrix)
            for face in self.faces:
                for crn in face.loops:
                    crn_uv = crn[uv]
                    crn_uv.uv = crn_uv.uv @ rot_matrix + diff
        else:
            rot_matrix = Matrix.Rotation(-angle, 2)
            diff = pivot - (rot_matrix @ pivot)
            vec_rotate = Vector.rotate
            for face in self.faces:
                for crn in face.loops:
                    crn_co = crn[uv].uv
                    vec_rotate(crn_co, rot_matrix)
                    crn_co += diff
        return True

    def rotate_simple(self, angle: float, aspect: float = 1.0) -> bool:
        """Rotate a list of faces by angle (in radians) around a world center"""
        if math.isclose(angle, 0, abs_tol=0.0001):
            return False

        uv = self.umesh.uv
        if aspect != 1.0:
            rot_matrix = Matrix.Rotation(-angle, 2)
            rot_matrix[0][1] = aspect * rot_matrix[0][1]
            rot_matrix[1][0] = rot_matrix[1][0] / aspect

            for face in self.faces:
                for crn in face.loops:
                    crn_uv = crn[uv]
                    crn_uv.uv = crn_uv.uv @ rot_matrix
        else:
            vec_rotate = Vector.rotate
            rot_matrix = Matrix.Rotation(angle, 2)
            for face in self.faces:
                for crn in face.loops:
                    vec_rotate(crn[uv].uv, rot_matrix)
        return True

    def scale(self, scale: Vector, pivot: Vector) -> bool:
        """Scale a list of faces by pivot"""
        if utils.vec_isclose_to_uniform(scale):
            return False
        diff = pivot - pivot * scale

        uv = self.umesh.uv
        for face in self.faces:
            for crn in face.loops:
                crn_co = crn[uv].uv
                crn_co *= scale
                crn_co += diff
        return True


    def scale_simple(self, scale: Vector) -> bool:
        """Scale a list of faces by world center"""
        if utils.vec_isclose_to_uniform(scale):
            return False

        uv = self.umesh.uv
        for face in self.faces:
            for crn in face.loops:
                crn[uv].uv *= scale
        return True


    def set_corners_tag(self, tag=True):
        if tag:
            for f in self:
                for crn in f.loops:
                    crn.tag = True
        else:
            for f in self:
                for crn in f.loops:
                    crn.tag = False

    def set_boundary_tag(self, match_idx=False):
        is_boundary = utils.is_boundary_func(self.umesh)
        if match_idx:
            for f in self:
                idx = f.index
                for crn in f.loops:
                    crn.tag = is_boundary(crn) or crn.link_loop_radial_prev.face.index != idx
        else:
            for f in self:
                for crn in f.loops:
                    crn.tag = is_boundary(crn)

    def set_selected_crn_edge_tag(self):
        if self.umesh.sync and not self.umesh.sync_valid:
            for f in self:
                for crn in f.loops:
                    crn.tag = crn.edge.select
        else:
            for f in self:
                for crn in f.loops:
                    crn.tag = crn.uv_select_edge

    def iter_corners_by_tag(self):
        return (crn for f in self for crn in f.loops if crn.tag)

    def corners_iter(self):
        return (crn for f in self for crn in f.loops)


    def calc_selected_edge_corners_iter(self):
        if self.umesh.sync and not self.umesh.sync_valid:
            return (crn for f in self for crn in f.loops if crn.edge.select)
        else:
            return (crn for f in self for crn in f.loops if crn.uv_select_edge)


    def is_flipped(self) -> bool:
        uv = self.umesh.uv
        for f in self.faces:
            area = 0.0
            uvs: list[Vector] = [crn[uv].uv for crn in f.loops]
            for i in range(len(uvs)):
                area += uvs[i - 1].cross(uvs[i])
            if area < 0:
                return True
        return False


    def calc_bbox(self) -> BBox:
        return BBox.calc_bbox_uv(self.faces, self.umesh.uv)


    @property
    def select(self):
        raise NotImplementedError()

    @select.setter
    def select(self, state: bool):
        # TODO: Use bm.foreach
        if self.umesh.sync:
            if self.umesh.sync_valid:
                self.umesh.bm.uv_select_foreach_set_from_mesh(state, faces=self.faces, sticky_select_mode='DISABLED')

            if state:  # FAST_LOAD
                for face in self.faces:
                    face.select = True
            else:
                for face in self.faces:
                    face.select = False
        else:
            for face in self.faces:
                face.uv_select = state
                for crn in face.loops:
                    crn.uv_select_vert = state
                    crn.uv_select_edge = state


    def is_full_face_selected(self):
        if self.umesh.sync and not self.umesh.sync_valid:
            return all(f.select for f in self)
        return all(f.uv_select for f in self)

    def is_full_face_deselected(self):
        if self.umesh.sync and not self.umesh.sync_valid:
            return not any(f.select for f in self)
        return not any(f.uv_select for f in self)

    def is_full_vert_deselected(self):
        if self.umesh.sync and not self.umesh.sync_valid:
            return not any(v.select for f in self for v in f.verts)
        return not any(crn.uv_select_vert for f in self for crn in f.loops)


    def mark_seam(self, additional=False):
        uv = self.umesh.uv
        if self.umesh.sync:
            for f in self.faces:
                for crn in f.loops:
                    pair = crn.link_loop_radial_prev
                    if crn == pair or pair.face.hide:
                        crn.edge.seam = True
                        continue
                    seam = not (crn[uv].uv == pair.link_loop_next[uv].uv and crn.link_loop_next[uv].uv == pair[uv].uv)
                    if additional:
                        crn.edge.seam |= seam
                    else:
                        crn.edge.seam = seam
        else:
            for f in self.faces:
                for crn in f.loops:
                    pair = crn.link_loop_radial_prev
                    if crn == pair or not pair.face.select:
                        crn.edge.seam = True
                        continue
                    seam = not (crn[uv].uv == pair.link_loop_next[uv].uv and crn.link_loop_next[uv].uv == pair[uv].uv)
                    if additional:
                        crn.edge.seam |= seam
                    else:
                        crn.edge.seam = seam


    # TODO: Add mark seam with index


    def __iter__(self):
        return iter(self.faces)

    def __getitem__(self, idx) -> BMFace:
        return self.faces[idx]

    def __len__(self):
        return len(self.faces)

    def __bool__(self):
        return bool(self.faces)

    def __str__(self):
        return f'Face Island. Faces count = {len(self.faces)}'

    def __hash__(self):
        return hash(self[0])


class AdvIsland(FaceIsland):
    def __init__(self, faces: list[BMFace] | tuple | typing.Iterable[BMFace] = (), umesh: _umesh.UMesh | None = None):
        super().__init__(faces, umesh)
        self.tris: list[tuple[BMLoop, BMLoop, BMLoop]] = []
        self.flat_unique_uv_coords: list[Vector] = []
        self.flat_coords: list[Vector] | list[tuple[Vector, Vector, Vector]] = []  # rename to flat_uv_coords
        self.flat_3d_coords: list[Vector] | list[tuple[Vector, Vector, Vector]] = []
        self.is_flat_3d_coords_scaled: bool = False
        self.weights: list[float] = []
        # self.custom_value_2: int | float | Vector = -1
        self.convex_coords = []
        self._bbox: BBox | None = None
        self.tag = True
        self.select_state = None
        self.area_3d: float = -1.0
        self.area_uv: float = -1.0
        self.sequence = []

    def move(self, delta: Vector) -> bool:
        if self._bbox is not None:
            self._bbox.move(delta)
        return super().move(delta)

    def scale(self, scale: Vector, pivot: Vector) -> bool:
        if self._bbox is not None:
            self._bbox.scale(scale, pivot)
        return super().scale(scale, pivot)

    def set_texel(self, texel: float, texture_size: float | int):
        """Warning: Need calc uv and 3d area"""
        assert self.area_3d != -1.0 and self.area_uv != -1.0, "Need calculate uv and 3d area"
        area_3d = math.sqrt(self.area_3d)
        area_uv = math.sqrt(self.area_uv) * texture_size
        if math.isclose(area_3d, 0.0, abs_tol=1e-6) or math.isclose(area_uv, 0.0, abs_tol=1e-6):
            return None  # TODO: Highlight islands with zero area
        scale = (texel / (area_uv / area_3d))
        return self.scale(Vector((scale, scale)), self.bbox.center)

    def rotate(self, angle: float, pivot: Vector, aspect: float = 1.0) -> bool:
        self._bbox = None  # TODO: Implement Rotate 90 degrees and aspect ratio for bbox
        return super().rotate(angle, pivot, aspect)

    def set_position(self, to: Vector, _from: Vector = None):
        if _from is None:
            _from = self.bbox.min
        return self.move(to - _from)

    def calc_flat_coords(self, save_triplet=False):
        assert self.tris, 'Calculate tris'

        uv = self.umesh.uv
        if save_triplet:
            self.flat_coords = [(t[0][uv].uv, t[1][uv].uv, t[2][uv].uv) for t in self.tris]
        else:
            extend = self.flat_coords.extend
            for t in self.tris:
                extend(t_crn[uv].uv for t_crn in t)

    def calc_flat_uv_coords(self, save_triplet_=False):
        self.calc_flat_coords(save_triplet_)

    def calc_tris_simple(self):
        tris_isl: list[tuple[BMLoop, BMLoop, BMLoop]] = []
        tris_isl_append = tris_isl.append
        for f in self:
            corners = f.loops
            n = len(corners)
            if n == 4:
                l1, l2, l3, l4 = corners
                tris_isl_append((l1, l2, l3))
                tris_isl_append((l3, l4, l1))
            elif n == 3:
                tris_isl_append(tuple(corners))
            else:
                first_crn = corners[0]
                for i in range(1, n - 1):
                    tris_isl_append((first_crn, corners[i], corners[i + 1]))

        self.tris = tris_isl
        return bool(tris_isl)

    def calc_flat_unique_uv_coords(self):
        uv = self.umesh.uv
        self.flat_unique_uv_coords = [crn[uv].uv for f in self for crn in f.loops]

    def calc_flat_3d_coords(self, save_triplet=False, scale_=None):
        assert self.tris, 'Calculate tris'
        self.is_flat_3d_coords_scaled = bool(scale_)
        if save_triplet:
            if scale_:
                self.flat_3d_coords = [(t[0].vert.co * scale_, t[1].vert.co * scale_,
                                        t[2].vert.co * scale_) for t in self.tris]
            else:
                self.flat_3d_coords = [(t[0].vert.co, t[1].vert.co, t[2].vert.co) for t in self.tris]
        else:
            extend = self.flat_3d_coords.extend
            if scale_:
                for t in self.tris:
                    extend([t_crn.vert.co * scale_ for t_crn in t])
            else:
                for t in self.tris:
                    extend([t_crn.vert.co for t_crn in t])


    def calc_bbox(self) -> BBox:
        if self.convex_coords:
            self._bbox = BBox.calc_bbox(self.convex_coords)
        elif self.flat_coords:
            if isinstance(self.flat_coords[0], tuple):
                self._bbox = BBox.calc_bbox(itertools.chain.from_iterable(self.flat_coords))
            else:
                self._bbox = BBox.calc_bbox(self.flat_coords)
        else:
            self._bbox = BBox.calc_bbox_uv(self.faces, self.umesh.uv)
        return self._bbox

    @property
    def bbox(self) -> BBox:
        if self._bbox is None:
            self.calc_bbox()
        return self._bbox


    def calc_area_3d(self, scale=None, areas_to_weight=False):
        area = 0.0
        # self.weights = []
        if self.flat_3d_coords and scale:
            if self.is_flat_3d_coords_scaled:
                scale = None

        weight_append = self.weights.append
        it = self.flat_3d_coords if self.flat_3d_coords else (
            (crn_a.vert.co, crn_b.vert.co, crn_c.vert.co) for crn_a, crn_b, crn_c in self.tris)
        if areas_to_weight:
            assert self.tris, 'Calculate tris'
            if scale:
                if utils.vec_isclose(scale, scale.xxx):
                    x_component = abs(scale.x)
                    for va, vb, vc in it:
                        ar = area_tri(va, vb, vc) * x_component
                        weight_append(ar)
                        area += ar
                else:
                    for va, vb, vc in it:
                        ar = area_tri(va * scale, vb * scale, vc * scale)
                        weight_append(ar)
                        area += ar
            else:
                for va, vb, vc in it:
                    ar = area_tri(va, vb, vc)
                    weight_append(ar)
                    area += ar
        elif scale:
            if self.tris:
                if utils.vec_isclose(scale, scale.xxx):  # Uniform Scale
                    for va, vb, vc in it:
                        area += area_tri(va, vb, vc)
                    area *= (abs(scale.x) ** 2)
                else:
                    for va, vb, vc in it:
                        area += area_tri(va * scale, vb * scale, vc * scale)
            else:
                if utils.vec_isclose(scale, scale.xxx):  # Uniform Scale
                    for f in self:
                        area += f.calc_area()
                    area *= (abs(scale.z) ** 2)
                else:
                    from ..utils import calc_face_area_3d
                    for f in self:
                        area += calc_face_area_3d(f, scale)
                    area *= 0.5
        else:
            for f in self:
                area += f.calc_area()

        self.area_3d = area
        return area

    def calc_area_uv(self):
        area = 0.0
        uv = self.umesh.uv
        if self.flat_coords:
            flat_coords = self.flat_coords
            if isinstance(flat_coords[0], tuple):
                for triplet in flat_coords:
                    area += area_tri(*triplet)
            else:
                for i in range(0, len(flat_coords), 3):
                    area += area_tri(flat_coords[i], flat_coords[i + 1], flat_coords[i + 2])
        elif self.tris:
            for crn_a, crn_b, crn_c in self.tris:
                area += area_tri(crn_a[uv].uv, crn_b[uv].uv, crn_c[uv].uv)
        else:
            from ..utils import calc_face_area_uv
            for f in self:
                area += calc_face_area_uv(f, uv)

        self.area_uv = area
        return area


    def __str__(self):
        return f'Advanced Island. Faces count = {len(self.faces)}, Tris Count = {len(self.tris)}'


class IslandsBaseTagFilterPre:


    @staticmethod
    def tag_filter_visible(umesh: _umesh.UMesh):
        if umesh.is_full_face_selected:
            for face in umesh.bm.faces:
                face.tag = True
            return

        if umesh.sync:
            for face in umesh.bm.faces:
                face.tag = not face.hide
        else:
            for face in umesh.bm.faces:
                face.tag = face.select


class IslandsBaseTagFilterPost:

    @staticmethod
    def island_filter_is_any_face_selected(island: list[BMFace], umesh: _umesh.UMesh) -> bool:
        if umesh.sync and not umesh.sync_valid:
            return any(f.select for f in island)
        else:
            return any(f.uv_select for f in island)

    @staticmethod
    def island_filter_is_any_vert_selected(island: list[BMFace], umesh: _umesh.UMesh) -> bool:
        if umesh.sync and not umesh.sync_valid:
            return any(v.select for face in island for v in face.verts)
        else:
            return any(crn.uv_select_vert for face in island for crn in face.loops)

    @staticmethod
    def island_filter_is_any_edge_selected(island: list[BMFace], umesh: _umesh.UMesh) -> bool:
        if umesh.sync and not umesh.sync_valid:
            return any(e.select for face in island for e in face.edges)
        else:
            return any(crn.uv_select_edge for face in island for crn in face.loops)


class IslandsBase(IslandsBaseTagFilterPre, IslandsBaseTagFilterPost):
    @staticmethod
    def calc_iter_ex(umesh: _umesh.UMesh):
        uv = umesh.uv
        island: list[BMFace] = []

        for face in umesh.bm.faces:
            if not face.tag:  # Skip unselected and appended faces
                continue
            face.tag = False  # Tag first element in island (don't add again)

            parts_of_island = [face]  # Container collector of island elements
            temp = []  # Container for get elements from loop from parts_of_island

            while parts_of_island:  # Blank list == all faces of the island taken
                for f in parts_of_island:
                    for l in f.loops:  # Running through all the neighboring faces
                        shared_crn = l.link_loop_radial_prev
                        ff = shared_crn.face
                        if not ff.tag:
                            continue
                        if l[uv].uv == shared_crn.link_loop_next[uv].uv and l.link_loop_next[uv].uv == shared_crn[uv].uv:
                            temp.append(ff)
                            ff.tag = False

                island.extend(parts_of_island)
                parts_of_island = temp
                temp = []

            yield island
            island = []

    @staticmethod
    def calc_iter_non_manifold_ex(umesh: _umesh.UMesh):
        uv = umesh.uv
        island: list[BMFace] = []

        for face in umesh.bm.faces:
            if not face.tag:  # Skip unselected and appended faces
                continue
            face.tag = False  # Tag first element in island (don't add again)

            parts_of_island = [face]  # Container collector of island elements
            temp = []  # Container for get elements from loop from parts_of_island

            while parts_of_island:  # Blank list == all faces of the island taken
                for f in parts_of_island:
                    for l in f.loops:  # Running through all the neighboring faces
                        shared_crn = l.link_loop_radial_prev
                        ff = shared_crn.face
                        if not ff.tag:
                            continue
                        if l[uv].uv == shared_crn.link_loop_next[uv].uv or l.link_loop_next[uv].uv == shared_crn[uv].uv:
                            temp.append(ff)
                            ff.tag = False

                island.extend(parts_of_island)
                parts_of_island = temp
                temp = []

            yield island
            island = []

    @staticmethod
    def calc_with_markseam_iter_ex(umesh: _umesh.UMesh):
        uv = umesh.uv
        island: list[BMFace] = []

        for face in umesh.bm.faces:
            if not face.tag:
                continue
            face.tag = False

            parts_of_island = [face]
            temp = []

            while parts_of_island:
                for f in parts_of_island:
                    for l in f.loops:
                        shared_crn = l.link_loop_radial_prev
                        ff = shared_crn.face
                        if not ff.tag:
                            continue
                        if l.edge.seam:  # Skip if seam
                            continue
                        if l[uv].uv == shared_crn.link_loop_next[uv].uv and l.link_loop_next[uv].uv == shared_crn[uv].uv:
                            temp.append(ff)
                            ff.tag = False

                island.extend(parts_of_island)
                parts_of_island = temp
                temp = []

            yield island
            island = []


class Islands(IslandsBase):
    island_type = FaceIsland

    def __init__(self, islands=(), umesh: _umesh.UMesh | utils.NoInit = utils.NoInit()):
        self.islands: list[FaceIsland] | tuple = islands
        self.umesh: _umesh.UMesh | utils.NoInit = umesh
        self.value: float | int | Vector = -1  # value for different purposes


    @classmethod
    def calc_visible_with_mark_seam(cls, umesh: _umesh.UMesh):
        cls.tag_filter_visible(umesh)
        islands = [cls.island_type(i, umesh) for i in cls.calc_with_markseam_iter_ex(umesh)]
        return cls(islands, umesh)


    @classmethod
    def calc_extended_with_mark_seam(cls, umesh: _umesh.UMesh):
        if umesh.is_full_face_deselected:
            return cls()
        cls.tag_filter_visible(umesh)
        if umesh.sync and umesh.is_full_face_deselected:
            islands = [cls.island_type(i, umesh) for i in cls.calc_with_markseam_iter_ex(umesh)]
        else:
            islands = [cls.island_type(i, umesh) for i in cls.calc_with_markseam_iter_ex(umesh)
                       if cls.island_filter_is_any_face_selected(i, umesh)]
        return cls(islands, umesh)


    @classmethod
    def calc_extended_any_vert_non_manifold(cls, umesh: _umesh.UMesh):
        """Calc any verts selected islands"""
        if umesh.sync:
            if umesh.elem_mode == 'FACE':
                if umesh.is_full_face_deselected:
                    return cls()
            elif umesh.elem_mode == 'VERT':
                if umesh.is_full_vert_deselected:
                    return cls()
            else:
                if umesh.is_full_edge_deselected:
                    return cls()
        else:
            if umesh.is_full_face_deselected:
                return cls()

        cls.tag_filter_visible(umesh)
        if umesh.is_full_face_selected_for_avoid_force_explicit_check:
            islands = [cls.island_type(i, umesh) for i in cls.calc_iter_non_manifold_ex(umesh)]
        else:
            islands = [cls.island_type(i, umesh) for i in cls.calc_iter_non_manifold_ex(umesh)
                       if cls.island_filter_is_any_vert_selected(i, umesh)]
        return cls(islands, umesh)

    @classmethod
    def calc_extended_any_edge_non_manifold(cls, umesh: _umesh.UMesh):
        """Calc any edges selected islands"""
        if umesh.sync:
            if umesh.elem_mode == 'FACE':
                if umesh.is_full_face_deselected:
                    return cls()
            elif umesh.elem_mode == 'VERT':
                if umesh.is_full_vert_deselected:
                    return cls()
            else:
                if umesh.is_full_edge_deselected:
                    return cls()
        else:
            if umesh.is_full_face_deselected:
                return cls()

        cls.tag_filter_visible(umesh)
        if umesh.is_full_face_selected_for_avoid_force_explicit_check:
            islands = [cls.island_type(i, umesh) for i in cls.calc_iter_non_manifold_ex(umesh)]
        else:
            islands = [cls.island_type(i, umesh) for i in cls.calc_iter_non_manifold_ex(umesh)
                       if cls.island_filter_is_any_edge_selected(i, umesh)]
        return cls(islands, umesh)


    @classmethod
    def calc_visible_non_manifold(cls, umesh: _umesh.UMesh):
        cls.tag_filter_visible(umesh)
        islands = [cls.island_type(i, umesh) for i in cls.calc_iter_non_manifold_ex(umesh)]
        return cls(islands, umesh)


    @classmethod
    def calc_any_extended_or_visible_non_manifold(cls, umesh: _umesh.UMesh, *, extended) -> 'Islands':
        if extended:
            return cls.calc_extended_any_vert_non_manifold(umesh)
        return cls.calc_visible_non_manifold(umesh)


    def move(self, delta: Vector) -> bool:
        return bool(sum(island.move(delta) for island in self.islands))

    def set_position(self, to, _from):
        return bool(sum(island.set_position(to, _from) for island in self.islands))


    def scale_simple(self, scale: Vector):
        return bool(sum(island.scale_simple(scale) for island in self.islands))

    def scale(self, scale: Vector, pivot: Vector) -> bool:
        return bool(sum(island.scale(scale, pivot) for island in self.islands))

    def rotate(self, angle: float, pivot: Vector, aspect: float = 1.0) -> bool:
        return bool(sum(island.rotate(angle, pivot, aspect) for island in self.islands))

    def rotate_simple(self, angle: float, aspect: float = 1.0):
        return bool(sum(island.rotate_simple(angle, aspect) for island in self.islands))

    def calc_bbox(self) -> BBox:
        general_bbox = BBox()
        for island in self.islands:
            general_bbox.union(island.calc_bbox())
        return general_bbox

    def indexing(self, force=True):
        if force:
            if sum(len(isl) for isl in self.islands) != len(self.umesh.bm.faces):
                for f in self.umesh.bm.faces:
                    f.index = -1
            for idx, island in enumerate(self.islands):
                for face in island:
                    face.index = idx
            return

        for idx, island in enumerate(self.islands):
            for face in island:
                face.tag = True
                face.index = idx


    def __iter__(self) -> typing.Iterator[FaceIsland]:
        return iter(self.islands)

    def __getitem__(self, idx) -> FaceIsland:  # TODO: Add type[typing.Self].island_type
        return self.islands[idx]

    def __bool__(self):
        return bool(self.islands)

    def __len__(self):
        return len(self.islands)

    def __str__(self):
        return f'Islands count = {len(self.islands)}'


class UnionIslandsController:
    def __init__(self, islands):
        self._islands = islands

    @property
    def update_tag(self):
        return any(isl.umesh.update_tag for isl in self._islands)

    @update_tag.setter
    def update_tag(self, value):
        for isl in self._islands:
            isl.umesh.update_tag = value

    @property
    def aspect(self):
        return float(np.mean([isl.umesh.aspect for isl in self._islands]))

    @property
    def sync(self):
        return self._islands[0].umesh.sync


class UnionIslands(Islands):
    def __init__(self, islands: list[AdvIsland]):
        super().__init__([])
        self.islands: list[AdvIsland] = islands
        self.umesh: UnionIslandsController = UnionIslandsController(islands)
        # self.flat_coords = []
        self.convex_coords = []
        self._bbox = None

    def calc_bbox(self, force=True) -> BBox:
        self._bbox = BBox()
        if force:
            for island in self.islands:
                self._bbox.union(island.calc_bbox())
        else:
            for island in self.islands:
                self._bbox.union(island.bbox)
        return self._bbox

    @property
    def bbox(self) -> BBox:
        if self._bbox is None:
            self.calc_bbox()
        return self._bbox

    @property
    def area_3d(self) -> float:
        return sum(isl.area_3d for isl in self)

    @property
    def area_uv(self) -> float:
        return sum(isl.area_uv for isl in self)

    def set_texel(self, texel: float, texture_size: float | int):
        """Warning: Need calc uv and 3d area"""
        assert self.islands[0].area_3d != -1.0 and self.islands[0].area_uv != -1.0, "Need calculate uv and 3d area"
        area_3d = math.sqrt(self.area_3d)
        area_uv = math.sqrt(self.area_uv) * texture_size
        if math.isclose(area_3d, 0.0, abs_tol=1e-6) or math.isclose(area_uv, 0.0, abs_tol=1e-6):
            return None
        scale = (texel / (area_uv / area_3d))
        return self.scale(Vector((scale, scale)), self.bbox.center)

    @property
    def flat_3d_coords(self):
        return itertools.chain.from_iterable(isl.flat_3d_coords for isl in self)

    @property
    def flat_uv_coords(self):
        return itertools.chain.from_iterable(isl.flat_coords for isl in self)

    @property
    def flat_coords(self):  # TODO: Remove
        return itertools.chain.from_iterable(isl.flat_coords for isl in self)

    @property
    def weights(self):
        return itertools.chain.from_iterable(isl.weights for isl in self)

    @property
    def flat_unique_uv_coords(self):
        return itertools.chain.from_iterable(isl.flat_unique_uv_coords for isl in self)  # noqa

    @property
    def select(self):
        raise

    @select.setter
    def select(self, value):
        for isl in self:
            isl.select = value

    def calc_area_uv(self):
        return sum(isl.calc_area_uv() for isl in self)


    def append(self, island):
        self.islands.append(island)

    def pop(self, island):
        self.islands.pop(island)

    def __iter__(self) -> typing.Iterator[AdvIsland]:
        return iter(self.islands)

    def __getitem__(self, idx) -> AdvIsland:  # TODO: Add type[typing.Self].island_type
        return self.islands[idx]


class AdvIslands(Islands):
    island_type = AdvIsland

    def __init__(self, islands: list[AdvIsland] | tuple = (), umesh: _umesh.UMesh | utils.NoInit = utils.NoInit()):
        super().__init__([], umesh)
        self.islands: list[AdvIsland] = islands


    def calc_tris_simple(self):
        return bool(sum(isl.calc_tris_simple() for isl in self.islands))

    def calc_flat_coords(self, save_triplet=False):
        for island in self.islands:
            island.calc_flat_coords(save_triplet)

    def calc_flat_uv_coords(self, save_triplet=False):
        self.calc_flat_coords(save_triplet)

    def calc_flat_unique_uv_coords(self):
        for island in self.islands:
            island.calc_flat_unique_uv_coords()

    def calc_flat_3d_coords(self, save_triplet=False, scale=None):
        for island in self.islands:
            island.calc_flat_3d_coords(save_triplet, scale)

    def calc_area_3d(self, scale=None, areas_to_weight=False):
        return sum(isl.calc_area_3d(scale, areas_to_weight) for isl in self)

    def calc_area_uv(self):
        return sum(isl.calc_area_uv() for isl in self)

    def __iter__(self) -> typing.Iterator[AdvIsland]:
        return iter(self.islands)

    def __getitem__(self, idx) -> AdvIsland:
        return self.islands[idx]
