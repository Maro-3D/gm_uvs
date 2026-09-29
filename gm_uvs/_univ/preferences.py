"""RNA settings adapter for the bundled UniV operators."""
import bpy


class GMUVS_PG_univ_settings(bpy.types.PropertyGroup):
    max_pick_distance: bpy.props.IntProperty(default=75, min=1)
    overlay_2d_uv_edge_seam_color: bpy.props.FloatVectorProperty(
        size=4, subtype="COLOR", default=(0.8, 0.0, 0.0, 0.25))
    use_texel: bpy.props.BoolProperty(name="Use Texel Density", default=False)
    size_x: bpy.props.StringProperty(default="2048")
    size_y: bpy.props.StringProperty(default="2048")
    texel_density: bpy.props.FloatProperty(default=512.0, min=0.001)


def prefs():
    addons = bpy.context.preferences.addons
    for name in addons.keys():
        if name == "univ" or name.endswith(".univ"):
            return addons[name].preferences
    return bpy.context.scene.gm_uvs_univ_settings


def univ_settings():
    return prefs()
