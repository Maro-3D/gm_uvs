"""Game Makers UVs: UV Editor tools."""
import bpy
import bmesh
from math import atan2, cos, isclose, pi, sin
from mathutils import Matrix, Vector
from bpy.props import BoolProperty, EnumProperty, FloatProperty
from .quadrify import GMUVS_OT_quadrify
from .univ_weld import GMUVS_OT_weld


# Selection and island movement follow the approach used by UniV:
# https://github.com/Oxicid/UniV (GPL-3.0-or-later).
def _uv_island_faces(bm, uv_layer):
    """Group visible faces across mesh edges that are continuous in UV space."""
    pending = set(face for face in bm.faces if not face.hide)
    while pending:
        seed = pending.pop()
        island = [seed]
        queue = [seed]
        while queue:
            face = queue.pop()
            for loop in face.loops:
                if loop.edge.seam:
                    continue
                ends = {
                    loop.vert: loop[uv_layer].uv.copy(),
                    loop.link_loop_next.vert: loop.link_loop_next[uv_layer].uv.copy(),
                }
                for other in loop.edge.link_loops:
                    neighbor = other.face
                    if neighbor not in pending:
                        continue
                    if all(
                        (ends[corner.vert] - corner[uv_layer].uv).length_squared < 1e-10
                        for corner in (other, other.link_loop_next)
                    ):
                        pending.remove(neighbor)
                        island.append(neighbor)
                        queue.append(neighbor)
        yield island


def selected_uvs(context):
    """Return editable mesh/UV-layer/loop groups, with UniV-style island selection."""
    groups = []
    tools = context.scene.tool_settings
    sync = tools.use_uv_select_sync
    island_mode = (
        tools.mesh_select_mode[2] if sync else tools.uv_select_mode == "FACE"
    )
    for obj in context.objects_in_mode_unique_data:
        if obj.type != "MESH":
            continue
        bm = bmesh.from_edit_mesh(obj.data)
        uv_layer = bm.loops.layers.uv.active
        if uv_layer is None:
            continue
        if island_mode:
            selected_faces = {
                face for face in bm.faces if not face.hide
                and (
                    face.select if sync
                    else face.uv_select or all(loop.uv_select_vert for loop in face.loops)
                )
            }
            loops = [
                loop
                for island in _uv_island_faces(bm, uv_layer)
                if any(face in selected_faces for face in island)
                for face in island
                for loop in face.loops
            ]
        else:
            loops = []
            for face in bm.faces:
                if face.hide or (not sync and not face.select):
                    continue
                for loop in face.loops:
                    if sync:
                        if bm.uv_select_sync_valid:
                            selected = loop.uv_select_vert
                        elif tools.mesh_select_mode[1]:
                            selected = (
                                loop.edge.select or loop.link_loop_prev.edge.select
                            )
                        else:
                            selected = loop.vert.select
                    else:
                        selected = loop.uv_select_vert
                    if selected:
                        loops.append(loop)
            # A valid UV-selection cache can still be stale after external mesh
            # selection changes. Fall back to the mesh selection in that case.
            if sync and not loops:
                for face in bm.faces:
                    if face.hide:
                        continue
                    for loop in face.loops:
                        if (
                            loop.vert.select
                            if tools.mesh_select_mode[0]
                            else loop.edge.select or loop.link_loop_prev.edge.select
                        ):
                            loops.append(loop)
        if loops:
            # Keep the edit BMesh alive while the operator holds its BMLoops.
            groups.append((obj.data, bm, uv_layer, loops))
    return groups


