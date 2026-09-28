"""Default UniV 4.0.0 preferences used by its bundled Weld core.

The full UniV preferences UI imports unrelated operators. These values match
UniV's defaults for the settings reached by Weld and its Stitch fallback.
"""
import bpy
from types import SimpleNamespace

_DEFAULTS = SimpleNamespace(
    max_pick_distance=75,
    overlay_2d_uv_edge_seam_color=(0.8, 0.0, 0.0, 0.25),
    use_texel=False,
    size_x="2048",
    size_y="2048",
    texel_density=512.0,
)


def prefs():
    # Honor the user's UniV settings when that extension is enabled; GM UVs
    # still works alone using UniV's own defaults above.
    addons = bpy.context.preferences.addons
    for name in addons.keys():
        if name == "univ" or name.endswith(".univ"):
            return addons[name].preferences
    return _DEFAULTS


def univ_settings():
    return prefs()