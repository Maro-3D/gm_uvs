# SPDX-FileCopyrightText: 2026 Oxicid
# SPDX-License-Identifier: GPL-3.0-or-later

import typing
from mathutils import Vector
from bmesh.types import BMLoop
from ..utils import linked_crn_uv, vec_isclose_to_zero
from . import umesh as _umesh
from . import bbox
from .. import utils

if typing.TYPE_CHECKING:
    from . import AdvIsland, FaceIsland  # noqa


class LoopGroup:
    def __init__(self, umesh: _umesh.UMesh):
        self.umesh: _umesh.UMesh = umesh
        self.corners: list[BMLoop] = []
        self.tag = True
        self.value: typing.Any | utils.NoInit = utils.NoInit()
        self.dirt = False
        self.is_shared = False
        self.is_flipped_3d = False
        self._length_uv: float | None = None
        self._length_3d: float | None = None
        self.weights: list[float] | None = None
        self.is_unpinned_exist_: bool | None = None
        self.chain_linked_corners: list[list[BMLoop]] = []
        self.chain_linked_corners_mask: list[bool] = []


    @property
    def is_cyclic(self):
        crn_a = self.corners[0]
        crn_b = self.corners[-1].link_loop_next
        return crn_a.vert == crn_b.vert and crn_a[self.umesh.uv].uv == crn_b[self.umesh.uv].uv


    def calc_shared_group_for_stitch(self) -> 'typing.Self':
        shared_group = []
        is_flipped = self._is_flipped_3d
        if is_flipped:
            for crn in self.corners:
                shared_group.append(crn.link_loop_radial_prev)
        else:
            for crn in self.corners:
                shared_group.append(crn.link_loop_radial_prev.link_loop_next)
        lg = LoopGroup(self.umesh)
        lg.is_shared = True
        lg.is_flipped_3d = is_flipped
        lg.corners = shared_group
        return lg

    def calc_begin_end_pt(self):
        uv = self.umesh.uv
        if self.is_shared:
            if self.is_flipped_3d:
                return self[0][uv].uv, self[-1].link_loop_next[uv].uv
            else:
                return self[0][uv].uv, self[-1].link_loop_prev[uv].uv
        else:
            return self[0][uv].uv, self[-1].link_loop_next[uv].uv

    @property
    def _is_flipped_3d(self):
        assert not self.is_shared
        pair = self[0].link_loop_radial_prev
        return pair.vert == self[0].vert

    def copy_coords_from_ref(self, ref, clean_seams):
        uv = self.umesh.uv
        for ref_crn, trans_crn in zip(ref, self):
            if clean_seams:
                ref_crn.edge.seam = False
            ref_co = ref_crn[uv].uv
            # TODO: Implement linked_crn_to_vert_by_idx_pair_with_seam
            for trans_crn_linked in utils.linked_crn_to_vert_pair_with_seam(trans_crn, uv, self.umesh.sync):
                trans_crn_linked[uv].uv = ref_co
            trans_crn[uv].uv = ref_co

        ref_co = ref[-1].link_loop_next[uv].uv
        end_crn = self[-1].link_loop_next if self.is_flipped_3d else self[-1].link_loop_prev

        for trans_crn_linked in utils.linked_crn_to_vert_pair_with_seam(end_crn, uv, self.umesh.sync):
            trans_crn_linked[uv].uv = ref_co
        end_crn[uv].uv = ref_co


    def calc_signed_face_area(self):
        uv = self.umesh.uv
        # TODO: Report small areas in stitch
        return sum(utils.calc_signed_face_area_uv(crn.face, uv) for crn in self)

    def tagging(self, island: 'AdvIsland | FaceIsland'):
        face_is_invisible = utils.is_invisible_func(island.umesh.sync)
        get_edge_select = utils.edge_select_get_func(island.umesh)
        is_pair = utils.is_pair

        uv = self.umesh.uv
        for f in island:
            for crn in f.loops:
                shared_crn = crn.link_loop_radial_prev
                if shared_crn == crn:
                    crn.tag = False
                    continue
                if not get_edge_select(crn):
                    crn.tag = False
                    continue
                if face_is_invisible(shared_crn.face):  # Change
                    crn.tag = False
                    continue
                crn.tag = not is_pair(crn, shared_crn, uv)


    def move(self, delta: Vector) -> bool:
        if vec_isclose_to_zero(delta):
            return False
        uv = self.umesh.uv
        for loop in self.corners:
            loop[uv].uv += delta
        return True

    def set_position(self, to: Vector, _from: Vector):
        return self.move(to - _from)

    def calc_bbox(self):
        return bbox.BBox.calc_bbox_uv_corners(self.corners, self.umesh.uv)

    def calc_length_uv(self):
        uv = self.umesh.uv
        aspect = self.umesh.aspect

        length = 0.0
        if aspect == 1.0:
            for crn in self:
                length += (crn[uv].uv - crn.link_loop_next[uv].uv).length
        else:
            for crn in self:
                vec = crn[uv].uv - crn.link_loop_next[uv].uv
                vec.x *= aspect
                length += vec.length
        self._length_uv = length
        return length

    def calc_length_3d(self):
        length = 0.0
        for crn in self:
            length += crn.edge.calc_length()
        self._length_3d = length
        return length

    @property
    def length_uv(self):
        if self._length_uv is None:
            return self.calc_length_uv()
        return self._length_uv

    @length_uv.setter
    def length_uv(self, v):
        self._length_uv = v

    @property
    def length_3d(self):
        if self._length_3d is None:
            return self.calc_length_3d()
        return self._length_3d

    @length_3d.setter
    def length_3d(self, v):
        self._length_3d = v


    def __iter__(self):
        return iter(self.corners)

    def __getitem__(self, idx) -> BMLoop:
        return self.corners[idx]

    def __len__(self):
        return len(self.corners)

    def __bool__(self):
        return bool(self.corners)

    def __str__(self):
        return f'Corner Edge count = {len(self.corners)}'


