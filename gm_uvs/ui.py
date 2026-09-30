"""GM UVs sidebar panel."""
import bpy

from .transform import is_uv_editor


class GMUVS_PT_main(bpy.types.Panel):
    bl_label = "GM UVs"
    bl_idname = "GMUVS_PT_main"
    bl_space_type = "IMAGE_EDITOR"
    bl_region_type = "UI"
    bl_category = "GM UVs"

    @classmethod
    def poll(cls, context):
        return is_uv_editor(context)

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
        quadrify.mark_seam = context.scene.gm_uvs_quad_mark_seams
        quadrify.use_aspect = context.scene.gm_uvs_quad_correct_aspect
        quadrify.xy_scale = context.scene.gm_uvs_quad_scale_independently
        row.operator("uv.gm_uvs_weld", text="Weld")
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
