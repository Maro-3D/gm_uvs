UniV Weld source bundled with GM UVs
====================================

Source: https://github.com/Oxicid/UniV
Version: 4.0.0 (installed Blender extension, 2026)
License: GPL-3.0-or-later; see LICENSE in this directory.

The `utils`, `utypes`, `draw`, and `operators/stitch_and_weld.py` Python
modules are copied from UniV. GM UVs does not register UniV's UI or unrelated
operators. `__init__.py` is a minimal package initializer, and
`preferences.py` uses the enabled UniV extension's settings when present and
otherwise supplies UniV 4.0.0's default values used by Weld. UniV's full
preferences UI imports unrelated operators. The GM UVs operator
inherits UniV's Weld implementation and uses the `uv.gm_uvs_weld` identifier.