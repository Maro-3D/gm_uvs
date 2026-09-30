# SPDX-FileCopyrightText: 2026 Oxicid
# SPDX-License-Identifier: GPL-3.0-or-later

"""Blender 5 UV selection and boundary predicates."""
import typing
from bmesh.types import BMFace, BMLoop, BMLayerItem

if typing.TYPE_CHECKING:
    from .. import utypes


def face_select_get_func(umesh: 'utypes.UMesh') -> typing.Callable[[BMFace], bool]:
    if umesh.sync and not umesh.sync_valid:
        select_get = BMFace.select.__get__
    else:
        if umesh.sync:
            def select_get(f):
                return (not f.hide) and f.uv_select
        else:
            def select_get(f):
                return (not f.hide) and f.select and f.uv_select
    return select_get


def face_invisible_get_func(umesh: 'utypes.UMesh') -> typing.Callable[[BMFace], bool]:
    if umesh.sync:
        return BMFace.hide.__get__
    else:
        return lambda f: not f.select


def edge_select_linked_set_func(umesh: 'utypes.UMesh', force=False,
                                clamp_by_seams=False) -> typing.Callable[[BMLoop, bool], None]:
    # NOTE: UV_SELECT_FLUSH_MODE_NEEDED and UV_SELECT_SYNC_TO_MESH_NEEDED for deselect
    def inner(uv, sync, sync_invalid, face_is_invisible, is_edge_mode):
        if sync_invalid:
            def select_set(crn, state):
                crn.edge.select = state
        else:
            if force or clamp_by_seams:
                raise NotImplementedError()

            def select_set(crn: BMLoop, state):
                # Check vertex select to avoid selected single vert
                if crn.uv_select_edge == state and crn.uv_select_vert == state:
                    return

                v1_co = crn[uv].uv
                v2_co = crn.link_loop_next[uv].uv
                pair_crn = crn.link_loop_radial_prev
                if state:
                    # Select pair edge
                    crn.edge.select = True
                    crn.uv_select_edge = True
                    if not face_is_invisible(pair_crn.face) and not pair_crn.uv_select_edge:
                        if v2_co == pair_crn[uv].uv and v1_co == pair_crn.link_loop_next[uv].uv:
                            pair_crn.uv_select_edge = True

                    # Select A
                    for linked_crn in crn.vert.link_loops:
                        if not face_is_invisible(linked_crn.face):
                            if linked_crn[uv].uv == v1_co:
                                linked_crn.uv_select_vert = True
                    # Select B
                    for linked_crn in crn.link_loop_next.vert.link_loops:
                        if not face_is_invisible(linked_crn.face):
                            if linked_crn[uv].uv == v2_co:
                                linked_crn.uv_select_vert = True
                else:  # TODO: Fix that (edge shrink)
                    crn.uv_select_edge = False
                    if is_edge_mode and sync:
                        crn.edge.select = False

                    if not face_is_invisible(pair_crn.face) and pair_crn.uv_select_edge:
                        if v2_co == pair_crn[uv].uv and v1_co == pair_crn.link_loop_next[uv].uv:
                            pair_crn.uv_select_edge = False

                    to_deselect = []
                    # When deselecting uv_vert_select, make sure that there are no linked selected edges.
                    # Deselect A
                    link_loops = crn.vert.link_loops
                    for linked_crn in link_loops:
                        if not face_is_invisible(linked_crn.face):
                            if linked_crn[uv].uv == v1_co:
                                to_deselect.append(linked_crn)
                                if linked_crn.uv_select_edge or linked_crn.link_loop_prev.uv_select_edge:
                                    to_deselect.clear()  # Has linked selected edge.
                                    break

                    # if to_deselect:
                    for crn in to_deselect:
                        crn.uv_select_vert = False

                    if not is_edge_mode and sync:
                        if len(to_deselect) == len(link_loops):
                            crn.vert.select = False
                        elif not any(crn.uv_select_vert and not face_is_invisible(crn.face) for crn in link_loops):
                            crn.vert.select = False

                    to_deselect.clear()

                    # Deselect B
                    link_loops = crn.link_loop_next.vert.link_loops
                    for linked_crn in link_loops:
                        if not face_is_invisible(linked_crn.face):
                            if linked_crn[uv].uv == v2_co:
                                to_deselect.append(linked_crn)
                                if linked_crn.uv_select_edge or linked_crn.link_loop_prev.uv_select_edge:
                                    to_deselect.clear()  # Has linked selected edge.
                                    break

                    # if to_deselect:
                    for crn in to_deselect:
                        crn.uv_select_vert = False

                    if not is_edge_mode and sync:
                        if len(to_deselect) == len(link_loops):
                            crn.link_loop_next.vert.select = False
                        elif not any(crn.uv_select_vert and not face_is_invisible(crn.face) for crn in link_loops):
                            crn.link_loop_next.vert.select = False

        return select_set
    return inner(umesh.uv, umesh.sync, (umesh.sync and not umesh.sync_valid), face_invisible_get_func(umesh), umesh.elem_mode == 'EDGE')


