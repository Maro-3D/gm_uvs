# SPDX-FileCopyrightText: 2026 Oxicid
# SPDX-License-Identifier: GPL-3.0-or-later

"""UniV normalization helpers used by Quadrify; see VENDORED.md."""
import itertools
import math
from math import sqrt, isclose

import bl_math
import numpy as np
from bl_math import clamp
from mathutils import Vector, Matrix

from . import utils
from .utypes import AdvIsland


def individual_scale(operator, isl: AdvIsland, threshold=1e-8):
    if not operator.shear and not operator.xy_scale:
        return isl.value

    if isinstance(isl.value, Vector):
        new_center = isl.value.copy()
    else:
        new_center = Vector((1, 1))

    aspect = isl.umesh.aspect
    transform_acc = Matrix.Identity(2)
    scale_acc = Vector((1.0, 1.0))

    flat_3d_coords = np.array([(pt_a.to_tuple(), pt_b.to_tuple(), pt_c.to_tuple())
                              for pt_a, pt_b, pt_c in isl.flat_3d_coords], dtype=np.float32)
    vec_ac = flat_3d_coords[:, 0] - flat_3d_coords[:, 2]
    vec_bc = flat_3d_coords[:, 1] - flat_3d_coords[:, 2]
    flat_uv_coords = np.array([(pt_a.to_tuple(), pt_b.to_tuple(), pt_c.to_tuple())
                              for pt_a, pt_b, pt_c in isl.flat_coords], dtype=np.float32)
    weights = np.array(list(isl.weights) if isinstance(
        isl.weights, itertools.chain) else isl.weights, dtype=np.float32)

    for _ in range(10):
        m00 = flat_uv_coords[:, 0, 0] - flat_uv_coords[:, 2, 0]
        m01 = flat_uv_coords[:, 0, 1] - flat_uv_coords[:, 2, 1]
        m10 = flat_uv_coords[:, 1, 0] - flat_uv_coords[:, 2, 0]
        m11 = flat_uv_coords[:, 1, 1] - flat_uv_coords[:, 2, 1]

        det = m00 * m11 - m01 * m10
        mask = np.abs(det) > threshold

        with np.errstate(divide='ignore', invalid='ignore'):
            inv00, inv01 = m11 / det, -m01 / det
            inv10, inv11 = -m10 / det, m00 / det

            cou = inv00[:, None] * vec_ac + inv01[:, None] * vec_bc
            cov = inv10[:, None] * vec_ac + inv11[:, None] * vec_bc

        w = weights
        if not np.all(mask):
            if not np.any(mask):
                break
            cou = cou[mask]
            cov = cov[mask]
            w = weights[mask]

        scale_cou: float = np.sum(utils.np_vec_normalized(cou, keepdims=False) * w)
        scale_cov: float = np.sum(utils.np_vec_normalized(cov, keepdims=False) * w)
        scale_cross = 0.0
        if operator.shear:
            cou_n = cou / utils.np_vec_normalized(cou)
            cov_n = cov / utils.np_vec_normalized(cov)
            scale_cross = np.sum(utils.np_vec_dot(cou_n, cov_n) * w)

        if scale_cou * scale_cov < 1e-10:
            break

        scale_factor_u = sqrt(scale_cou / scale_cov / aspect) if operator.xy_scale else 1.0

        tolerance = 1e-5  # Trade accuracy for performance.
        if operator.shear:
            t = Matrix.Identity(2)
            t[0][0] = scale_factor_u
            t[1][0] = clamp((scale_cross / isl.area_3d) * aspect, -0.5 * aspect, 0.5 * aspect)
            t[0][1] = 0
            t[1][1] = 1 / scale_factor_u

            err = abs(t[0][0] - 1.0) + abs(t[1][0]) + abs(t[0][1]) + abs(t[1][1] - 1.0)
            if err < tolerance:
                break

            # Transform
            transform_acc @= t
            flat_uv_coords = flat_uv_coords @ np.array(t, dtype=np.float32)
        else:
            if math.isclose(scale_factor_u, 1.0, abs_tol=tolerance):
                break
            scale = Vector((scale_factor_u, 1.0/scale_factor_u))
            scale_acc *= scale
            flat_uv_coords *= np.array(scale, dtype=np.float32)

    if operator.shear:
        if transform_acc != Matrix.Identity(2):
            isl.umesh.update_tag = True
            for uv_coord in isl.flat_unique_uv_coords:
                uv_coord.xy = uv_coord @ transform_acc
            new_center = new_center @ transform_acc
    else:
        if scale_acc != Vector((1.0, 1.0)):
            isl.umesh.update_tag = True
            for uv_coord in isl.flat_unique_uv_coords:
                uv_coord *= scale_acc
            new_center *= scale_acc
    return new_center