class GMUVS_OT_align(bpy.types.Operator):
    """Move the selected UV layout to a 0-1 canvas anchor without changing its shape"""
    bl_idname = "uv.gm_uvs_align"
    bl_label = "Align UVs"
    bl_options = {"REGISTER", "UNDO"}

    direction: EnumProperty(
        name="Direction",
        items=(
            ("TOP_LEFT", "Top Left", "Move the selected UV bounds to the left and top edges of the 0-1 canvas"),
            ("TOP", "Top", "Move the selected UV bounds to the top edge of the 0-1 canvas"),
            ("TOP_RIGHT", "Top Right", "Move the selected UV bounds to the right and top edges of the 0-1 canvas"),
            ("LEFT", "Left", "Move the selected UV bounds to the left edge of the 0-1 canvas"),
            ("CENTER_V", "Center V", "Move the selected UV bounds to the vertical center of the 0-1 canvas"),
            ("CENTER", "Center", "Move the selected UV bounds to the canvas center of the 0-1 canvas"),
            ("CENTER_U", "Center U", "Move the selected UV bounds to the horizontal center of the 0-1 canvas"),
            ("RIGHT", "Right", "Move the selected UV bounds to the right edge of the 0-1 canvas"),
            ("BOTTOM_LEFT", "Bottom Left", "Move the selected UV bounds to the left and bottom edges of the 0-1 canvas"),
            ("BOTTOM", "Bottom", "Move the selected UV bounds to the bottom edge of the 0-1 canvas"),
            ("BOTTOM_RIGHT", "Bottom Right", "Move the selected UV bounds to the right and bottom edges of the 0-1 canvas"),
        ),
        default="LEFT",
    )

    @classmethod
    def poll(cls, context):
        space = context.space_data
        return (
            space is not None
            and space.type == "IMAGE_EDITOR"
            and space.mode == "UV"
            and context.mode == "EDIT_MESH"
        )

    def execute(self, context):
        groups = selected_uvs(context)
        coordinates = [
            loop[uv_layer].uv.copy()
            for _, bm, uv_layer, loops in groups
            for loop in loops
        ]
        if not coordinates:
            status = "No selected UVs found"
            context.window_manager["gm_uvs_last_status"] = status
            self.report({"WARNING"}, status)
            context.area.tag_redraw()
            return {"CANCELLED"}
        bounds_min = (
            min(uv.x for uv in coordinates),
            min(uv.y for uv in coordinates),
        )
        bounds_max = (
            max(uv.x for uv in coordinates),
            max(uv.y for uv in coordinates),
        )
        offset = [0.0, 0.0]
        if "LEFT" in self.direction:
            offset[0] = -bounds_min[0]
        elif "RIGHT" in self.direction:
            offset[0] = 1.0 - bounds_max[0]
        elif self.direction in {"CENTER_U", "CENTER"}:
            offset[0] = 0.5 - (bounds_min[0] + bounds_max[0]) / 2.0
        if "BOTTOM" in self.direction:
            offset[1] = -bounds_min[1]
        elif "TOP" in self.direction:
            offset[1] = 1.0 - bounds_max[1]
        elif self.direction in {"CENTER_V", "CENTER"}:
            offset[1] = 0.5 - (bounds_min[1] + bounds_max[1]) / 2.0
        delta = Vector(offset)
        for mesh, bm, uv_layer, loops in groups:
            for loop in loops:
                loop[uv_layer].uv += delta
            bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)
        status = (
            f"{len(coordinates)} UVs: U {offset[0]:+.3f}, V {offset[1]:+.3f}"
        )
        context.window_manager["gm_uvs_last_status"] = status
        self.report({"INFO"}, status)
        context.area.tag_redraw()
        return {"FINISHED"}


def _gravity_aspect(context, obj):
    """Use the active texture image width/height when one is available."""
    material = obj.active_material
    if material and material.use_nodes and material.node_tree:
        node = material.node_tree.nodes.active
        if node and node.type == "TEX_IMAGE" and node.image and node.image.size[1]:
            return node.image.size[0] / node.image.size[1]
    image = getattr(context.space_data, "image", None)
    if image and image.size[1]:
        return image.size[0] / image.size[1]
    return 1.0


def _gravity_angle(faces, uv_layer, matrix, x_axis, y_axis, flip_x, flip_y, aspect):
    """Average the 3D-to-UV edge angles, as in UniV's Gravity tool."""
    angle_sum = 0.0
    edge_count = 0
    for face in faces:
        for loop in face.loops:
            world_start = matrix @ loop.vert.co
            world_end = matrix @ loop.link_loop_next.vert.co
            edge = world_end - world_start
            dominant = max(abs(value) for value in edge)
            if dominant < 1e-12:
                continue
            if abs(edge[x_axis]) != dominant and abs(edge[y_axis]) != dominant:
                continue
            uv_start = loop[uv_layer].uv
            uv_end = loop.link_loop_next[uv_layer].uv
            uv_delta = uv_end - uv_start
            uv_delta.x *= aspect
            if uv_delta.length_squared < 1e-12:
                continue
            dx = -edge[x_axis] if flip_x else edge[x_axis]
            dy = -edge[y_axis] if flip_y else edge[y_axis]
            difference = atan2(dx, dy) - atan2(uv_delta.x, uv_delta.y)
            angle = atan2(sin(difference), cos(difference))
            if edge_count:
                mean = angle_sum / edge_count
                if abs(mean - angle) > pi - 1e-8:
                    angle += -2 * pi if angle > 0 else 2 * pi
            angle_sum += angle
            edge_count += 1
    return angle_sum / edge_count if edge_count else None