def edge_select_get_func(umesh: 'utypes.UMesh') -> typing.Callable[[BMLoop], bool]:
    def inner(sync, sync_valid):
        select_get = BMLoop.uv_select_edge.__get__
        if sync and not sync_valid:
            def select_get(crn):  # noqa
                return crn.edge.select
        return select_get
    return inner(umesh.sync, umesh.sync_valid)


def vert_select_get_func(umesh: 'utypes.UMesh') -> typing.Callable[[BMLoop], bool]:
    def inner(sync, sync_valid):
        select_get = BMLoop.uv_select_vert.__get__
        if sync and not sync_valid:
            def select_get(crn):  # noqa
                return crn.vert.select
        return select_get
    return inner(umesh.sync, umesh.sync_valid)


def shared_crn(crn: BMLoop) -> BMLoop | None:
    shared = crn.link_loop_radial_prev
    if shared != crn:
        return shared
    return None


def is_flipped_3d(crn):
    pair = crn.link_loop_radial_prev
    if pair == crn:
        return False
    return pair.vert == crn.vert


def is_pair(crn: BMLoop, _rad_prev: BMLoop, uv: BMLayerItem):
    return crn.link_loop_next[uv].uv == _rad_prev[uv].uv and \
        crn[uv].uv == _rad_prev.link_loop_next[uv].uv


def is_pair_with_flip(crn: BMLoop, _rad_prev: BMLoop, uv: BMLayerItem):
    if crn.vert == _rad_prev.vert:  # is flipped
        return crn[uv].uv.to_tuple() == _rad_prev[uv].uv.to_tuple() and \
            crn.link_loop_next[uv].uv.to_tuple() == _rad_prev.link_loop_next[uv].uv.to_tuple()
    return crn.link_loop_next[uv].uv.to_tuple() == _rad_prev[uv].uv.to_tuple() and \
        crn[uv].uv.to_tuple() == _rad_prev.link_loop_next[uv].uv.to_tuple()


def set_faces_tag(faces, tag=True):
    if tag:  # Constant load optimisation
        for f in faces:
            f.tag = True
    else:
        for f in faces:
            f.tag = False


def is_boundary_non_sync(crn: BMLoop, uv: BMLayerItem):
    # assert(l.face.select)
    pair = crn.link_loop_radial_prev
    if pair == crn:
        return True
    if not pair.face.select:
        return True
    return (crn[uv].uv.to_tuple() != pair.link_loop_next[uv].uv.to_tuple() or
            crn.link_loop_next[uv].uv.to_tuple() != pair[uv].uv.to_tuple())


def is_boundary_sync(crn: BMLoop, uv: BMLayerItem):
    # assert(not l.face.hide)
    pair = crn.link_loop_radial_prev
    if pair == crn:
        return True
    if pair.face.hide:
        return True
    return (crn[uv].uv.to_tuple() != pair.link_loop_next[uv].uv.to_tuple() or
            crn.link_loop_next[uv].uv.to_tuple() != pair[uv].uv.to_tuple())


