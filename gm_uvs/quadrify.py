"""GM UVs entry point for the original UniV 4.0.0 Quadrify operator."""
from ._univ.operators.quadrify import UNIV_OT_Quadrify


class GMUVS_OT_quadrify(UNIV_OT_Quadrify):
    bl_idname = "uv.gm_uvs_quadrify"
    bl_label = "Quadrify"