def normalize(operator, islands: list[AdvIsland], tot_area_uv, tot_area_3d):
    """ NOTE: The pivot stored in saved in 'AdvIsland.value' is taken into account when 'scale' is enabled."""
    error = False
    if (not operator.xy_scale and not operator.shear) and len(islands) <= 1:
        error = True
        operator.report({'WARNING'}, f"Islands should be more than 1, given {len(islands)} islands")
    elif tot_area_3d == 0.0 or tot_area_uv == 0.0:
        error = True
        # Prevent divide by zero.
        operator.report({'WARNING'}, f"Cannot normalize islands, total {'UV-area' if tot_area_3d else '3D-area'} of faces is zero")

    if error:
        # Apply transforms after xy_scale and shear.
        if operator.xy_scale or operator.shear:
            for isl in islands:
                old_pivot = isl.bbox.center
                new_pivot = isl.value
                isl.umesh.update_tag |= isl.set_position(old_pivot, new_pivot)
        return False

    tot_fac = tot_area_3d / tot_area_uv

    zero_area_islands = []
    for isl in islands:
        if isclose(isl.area_3d, 0.0, abs_tol=1e-6) or isclose(isl.area_uv, 0.0, abs_tol=1e-6):
            zero_area_islands.append(isl)
            continue

        fac = isl.area_3d / isl.area_uv
        scale = math.sqrt(fac / tot_fac)

        if operator.xy_scale or operator.shear:
            old_pivot = isl.bbox.center
            new_pivot = isl.value
            new_pivot_with_scale = new_pivot * scale

            diff1 = old_pivot - new_pivot
            diff = (new_pivot - new_pivot_with_scale) + diff1

            if utils.vec_isclose(old_pivot, new_pivot) and math.isclose(scale, 1.0, abs_tol=0.00001):
                continue

            assert isl.flat_unique_uv_coords
            for crn_co in isl.flat_unique_uv_coords:
                crn_co *= scale
                crn_co += diff

            isl.umesh.update_tag = True
        else:
            if math.isclose(scale, 1.0, abs_tol=0.00001):
                continue
            if isl.scale(Vector((scale, scale)), pivot=isl.calc_bbox().center):
                isl.umesh.update_tag = True

    if zero_area_islands:
        need_validation = False
        if utils.sync() and utils.get_select_mode_mesh() in ('VERT', 'EDGE'):
            need_validation = True

        for isl in islands:
            if isl not in zero_area_islands:
                isl.select = False
                isl.umesh.update_tag = True
        for isl in zero_area_islands:
            if need_validation:
                isl.umesh.sync_from_mesh_if_needed()
            isl.select = True
            isl.umesh.update_tag = True

        operator.report({'WARNING'}, f"Found {len(zero_area_islands)} islands with zero area")
    return True


def avg_by_frequencies(operator, all_islands: list[AdvIsland]):
    areas_uv = np.empty(len(all_islands), dtype=float)
    areas_3d = np.empty(len(all_islands), dtype=float)

    for idx, isl in enumerate(all_islands):
        areas_uv[idx] = isl.calc_area_uv()
        areas_3d[idx] = isl.area_3d

    areas = areas_uv if operator.bl_idname.startswith('UV') else areas_3d
    median: float = np.median(areas)  # noqa
    min_area: float = np.amin(areas)
    max_area: float = np.amax(areas)

    center = (min_area + max_area) / 2
    if center > median:
        diff = bl_math.lerp(median, max_area, 0.15) - median
    else:
        diff = median - bl_math.lerp(median, min_area, 0.15)

    min_clamp = median - diff
    max_clamp = median + diff

    indexes = (areas >= min_clamp) & (areas <= max_clamp)
    total_uv_area = np.sum(areas_uv, where=indexes)
    total_3d_area = np.sum(areas_3d, where=indexes)

    # TODO: Averaging by area_3d to area_uv ratio (by frequency of occurrence of the same values)
    if total_uv_area and total_3d_area:
        return total_uv_area, total_3d_area
    else:
        idx_for_find = math.nextafter(median, max_area)
        idx = np_find_nearest(areas, idx_for_find)
        total_uv_area = areas_uv[idx]
        total_3d_area = areas_3d[idx]
        if total_uv_area and total_3d_area:
            return total_uv_area, total_3d_area
        else:
            return np.sum(areas_uv), np.sum(areas_3d)


def np_find_nearest(array, value):
    idx = (np.abs(array - value)).argmin()
    return idx
