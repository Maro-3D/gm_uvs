UniV Quadrify and Weld source bundled with GM UVs
================================================

Source: https://github.com/Oxicid/UniV
Version: 4.0.0 (installed Blender extension, 2026)
License: GPL-3.0-or-later; see LICENSE in this directory.

The utils, utypes, draw, and operators/stitch_and_weld.py, operators/quadrify.py,
and operators/texel.py Python modules are copied unchanged from UniV.
Original copyright and attribution headers are preserved, including Quadrify's
UvSquares attribution. GM UVs registers only its two operator subclasses,
using uv.gm_uvs_quadrify and uv.gm_uvs_weld identifiers.

Integration adapters:
- Minimal package initializers load utypes first, following upstream order.
- preferences.py returns enabled UniV preferences when available. Otherwise,
  an RNA PropertyGroup on the scene supplies the required UniV defaults, so
  the inherited operator redo UI can draw the Use Texel Density property.
- GM UVs initializes UniV's shaders through a registration timer, as upstream
  does, and removes its own temporary drawing handlers when disabled.
- GM UVs panel controls map to mark_seam, use_aspect, and xy_scale directly.

No separate UniV installation is required. GPU initialization is skipped in
background Blender; tests/test_gpu.py exercises it in foreground Blender.
