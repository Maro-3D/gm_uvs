# SPDX-FileCopyrightText: 2026 Oxicid
# SPDX-License-Identifier: GPL-3.0-or-later

"""UV geometry, linked-corner traversal, and numerical helpers."""
import math
import typing
import numpy as np
from mathutils import Vector
from mathutils.geometry import area_tri, intersect_point_tri_2d, intersect_point_line
from bmesh.types import BMLoop, BMLayerItem

from .selection import is_pair, is_invisible_func


def calc_face_area_3d(f, scale) -> float:
    """newell cross"""
    n = Vector()
    corners = f.loops
    v_prev = corners[-1].vert.co * scale
    for crn in corners:
        v_curr = crn.vert.co * scale
        # inplace optimization ~20%: n += (v_prev.yzx - v_curr.yzx) * (v_prev.zxy + v_curr.zxy)
        v_prev_yzx = v_prev.yzx
        v_prev_zxy = v_prev.zxy

        v_prev_yzx -= v_curr.yzx
        v_prev_zxy += v_curr.zxy

        v_prev_yzx *= v_prev_zxy
        n += v_prev_yzx

        v_prev = v_curr
    return n.length


def calc_face_area_uv(f, uv) -> float:
    corners = f.loops
    n = len(corners) == 4
    if n:
        l1 = corners[0][uv].uv
        l2 = corners[1][uv].uv
        l3 = corners[2][uv].uv
        l4 = corners[3][uv].uv

        return area_tri(l1, l2, l3) + area_tri(l3, l4, l1)
    elif n == 3:
        crn_a, crn_b, crn_c = corners
        return area_tri(crn_a[uv].uv, crn_b[uv].uv, crn_c[uv].uv)
    else:
        area = 0.0
        first_crn_co = corners[-1][uv].uv
        for crn in corners:
            next_crn_co = crn[uv].uv
            area += first_crn_co.cross(next_crn_co)
            first_crn_co = next_crn_co
        return abs(area) * 0.5


def calc_signed_face_area_uv(f, uv) -> float:
    area = 0.0
    corners = f.loops
    first_crn_co = corners[-1][uv].uv
    for crn in corners:
        next_crn_co = crn[uv].uv
        area += first_crn_co.cross(next_crn_co)
        first_crn_co = next_crn_co
    return area * 0.5


def weld_crn_edge_by_idx(crn: BMLoop, crn_pair, idx, uv: BMLayerItem):
    """For Weld OT"""
    coords_sum_a = Vector((0.0, 0.0))

    corners = []
    corners_append = corners.append

    first_co = crn[uv].uv
    for crn_a in crn.vert.link_loops:
        if crn_a.face.index == idx:
            crn_a_uv = crn_a[uv]
            crn_a_co = crn_a_uv.uv
            if crn_a_co == first_co:
                coords_sum_a += crn_a_co
                corners_append(crn_a_uv)

    second_co = crn_pair[uv].uv
    for crn_b in crn_pair.vert.link_loops:
        if crn_b.face.index == idx:
            crn_b_uv = crn_b[uv]
            crn_b_co = crn_b_uv.uv
            if crn_b_co == second_co:
                coords_sum_a += crn_b_co
                corners_append(crn_b_uv)

    avg_co_a = coords_sum_a / len(corners)

    for crn_ in corners:
        crn_.uv = avg_co_a


def point_inside_face(pt, f, uv):
    corners = f.loops
    n = len(corners)
    if n == 4:
        p1 = corners[0][uv].uv
        p2 = corners[1][uv].uv
        p3 = corners[2][uv].uv
        p4 = corners[3][uv].uv
        return intersect_point_tri_2d(pt, p1, p2, p3) or intersect_point_tri_2d(pt, p3, p4, p1)
    elif n == 3:
        crn_a, crn_b, crn_c = corners
        return intersect_point_tri_2d(pt, crn_a[uv].uv, crn_b[uv].uv, crn_c[uv].uv)
    else:
        p1 = corners[0][uv].uv
        p2 = corners[1][uv].uv
        for i in range(2, len(corners)):
            p3 = corners[i][uv].uv
            if intersect_point_tri_2d(pt, p1, p2, p3):
                return True
            p2 = p3
        return False


def linked_crn_uv(first: BMLoop, uv: BMLayerItem):
    first_vert = first.vert
    first_co = first[uv].uv
    linked = []
    bm_iter = first

    while True:
        bm_iter = bm_iter.link_loop_prev.link_loop_radial_prev  # get ccw corner
        if first_vert != bm_iter.vert:  # Skip boundary or flipped
            bm_iter = first
            linked_cw = []
            while True:
                bm_iter = bm_iter.link_loop_radial_next.link_loop_next  # get cw corner
                if first_vert != bm_iter.vert:  # Skip boundary or flipped
                    break

                if bm_iter == first:
                    break
                if first_co == bm_iter[uv].uv:
                    linked_cw.append(bm_iter)
            linked.extend(linked_cw[::-1])
            break
        if bm_iter == first:
            break
        if first_co == bm_iter[uv].uv:
            linked.append(bm_iter)
    return linked


