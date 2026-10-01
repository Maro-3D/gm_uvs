# GM UVs (Game Makers UVs)

Blender 5.0+ UV Editor tools for game artists.

## Use

Open the UV Editing workspace, hover over the UV Editor, press **N**, and select **GM UVs**. Enter mesh Edit Mode and select UVs.

**Align UV Islands to Canvas** uses a compass layout:

```text
↖       ↑       ↗
←     — + |     →
↙       ↓       ↘
```

- Corner buttons move the corresponding corner of the selected UV layout to a corner of the 0–1 UV canvas. For example, ↙ moves the selected layout so its lower-left bound reaches (0, 0).
- Edge buttons move the selection to a canvas edge on one axis; the other axis stays where it is.
- The middle controls center the selection vertically (—), on both axes (+), or horizontally (|).

The add-on gathers UV loops and islands like UniV's alignment workflow. In vertex or edge selection it moves the selected UV loops. In face selection it includes the whole UV island containing each selected face. All affected UVs move by the same offset, preserving their shape and spacing. Unselected islands remain in place.

The **Gravity (Z)** button below the compass orients selected UV islands to the object's world-space direction, like UniV's Gravity tool. It preserves each island's center and works without UniV installed. The redo panel also offers X/Y axes, Flip, Additional Angle, and Correct Aspect.

The **UV Tools** box uses bundled **UniV 4.0.0 Quadrify and Weld** implementations. Quadrify includes UniV's quad propagation, normalization, and handling of connected unselected corners. **Mark Seams**, **Correct Aspect**, and **Scale Independently** are enabled by default. Correct Aspect uses UniV's material-image lookup. The redo panel also exposes Unlink, Shear, and Use Texel Density. Weld includes UniV's Stitch fallback for separate UV islands, partial-edge welding, paired selection, and distance modes. Both tools work without a separate UniV installation.
For alignment, the target is the 0–1 UV canvas. If the selection already touches an edge, that axis may not move. The status line below the buttons shows how many UV corners were found and the computed U/V offset. The operator supports UV Sync Selection, multi-object Edit Mode, and Undo. Other tool sections remain placeholders.

### Packing layers

In **Packing**, press **+** to create a layer and rename it in the list. Select
UVs belonging to islands, then press **Assign Selected** to assign whole islands
to the active layer. **Unassign** returns selected islands to the default group;
removing a layer clears its assignments on visible edited islands. Assignments
are stored as mesh face attributes separately for each UV map and saved with
the blend file. If joined faces have mixed assignments, the resulting island
uses the default group until reassigned.

Click the select icon beside a layer to select all its visible UV islands,
replacing the previous UV selection. This works with UV Sync on or off across
edited meshes. Click the color swatch beside its name to choose its color.
**Show Layer Colors** displays a translucent fill and colored edges in the UV
Editor. Colors are saved with the layer and follow UV edits and packing; they
are editor overlays and do not change textures or materials.
Colors follow interactive scaling, movement, and rotation using UV references
prepared before the transform. Middle-mouse panning and zoom navigation retain
the colors and reuse the prepared face triangles. Each UV editor has a separate
cache. Other modal tools temporarily hide the overlay
because they may change topology and invalidate those references.

**Scale Limit** is a maximum linear multiplier relative to the UVs immediately
before packing: `1` prevents enlargement, `0.5` caps size at half, and `2` allows
up to double size. Unassigned islands use `1`. Islands may shrink further to
fit; repeated packs apply the multiplier to their current size.

**Pack UVs & Measure Coverage** packs all visible islands across meshes in Edit
Mode into the 0-1 tile, regardless of selection. Hidden faces are excluded.
Margin is measured in UV units. The deterministic bounding-box packer preserves
island shapes and optionally rotates by 90 degrees. Concave islands leave more
unused space than Blender/UniV's native shape packer. It supports independent
layer enlargement caps and requires no external packing add-on.

The result displays summed UV polygon area as a percentage of the tile, measured
at the last pack. Island bounds do not overlap; self-overlapping faces within an
island are counted individually. Later manual edits do not update this result.

## Development

The development extension points to this repository's `gm_uvs` folder. Blender keeps loaded Python code in memory. After a source change, restart Blender to reload the bundled modules.

### Source layout

```text
gm_uvs/
  __init__.py          Registration, settings, and Quadrify/Weld adapters
  blender_manifest.toml
  transform.py        Align, Gravity, and their shared UV selection
  ui.py               Sidebar panel
  packing.py          UV island layers, bounded packing, and coverage
  _univ/
    quadrify.py       Quad propagation
    weld.py           Welding and internal Stitch fallback
    normalize.py      Quadrify normalization math
    draw.py           Temporary UV overlays
    preferences.py    Optional UniV preferences and local defaults
    utils/            Context, selection, and geometry helpers (3 files)
    utypes/           Mesh/island types and UV picking (7 files)
    LICENSE
    VENDORED.md
tests/                Blender regression scripts
```

There are 19 Python files in the add-on, including package initializers.
Keep registration in `__init__.py`, panel layout in `ui.py`, and the native
tools in `transform.py`. The reduced UniV implementation lives under `_univ`;
record changes to it in [VENDORED.md](gm_uvs/_univ/VENDORED.md).

### Validation

Run the regression tests with Blender 5.0+:

```powershell
blender --background --factory-startup --python-exit-code 1 --python tests/test_align.py
blender --background --factory-startup --python-exit-code 1 --python tests/test_gravity.py
blender --background --factory-startup --python-exit-code 1 --python tests/test_quadrify.py
blender --background --factory-startup --python-exit-code 1 --python tests/test_weld.py
blender --background --factory-startup --python-exit-code 1 --python tests/test_normalize.py
blender --background --factory-startup --python-exit-code 1 --python tests/test_registration.py
blender --background --factory-startup --python-exit-code 1 --python tests/test_packing.py
blender --background --factory-startup --python-exit-code 1 --python tests/test_layer_scale.py
blender --background --factory-startup --python-exit-code 1 --python tests/test_workflows.py
```

The alignment test uses a small UV cross inside the canvas, checks all eleven buttons with UV Sync on and off, checks whole-island movement from one selected face, and forces garbage collection between selection and movement to catch invalid BMesh loops.

Normalization tests compare eight combinations of Shear, Scale Independently,
and Use Texel Density against the original add-on's Blender 5.0.1 results.
Registration tests check repeated enable/disable and extension-style package
imports. Workflow tests cover 50 combinations of selection modes, multi-object
editing, distance welding, and picking without selected UVs. Their optional
`--addon-root` and `--snapshot` arguments support comparisons with an older
copy of the add-on.

GPU tests exercise both overlay draw callbacks and cleanup, including disabling
before shader startup. They need a separate foreground Blender process, which
exits after the test; check its output for `PASS`:

```powershell
blender --factory-startup --python tests/test_gpu.py
blender --factory-startup --python tests/test_layer_colors_gpu.py
blender --factory-startup --enable-event-simulate --python tests/test_overlay_modal.py
```

The alignment and Gravity structures are adapted from [UniV's transform implementation](https://github.com/Oxicid/UniV/blob/main/operators/transform.py). Quadrify and Weld bundle UniV's operators and their required core modules, with unused standalone operators removed; see [VENDORED.md](gm_uvs/_univ/VENDORED.md). UniV and GM UVs are licensed under GPL-3.0-or-later.

