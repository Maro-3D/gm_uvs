"""GM UVs entry point for the bundled UniV 4.0.0 Weld operator."""
from ._univ.operators.stitch_and_weld import UNIV_OT_Weld


class GMUVS_OT_weld(UNIV_OT_Weld):
    bl_idname = "uv.gm_uvs_weld"
    bl_label = "Weld UVs"