class GMUVS_OT_gravity(bpy.types.Operator):
    """Orient UV islands from their 3D direction in world space"""
    bl_idname = "uv.gm_uvs_gravity"
    bl_label = "Gravity"
    bl_options = {"REGISTER", "UNDO"}

    axis: EnumProperty(
        name="Axis",
        items=(
            ("Z", "Up", "Orient using world Z as up"),
            ("X", "Side", "Orient using world X as up"),
            ("Y", "Front", "Orient using world Y as up"),
        ),
        default="Z",
    )
    flip: BoolProperty(name="Flip", default=False)
    additional_angle: FloatProperty(
        name="Additional Angle", default=0.0, subtype="ANGLE"
    )
    use_correct_aspect: BoolProperty(name="Correct Aspect", default=True)

    @classmethod
    def poll(cls, context):
        return GMUVS_OT_align.poll(context)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "axis", expand=True)
        layout.prop(self, "flip")
        layout.prop(self, "additional_angle")
        layout.prop(self, "use_correct_aspect")

    def execute(self, context):
        selected_groups = selected_uvs(context)
        selected_by_mesh = {
            mesh.as_pointer(): (bm, set(loops))
            for mesh, bm, _uv_layer, loops in selected_groups
        }
        has_selection = bool(selected_groups)
        oriented = 0
        skipped = 0

        flip_angle = pi if self.flip else 0.0
        if self.axis == "Z":
            axis_matrix = Matrix.Rotation(flip_angle, 3, "X")
        elif self.axis == "Y":
            axis_matrix = Matrix.Rotation(pi / 2 + flip_angle, 3, "X")
        else:
            axis_matrix = Matrix.Rotation(-pi / 2 + flip_angle, 3, "Y")

        for obj in context.objects_in_mode_unique_data:
            if obj.type != "MESH":
                continue
            key = obj.data.as_pointer()
            if has_selection and key not in selected_by_mesh:
                continue
            bm = (
                selected_by_mesh[key][0]
                if key in selected_by_mesh
                else bmesh.from_edit_mesh(obj.data)
            )
            uv_layer = bm.loops.layers.uv.active
            if uv_layer is None:
                continue
            selected_loops = selected_by_mesh[key][1] if has_selection else set()
            bm.normal_update()
            rotation = obj.matrix_world.decompose()[1].to_matrix() @ axis_matrix
            aspect = _gravity_aspect(context, obj) if self.use_correct_aspect else 1.0
            changed = False

            for island in _uv_island_faces(bm, uv_layer):
                island_loops = [loop for face in island for loop in face.loops]
                if has_selection and not any(loop in selected_loops for loop in island_loops):
                    continue
                uv_points = [loop[uv_layer].uv.copy() for loop in island_loops]
                min_u = min(uv.x for uv in uv_points)
                max_u = max(uv.x for uv in uv_points)
                min_v = min(uv.y for uv in uv_points)
                max_v = max(uv.y for uv in uv_points)
                pivot = Vector(((min_u + max_u) / 2, (min_v + max_v) / 2))
                signed_area = sum(
                    loop.link_loop_prev[uv_layer].uv.cross(loop[uv_layer].uv)
                    for face in island
                    for loop in face.loops
                )
                if isclose(signed_area, 0.0, abs_tol=1e-8) and isclose(
                    (max_u - min_u) * (max_v - min_v), 0.0, abs_tol=1e-8
                ):
                    skipped += 1
                    continue
                mirrored = signed_area < 0
                if mirrored:
                    for loop in island_loops:
                        uv = loop[uv_layer].uv
                        uv.y = 2 * pivot.y - uv.y

                faces_for_angle = (
                    [face for face in island if any(loop in selected_loops for loop in face.loops)]
                    if has_selection else island
                )
                normal = Vector((0.0, 0.0, 0.0))
                for face in faces_for_angle:
                    normal += face.normal * face.calc_area()
                normal = rotation @ normal
                if normal.length_squared < 1e-12:
                    if mirrored:
                        for loop in island_loops:
                            uv = loop[uv_layer].uv
                            uv.y = 2 * pivot.y - uv.y
                    skipped += 1
                    continue
                dominant_axis = max(range(3), key=lambda axis: abs(normal[axis]))
                if dominant_axis == 2:
                    x_axis, y_axis = 0, 1
                    flip_x, flip_y = False, normal.z < 0
                elif dominant_axis == 1:
                    x_axis, y_axis = 0, 2
                    flip_x, flip_y = normal.y > 0, False
                else:
                    x_axis, y_axis = 1, 2
                    flip_x, flip_y = normal.x < 0, False
                angle = _gravity_angle(
                    faces_for_angle, uv_layer, rotation,
                    x_axis, y_axis, flip_x, flip_y, aspect,
                )
                if angle is None:
                    if mirrored:
                        for loop in island_loops:
                            uv = loop[uv_layer].uv
                            uv.y = 2 * pivot.y - uv.y
                    skipped += 1
                    continue
                changed |= mirrored
                angle += self.additional_angle
                if abs(angle) > 1e-4:
                    cosine = cos(angle)
                    sine = sin(angle)
                    for loop in island_loops:
                        uv = loop[uv_layer].uv
                        du = (uv.x - pivot.x) * aspect
                        dv = uv.y - pivot.y
                        uv.x = pivot.x + (cosine * du + sine * dv) / aspect
                        uv.y = pivot.y - sine * du + cosine * dv
                    changed = True
                oriented += 1

            if changed:
                bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)

        if not oriented:
            self.report({"WARNING"}, "No UV islands could be oriented")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Oriented {oriented} UV island(s)" + (
            f"; skipped {skipped} degenerate island(s)" if skipped else ""
        ))
        context.area.tag_redraw()
        return {"FINISHED"}


