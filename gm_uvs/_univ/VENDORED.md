UniV Quadrify and Weld source bundled with GM UVs
================================================

Source: https://github.com/Oxicid/UniV
Version: 4.0.0 (installed Blender extension, 2026)
License: GPL-3.0-or-later; see LICENSE in this directory.

The utils, utypes, draw, and operator modules originate from UniV.
Original copyright and attribution headers are preserved, including Quadrify's
UvSquares attribution. GM UVs registers only its two operator subclasses,
using uv.gm_uvs_quadrify and uv.gm_uvs_weld identifiers.

Local reductions (2026-09-30):
- normalize.py retains only the four normalization helpers called
  by Quadrify from upstream operators/texel.py. They are module functions
  with an explicit operator argument; their numerical logic is unchanged.
  The unused texel-density, reset/adjust-scale, area, and coverage operators
  and their GPU dependencies have been removed.
- quadrify.py calls these extracted helpers.
- weld.py retains Stitch and UNIV_OT_Weld from operators/stitch_and_weld.py. The unused
  standalone Stitch and 3D operator classes are removed, while Weld's
  internal Stitch fallback and distance modes are preserved.
- Unused utilities, class methods, packing/overlap helpers, mesh-island
  operators, 3D ray casting, drawing demos, profiling, and UI structs are removed.
  Calls through inheritance, descriptors, and operator callbacks are retained.
- utils is consolidated into context/settings helpers in __init__.py,
  selection.py, and geometry.py. Package exports are explicit.
- draw.py retains Weld's solid and dotted UV overlays, sharing their identical
  cleanup timer. Unused text/3D overlays and unrelated shaders are removed.
  The OpenGL/Vulkan behavior of the retained shaders is preserved.
- Blender 5's generic UV-selection branches replace the old compatibility
  branches. The BMesh/View2D C layouts and their 5.1/5.2 version guards remain.
- Operator modules are flattened into this folder; the old operators and
  draw packages and unused utility files are removed.

The remaining shared geometry, selection, and drawing code supports picking,
sync, seams, and multi-object behavior. Fifty workflow cases were compared
with the saved pre-reduction add-on on Blender 5.0.1: UV coordinates, seam
flags, and UV selection flags matched exactly. The original regression tests,
normalization tests, and foreground GPU callback/cleanup tests also pass.

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
