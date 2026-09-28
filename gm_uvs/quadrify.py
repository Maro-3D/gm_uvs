"""Native quad layout tool for GM UVs.

Behavior based on UniV's Quadrify (GPL-3.0-or-later):
https://github.com/Oxicid/UniV
"""
from collections import deque
from math import atan2, pi, sqrt

import bmesh
import bpy
from bpy.props import BoolProperty
from mathutils import Matrix, Vector


def _poll_uv_edit(context):
    space = context.space_data
    return (context.mode == "EDIT_MESH" and space is not None
            and space.type == "IMAGE_EDITOR" and space.mode == "UV")


def _selected_faces(bm, context):
    tools = context.scene.tool_settings
    if tools.use_uv_select_sync:
        return {face for face in bm.faces if face.select and not face.hide}
    return {
        face for face in bm.faces if not face.hide and face.select
        and (face.uv_select if tools.uv_select_mode == "FACE"
             else all(loop.uv_select_vert for loop in face.loops))
    }


def _neighbor(loop, allowed, uv_layer, require_continuity):
    if loop.edge.seam and require_continuity:
        return None
    for other in loop.edge.link_loops:
        if other.face is loop.face or other.face not in allowed:
            continue
        if require_continuity:
            ends = {
                loop.vert: loop[uv_layer].uv,
                loop.link_loop_next.vert: loop.link_loop_next[uv_layer].uv,
            }
            if any((ends[corner.vert] - corner[uv_layer].uv).length_squared > 1e-10
                   for corner in (other, other.link_loop_next)):
                continue
        return other.face
    return None


def _quad_components(faces, uv_layer):
    pending = set(faces)
    while pending:
        seed = pending.pop()
        component = [seed]
        queue = deque([seed])
        while queue:
            for loop in queue.popleft().loops:
                neighbor = _neighbor(loop, pending, uv_layer, True)
                if neighbor is not None:
                    pending.remove(neighbor)
                    component.append(neighbor)
                    queue.append(neighbor)
        yield component


def _seed_score(face, uv_layer):
    score = 0.0
    for loop in face.loops:
        center = loop[uv_layer].uv
        a = loop.link_loop_prev[uv_layer].uv - center
        b = loop.link_loop_next[uv_layer].uv - center
        if a.length_squared and b.length_squared:
            score -= abs(a.angle(b) - pi / 2)
    return score


def _rectify_seed(face, uv_layer):
    loops = list(face.loops)
    points = [loop[uv_layer].uv.copy() for loop in loops]
    edges = [points[(i + 1) % 4] - points[i] for i in range(4)]
    if any(edge.length_squared < 1e-12 for edge in edges):
        return False
    best = max(range(4), key=lambda i: edges[i].length_squared)
    edge_angle = atan2(edges[best].y, edges[best].x)
    angle = round(edge_angle / (pi / 2)) * (pi / 2) - edge_angle
    center = sum(points, Vector((0.0, 0.0))) / 4
    matrix = Matrix.Rotation(angle, 2)
    rotated = [center + matrix @ (point - center) for point in points]
    min_u, max_u = min(p.x for p in rotated), max(p.x for p in rotated)
    min_v, max_v = min(p.y for p in rotated), max(p.y for p in rotated)
    if max_u - min_u < 1e-8 or max_v - min_v < 1e-8:
        return False
    # The most axis-aligned edge determines the four rectangle corners.
    first, second = best, (best + 1) % 4
    third, fourth = (best + 2) % 4, (best + 3) % 4
    horizontal = abs((rotated[second] - rotated[first]).x) >= abs(
        (rotated[second] - rotated[first]).y)
    result = [None] * 4
    if horizontal:
        left_first = rotated[first].x < rotated[second].x
        bottom_first = rotated[first].y < rotated[fourth].y
        result[first] = Vector((min_u if left_first else max_u,
                                min_v if bottom_first else max_v))
        result[second] = Vector((max_u if left_first else min_u,
                                 min_v if bottom_first else max_v))
        result[third] = Vector((max_u if left_first else min_u,
                                max_v if bottom_first else min_v))
        result[fourth] = Vector((min_u if left_first else max_u,
                                 max_v if bottom_first else min_v))
    else:
        bottom_first = rotated[first].y < rotated[second].y
        left_first = rotated[first].x < rotated[fourth].x
        result[first] = Vector((min_u if left_first else max_u,
                                min_v if bottom_first else max_v))
        result[second] = Vector((min_u if left_first else max_u,
                                 max_v if bottom_first else min_v))
        result[third] = Vector((max_u if left_first else min_u,
                                max_v if bottom_first else min_v))
        result[fourth] = Vector((max_u if left_first else min_u,
                                 min_v if bottom_first else max_v))
    for loop, point in zip(loops, result):
        loop[uv_layer].uv = point
    return True


def _propagate_quad(source_loop, target_face, uv_layer):
    a_vert = source_loop.vert
    b_vert = source_loop.link_loop_next.vert
    target = {loop.vert: loop for loop in target_face.loops}
    if a_vert not in target or b_vert not in target:
        return False
    a_loop, b_loop = target[a_vert], target[b_vert]
    a_outer = a_loop.link_loop_next if a_loop.link_loop_next.vert is not b_vert else a_loop.link_loop_prev
    b_outer = b_loop.link_loop_next if b_loop.link_loop_next.vert is not a_vert else b_loop.link_loop_prev
    a = source_loop[uv_layer].uv.copy()
    b = source_loop.link_loop_next[uv_layer].uv.copy()
    source_a_outer = source_loop.link_loop_prev
    source_b_outer = source_loop.link_loop_next.link_loop_next
    source_width = (source_a_outer.vert.co - a_vert.co).length + (source_b_outer.vert.co - b_vert.co).length
    target_width = (a_outer.vert.co - a_vert.co).length + (b_outer.vert.co - b_vert.co).length
    if source_width < 1e-12:
        return False
    factor = target_width / source_width
    a_new = a - (source_a_outer[uv_layer].uv - a) * factor
    b_new = b - (source_b_outer[uv_layer].uv - b) * factor
    a_loop[uv_layer].uv = a
    b_loop[uv_layer].uv = b
    a_outer[uv_layer].uv = a_new
    b_outer[uv_layer].uv = b_new
    return True