class GMUVS_PT_main(bpy.types.Panel):
    bl_label = "GM UVs"
    bl_idname = "GMUVS_PT_main"
    bl_space_type = "IMAGE_EDITOR"
    bl_region_type = "UI"
    bl_category = "GM UVs"

    @classmethod
    def poll(cls, context):
        space = context.space_data
        return space is not None and space.type == "IMAGE_EDITOR" and space.mode == "UV"

    def draw(self, context):
        layout = self.layout
        layout.label(text="Game Makers UVs", icon="UV")
        box = layout.box()
        box.label(text="Align UV Islands to Canvas")
        column = box.column(align=True)
        # UniV-style compass: three equal outer cells, three center controls.
        for buttons in (
            (("TOP_LEFT", "↖"), ("TOP", "↑"), ("TOP_RIGHT", "↗")),
            (("LEFT", "←"), None, ("RIGHT", "→")),
            (("BOTTOM_LEFT", "↙"), ("BOTTOM", "↓"), ("BOTTOM_RIGHT", "↘")),
        ):
            row = column.row(align=True)
            row.scale_y = 1.2
            for button in buttons:
                cell = row.row(align=True)
                if button is None:
                    for direction, label in (
                        ("CENTER_V", "—"), ("CENTER", "+"), ("CENTER_U", "|"),
                    ):
                        cell.operator("uv.gm_uvs_align", text=label).direction = direction
                else:
                    direction, label = button
                    cell.operator("uv.gm_uvs_align", text=label).direction = direction
        box.separator()
        gravity_row = box.row()
        gravity_row.scale_y = 1.2
        gravity_row.operator("uv.gm_uvs_gravity", text="Gravity (Z)").axis = "Z"

        status = context.window_manager.get("gm_uvs_last_status")
        if status:
            box.label(text=status, icon="INFO")
        if context.mode != "EDIT_MESH":
            box.label(text="Enter mesh Edit Mode to align", icon="INFO")

        layout.separator()
        box = layout.box()
        box.label(text="UV Tools")
        row = box.row(align=True)
        quadrify = row.operator("uv.gm_uvs_quadrify", text="Quadrify")
        quadrify.mark_seams = context.scene.gm_uvs_quad_mark_seams
        quadrify.use_correct_aspect = context.scene.gm_uvs_quad_correct_aspect
        quadrify.scale_independently = context.scene.gm_uvs_quad_scale_independently
        row.operator("uv.gm_uvs_weld", text="Weld")
        settings = box.column(align=True)
        settings.prop(context.scene, "gm_uvs_quad_mark_seams", text="Mark Seams")
        settings.prop(context.scene, "gm_uvs_quad_correct_aspect", text="Correct Aspect")
        settings.prop(context.scene, "gm_uvs_quad_scale_independently", text="Scale Independently")
        box.operator("uv.gm_uvs_weld", text="Weld by Distance").use_by_distance = True
        for title, items in (
            ("Texel Density", ("Get Density", "Set Density")),
            ("Packing", ("Pack Islands",)),
        ):
            box = layout.box()
            box.label(text=title + " (Coming Soon)")
            column = box.column(align=True)
            column.enabled = False
            for item in items:
                column.label(text=item)


classes = (GMUVS_OT_align, GMUVS_OT_gravity, GMUVS_OT_quadrify, GMUVS_OT_weld, GMUVS_PT_main)


def register():
    bpy.types.Scene.gm_uvs_quad_mark_seams = BoolProperty(
        name="Mark Seams", default=True)
    bpy.types.Scene.gm_uvs_quad_correct_aspect = BoolProperty(
        name="Correct Aspect", default=True)
    bpy.types.Scene.gm_uvs_quad_scale_independently = BoolProperty(
        name="Scale Independently", default=True)
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.gm_uvs_quad_scale_independently
    del bpy.types.Scene.gm_uvs_quad_correct_aspect
    del bpy.types.Scene.gm_uvs_quad_mark_seams


if __name__ == "__main__":
    register()