def is_boundary_with_flip_check_non_sync(crn: BMLoop, uv: BMLayerItem):
    # assert(l.face.select)
    pair = crn.link_loop_radial_prev
    if pair == crn:
        return True
    if not pair.face.select:
        return True
    if crn.vert == pair.vert:
        return True
    return (crn[uv].uv.to_tuple() != pair.link_loop_next[uv].uv.to_tuple() or
            crn.link_loop_next[uv].uv.to_tuple() != pair[uv].uv.to_tuple())


def is_boundary_with_flip_check_sync(crn: BMLoop, uv: BMLayerItem):
    # assert(not l.face.hide)
    pair = crn.link_loop_radial_prev
    if pair == crn:
        return True
    if pair.face.hide:
        return True
    if crn.vert == pair.vert:
        return True
    return (crn[uv].uv.to_tuple() != pair.link_loop_next[uv].uv.to_tuple() or
            crn.link_loop_next[uv].uv.to_tuple() != pair[uv].uv.to_tuple())


def is_boundary_func(umesh, with_seam=True, with_flipped_check=True, invisible_check=True) -> typing.Callable[[BMLoop], bool]:
    """
    with_seam - check seams

    with_flipped_check - if True, non-manifolds edges returns True (this is not flipped correction check)

    invisible_check - hidden shared face return True
    """
    def catcher(uv: BMLayerItem, is_boundary_):
        if with_seam:
            def is_boundary(crn: BMLoop):
                # assert(l.face.select)
                if crn.edge.seam:
                    return True
                return is_boundary_(crn, uv)
            return is_boundary
        else:
            def is_boundary(crn: BMLoop):
                # assert(l.face.select)
                return is_boundary_(crn, uv)
            return is_boundary


    if invisible_check:
        if umesh.sync:
            if with_flipped_check:
                return catcher(umesh.uv, is_boundary_with_flip_check_sync)
            else:
                return catcher(umesh.uv, is_boundary_sync)
        else:
            if with_flipped_check:
                return catcher(umesh.uv, is_boundary_with_flip_check_non_sync)
            else:
                return catcher(umesh.uv, is_boundary_non_sync)
    else:
        if with_flipped_check:
            def is_boundary_with_flip_no_invisible_check(crn: BMLoop, uv: BMLayerItem):
                pair = crn.link_loop_radial_prev
                if pair == crn:
                    return True
                if crn.vert == pair.vert:
                    return True
                return (crn[uv].uv.to_tuple() != pair.link_loop_next[uv].uv.to_tuple() or
                        crn.link_loop_next[uv].uv.to_tuple() != pair[uv].uv.to_tuple())

            return catcher(umesh.uv, is_boundary_with_flip_no_invisible_check)
        else:
            def is_boundary_no_invisible_check(crn: BMLoop, uv: BMLayerItem):
                pair = crn.link_loop_radial_prev
                if pair == crn:
                    return True
                return (crn[uv].uv.to_tuple() != pair.link_loop_next[uv].uv.to_tuple() or
                        crn.link_loop_next[uv].uv.to_tuple() != pair[uv].uv.to_tuple())

            return catcher(umesh.uv, is_boundary_no_invisible_check)


def is_visible_func(sync: bool):
    # TODO: Rename to is_visible_face
    if sync:
        return lambda f: not f.hide
    else:
        return BMFace.select.__get__


def is_invisible_func(sync: bool):
    if sync:
        return BMFace.hide.__get__
    else:
        return lambda f: not f.select


def calc_visible_uv_faces_iter(umesh: 'utypes.UMesh') -> typing.Iterable[BMFace]:
    if umesh.is_full_face_selected:
        return umesh.bm.faces
    if umesh.sync:
        return (f for f in umesh.bm.faces if not f.hide)

    if umesh.is_full_face_deselected:
        return []
    return (f for f in umesh.bm.faces if f.select)