def _scale_quad_independently(faces, uv_layer, aspect, world_matrix):
    """Balance U/V UV scale against the quads' world-space edge lengths."""
    u_ratios = []
    v_ratios = []
    for face in faces:
        for loop in face.loops:
            uv_edge = loop.link_loop_next[uv_layer].uv - loop[uv_layer].uv
            edge_length = (world_matrix @ loop.link_loop_next.vert.co -
                           world_matrix @ loop.vert.co).length
            if abs(uv_edge.x) > abs(uv_edge.y) and abs(uv_edge.x) > 1e-10:
                u_ratios.append(edge_length / abs(uv_edge.x))
            elif abs(uv_edge.y) > 1e-10:
                v_ratios.append(edge_length / abs(uv_edge.y))
    if not u_ratios or not v_ratios:
        return False
    u_scale = sum(u_ratios) / len(u_ratios)
    v_scale = sum(v_ratios) / len(v_ratios)
    factor = sqrt(u_scale / v_scale / aspect)
    if abs(factor - 1.0) < 1e-5:
        return False
    loops = [loop for face in faces for loop in face.loops]
    min_u = min(loop[uv_layer].uv.x for loop in loops)
    max_u = max(loop[uv_layer].uv.x for loop in loops)
    min_v = min(loop[uv_layer].uv.y for loop in loops)
    max_v = max(loop[uv_layer].uv.y for loop in loops)
    pivot_u = (min_u + max_u) / 2
    pivot_v = (min_v + max_v) / 2
    for loop in loops:
        uv = loop[uv_layer].uv
        uv.x = pivot_u + (uv.x - pivot_u) * factor
        uv.y = pivot_v + (uv.y - pivot_v) / factor
    return True


class GMUVS_OT_quadrify(bpy.types.Operator):
    """Straighten selected connected quads into a rectangular UV grid"""
    bl_idname = "uv.gm_uvs_quadrify"
    bl_label = "Quadrify"
    bl_options = {"REGISTER", "UNDO"}

    mark_seams: BoolProperty(name="Mark Seams", default=True,
                             description="Mark edges where the resulting UVs are split")
    scale_independently: BoolProperty(name="Scale Independently", default=True,
                                      description="Scale U and V to match the mesh proportions")
    use_correct_aspect: BoolProperty(name="Correct Aspect", default=True,
                                     description="Account for the active image aspect ratio")

    @classmethod
    def poll(cls, context):
        return _poll_uv_edit(context)

    def draw(self, context):
        self.layout.prop(self, "mark_seams")
        self.layout.prop(self, "use_correct_aspect")
        self.layout.prop(self, "scale_independently")

    def execute(self, context):
        from . import _gravity_aspect
        completed = 0
        ignored = 0
        for obj in context.objects_in_mode_unique_data:
            if obj.type != "MESH":
                continue
            bm = bmesh.from_edit_mesh(obj.data)
            uv_layer = bm.loops.layers.uv.active
            if uv_layer is None:
                continue
            selected = _selected_faces(bm, context)
            aspect = _gravity_aspect(context, obj) if self.use_correct_aspect else 1.0
            ignored += sum(len(face.loops) != 4 for face in selected)
            quads = {face for face in selected if len(face.loops) == 4}
            changed = False
            for component in _quad_components(quads, uv_layer):
                allowed = set(component)
                seed = max(component, key=lambda face: _seed_score(face, uv_layer))
                if not _rectify_seed(seed, uv_layer):
                    ignored += len(component)
                    continue
                visited = {seed}
                queue = deque([seed])
                while queue:
                    face = queue.popleft()
                    for loop in face.loops:
                        neighbor = _neighbor(loop, allowed - visited, uv_layer, False)
                        if neighbor is None:
                            continue
                        if _propagate_quad(loop, neighbor, uv_layer):
                            visited.add(neighbor)
                            queue.append(neighbor)
                if self.scale_independently:
                    _scale_quad_independently(visited, uv_layer, aspect, obj.matrix_world)
                completed += len(visited)
                changed = True
            if changed and self.mark_seams:
                for face in selected:
                    for loop in face.loops:
                        if len(loop.edge.link_loops) != 2:
                            continue
                        other = next(other for other in loop.edge.link_loops if other.face is not face)
                        ends = {loop.vert: loop[uv_layer].uv,
                                loop.link_loop_next.vert: loop.link_loop_next[uv_layer].uv}
                        if any((ends[corner.vert] - corner[uv_layer].uv).length_squared > 1e-10
                               for corner in (other, other.link_loop_next)):
                            loop.edge.seam = True
            if changed:
                bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
        if not completed:
            self.report({"WARNING"}, "Select at least one non-degenerate UV quad")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Quadrified {completed} quad(s)" +
                    (f"; ignored {ignored} non-quad/degenerate face(s)" if ignored else ""))
        context.area.tag_redraw()
        return {"FINISHED"}