class LoopGroups:
    def __init__(self, loop_groups, umesh):
        self.loop_groups: list[LoopGroup] = loop_groups
        self.umesh: _umesh.UMesh | None = umesh
        self.tag = True

    @classmethod
    def calc_by_boundary_crn_tags(cls, isl):
        """Warning: Need uninterrupted tagging by boundary loops"""
        uv = isl.umesh.uv
        loop_groups = []
        for crn in isl.iter_corners_by_tag():
            crn.tag = False
            group = [crn]
            temp_crn: BMLoop | None = crn
            while temp_crn:
                next_crn = temp_crn.link_loop_next
                if next_crn.tag:
                    next_crn.tag = False
                    temp_crn = next_crn
                    group.append(next_crn)
                    continue

                for linked_crn in reversed(utils.linked_crn_uv_by_idx_unordered(next_crn, uv)):
                    if linked_crn.tag:
                        linked_crn.tag = False
                        temp_crn = linked_crn
                        group.append(linked_crn)
                        break
                else:
                    temp_crn = None

            lg = LoopGroup(isl.umesh)
            lg.corners = group
            loop_groups.append(lg)
        return cls(loop_groups, isl.umesh)

    @classmethod
    def calc_by_boundary_crn_tags_v2(cls, isl):
        """Warning: Need tagging by boundary loops"""
        uv = isl.umesh.uv
        loop_groups = []
        for crn in isl.iter_corners_by_tag():
            crn.tag = False
            group = [crn]
            temp_crn: BMLoop | None = crn
            while temp_crn:  # forward
                next_crn = temp_crn.link_loop_next
                if next_crn.tag:
                    next_crn.tag = False
                    temp_crn = next_crn
                    group.append(next_crn)
                    continue

                # TODO: Replace linked_crn_uv with linked_crn_to_vert_pair_iter to avoid non-manifold uv vert links
                for linked_crn in reversed(linked_crn_uv(next_crn, uv)):
                    if linked_crn.tag:
                        linked_crn.tag = False
                        temp_crn = linked_crn
                        group.append(linked_crn)
                        break
                else:
                    temp_crn = None

            temp_crn = crn
            while temp_crn:  # backward
                if temp_crn.link_loop_prev.tag:
                    temp_crn = temp_crn.link_loop_prev
                    temp_crn.tag = False
                    group.insert(0, temp_crn)
                    continue

                for linked_crn in reversed(linked_crn_uv(temp_crn, uv)):
                    linked_crn_prev = linked_crn.link_loop_prev
                    if linked_crn_prev.tag:
                        temp_crn = linked_crn_prev
                        temp_crn.tag = False
                        group.insert(0, temp_crn)
                        break
                else:
                    temp_crn = None

            lg = LoopGroup(isl.umesh)
            lg.corners = group
            loop_groups.append(lg)
        return cls(loop_groups, isl.umesh)

    def indexing(self, _=None):
        for f in self.umesh.bm.faces:
            for crn in f.loops:
                crn.index = -1

        for idx, lg in enumerate(self.loop_groups):
            for crn in lg:
                crn.index = idx

    def set_position(self, to: Vector, _from: Vector):
        return bool(sum(lg.set_position(to, _from) for lg in self.loop_groups))

    def move(self, delta: Vector):
        return bool(sum(lg.move(delta) for lg in self.loop_groups))


    def __iter__(self) -> typing.Iterator[LoopGroup]:
        return iter(self.loop_groups)

    def __getitem__(self, idx) -> LoopGroup:
        return self.loop_groups[idx]

    def __bool__(self):
        return bool(self.loop_groups)

    def __len__(self):
        return len(self.loop_groups)

    def __str__(self):
        return f'Loop Groups count = {len(self.loop_groups)}'
