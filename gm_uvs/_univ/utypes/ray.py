# SPDX-FileCopyrightText: 2026 Oxicid
# SPDX-License-Identifier: GPL-3.0-or-later


import math
from math import inf, isclose
from bmesh.types import BMFace, BMLoop

from . import FaceIsland, AdvIsland, UnionIslands
from .. import utils
from ..utils import closest_pt_to_line, point_inside_face


class IslandHit:
    def __init__(self, pt, min_dist=1e200):
        self.island: AdvIsland | FaceIsland | UnionIslands | None = None
        self.point = pt
        self.min_dist = min_dist
        self.crn = None
        self.face = None


    def find_nearest_island_by_crn(self, isl: AdvIsland):
        pt = self.point
        min_dist = self.min_dist
        min_crn = None

        uv = isl.umesh.uv
        for f in isl:
            corners = f.loops
            v_prev = corners[-1][uv].uv
            for crn in corners:
                v_curr = crn[uv].uv

                close_pt = closest_pt_to_line(pt, v_prev, v_curr)

                dist = (close_pt - pt).length
                if isclose(dist, min_dist, abs_tol=1e-07):
                    if point_inside_face(pt, f, uv):
                        min_dist = dist
                        min_crn = crn
                        self.min_dist = math.nextafter(self.min_dist, self.min_dist+1)
                elif dist < min_dist:
                    min_dist = dist
                    min_crn = crn
                v_prev = v_curr

        if self.min_dist != min_dist:
            self.min_dist = min_dist
            self.island = isl
            self.crn = min_crn.link_loop_prev
            return True
        return False

    @staticmethod
    def closest_pt_to_selected_edge(island: AdvIsland, pt) -> float:
        min_dist = math.inf
        uv = island.umesh.uv
        for crn in island.calc_selected_edge_corners_iter():
            closest_pt = utils.closest_pt_to_line(pt, crn[uv].uv, crn.link_loop_next[uv].uv)
            min_dist = min(min_dist, (closest_pt - pt).length_squared)

        return min_dist


    def __bool__(self):
        return bool(self.island)

    def __str__(self):
        if self.island:
            return f"{self.island}. Distance={self.min_dist:.5}."
        else:
            return f"Island not found. Distance={self.min_dist:.5}."


class CrnEdgeHit:
    def __init__(self, pt, min_dist=1e200):
        self.point = pt
        self.min_dist = min_dist
        self.crn: BMLoop | None = None
        self.face: BMFace | None = None  # use for incref
        self.umesh = None

    def find_nearest_crn_by_visible_faces(self, umesh, use_faces_from_umesh_seq=False):
        from .. import utils
        from math import nextafter, inf
        from ..utils import intersect_point_line_segment

        pt = self.point
        min_dist = self.min_dist
        min_crn = None

        uv = umesh.uv

        if use_faces_from_umesh_seq:
            visible_faces = umesh.sequence
        else:
            visible_faces = utils.calc_visible_uv_faces_iter(umesh)

        for f in visible_faces:
            corners = f.loops
            v_prev = corners[-1][uv].uv
            for crn in corners:
                v_curr = crn[uv].uv

                _, dist = intersect_point_line_segment(pt, v_prev, v_curr)
                # TODO: Prioritize flipped face
                if dist < min_dist:
                    # If the point is inside the face, we add it immediately,
                    # otherwise, we do nextafter and check again for nearest.
                    if point_inside_face(pt, f, uv):
                        min_crn = crn
                        min_dist = dist
                    else:
                        # Adding dist after nextafter is necessary for the next for_each loop
                        # to “hook” another edge (thus avoiding float point errors).
                        dist = nextafter(dist, inf)
                        if dist < min_dist:
                            min_crn = crn
                            min_dist = dist

                v_prev = v_curr

        if min_crn:
            self.crn = min_crn.link_loop_prev
            self.min_dist = min_dist

            radial_prev = self.crn.link_loop_radial_prev
            if (utils.is_pair_with_flip(self.crn, radial_prev, umesh.uv) and
                    utils.is_visible_func(umesh.sync)(radial_prev.face)):
                if point_inside_face(pt, radial_prev.face, uv):
                    self.crn = radial_prev
            else:
                # Prioritize boundary edges where the point is inside the face,
                # otherwise lower the priority to find other boundary edges with the point inside the face.
                if point_inside_face(pt, self.crn.face, uv):
                    self.min_dist = nextafter(min_dist, -inf)
                else:
                    self.min_dist = nextafter(min_dist, inf)

            self.umesh = umesh
            return True
        return False

    def calc_island_with_seam(self):
        assert self.crn, 'Not found picked corner'

        uv = self.umesh.uv
        faces: set[BMFace] = {self.crn.face}
        is_visible = utils.is_visible_func(self.umesh.sync)

        stack = []
        parts_of_island = [self.crn.face]
        while parts_of_island:
            for f in parts_of_island:
                for l in f.loops:
                    if l.edge.seam:
                        continue
                    pair_crn = l.link_loop_radial_prev
                    ff = pair_crn.face
                    if ff in faces or not is_visible(ff):
                        continue

                    if (l[uv].uv == pair_crn.link_loop_next[uv].uv and
                            l.link_loop_next[uv].uv == pair_crn[uv].uv):
                        faces.add(ff)
                        stack.append(ff)
            parts_of_island = stack
            stack = []

        return AdvIsland(list(faces), self.umesh), faces

    def calc_island_non_manifold(self) -> tuple[AdvIsland, set[BMFace]]:
        assert self.crn, 'Not found picked corner'

        uv = self.umesh.uv
        island: set[BMFace] = {self.crn.face}
        is_visible = utils.is_visible_func(self.umesh.sync)

        stack = []
        parts_of_island = [self.crn.face]
        while parts_of_island:
            for f in parts_of_island:
                for crn in f.loops:
                    pair_crn = crn.link_loop_radial_prev
                    ff = pair_crn.face
                    if ff in island or not is_visible(ff):
                        continue

                    if (crn[uv].uv == pair_crn.link_loop_next[uv].uv or
                            crn.link_loop_next[uv].uv == pair_crn[uv].uv):
                        island.add(ff)
                        stack.append(ff)
            parts_of_island = stack
            stack = []

        return AdvIsland(list(island), self.umesh), island

    def calc_island_non_manifold_with_flip(self) -> tuple[AdvIsland, set[BMFace]]:
        assert self.crn, 'Not found picked corner'

        uv = self.umesh.uv
        island: set[BMFace] = {self.crn.face}
        is_visible = utils.is_visible_func(self.umesh.sync)

        stack = []
        parts_of_island = [self.crn.face]
        while parts_of_island:
            for f in parts_of_island:
                for crn in f.loops:
                    pair_crn = crn.link_loop_radial_prev
                    ff = pair_crn.face
                    if ff in island or not is_visible(ff):
                        continue

                    if crn.vert == pair_crn.vert:
                        if (crn[uv].uv == pair_crn[uv].uv or
                                crn.link_loop_next[uv].uv == pair_crn.link_loop_next[uv].uv):
                            island.add(ff)
                            stack.append(ff)
                    else:
                        if (crn[uv].uv == pair_crn.link_loop_next[uv].uv or
                                crn.link_loop_next[uv].uv == pair_crn[uv].uv):
                            island.add(ff)
                            stack.append(ff)
            parts_of_island = stack
            stack = []

        return AdvIsland(list(island), self.umesh), island


    def __bool__(self):
        return bool(self.crn)