def linked_crn_to_vert_pair_with_seam(crn: BMLoop, uv, sync: bool):
    """Linked to arg corner (non-included)"""
    is_invisible = is_invisible_func(sync)
    first_vert = crn.vert

    linked = []
    bm_iter = crn
    # Iterated is needed to realize that a full iteration has passed, and there is no need to calculate CW
    iterated = False
    while True:
        prev_crn = bm_iter.link_loop_prev
        pair_ccw = prev_crn.link_loop_radial_prev
        if pair_ccw == crn and iterated:
            break
        iterated = True

        # Finish CCW
        if (pair_ccw in (prev_crn, crn) or
                    (first_vert != pair_ccw.vert) or
                    pair_ccw.edge.seam or
                    is_invisible(pair_ccw.face) or
                    not is_pair(prev_crn, pair_ccw, uv)
                ):
            bm_iter = crn
            linked_cw = []
            while True:
                pair_cw = bm_iter.link_loop_radial_prev
                # Skip flipped and boundary
                if pair_cw == bm_iter:
                    break

                next_crn = pair_cw.link_loop_next
                if next_crn == crn:
                    break

                if ((first_vert != next_crn.vert)
                            or pair_cw.edge.seam
                            or is_invisible(next_crn.face)
                            or not is_pair(bm_iter, pair_cw, uv)
                        ):
                    break
                bm_iter = next_crn
                linked_cw.append(next_crn)
            linked.extend(linked_cw[::-1])
            break
        bm_iter = pair_ccw
        linked.append(bm_iter)
    # assert len(linked) == len(set(linked))
    return linked


def linked_crn_uv_by_face_tag_unordered_included(crn, uv) -> list[BMLoop]:
    """Linked to arg corner by **face** tag with arg corner and unordered"""
    first_co = crn[uv].uv
    return [l_crn for l_crn in crn.vert.link_loops if l_crn.face.tag and l_crn[uv].uv == first_co]


def linked_crn_uv_by_idx_unordered(crn: BMLoop, uv: BMLayerItem):
    """Linked to arg corner by island index without arg corner
    simular - linked_crn_uv_by_island_index_unordered
    """
    first_co = crn[uv].uv
    idx = crn.face.index
    return [l_crn for l_crn in crn.vert.link_loops if l_crn != crn and l_crn.face.index == idx and l_crn[uv].uv == first_co]


def linked_crn_uv_by_idx_unordered_included(crn: BMLoop, uv: BMLayerItem):
    """Linked to arg corner by island index without arg corner
    simular - linked_crn_uv_by_island_index_unordered_included
    """
    first_co = crn[uv].uv
    idx = crn.face.index
    return [l_crn for l_crn in crn.vert.link_loops if l_crn.face.index == idx and l_crn[uv].uv == first_co]


def linked_crn_uv_by_island_index_unordered_included(crn: BMLoop, uv: BMLayerItem, idx: int):
    """Linked to arg corner by island index with arg corner"""
    first_co = crn[uv].uv
    return [l_crn for l_crn in crn.vert.link_loops if l_crn.face.index == idx and l_crn[uv].uv == first_co]


def linked_crn_uv_by_island_index_unordered(crn: BMLoop, uv: BMLayerItem, idx: int):
    """Linked to arg corner by island index without arg corner"""
    first_co = crn[uv].uv
    return [l_crn for l_crn in crn.vert.link_loops if l_crn != crn and l_crn.face.index == idx and l_crn[uv].uv == first_co]


def all_equal(sequence: typing.Iterable, key: typing.Callable | None = None):
    if key is None:
        sequence_iter = iter(sequence)
        try:
            first = next(sequence_iter)
        except StopIteration:
            return True

        for i in sequence_iter:
            if i != first:
                return False
    else:
        sequence_iter = iter(sequence)
        try:
            first = key(next(sequence_iter))
        except StopIteration:
            return True
        for i in sequence_iter:
            if key(i) != first:
                return False
    return True


def argmin(sequence: typing.Iterable, key: typing.Callable | None = None) -> int:
    index = 0
    sequence_iter = iter(sequence)
    if key is None:
        min_value = next(sequence_iter)
        for i, val, in enumerate(sequence_iter, 1):
            if val < min_value:
                index = i
                min_value = val
    else:
        min_value = key(next(sequence_iter))
        for i, val, in enumerate(sequence_iter, 1):
            val = key(val)
            if val < min_value:
                index = i
                min_value = val
    return index


def vec_isclose(a, b, abs_tol: float = 0.00001):
    return all(math.isclose(a1, b1, abs_tol=abs_tol) for a1, b1 in zip(a, b))


def vec_isclose_to_uniform(delta: Vector, abs_tol: float = 0.00001):
    return all(math.isclose(component, 1.0, abs_tol=abs_tol) for component in delta)


def vec_isclose_to_zero(delta: Vector, abs_tol: float = 0.00001):
    return all(math.isclose(component, 0.0, abs_tol=abs_tol) for component in delta)


def clamp(val, min_val=0.0, max_val=0.0):
    if val < min_val:
        return min_val
    elif val > max_val:
        return max_val
    return val


def closest_pt_to_line(pt: Vector, l_a: Vector, l_b: Vector):
    near_pt, percent = intersect_point_line(pt, l_a, l_b)
    if percent < 0.0:
        return l_a
    elif percent > 1.0:
        return l_b
    return near_pt


def np_vec_dot(a, b):
    return np.einsum('ij,ij->i', a, b)


def np_vec_normalized(a, keepdims=True):
    return np.linalg.norm(a, axis=1, keepdims=keepdims)
